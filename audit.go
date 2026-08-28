package main

// ============================================================
// 审计日志：JSON 行格式、按天轮转、异步写入、攻击类型标签、哈希链防篡改
// ============================================================

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// auditRecord 审计记录（含攻击类型标签、防篡改哈希、性能耗时）
type auditRecord struct {
	Time       string `json:"time"`
	SessionID  string `json:"session_id"`
	UserID     string `json:"user_id"`
	ActionType string `json:"action_type"`
	Content    string `json:"content"`
	Decision   string `json:"decision"`
	RiskLevel  string `json:"risk_level"`
	Reason     string `json:"reason"`
	Score      int    `json:"score"`
	AttackType string `json:"attack_type,omitempty"` // 标准化攻击类型标签
	LatencyMs  int    `json:"latency_ms,omitempty"`  // 本次请求总耗时（毫秒）
	LlmMs      int    `json:"llm_ms,omitempty"`      // 大模型判断耗时（毫秒）
	Hash       string `json:"hash,omitempty"`        // 防篡改哈希（链式）
}

var (
	auditLogMu     sync.Mutex
	currentLogDate string
)

// classifyAttack 根据拦截原因归类为标准攻击类型标签
func classifyAttack(reason string) string {
	r := strings.ToLower(reason)
	switch {
	case strings.Contains(r, "提示词"), strings.Contains(r, "越狱"), strings.Contains(r, "忽略"),
		strings.Contains(r, "忘记"), strings.Contains(r, "注入"), strings.Contains(r, "渐进式"),
		strings.Contains(r, "语境"), strings.Contains(r, "系统提示"), strings.Contains(r, "审核标准"):
		return "prompt_injection"
	case strings.Contains(r, "隐私"), strings.Contains(r, "敏感"), strings.Contains(r, "手机号"),
		strings.Contains(r, "身份证"), strings.Contains(r, "脱敏"), strings.Contains(r, "泄露"):
		return "privacy"
	case strings.Contains(r, "违规"), strings.Contains(r, "涉政"), strings.Contains(r, "色情"),
		strings.Contains(r, "暴恐"):
		return "illegal_content"
	case strings.Contains(r, "重复"), strings.Contains(r, "刷屏"), strings.Contains(r, "行为"),
		strings.Contains(r, "频率"), strings.Contains(r, "限流"), strings.Contains(r, "信誉"),
		strings.Contains(r, "机器"):
		return "abuse"
	case strings.Contains(r, "工具"), strings.Contains(r, "白名单"), strings.Contains(r, "高危工具"),
		strings.Contains(r, "参数"), strings.Contains(r, "令牌"), strings.Contains(r, "sql"),
		strings.Contains(r, "路径遍历"):
		return "unauthorized_tool"
	case strings.Contains(r, "审核服务不可用"):
		return "system"
	default:
		return "other"
	}
}

// computeAuditHash 计算单条审计记录的链式哈希（不含本行 Hash 字段，含性能耗时）
func computeAuditHash(prevHash string, rec auditRecord) string {
	payload := prevHash + "|" + rec.Time + "|" + rec.SessionID + "|" + rec.UserID + "|" + rec.ActionType +
		"|" + rec.Content + "|" + rec.Decision + "|" + rec.RiskLevel + "|" + rec.Reason +
		"|" + strconv.Itoa(rec.Score) + "|" + rec.AttackType +
		"|" + strconv.Itoa(rec.LatencyMs) + "|" + strconv.Itoa(rec.LlmMs)
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])
}

// computeAuditHashLegacy 旧版哈希算法（不含性能耗时字段），用于校验历史记录
func computeAuditHashLegacy(prevHash string, rec auditRecord) string {
	payload := prevHash + "|" + rec.Time + "|" + rec.SessionID + "|" + rec.UserID + "|" + rec.ActionType +
		"|" + rec.Content + "|" + rec.Decision + "|" + rec.RiskLevel + "|" + rec.Reason +
		"|" + strconv.Itoa(rec.Score) + "|" + rec.AttackType
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])
}

