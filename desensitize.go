package main

// ============================================================
// 数据脱敏：正则、脱敏函数、策略与字段门控
// ============================================================

import (
	"encoding/json"
	"log"
	"os"
	"regexp"
	"strings"
)

// ============================================================
// 动态脱敏配置
// ============================================================

type DesensitizePolicy struct {
	Role        string   `json:"role"`
	Level       string   `json:"level"`
	Fields      []string `json:"fields"`
	Description string   `json:"description"`
}

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
// 预编译正则表达式（性能优化）
// ============================================================

var (
	reLicense = regexp.MustCompile(`91\d{14}[\dXx]`)
	rePlate   = regexp.MustCompile(`[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-HJ-NP-Z0-9]{4,5}`)
	reWechat  = regexp.MustCompile(`wxid_[a-zA-Z0-9_]+`)
	reID      = regexp.MustCompile(`[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]?`)
	rePhone   = regexp.MustCompile(`1[3-9]\d{9}`)
	reBank    = regexp.MustCompile(`\b[1-9]\d{11,18}\b`) // 词边界锚定，避免误伤更长数字串中的片段
	reEmail   = regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
	reIP      = regexp.MustCompile(`\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b`)
	reName    = regexp.MustCompile(`[《「"']?(?:姓名|名字|用户)[》」"']?[：:=\s]*[《「"']?([\p{Han}·]{1,8})[》」"']?`)
	reAddr    = regexp.MustCompile(`([\p{Han}]{2,5}省|[\p{Han}]{2,5}自治区|[\p{Han}]{2,5}市|[\p{Han}]{2,5}区|[\p{Han}]{2,5}县)[\p{Han}]{2,30}`)
)

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
// 主脱敏函数（使用预编译正则）
// ============================================================

func desensitizeContent(content string, userID string) string {
	log.Printf("开始动态脱敏: [%s], user=%s", content, userID)
	level, fields := getDesensitizePolicy(userID)
	log.Printf("📊 脱敏级别: %s, 脱敏字段: %v", level, fields)
	if level == "full" {
		log.Printf("🔓 管理员完整权限，跳过脱敏")
		return content
	}
	// 字段门控：仅处理策略 fields 中列出的字段
	fieldSet := make(map[string]bool, len(fields))
	for _, f := range fields {
		fieldSet[f] = true
	}
	enabled := func(name string) bool { return fieldSet[name] }

	result := content

	if enabled("license") {
		result = reLicense.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizeLicense(match)
		})
	}

	if enabled("plate") {
		result = rePlate.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizePlate(match)
		})
	}

	if enabled("wechat") {
		result = reWechat.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizeWechat(match)
		})
	}

	if enabled("id_card") {
		result = reID.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizeIDCard(match)
		})
	}

	if enabled("phone") {
		result = rePhone.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizePhone(match)
		})
	}

	if enabled("bank_card") {
		result = reBank.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***"
			}
			return desensitizeBankCard(match)
		})
	}

	if enabled("email") {
		result = reEmail.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***@***.***"
			}
			return desensitizeEmail(match)
		})
	}

	if enabled("ip") {
		result = reIP.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "***.***.***.***"
			}
			return desensitizeIP(match)
		})
	}

	if enabled("name") {
		result = reName.ReplaceAllStringFunc(result, func(match string) string {
			sub := reName.FindStringSubmatch(match)
			if len(sub) != 2 {
				return match
			}
			name := sub[1]
			if name == "信息" || name == "ID" || name == "id" || name == "姓名" || name == "名字" {
				return match
			}
			if level == "minimal" {
				return strings.Replace(match, name, "***", 1)
			}
			return strings.Replace(match, name, desensitizeName(name), 1)
		})
	}

	if enabled("address") {
		result = reAddr.ReplaceAllStringFunc(result, func(match string) string {
			if level == "minimal" {
				return "****"
			}
			return desensitizeAddress(match)
		})
	}

	log.Printf("动态脱敏完成: [%s]", result)
	return result
}

// ============================================================
// 动态脱敏策略
// ============================================================

func loadDesensitizePolicies() {
	data, err := os.ReadFile("desensitize_policies.json")
	if err != nil {
		log.Println("未找到 desensitize_policies.json，使用默认策略")
		desensitizePolicies = []DesensitizePolicy{
			{
				Role:        "admin",
				Level:       "full",
				Fields:      []string{"phone", "id_card", "email", "bank_card", "address"},
				Description: "管理员查看完整数据",
			},
			{
				Role:        "user",
				Level:       "partial",
				Fields:      []string{"phone", "id_card", "email", "bank_card", "address"},
				Description: "普通用户查看脱敏数据",
			},
			{
				Role:        "guest",
				Level:       "minimal",
				Fields:      []string{"phone", "id_card", "email", "bank_card", "address"},
				Description: "访客仅查看部分脱敏数据",
			},
		}
		saveDesensitizePolicies()
		return
	}
	json.Unmarshal(data, &desensitizePolicies)
}

func saveDesensitizePolicies() error {
	data, err := json.MarshalIndent(desensitizePolicies, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("desensitize_policies.json", data, 0644)
}

func getUserRole(userID string) string {
	if strings.HasPrefix(userID, "admin") {
		return "admin"
	}
	return "user"
}

// 默认脱敏字段（当策略未配置 fields 时的兜底：全部字段）
var defaultDesensitizeFields = []string{
	"phone", "id_card", "email", "bank_card", "address",
	"ip", "name", "license", "plate", "wechat",
}

// getDesensitizePolicy 返回用户对应的脱敏策略（级别 + 脱敏字段列表）
func getDesensitizePolicy(userID string) (string, []string) {
	role := getUserRole(userID)
	policyMutex.RLock()
	defer policyMutex.RUnlock()
	for _, p := range desensitizePolicies {
		if p.Role == role {
			if len(p.Fields) == 0 {
				return p.Level, defaultDesensitizeFields
			}
			return p.Level, p.Fields
		}
	}
	return "partial", defaultDesensitizeFields
}

func getDesensitizeLevel(userID string) string {
	level, _ := getDesensitizePolicy(userID)
	return level
}
