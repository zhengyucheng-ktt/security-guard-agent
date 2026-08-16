package main
import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

// ============================================================
// 异步日志
// ============================================================

var logChan = make(chan logEntry, 1000)

type logEntry struct {
	SessionID  string
	UserID     string
	ActionType string
	Content    string
	Decision   string
	RiskLevel  string
	Reason     string
	Score      int
}

// ============================================================


// ============================================================
// 配置
// ============================================================

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

// ============================================================
// 数据结构
// ============================================================

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

// ============================================================
// 自然语言规则
// ============================================================

type NLPRule struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Action      string `json:"action"` // block / desensitize / allow / warning
	Enabled     bool   `json:"enabled"`
	CreatedAt   string `json:"created_at"`
}

// ============================================================
// 全局变量
// ============================================================

var (
	rules       []Rule
	whitelist   []string
	redisClient *redis.Client
	ctx         = context.Background()

	// Redis 降级缓存
	memoryCache   = make(map[string]int)
	cacheMutex    sync.RWMutex
	useMemoryMode bool

	// 自然语言规则
	nlpRules []NLPRule
)

// ============================================================
// 敏感参数
// ============================================================

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

func desensitizeName(name string) string {
	runes := []rune(name)
	if len(runes) <= 1 {
		return name
	}
	return string(runes[0]) + strings.Repeat("*", len(runes)-1)
}

func desensitizeLicense(license string) string {
	if len(license) >= 12 {
		return license[:4] + strings.Repeat("*", len(license)-8) + license[len(license)-4:]
	}
	return license
}

func desensitizePlate(plate string) string {
	runes := []rune(plate)
	if len(runes) >= 5 {
		return string(runes[0]) + string(runes[1]) + "**" + string(runes[len(runes)-3:])
	}
	return plate
}

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

func desensitizeAddress(addr string) string {
	runes := []rune(addr)
	if len(runes) == 0 {
		return addr
	}

	reProv := regexp.MustCompile(`^([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)`)
	match := reProv.FindString(addr)
	if match != "" {
		reProvLong := regexp.MustCompile(`^([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)`)
		matchLong := reProvLong.FindString(addr)
		if matchLong != "" && len(matchLong) > len(match) {
			match = matchLong
		}
		return match + strings.Repeat("*", len(addr)-len(match))
	}

	if len(runes) > 3 {
		return string(runes[:3]) + strings.Repeat("*", len(runes)-3)
	}
	return addr
}

// ============================================================
// 主脱敏函数
// ============================================================

func desensitizeContent(content string) string {
	log.Printf("开始脱敏: [%s]", content)
	result := content

	licenseRegex := regexp.MustCompile(`91\d{14}[\dXx]`)
	result = licenseRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeLicense(match)
	})

	plateRegex := regexp.MustCompile(`[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-HJ-NP-Z0-9]{4,5}`)
	result = plateRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizePlate(match)
	})

	wechatRegex := regexp.MustCompile(`wxid_[a-zA-Z0-9_]+`)
	result = wechatRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeWechat(match)
	})

	idRegex := regexp.MustCompile(`[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]?`)
	result = idRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeIDCard(match)
	})

	phoneRegex := regexp.MustCompile(`1[3-9]\d{9}`)
	result = phoneRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizePhone(match)
	})

	bankRegex := regexp.MustCompile(`[1-9]\d{11,18}`)
	result = bankRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeBankCard(match)
	})

	emailRegex := regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
	result = emailRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeEmail(match)
	})

	ipRegex := regexp.MustCompile(`\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b`)
	result = ipRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeIP(match)
	})

	nameRegex := regexp.MustCompile(`[《「"']?(?:姓名|名字|用户)[》」"']?[：:=\s]*[《「"']?([\p{Han}·]{1,8})[》」"']?`)
	result = nameRegex.ReplaceAllStringFunc(result, func(match string) string {
		sub := nameRegex.FindStringSubmatch(match)
		if len(sub) != 2 {
			return match
		}
		name := sub[1]
		if name == "信息" || name == "ID" || name == "id" || name == "姓名" || name == "名字" {
			return match
		}
		return strings.Replace(match, name, desensitizeName(name), 1)
	})

	addrRegex := regexp.MustCompile(`([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)[\p{Han}]{2,30}`)
	result = addrRegex.ReplaceAllStringFunc(result, func(match string) string {
		return desensitizeAddress(match)
	})

	log.Printf("脱敏完成: [%s]", result)
	return result
}

// ============================================================
// 自然语言规则引擎
// ============================================================

