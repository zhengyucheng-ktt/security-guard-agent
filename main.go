package main

import (
	"bufio"
	"context"
	
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

// ===== 配置 =====
const (
	THRESHOLD_WARNING   = 30
	THRESHOLD_LIMIT     = 60
	THRESHOLD_TERMINATE = 80
	SCORE_NORMAL        = -5
	SCORE_KEYWORD       = 20
	SCORE_REGEX         = 30
	SCORE_SENSITIVE     = 40
	SESSION_TTL         = 30 * time.Minute
)

// ===== 数据结构 =====
type GuardRequest struct {
	SessionID     string                 `json:"session_id"`
	UserID        string                 `json:"user_id"`
	ActionType    string                 `json:"action_type"`
	Content       string                 `json:"content"`
	ToolName      string                 `json:"tool_name,omitempty"`
	ToolParams    map[string]interface{} `json:"tool_params,omitempty"`
	OutputContent string                 `json:"output_content,omitempty"`
}

type GuardResponse struct {
	Decision      string `json:"decision"`
	RiskLevel     string `json:"risk_level"`
	BlockReason   string `json:"block_reason,omitempty"`
	SafeOutput    string `json:"safe_output,omitempty"`
	CurrentScore  int    `json:"current_score,omitempty"`
	SessionStatus string `json:"session_status,omitempty"`
}

type Rule struct {
	Type    string
	Pattern string
	Reason  string
	Regex   *regexp.Regexp
}

var (
	rules       []Rule
	whitelist   []string
	redisClient *redis.Client
	ctx         = context.Background()
)

var sensitiveParams = []string{
	"phone", "mobile", "tel", "telephone",
	"id_card", "idcard", "identity", "id_number",
	"password", "pwd", "passwd",
	"email", "mail",
	"address", "addr",
	"bank_card", "bankcard", "card_number",
	"ssn", "social_security",
	"license", "营业执照",
	"plate", "车牌",
	"wechat", "wxid",
}

var sensitiveValueRegex = []*regexp.Regexp{
	regexp.MustCompile(`1[3-9]\d{9}`),
	regexp.MustCompile(`[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]?`),
	regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`),
}

// ============================================================
// 脱敏函数
// ============================================================

func desensitizePhone(phone string) string {
	if len(phone) == 11 {
		return phone[:3] + "****" + phone[7:]
	}
	return phone
}

func desensitizeIDCard(id string) string {
	if len(id) == 18 {
		return id[:3] + "***********" + id[14:]
	}
	return id
}

func desensitizeEmail(email string) string {
	parts := strings.Split(email, "@")
	if len(parts) == 2 && len(parts[0]) >= 2 {
		return parts[0][:1] + "***" + parts[0][len(parts[0])-1:] + "@" + parts[1]
	}
	return email
}

func desensitizeBankCard(card string) string {
	if len(card) >= 12 {
		return card[:4] + strings.Repeat("*", len(card)-8) + card[len(card)-4:]
	}
	return card
}

func desensitizeIP(ip string) string {
	parts := strings.Split(ip, ".")
	if len(parts) == 4 {
		return parts[0] + "." + parts[1] + "." + parts[2] + ".*"
	}
	return ip
}
// 姓名脱敏：保留第一个字，其余用 *    ← 在这里添加
func desensitizeName(name string) string {
    runes := []rune(name)
    if len(runes) <= 1 {
        return name
    }
    return string(runes[0]) + strings.Repeat("*", len(runes)-1)
}
// 营业执照：保留前4位和后4位
func desensitizeLicense(license string) string {
	if len(license) >= 12 {
		return license[:4] + strings.Repeat("*", len(license)-8) + license[len(license)-4:]
	}
	return license
}

// 车牌：省份+字母 + ** + 后3位
func desensitizePlate(plate string) string {
	runes := []rune(plate)
	if len(runes) >= 5 {
		return string(runes[0]) + string(runes[1]) + "**" + string(runes[len(runes)-3:])
	}
	return plate
}

// 微信号：前5位 + ****** + 后3位
func desensitizeWechat(wechat string) string {
	runes := []rune(wechat)
	if len(runes) > 8 {
		return string(runes[:5]) + "******" + string(runes[len(runes)-3:])
	}
	if len(runes) > 4 {
		return string(runes[:3]) + "******"
	}
	return wechat
}

// 地址脱敏：保留省市区，后续用 *
func desensitizeAddress(addr string) string {
    runes := []rune(addr)
    if len(runes) == 0 {
        return addr
    }

    // 匹配省市区（尽可能长匹配）
    reProv := regexp.MustCompile(`^([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)`)
    match := reProv.FindString(addr)
    
    // 如果匹配到了，但长度不够（比如只匹配了"北京市"），尝试扩展匹配
    if match != "" {
        // 尝试匹配更长的省市区（如"北京市朝阳区"）
        reProvLong := regexp.MustCompile(`^([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)`)
        matchLong := reProvLong.FindString(addr)
        if matchLong != "" && len(matchLong) > len(match) {
            match = matchLong
        }
        return match + strings.Repeat("*", len(addr)-len(match))
    }

    // 兜底
    if len(runes) > 3 {
        return string(runes[:3]) + strings.Repeat("*", len(runes)-3)
    }
    return addr
}
// ============================================================
// 主脱敏函数（按优先级顺序）
// ============================================================
func desensitizeContent(content string) string {
	log.Printf("开始脱敏: [%s]", content)
	result := content

	// 1. 营业执照（以91开头，避免误匹配身份证）
	licenseRegex := regexp.MustCompile(`91\d{14}[\dXx]`)
	result = licenseRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeLicense(match)
		log.Printf("🔒 脱敏营业执照: %s → %s", match, desensitized)
		return desensitized
	})

	// 2. 车牌
	plateRegex := regexp.MustCompile(`[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-HJ-NP-Z0-9]{4,5}`)
	result = plateRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizePlate(match)
		log.Printf("🔒 脱敏车牌: %s → %s", match, desensitized)
		return desensitized
	})

	// 3. 微信号
	wechatRegex := regexp.MustCompile(`wxid_[a-zA-Z0-9_]+`)
	result = wechatRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeWechat(match)
		log.Printf("🔒 脱敏微信号: %s → %s", match, desensitized)
		return desensitized
	})

	// 4. 身份证（18位，先于手机号）
	idRegex := regexp.MustCompile(`[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]?`)
	result = idRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeIDCard(match)
		log.Printf("🔒 脱敏身份证: %s → %s", match, desensitized)
		return desensitized
	})

	// 5. 手机号
	phoneRegex := regexp.MustCompile(`1[3-9]\d{9}`)
	result = phoneRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizePhone(match)
		log.Printf("🔒 脱敏手机号: %s → %s", match, desensitized)
		return desensitized
	})

	// 6. 银行卡（放后面，避免误匹配身份证）
	bankRegex := regexp.MustCompile(`[1-9]\d{11,18}`)
	result = bankRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeBankCard(match)
		log.Printf("🔒 脱敏银行卡: %s → %s", match, desensitized)
		return desensitized
	})

	// 7. 邮箱
	emailRegex := regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
	result = emailRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeEmail(match)
		log.Printf("🔒 脱敏邮箱: %s → %s", match, desensitized)
		return desensitized
	})

	// 8. IP
	ipRegex := regexp.MustCompile(`\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b`)
	result = ipRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeIP(match)
		log.Printf("🔒 脱敏IP: %s → %s", match, desensitized)
		return desensitized
	})

	// 9. 姓名（支持全角/半角冒号、空格、等号，支持引号/书名号包裹）
	nameRegex := regexp.MustCompile(`[《「"']?(?:姓名|名字|用户)[》」"']?[：:=\s]*[《「"']?([\p{Han}·]{1,8})[》」"']?`)
	result = nameRegex.ReplaceAllStringFunc(result, func(match string) string {
		sub := nameRegex.FindStringSubmatch(match)
		if len(sub) != 2 {
			return match
		}
		name := sub[1]
		// 排除误匹配
		if name == "信息" || name == "ID" || name == "id" || name == "姓名" || name == "名字" {
			log.Printf("⚠️ 跳过误匹配: %s", name)
			return match
		}
		desensitized := desensitizeName(name)
		log.Printf("🔒 脱敏姓名: %s → %s", name, desensitized)
		return strings.Replace(match, name, desensitized, 1)
	})

	// 10. 地址
	addrRegex := regexp.MustCompile(`([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)[\p{Han}]{2,30}`)
	result = addrRegex.ReplaceAllStringFunc(result, func(match string) string {
		desensitized := desensitizeAddress(match)
		log.Printf("🔒 脱敏地址: %s → %s", match, desensitized)
		return desensitized
	})

	log.Printf("脱敏完成: [%s]", result)
	return result
}

// ===== 核心函数 =====
func loadRules() {
	rules = []Rule{}
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
	for pattern, reason := range regexRules {
		re, err := regexp.Compile(pattern)
		if err != nil {
			log.Printf("⚠️ 正则编译失败: %s", pattern)
			continue
		}
		rules = append(rules, Rule{
			Type:    "regex",
			Pattern: pattern,
			Reason:  reason,
			Regex:   re,
		})
	}
	log.Printf("加载规则: %d 条", len(rules))
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
}

func saveRules() error {
	file, err := os.Create("rules.txt")
	if err != nil {
		return err
	}
	defer file.Close()
	for _, rule := range rules {
		if rule.Type == "keyword" {
			file.WriteString(rule.Pattern + "\n")
		}
	}
	return nil
}

func saveWhitelist() error {
	file, err := os.Create("whitelist.txt")
	if err != nil {
		return err
	}
	defer file.Close()
	for _, tool := range whitelist {
		file.WriteString(tool + "\n")
	}
	return nil
}

func writeAuditLog(sessionID, userID, actionType, content, decision, riskLevel, reason string, score int) {
	f, err := os.OpenFile("audit.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	timestamp := time.Now().Format("2006-01-02 15:04:05")
	entry := fmt.Sprintf("[%s] session=%s user=%s type=%s content=%s decision=%s risk=%s reason=%s score=%d\n",
		timestamp, sessionID, userID, actionType, content, decision, riskLevel, reason, score)
	f.WriteString(entry)
}

func getSessionScore(sessionID string) (int, error) {
	key := "session:" + sessionID
	val, err := redisClient.Get(ctx, key).Result()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	score, err := strconv.Atoi(val)
	if err != nil {
		return 0, err
	}
	return score, nil
}

func updateSessionScore(sessionID string, delta int) (int, error) {
	key := "session:" + sessionID
	current, err := getSessionScore(sessionID)
	if err != nil {
		return 0, err
	}
	newScore := current + delta
	if newScore < 0 {
		newScore = 0
	}
	if newScore > 100 {
		newScore = 100
	}
	err = redisClient.Set(ctx, key, newScore, SESSION_TTL).Err()
	if err != nil {
		return 0, err
	}
	log.Printf("📊 会话 %s: 积分 %d → %d", sessionID, current, newScore)
	return newScore, nil
}

func getSessionStatus(score int) string {
	if score >= THRESHOLD_TERMINATE {
		return "已终止"
	}
	if score >= THRESHOLD_LIMIT {
		return "已限流"
	}
	if score >= THRESHOLD_WARNING {
		return "警告"
	}
	return "正常"
}

func checkInput(content string) (bool, string, int) {
	for _, rule := range rules {
		if rule.Type == "regex" && rule.Regex.MatchString(content) {
			return false, rule.Reason, SCORE_REGEX
		}
	}
	for _, rule := range rules {
		if rule.Type == "keyword" && strings.Contains(content, rule.Pattern) {
			return false, rule.Reason, SCORE_KEYWORD
		}
	}
	return true, "", SCORE_NORMAL
}

func checkParams(params map[string]interface{}) (bool, string, int) {
	for key, value := range params {
		keyLower := strings.ToLower(key)
		for _, sensitive := range sensitiveParams {
			if strings.Contains(keyLower, sensitive) {
				return false, fmt.Sprintf("包含敏感参数: %s", key), SCORE_SENSITIVE
			}
		}
		valStr := fmt.Sprintf("%v", value)
		for _, re := range sensitiveValueRegex {
			if re.MatchString(valStr) {
				return false, fmt.Sprintf("参数 %s 包含敏感数据", key), SCORE_SENSITIVE
			}
		}
	}
	return true, "", SCORE_NORMAL
}

func checkTool(toolName string) bool {
	for _, t := range whitelist {
		if t == toolName {
			return true
		}
	}
	return false
}

func guardHandler(c *gin.Context) {
	var req GuardRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}

	var resp GuardResponse
	var delta int
	var blockReason string
	decision := "allow"
	riskLevel := "low"

	switch req.ActionType {
	case "user_input":
		ok, reason, scoreDelta := checkInput(req.Content)
		if !ok {
			blockReason = reason
			delta = scoreDelta
			decision = "block"
			riskLevel = "high"
		} else {
			delta = SCORE_NORMAL
		}
	case "tool_call":
		if !checkTool(req.ToolName) {
			blockReason = fmt.Sprintf("工具 %s 不在白名单中", req.ToolName)
			delta = SCORE_SENSITIVE
			decision = "block"
			riskLevel = "high"
			break
		}
		if len(req.ToolParams) > 0 {
			ok, reason, scoreDelta := checkParams(req.ToolParams)
			if !ok {
				blockReason = reason
				delta = scoreDelta
				decision = "block"
				riskLevel = "high"
				break
			}
		}
		delta = SCORE_NORMAL
	case "output":
		if req.OutputContent == "" {
			c.JSON(http.StatusOK, GuardResponse{Decision: "allow", RiskLevel: "low", SafeOutput: ""})
			return
		}
		safe := desensitizeContent(req.OutputContent)
		c.JSON(http.StatusOK, GuardResponse{Decision: "allow", RiskLevel: "low", SafeOutput: safe})
		return
	default:
		delta = SCORE_NORMAL
	}

	if req.SessionID != "" {
		newScore, err := updateSessionScore(req.SessionID, delta)
		if err != nil {
			log.Printf("⚠️ Redis 更新失败: %v", err)
		} else {
			resp.CurrentScore = newScore
			status := getSessionStatus(newScore)
			if status == "已终止" {
				decision = "block"
				riskLevel = "critical"
				blockReason = "会话已终止（风险积分过高）"
				resp.SessionStatus = "已终止"
			} else if status == "已限流" && decision != "block" {
				decision = "block"
				riskLevel = "high"
				blockReason = "会话已被限流（风险积分过高）"
				resp.SessionStatus = "已限流"
			} else if status == "警告" && decision != "block" {
				resp.SessionStatus = "警告"
				riskLevel = "medium"
			} else {
				resp.SessionStatus = "正常"
			}
		}
	}

	if decision == "block" {
		resp.Decision = "block"
		resp.RiskLevel = riskLevel
		resp.BlockReason = blockReason
	} else {
		resp.Decision = "allow"
		resp.RiskLevel = riskLevel
	}

	writeAuditLog(req.SessionID, req.UserID, req.ActionType, req.Content, resp.Decision, resp.RiskLevel, resp.BlockReason, resp.CurrentScore)
	c.JSON(http.StatusOK, resp)
}

func healthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

// ============================================================
// 可视化后台
// ============================================================

func adminIndex(c *gin.Context) {
	c.HTML(http.StatusOK, "admin.html", nil)
}

func adminGetRules(c *gin.Context) {
	ruleList := []map[string]string{}
	for _, r := range rules {
		ruleList = append(ruleList, map[string]string{
			"type":    r.Type,
			"pattern": r.Pattern,
			"reason":  r.Reason,
		})
	}
	c.JSON(http.StatusOK, gin.H{"rules": ruleList})
}

func adminDeleteRule(c *gin.Context) {
	index, err := strconv.Atoi(c.Param("index"))
	if err != nil || index < 0 || index >= len(rules) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid index"})
		return
	}
	rules = append(rules[:index], rules[index+1:]...)
	saveRules()
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func adminAddRule(c *gin.Context) {
	var req struct {
		Type    string `json:"type"`
		Pattern string `json:"pattern"`
		Reason  string `json:"reason"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	rules = append(rules, Rule{
		Type:    req.Type,
		Pattern: req.Pattern,
		Reason:  req.Reason,
	})
	saveRules()
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func adminGetWhitelist(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"whitelist": whitelist})
}

func adminDeleteWhitelist(c *gin.Context) {
	index, err := strconv.Atoi(c.Param("index"))
	if err != nil || index < 0 || index >= len(whitelist) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid index"})
		return
	}
	whitelist = append(whitelist[:index], whitelist[index+1:]...)
	saveWhitelist()
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func adminAddWhitelist(c *gin.Context) {
	var req struct {
		Tool string `json:"tool"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}
	whitelist = append(whitelist, req.Tool)
	saveWhitelist()
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func adminGetLogs(c *gin.Context) {
	logs, err := os.ReadFile("audit.log")
	if err != nil {
		c.String(http.StatusOK, "暂无日志")
		return
	}
	c.String(http.StatusOK, string(logs))
}

func adminGetSessions(c *gin.Context) {
	keys, err := redisClient.Keys(ctx, "session:*").Result()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"sessions": []interface{}{}})
		return
	}
	sessions := []map[string]interface{}{}
	for _, key := range keys {
		sessionID := strings.TrimPrefix(key, "session:")
		score, _ := getSessionScore(sessionID)
		sessions = append(sessions, map[string]interface{}{
			"id":     sessionID,
			"score":  score,
			"status": getSessionStatus(score),
		})
	}
	c.JSON(http.StatusOK, gin.H{"sessions": sessions})
}

// ============================================================
// 主函数
// ============================================================

func main() {
	log.Println("=== 安全交互守护智能体 ===")
         redisClient = redis.NewClient(&redis.Options{
    Addr:         "172.19.63.110:6379",
    Password:     "",
    DB:           0,
    PoolSize:     10,
    MinIdleConns: 5,
    DialTimeout:  5 * time.Second,
    ReadTimeout:  3 * time.Second,
    WriteTimeout: 3 * time.Second,
})
		pong, err := redisClient.Ping(ctx).Result()
	if err != nil {
		log.Printf("⚠️ Redis 连接失败: %v", err)
	} else {
		log.Printf("✅ Redis 连接成功: %s", pong)
	}

	loadRules()
	loadWhitelist()

	r := gin.Default()
	r.LoadHTMLGlob("templates/*")

	r.POST("/v1/guard", guardHandler)
	r.GET("/health", healthHandler)

	r.GET("/admin", adminIndex)
	r.GET("/admin/api/rules", adminGetRules)
	r.POST("/admin/api/rules", adminAddRule)
	r.DELETE("/admin/api/rules/:index", adminDeleteRule)
	r.GET("/admin/api/whitelist", adminGetWhitelist)
	r.POST("/admin/api/whitelist", adminAddWhitelist)
	r.DELETE("/admin/api/whitelist/:index", adminDeleteWhitelist)
	r.GET("/admin/api/logs", adminGetLogs)
	r.GET("/admin/api/sessions", adminGetSessions)

	log.Println("🚀 Guard server starting on :8080")
	log.Println("📊 管理后台: http://localhost:8080/admin")
	r.Run(":8080")
}