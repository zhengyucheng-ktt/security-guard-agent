package main

// ============================================================
// 审计报表导出（CSV，Excel 兼容）
// ============================================================

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
)

// adminExportLogs 导出审计日志为 CSV（UTF-8 BOM，Excel 直接打开）
func adminExportLogs(c *gin.Context) {
	file := "audit.log"
	if d := c.Query("date"); d != "" {
		file = fmt.Sprintf("audit-%s.log", d)
	}
	logs, err := os.ReadFile(file)
	if err != nil {
		c.String(http.StatusOK, "暂无日志")
		return
	}

	var buf bytes.Buffer
	buf.WriteString("\xEF\xBB\xBF") // UTF-8 BOM，Excel 识别中文
	w := csv.NewWriter(&buf)
	w.Write([]string{"时间", "会话ID", "用户ID", "类型", "内容", "决策", "风险级别", "攻击类型", "拦截原因", "积分"})

	for _, line := range strings.Split(string(logs), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec auditRecord
		if json.Unmarshal([]byte(line), &rec) != nil {
			// 兼容旧文本格式
			w.Write([]string{"", "", "", "", line, "", "", "", "", ""})
			continue
		}
		w.Write([]string{
			rec.Time, rec.SessionID, rec.UserID, rec.ActionType, rec.Content,
			rec.Decision, rec.RiskLevel, rec.AttackType, rec.Reason, strconv.Itoa(rec.Score),
		})
	}
	w.Flush()

	fileName := "audit-export.csv"
	if d := c.Query("date"); d != "" {
		fileName = fmt.Sprintf("audit-%s.csv", d)
	}
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s", fileName))
	c.Data(http.StatusOK, "text/csv; charset=utf-8", buf.Bytes())
}
