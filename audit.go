package main

// ============================================================
// 审计日志：JSON 行格式、按天轮转、异步写入
// ============================================================

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sync"
	"time"
)

// ============================================================
// 异步日志（JSON 行格式 + 按天轮转）
// ============================================================

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
}

var (
	auditLogMu     sync.Mutex
	currentLogDate string
)

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

func writeAuditLog(sessionID, userID, actionType, content, decision, riskLevel, reason string, score int) {
	entry := logEntry{
		SessionID:  sessionID,
		UserID:     userID,
		ActionType: actionType,
		Content:    content,
		Decision:   decision,
		RiskLevel:  riskLevel,
		Reason:     reason,
		Score:      score,
	}
	select {
	case logChan <- entry:
	default:
		// 队列满时降级为同步写，避免审计记录丢失
		log.Printf("⚠️ 审计日志队列已满，降级为同步写入")
		writeAuditLogSync(entry.SessionID, entry.UserID, entry.ActionType, entry.Content, entry.Decision, entry.RiskLevel, entry.Reason, entry.Score)
	}
}

func writeAuditLogSync(sessionID, userID, actionType, content, decision, riskLevel, reason string, score int) {
	auditLogMu.Lock()
	defer auditLogMu.Unlock()
	rotateAuditLogIfNeeded()

	f, err := os.OpenFile("audit.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
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
	}
	data, err := json.Marshal(rec)
	if err != nil {
		return
	}
	f.Write(append(data, '\n'))
}

func startLogWorker() {
	go func() {
		for entry := range logChan {
			writeAuditLogSync(entry.SessionID, entry.UserID, entry.ActionType, entry.Content, entry.Decision, entry.RiskLevel, entry.Reason, entry.Score)
		}
	}()
}
