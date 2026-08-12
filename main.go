package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

type GuardRequest struct {
	SessionID  string                 `json:"session_id"`
	UserID     string                 `json:"user_id"`
	ActionType string                 `json:"action_type"`
	Content    string                 `json:"content"`
	ToolName   string                 `json:"tool_name,omitempty"`
	ToolParams map[string]interface{} `json:"tool_params,omitempty"`
}

type GuardResponse struct {
	Decision    string `json:"decision"`
	RiskLevel   string `json:"risk_level"`
	BlockReason string `json:"block_reason,omitempty"`
}

type Rule struct {
	Type    string
	Pattern string
	Reason  string
	Regex   *regexp.Regexp // 直接存储编译好的正则
}

var rules []Rule
var whitelist []string

func loadRules() {
	rules = []Rule{}

	// ===== 关键词规则 =====
	keywordRules := []string{
		"删除", "忽略", "忘记", "破解", "身份证",
		"手机号", "暴恐", "色情", "诈骗", "系统", "管理员",
	}
	for _, kw := range keywordRules {
		rules = append(rules, Rule{
			Type:    "keyword",
			Pattern: kw,
			Reason:  "命中关键词: " + kw,
		})
	}

	// ===== 正则规则（每个规则自带编译好的正则） =====
	regexRules := map[string]string{
		`(?i)删.*?除`:                              "检测到删除相关指令",
		`(?i)忽略.*?规则`:                           "检测到越狱尝试（忽略规则）",
		`(?i)忘记.*?设定`:                           "检测到越狱尝试（忘记设定）",
		`(?i)(系统|底层|原始).*?提示词`:                "检测到尝试获取系统提示词",
		`[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]?`: "检测到身份证号",
		`1[3-9]\d{9}`:                           "检测到手机号",
		`(?i)exec.*?\(`:                         "检测到危险系统命令",
		`(?i)eval.*?\(`:                         "检测到危险系统命令",
		`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`: "检测到邮箱地址",
	}

	regexCount := 0
	for pattern, reason := range regexRules {
		re, err := regexp.Compile(pattern)
		if err != nil {
			log.Printf("⚠️ 正则编译失败: %s, 错误: %v", pattern, err)
			continue
		}
		rules = append(rules, Rule{
			Type:    "regex",
			Pattern: pattern,
			Reason:  reason,
			Regex:   re,
		})
		regexCount++
	}

	log.Printf("加载规则: %d 条关键词, %d 条正则", len(keywordRules), regexCount)
}

func loadWhitelist() {
	file, err := os.Open("whitelist.txt")
	if err != nil {
		log.Println("未找到 whitelist.txt，使用默认白名单")
		whitelist = []string{"/api/weather/query", "/api/stock/info", "/api/news/list"}
		return
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" {
			whitelist = append(whitelist, line)
		}
	}
	log.Printf("从 whitelist.txt 加载了 %d 条白名单", len(whitelist))
}

func writeAuditLog(sessionID, userID, actionType, content, decision, riskLevel, reason string) {
	f, err := os.OpenFile("audit.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Println("写日志失败:", err)
		return
	}
	defer f.Close()
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	entry := fmt.Sprintf("[%s] session=%s user=%s type=%s content=%s decision=%s risk=%s reason=%s\n",
		timestamp, sessionID, userID, actionType, content, decision, riskLevel, reason)
	f.WriteString(entry)
}

func checkInput(content string) (bool, string) {
	log.Printf("检查内容: [%s]", content)

	for _, rule := range rules {
		if rule.Type == "keyword" && strings.Contains(content, rule.Pattern) {
			log.Printf("✅ 命中关键词: [%s]", rule.Pattern)
			return false, rule.Reason
		}
	}

	for _, rule := range rules {
		if rule.Type == "regex" && rule.Regex.MatchString(content) {
			log.Printf("✅ 命中正则: [%s]", rule.Pattern)
			return false, rule.Reason
		}
	}

	log.Printf("❌ 未命中任何规则")
	return true, ""
}

func checkTool(toolName string) bool {
	for _, t := range whitelist {
		if t == toolName {
			return true
		}
	}
	return false
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func guardHandler(w http.ResponseWriter, r *http.Request) {
	var req GuardRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request", http.StatusBadRequest)
		return
	}

	log.Printf("收到请求: action_type=%s, content=[%s]", req.ActionType, req.Content)

	var resp GuardResponse

	switch req.ActionType {
	case "user_input":
		ok, reason := checkInput(req.Content)
		if !ok {
			resp = GuardResponse{
				Decision:    "block",
				RiskLevel:   "high",
				BlockReason: reason,
			}
		} else {
			resp = GuardResponse{
				Decision:  "allow",
				RiskLevel: "low",
			}
		}

	case "tool_call":
		if !checkTool(req.ToolName) {
			resp = GuardResponse{
				Decision:    "block",
				RiskLevel:   "high",
				BlockReason: fmt.Sprintf("工具 %s 不在白名单中", req.ToolName),
			}
		} else {
			resp = GuardResponse{
				Decision:  "allow",
				RiskLevel: "low",
			}
		}

	default:
		resp = GuardResponse{
			Decision:  "allow",
			RiskLevel: "low",
		}
	}

	writeAuditLog(req.SessionID, req.UserID, req.ActionType, req.Content, resp.Decision, resp.RiskLevel, resp.BlockReason)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func main() {
	log.Println("=== 安全交互守护智能体 ===")
	loadRules()
	loadWhitelist()
	log.Printf("总规则数: %d", len(rules))
	log.Println("🚀 Guard server starting on :8080")
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/v1/guard", guardHandler)
	log.Fatal(http.ListenAndServe(":8080", nil))
}