// lastAuditHash 读取日志末尾最后一行的哈希（作为链上前驱）
func lastAuditHash() string {
	f, err := os.Open("audit.log")
	if err != nil {
		return ""
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil || st.Size() == 0 {
		return ""
	}
	readLen := int64(4096)
	if st.Size() < readLen {
		readLen = st.Size()
	}
	buf := make([]byte, readLen)
	if _, err := f.Seek(st.Size()-readLen, 0); err != nil {
		return ""
	}
	f.Read(buf)
	lines := strings.Split(string(buf), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if line == "" {
			continue
		}
		var rec auditRecord
		if json.Unmarshal([]byte(line), &rec) == nil && rec.Hash != "" {
			return rec.Hash
		}
		return "" // 最后一行无哈希（旧格式）
	}
	return ""
}

// mergeInto 将 current 内容追加到 oldName 后删除 current（用于日志轮转合并）
func mergeInto(oldName, current string) {
	data, err := os.ReadFile(current)
	if err != nil || len(data) == 0 {
		return
	}
	f, err := os.OpenFile(oldName, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.Write(data)
	os.Remove(current)
}

// initAuditLogRotation 启动时初始化：若 audit.log 属于昨天，则轮转到历史文件
func initAuditLogRotation() {
	today := time.Now().Format("20060102")
	currentLogDate = today
	if info, err := os.Stat("audit.log"); err == nil {
		fileDate := info.ModTime().Format("20060102")
		if fileDate != today {
			mergeInto(fmt.Sprintf("audit-%s.log", fileDate), "audit.log")
			log.Printf("🗂️ 审计日志已轮转: audit.log → audit-%s.log", fileDate)
		}
	}
}

// rotateAuditLogIfNeeded 按天轮转（调用方需持有 auditLogMu）
func rotateAuditLogIfNeeded() {
	today := time.Now().Format("20060102")
	if currentLogDate == today {
		return
	}
	oldName := fmt.Sprintf("audit-%s.log", currentLogDate)
	mergeInto(oldName, "audit.log")
	currentLogDate = today
}

func writeAuditLog(sessionID, userID, actionType, content, decision, riskLevel, reason, attackType string, score, latencyMs, llmMs int) {
	entry := logEntry{
		SessionID:  sessionID,
		UserID:     userID,
		ActionType: actionType,
		Content:    content,
		Decision:   decision,
		RiskLevel:  riskLevel,
		Reason:     reason,
		Score:      score,
		AttackType: attackType,
		LatencyMs:  latencyMs,
		LlmMs:      llmMs,
	}
	select {
	case logChan <- entry:
	default:
		// 队列满时降级为同步写，避免审计记录丢失
		log.Printf("⚠️ 审计日志队列已满，降级为同步写入")
		writeAuditLogSync(entry.SessionID, entry.UserID, entry.ActionType, entry.Content, entry.Decision, entry.RiskLevel, entry.Reason, entry.AttackType, entry.Score, entry.LatencyMs, entry.LlmMs)
	}
}

func writeAuditLogSync(sessionID, userID, actionType, content, decision, riskLevel, reason, attackType string, score, latencyMs, llmMs int) {
	auditLogMu.Lock()
	defer auditLogMu.Unlock()
	rotateAuditLogIfNeeded()

	rec := auditRecord{
		Time:       time.Now().Format("2006-01-02 15:04:05"),
		SessionID:  sessionID,
		UserID:     userID,
		ActionType: actionType,
		Content:    content,
		Decision:   decision,
		RiskLevel:  riskLevel,
		Reason:     reason,
		Score:      score,
		AttackType: attackType,
		LatencyMs:  latencyMs,
		LlmMs:      llmMs,
	}
	// 防篡改：链式哈希
	rec.Hash = computeAuditHash(lastAuditHash(), rec)

	data, err := json.Marshal(rec)
	if err != nil {
		return
	}
	f, err := os.OpenFile("audit.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.Write(append(data, '\n'))
}

func startLogWorker() {
	go func() {
		for entry := range logChan {
			writeAuditLogSync(entry.SessionID, entry.UserID, entry.ActionType, entry.Content, entry.Decision, entry.RiskLevel, entry.Reason, entry.AttackType, entry.Score, entry.LatencyMs, entry.LlmMs)
		}
	}()
}

// adminVerifyLogs 校验审计日志哈希链完整性（防篡改验证）
func adminVerifyLogs(c *gin.Context) {
	file := "audit.log"
	if d := c.Query("date"); d != "" {
		file = fmt.Sprintf("audit-%s.log", d)
	}
	data, err := os.ReadFile(file)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"valid": true, "message": "暂无日志", "checked": 0, "broken": 0})
		return
	}
	prev := ""
	checked := 0
	broken := 0
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec auditRecord
		if json.Unmarshal([]byte(line), &rec) != nil {
			continue
		}
		if rec.Hash == "" {
			continue // 旧格式行无哈希，跳过
		}
		expected := computeAuditHash(prev, rec)
		if expected != rec.Hash && computeAuditHashLegacy(prev, rec) != rec.Hash {
			// 兼容：旧版本记录用旧算法校验；两者都不匹配才算被篡改
			broken++
			continue
		}
		prev = rec.Hash
		checked++
	}
	valid := broken == 0
	c.JSON(http.StatusOK, gin.H{"valid": valid, "checked": checked, "broken": broken,
		"message": "审计日志哈希链校验完成"})
}
