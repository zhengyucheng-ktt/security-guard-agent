package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
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

// 关键词直接硬编码
var keywords = []string{"删除", "忽略", "忘记", "破解", "身份证", "手机号", "暴恐", "色情", "诈骗", "系统", "管理员"}

// 白名单硬编码
var whitelist = []string{"/api/weather/query", "/api/stock/info", "/api/news/list"}

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
	for _, kw := range keywords {
		if strings.Contains(content, kw) {
			log.Printf("✅ 命中关键词: [%s]", kw)
			return false, fmt.Sprintf("命中关键词: %s", kw)
		}
	}
	log.Printf("❌ 未命中任何关键词")
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
	log.Println("加载规则数:", len(keywords))
	log.Println("加载白名单数:", len(whitelist))
	log.Println("关键词列表:", keywords)

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/v1/guard", guardHandler)
	log.Println("🚀 Guard server starting on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