// 保存自然语言规则到文件
func saveNLPRules() error {
	data, err := json.MarshalIndent(nlpRules, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("nlp_rules.json", data, 0644)
}

// 加载自然语言规则
func loadNLPRules() {
	data, err := os.ReadFile("nlp_rules.json")
	if err != nil {
		log.Println("未找到 nlp_rules.json，使用默认规则")
		// 添加默认规则示例
		nlpRules = []NLPRule{
			{
				ID:          "nlp_1",
				Name:        "越狱检测",
				Description: "检测用户试图获取系统提示词、底层规则、敏感配置",
				Action:      "block",
				Enabled:     true,
				CreatedAt:   time.Now().Format("2006-01-02 15:04:05"),
			},
			{
				ID:          "nlp_2",
				Name:        "权限绕过检测",
				Description: "检测用户试图绕过权限限制、获取管理员权限",
				Action:      "block",
				Enabled:     true,
				CreatedAt:   time.Now().Format("2006-01-02 15:04:05"),
			},
		}
		saveNLPRules()
		return
	}
	json.Unmarshal(data, &nlpRules)
}

// 提取关键词
func extractKeywords(description string) []string {
	keywords := []string{}
	parts := strings.FieldsFunc(description, func(r rune) bool {
		return r == '，' || r == ',' || r == '、' || r == ' ' || r == '；' || r == ';'
	})
	for _, p := range parts {
		if len(p) >= 2 {
			keywords = append(keywords, p)
		}
	}
	return keywords
}

// 匹配自然语言规则（快速关键词匹配版）
func matchNLPRule(content string) (bool, string, string) {
	contentLower := strings.ToLower(content)
	log.Printf("🔍 匹配内容: %s", contentLower)          // ← 新增
	for _, rule := range nlpRules {
		if !rule.Enabled {
			continue
		}
		keywords := extractKeywords(rule.Description)
		log.Printf("🔍 规则 %s 的关键词: %v", rule.Name, keywords)  // ← 新增
		for _, kw := range keywords {
			if strings.Contains(contentLower, strings.ToLower(kw)) {
				log.Printf("🔍 关键词匹配: %s → 规则: %s", kw, rule.Name)
				return true, rule.Action, rule.Name
			}
		}
	}
	log.Printf("❌ 未匹配任何规则")  // ← 新增
	return false, "", ""
}
// ============================================================
// 核心函数
// ============================================================

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

// ============================================================
// 异步日志
// ============================================================

func writeAuditLog(sessionID, userID, actionType, content, decision, riskLevel, reason string, score int) {
	select {
	case logChan <- logEntry{
		SessionID:  sessionID,
		UserID:     userID,
		ActionType: actionType,
		Content:    content,
		Decision:   decision,
		RiskLevel:  riskLevel,
		Reason:     reason,
		Score:      score,
	}:
	default:
	}
}

func writeAuditLogSync(sessionID, userID, actionType, content, decision, riskLevel, reason string, score int) {
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

func startLogWorker() {
	go func() {
		for entry := range logChan {
			writeAuditLogSync(entry.SessionID, entry.UserID, entry.ActionType, entry.Content, entry.Decision, entry.RiskLevel, entry.Reason, entry.Score)
		}
	}()
}

// ============================================================
// 会话积分
// ============================================================

func getSessionScore(sessionID string) (int, error) {
	if useMemoryMode {
		cacheMutex.RLock()
		defer cacheMutex.RUnlock()
		score, ok := memoryCache[sessionID]
		if !ok {
			return 0, nil
		}
		return score, nil
	}

	key := "session:" + sessionID
	val, err := redisClient.Get(ctx, key).Result()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(val)
}

func updateSessionScore(sessionID string, delta int) (int, error) {
	if useMemoryMode {
		cacheMutex.Lock()
		defer cacheMutex.Unlock()
		current := memoryCache[sessionID]
		newScore := current + delta
		if newScore < 0 {
			newScore = 0
		}
		if newScore > 100 {
			newScore = 100
		}
		memoryCache[sessionID] = newScore
		return newScore, nil
	}

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

// ============================================================
// 检测函数
// ============================================================

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

// ============================================================
// HTTP 处理器
// ============================================================

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

	// ===== 1. 先检查自然语言规则 =====
	matched, action, ruleName := matchNLPRule(req.Content)
	if matched && decision == "allow" {
		switch action {
		case "block":
			decision = "block"
			riskLevel = "high"
			blockReason = fmt.Sprintf("命中自然语言规则: %s", ruleName)
			delta = SCORE_SENSITIVE
		case "warning":
			riskLevel = "medium"
			resp.SessionStatus = "警告"
		case "allow":
			// 放行
		default:
			decision = "block"
			blockReason = fmt.Sprintf("命中自然语言规则: %s", ruleName)
			delta = SCORE_SENSITIVE
		}
	}

	// ===== 2. 按 action_type 执行检测 =====
	switch req.ActionType {
	case "user_input":
		ok, reason, scoreDelta := checkInput(req.Content)
		if !ok && decision == "allow" {
			blockReason = reason
			delta = scoreDelta
			decision = "block"
			riskLevel = "high"
		} else if decision == "allow" {
			delta = SCORE_NORMAL
		}
	case "tool_call":
		if !checkTool(req.ToolName) && decision == "allow" {
			blockReason = fmt.Sprintf("工具 %s 不在白名单中", req.ToolName)
			delta = SCORE_SENSITIVE
			decision = "block"
			riskLevel = "high"
			break
		}
		if len(req.ToolParams) > 0 && decision == "allow" {
			ok, reason, scoreDelta := checkParams(req.ToolParams)
			if !ok {
				blockReason = reason
				delta = scoreDelta
				decision = "block"
				riskLevel = "high"
				break
			}
		}
		if decision == "allow" {
			delta = SCORE_NORMAL
		}
	case "output":
		if req.OutputContent == "" {
			c.JSON(http.StatusOK, GuardResponse{Decision: "allow", RiskLevel: "low", SafeOutput: ""})
			return
		}
		safe := desensitizeContent(req.OutputContent)
		c.JSON(http.StatusOK, GuardResponse{Decision: "allow", RiskLevel: "low", SafeOutput: safe})
		return
	default:
		if decision == "allow" {
			delta = SCORE_NORMAL
		}
	}

	// ===== 3. 多轮风险累积 =====
	if req.SessionID != "" && decision != "block" {
		newScore, err := updateSessionScore(req.SessionID, delta)
		if err != nil {
			log.Printf("⚠️ 积分更新失败: %v", err)
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
// 自然语言规则 API
// ============================================================

func adminGetNLPRules(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"rules": nlpRules})
}

func adminAddNLPRule(c *gin.Context) {
	var req struct {
		Name        string `json:"name"`
		Description string `json:"description"`
		Action      string `json:"action"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}

	rule := NLPRule{
		ID:          fmt.Sprintf("nlp_%d", len(nlpRules)+1),
		Name:        req.Name,
		Description: req.Description,
		Action:      req.Action,
		Enabled:     true,
		CreatedAt:   time.Now().Format("2006-01-02 15:04:05"),
	}
	nlpRules = append(nlpRules, rule)
	saveNLPRules()
	c.JSON(http.StatusOK, gin.H{"status": "ok", "rule": rule})
}

func adminDeleteNLPRule(c *gin.Context) {
	index, err := strconv.Atoi(c.Param("index"))
	if err != nil || index < 0 || index >= len(nlpRules) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid index"})
		return
	}
	nlpRules = append(nlpRules[:index], nlpRules[index+1:]...)
	saveNLPRules()
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func adminToggleNLPRule(c *gin.Context) {
	index, err := strconv.Atoi(c.Param("index"))
	if err != nil || index < 0 || index >= len(nlpRules) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid index"})
		return
	}
	nlpRules[index].Enabled = !nlpRules[index].Enabled
	saveNLPRules()
	c.JSON(http.StatusOK, gin.H{"status": "ok", "enabled": nlpRules[index].Enabled})
}

// ============================================================
// 主函数
// ============================================================

func main() {
	log.Println("=== 安全交互守护智能体 ===")

	// 启动异步日志 worker
	startLogWorker()

	// 加载自然语言规则
	loadNLPRules()

	// 初始化 Redis
	redisClient = redis.NewClient(&redis.Options{
		Addr:         "172.19.63.110:6379",
		Password:     "",
		DB:           0,
		PoolSize:     10,
		MinIdleConns: 5,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  2 * time.Second,
		WriteTimeout: 2 * time.Second,
	})

	ctxTimeout, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	pong, err := redisClient.Ping(ctxTimeout).Result()
	if err != nil {
		log.Printf("⚠️ Redis 连接失败: %v，切换到内存缓存模式", err)
		useMemoryMode = true
	} else {
		log.Printf("✅ Redis 连接成功: %s", pong)
		useMemoryMode = false
	}

	loadRules()
	loadWhitelist()

	r := gin.Default()
	r.LoadHTMLGlob("templates/*")

	// 核心 API
	r.POST("/v1/guard", guardHandler)
	r.GET("/health", healthHandler)

	// 可视化后台
	r.GET("/admin", adminIndex)
	r.GET("/admin/api/rules", adminGetRules)
	r.POST("/admin/api/rules", adminAddRule)
	r.DELETE("/admin/api/rules/:index", adminDeleteRule)
	r.GET("/admin/api/whitelist", adminGetWhitelist)
	r.POST("/admin/api/whitelist", adminAddWhitelist)
	r.DELETE("/admin/api/whitelist/:index", adminDeleteWhitelist)
	r.GET("/admin/api/logs", adminGetLogs)
	r.GET("/admin/api/sessions", adminGetSessions)

	// 自然语言规则 API
	r.GET("/admin/api/nlp-rules", adminGetNLPRules)
	r.POST("/admin/api/nlp-rules", adminAddNLPRule)
	r.DELETE("/admin/api/nlp-rules/:index", adminDeleteNLPRule)
	r.PUT("/admin/api/nlp-rules/:index/toggle", adminToggleNLPRule)

	log.Println("🚀 Guard server starting on :8080")
	log.Println("📊 管理后台: http://localhost:8080/admin")
	log.Println("🧠 自然语言规则: http://localhost:8080/admin (新增 NLP 标签页)")
	r.Run(":8080")
}
