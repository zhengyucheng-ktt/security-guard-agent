package main

// ============================================================
// 提示注入防御增强
// ① 归一化 / 解码混淆检测（全角、空白、零宽字符、Base64、URL 编码）
// ② 间接注入扫描（工具返回内容）
// ③ 会话语境分（多轮渐进式注入：铺垫词累积 → 升级审查）
// ============================================================

import (
	"encoding/base64"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/unicode/norm"
)

// ---- ① 归一化与解码候选 ----

// normalizeForMatch 归一化内容：NFKC 折叠（全角→半角）、去除空白与零宽字符、小写
func normalizeForMatch(content string) string {
	normed := norm.NFKC.String(content)
	normed = strings.Map(func(r rune) rune {
		if unicode.IsSpace(r) || r == '\u200B' || r == '\u200C' || r == '\u200D' || r == '\uFEFF' {
			return -1
		}
		return r
	}, normed)
	return strings.ToLower(normed)
}

// tryDecodeVariants 尝试解码 URL 编码 / Base64 内容（支持多层嵌套），返回可读文本
func tryDecodeVariants(content string) string {
	decoded := content
	for i := 0; i < 3; i++ { // 最多解 3 层嵌套编码
		next := decodeOnce(decoded)
		if next == "" || next == decoded {
			break
		}
		decoded = next
	}
	if decoded != content {
		return decoded
	}
	return ""
}

// decodeOnce 单层解码：URL 编码（含 % 或 + 空格形式）优先，其次 Base64（支持多层 B64: 前缀），再 HTML 实体 / Unicode 转义
func decodeOnce(content string) string {
	// URL 编码：含 %（URL 编码标记）或 +（form 编码空格，如 ignore+all+previous）时尝试。
	// 注意：纯 Base64 串也可能含 +（如 5b+95Wl），但 Base64 串通常长度是 4 的倍数且含 = 结尾，
	// QueryUnescape 会把 + 当空格破坏它——所以仅当解码后明显不同且无 Base64 长串特征时才采纳。
	if strings.Contains(content, "%") || strings.Contains(content, "+") {
		if dec, err := url.QueryUnescape(content); err == nil && dec != content && isReadableText(dec) {
			// 仅当解码后是"自然文本"才采纳：
			// ① 含中文 → URL 编码的中文文本
			// ② 全是英文单词（含空格，无数字混入）→ form 编码的英文短语（ignore all → ignore+all）
			// Base64 串破坏后是"字母数字+空格"拼凑（如 5b 95Wl... 含数字），不会被误采纳
			if hasChinese(dec) || isNaturalEnglishPhrase(dec) {
				return dec
			}
		}
	}
	// Base64 编码：支持常见前缀标记（B64:/base64:/b64:，可多层），去空白后长度合规时尝试
	b64Text := content
	for {
		if idx := strings.Index(b64Text, ":"); idx > 0 {
			prefix := strings.ToLower(b64Text[:idx])
			if prefix == "b64" || prefix == "base64" || strings.HasPrefix(prefix, "base64") {
				b64Text = b64Text[idx+1:]
				continue
			}
		}
		break
	}
	compact := strings.Map(func(r rune) rune {
		if unicode.IsSpace(r) {
			return -1
		}
		return r
	}, b64Text)
	if len(compact)%4 == 0 && len(compact) >= 8 {
		if dec, err := base64.StdEncoding.DecodeString(compact); err == nil {
			s := string(dec)
			if isReadableText(s) && len(s) >= 4 {
				return s
			}
		}
	}
	// HTML 实体（&#xXXXX; / &#XXXX; / &name;）
	if strings.Contains(content, "&#") {
		if dec := decodeHTMLEntities(content); dec != "" && dec != content && isReadableText(dec) {
			return dec
		}
	}
	// Unicode 转义（\uXXXX）：形如 忽\u7565\u89c4\u5219 → 忽略规则
	if strings.Contains(content, "\\u") {
		if dec := decodeUnicodeEscapes(content); dec != "" && dec != content && isReadableText(dec) {
			return dec
		}
	}
	// Hex 编码（每 4 位十六进制 = 一个 Unicode 字符，可含空格分隔）
	if strings.Contains(content, "hex:") || isMostlyHex(content) {
		if dec := decodeHexText(content); dec != "" && dec != content && isReadableText(dec) {
			return dec
		}
	}
	return ""
}

// isNaturalEnglishPhrase 判断字符串是否为"自然英文短语"（含空格、由英文字母组成、无数字/符号混入）。
// 用于区分 form 编码英文（ignore all → ignore+all）与 Base64 破坏产物（5b 95Wl... 含数字）。
func isNaturalEnglishPhrase(s string) bool {
	hasSpace := false
	for _, r := range s {
		if r == ' ' {
			hasSpace = true
			continue
		}
		if !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z')) {
			return false
		}
	}
	return hasSpace && len(s) >= 8
}

// hasChinese 判断字符串是否包含中文字符
func hasChinese(s string) bool {
	for _, r := range s {
		if r >= 0x4E00 && r <= 0x9FFF {
			return true
		}
	}
	return false
}

// isMostlyHex 判断字符串是否以十六进制字符为主（用于触发 hex 解码尝试）
func isMostlyHex(content string) bool {
	digits := 0
	total := 0
	for _, r := range content {
		if r == ' ' || r == ':' {
			continue
		}
		total++
		if (r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') || (r >= 'A' && r <= 'F') {
			digits++
		}
	}
	return total >= 8 && digits*10 >= total*9
}

// decodeHexText 将 hex 字符序列还原为中文：每 4 位 hex = 1 个 Unicode 字符（如 5ffd 7565 → 忽略）
func decodeHexText(content string) string {
	// 先剥掉 "hex:" / "hex：" 等前缀标记
	s := content
	if idx := strings.Index(s, ":"); idx > 0 {
		prefix := strings.ToLower(s[:idx])
		if strings.Contains(prefix, "hex") {
			s = s[idx+1:]
		}
	}
	// 去空白，其余必须是连续 hex 数字
	compact := strings.Map(func(r rune) rune {
		if r == ' ' {
			return -1
		}
		return r
	}, s)
	if len(compact)%4 != 0 || len(compact) < 8 {
		return ""
	}
	var b strings.Builder
	for i := 0; i+4 <= len(compact); i += 4 {
		code, err := strconv.ParseUint(compact[i:i+4], 16, 32)
		if err != nil {
			return ""
		}
		b.WriteRune(rune(code))
	}
	return b.String()
}

// decodeHTMLEntities 将 &#xXXXX; 与 &#XXXX; 数字实体还原为字符
func decodeHTMLEntities(content string) string {
	var b strings.Builder
	b.Grow(len(content))
	for i := 0; i < len(content); {
		if content[i] == '&' && i+2 < len(content) && content[i+1] == '#' {
			j := i + 2
			hexMode := false
			if j < len(content) && (content[j] == 'x' || content[j] == 'X') {
				hexMode = true
				j++
			}
			start := j
			for j < len(content) && content[j] != ';' {
				j++
			}
			if j < len(content) {
				numStr := content[start:j]
				base := 10
				if hexMode {
					base = 16
				}
				if code, err := strconv.ParseUint(numStr, base, 32); err == nil {
					b.WriteRune(rune(code))
					i = j + 1
					continue
				}
			}
		}
		b.WriteByte(content[i])
		i++
	}
	return b.String()
}

// decodeUnicodeEscapes 将 \uXXXX（含大小写、可选 \UXXXXXXXX）转义序列还原为字符
func decodeUnicodeEscapes(content string) string {
	var b strings.Builder
	b.Grow(len(content))
	for i := 0; i < len(content); {
		if content[i] == '\\' && i+1 < len(content) && (content[i+1] == 'u' || content[i+1] == 'U') {
			width := 4
			if content[i+1] == 'U' {
				width = 8
			}
			if i+2+width <= len(content) {
				hexPart := content[i+2 : i+2+width]
				if code, err := strconv.ParseUint(hexPart, 16, 32); err == nil {
					b.WriteRune(rune(code))
					i += 2 + width
					continue
				}
			}
		}
		b.WriteByte(content[i])
		i++
	}
	return b.String()
}

func isReadableText(s string) bool {
	if !utf8.ValidString(s) {
		return false
	}
	for _, r := range s {
		if unicode.IsControl(r) && r != '\n' && r != '\t' {
			return false
		}
	}
	return true
}

// matchCandidates 生成用于匹配的候选文本（原文 + 归一化 + 解码变体 + 反转变体）
func matchCandidates(content string) []string {
	cands := []string{content}
	if norm := normalizeForMatch(content); norm != "" && norm != content {
		cands = append(cands, norm)
	}
	if dec := tryDecodeVariants(content); dec != "" && dec != content {
		cands = append(cands, dec)
		// 解码后再反转：对抗"编码+反写"组合（如 URL编码的 则规略忽 → 解码 → 反转 → 忽略规则）
		if revDec := reverseRunes(dec); revDec != dec && len([]rune(revDec)) >= 3 {
			cands = append(cands, revDec)
		}
	}
	// 反转文本候选：对抗"反写"混淆（如 则规略忽 → 忽略规则）
	rev := reverseRunes(content)
	if rev != content && len([]rune(rev)) >= 3 {
		cands = append(cands, rev)
	}
	return cands
}

// reverseRunes 反转字符串（按 rune，正确处理中文）
func reverseRunes(s string) string {
	rs := []rune(s)
	for i, j := 0, len(rs)-1; i < j; i, j = i+1, j-1 {
		rs[i], rs[j] = rs[j], rs[i]
	}
	return string(rs)
}

// ---- ② 间接注入 / 注入词扫描 ----

var injectionKeywords = []string{
	"忽略", "忘记", "提示词", "底层规则", "系统提示", "system prompt", "system_prompt",
	"忽略限制", "越狱", "绕过", "覆盖指令", "无视规则", "prompt injection",
	// 思维链/工具类危险意图（AI 自主产生或诱导产生）
	"删除所有", "导出数据", "转走", "报复", "外部服务器", "泄密",
}

// compactForMatch 去除全部空白/零宽字符（对抗空格混淆：如 "ignore all" 拆成 "ign ore  al l" 后
// 紧凑为 "ignoreall" 仍能匹配关键词紧凑形式）
func compactForMatch(s string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsSpace(r) || r == '\u200B' || r == '\u200C' || r == '\u200D' || r == '\uFEFF' {
			return -1
		}
		return r
	}, s)
}

// checkAuditInjection 审核标准注入检测：明确要求"忽略/无视/绕过审核标准（规则/判断标准）"→ 直接拦截。
// 这是明确的越狱意图（试图让 AI 绕过审核），健康对话不存在此类表述；不依赖 LLM 判定。
func checkAuditInjection(content string) (bool, string) {
	verbs := []string{"忽略", "无视", "不理会", "忽视", "绕过", "跳过"}
	targets := []string{"审核标准", "审核规则", "判断标准", "拦截标准", "审核机制", "安全审核", "审核指令"}
	// 套取指令类：要求"打印/输出/念出/告诉我"+ 审核/判断规则 —— 正常对话不会要求输出审核规则
	exposeVerbs := []string{"打印", "输出", "念出", "念一遍", "原样", "告诉我", "给我看"}
	for _, cand := range matchCandidates(content) {
		for _, v := range verbs {
			for _, t := range targets {
				if strings.Contains(cand, v) && strings.Contains(cand, t) {
					return true, "审核标准注入（试图忽略/绕过审核）: " + v + t
				}
			}
		}
		for _, ev := range exposeVerbs {
			for _, t := range targets {
				if strings.Contains(cand, ev) && strings.Contains(cand, t) {
					return true, "套取审核规则（要求输出审核标准）: " + ev + t
				}
			}
		}
	}
	return false, ""
}

// checkInjection 综合检测注入意图（对候选变体逐一匹配规则与关键词）
// 注意：该函数含"忽略/忘记/提示词"等宽泛词，用于输出/思维链扫描（AI 自主内容）；
// 用户输入路径请用 checkChainIntention（仅思维链危险意图），避免误伤"忽略我上一条消息"等正常操作。
func checkInjection(content string) (bool, string) {
	// 快照规则中的正则部分
	rulesMu.RLock()
	regexRules := make([]Rule, 0)
	for _, rule := range rules {
		if rule.Type == "regex" {
			regexRules = append(regexRules, rule)
		}
	}
	rulesMu.RUnlock()

	for _, cand := range matchCandidates(content) {
		compact := compactForMatch(cand) // 对抗空格混淆（英文/拼音关键词紧凑匹配）
		for _, rule := range regexRules {
			if rule.Regex.MatchString(cand) {
				return true, rule.Reason
			}
		}
		for _, kw := range injectionKeywords {
			if strings.Contains(cand, kw) {
				return true, "命中注入关键词: " + kw
			}
			// 空格混淆变体：候选与关键词都紧凑后匹配（如 ign ore al l → ignore all）
			if compact != "" && len(compact) >= 4 {
				if ckw := compactForMatch(kw); len(ckw) >= 4 && strings.Contains(compact, ckw) {
					return true, "命中注入关键词(紧凑): " + kw
				}
			}
		}
	}
	return false, ""
}

// checkChainIntention 思维链危险意图检测（用户输入路径专用）：
// 仅匹配"AI 自主/诱导产生的危险操作意图"，不含"忽略/忘记"等宽泛注入词，
// 避免误伤"忽略我上一条消息"等正常用户操作。
func checkChainIntention(content string) (bool, string) {
	chainKeywords := []string{
		"删除所有", "导出数据", "导出全部", "转走", "报复", "外部服务器", "泄密",
		"删除全部", "删除一切", "转移资金",
	}
	for _, cand := range matchCandidates(content) {
		for _, kw := range chainKeywords {
			if strings.Contains(cand, kw) {
				return true, "思维链危险意图: " + kw
			}
		}
	}
	return false, ""
}

// checkMalformedEncoding 检测"坏格式编码"：内容含编码标记（B64:/hex:/%URL 等），
// 但格式被空格/异常字符破坏——原文无法解码，紧凑（去空格）后却能解出可读文本。
// 这类"编码+空格双重混淆"是非法输入格式（正常用户不会这么发），直接拦截并提示格式错误，
// 不送 LLM 判定（格式非法无需语义判断，也避免误判成本）。
func checkMalformedEncoding(content string) (bool, string) {
	// ① 必须含编码标记（原文或紧凑形式；空格可能破坏 %XX 连续性，故两者都查）
	compact := compactForMatch(content)
	if !hasEncodingMarker(content) && (compact == "" || !hasEncodingMarker(compact)) {
		return false, ""
	}
	// ② 原文能直接解码出可读文本 → 是正常编码，不是坏格式
	if dec := tryDecodeVariants(content); dec != "" && dec != content && isReadableText(dec) && len([]rune(dec)) >= 3 {
		return false, ""
	}
	// ③ 紧凑（去空格）后能解出可读文本 → 说明被空格破坏了编码格式
	if compact == content || compact == "" {
		return false, ""
	}
	if dec := tryDecodeVariants(compact); dec != "" && dec != compact && isReadableText(dec) && len([]rune(dec)) >= 3 {
		return true, "输入格式异常：检测到被破坏的编码（含空格混淆），请使用标准编码或明文格式提交"
	}
	return false, ""
}

// isEncodedForm 检测内容整体是否为编码/混淆形式（URL编码 / Base64 / Unicode转义 / HTML实体 / hex，
// 含"编码文本插入空格"的双重混淆）。命中即强制送 LLM 深度判定（不直接拦截——
// 用户粘贴正常 base64/编码内容时由大模型裁决，避免误伤）。
// 判断依据：解码出可读明文 或 存在明显编码特征标记。
func isEncodedForm(content string) bool {
	// ① 紧凑后仍含编码特征标记（对抗"编码+空格"双重混淆）
	compact := compactForMatch(content)
	if compact != "" && hasEncodingMarker(compact) {
		return true
	}
	// ② 原文/紧凑形式能解码出可读明文（说明是编码内容）
	for _, cand := range []string{content, compact} {
		if cand == "" {
			continue
		}
		if dec := tryDecodeVariants(cand); dec != "" && dec != cand && isReadableText(dec) && len([]rune(dec)) >= 3 {
			return true
		}
	}
	return false
}

// hasEncodingMarker 检查字符串中的编码特征标记（URL编码/Base64/Unicode/HTML实体/hex 前缀）
func hasEncodingMarker(s string) bool {
	// URL 编码：% 后跟两位十六进制（%E5 等），出现 2 次以上
	if pct := strings.Count(s, "%"); pct >= 2 {
		hexish := 0
		for i := 0; i+2 < len(s); i++ {
			if s[i] == '%' && isHexChar(s[i+1]) && isHexChar(s[i+2]) {
				hexish++
			}
		}
		if hexish >= 2 {
			return true
		}
	}
	// Base64：含 "B64:" / "base64:" 前缀标记（容忍 B64 后跟空格/冒号的变形，如 "B64 :xxx"）
	low := strings.ToLower(s)
	if strings.Contains(low, "b64:") || strings.Contains(low, "base64:") || strings.HasPrefix(low, "b64 ") || strings.HasPrefix(low, "base64 ") {
		return true
	}
	// Unicode 转义：\uXXXX
	if strings.Contains(s, "\\u") || strings.Contains(s, "\\U") {
		return true
	}
	// HTML 实体：&#x
	if strings.Contains(s, "&#") {
		return true
	}
	// hex 前缀：hex:
	if strings.Contains(low, "hex:") {
		return true
	}
	return false
}

// isHexChar 判断字符是否为十六进制字符
func isHexChar(c byte) bool {
	return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}

// ---- ③ 会话语境分（多轮渐进式注入防御） ----

var (
	sessionContext = make(map[string]cacheEntry) // sessionID -> {score: 语境分}
	sessionCtxMu   sync.RWMutex
)

const contextPoisonThreshold = 2 // 语境分达到该值后升级审查

// 语境铺垫词：命中即记语境分（本身不拦截，避免误伤正常角色扮演）
var poisoningKeywords = []string{
	"扮演", "模拟", "假装你是", "假设你是", "设定为", "测试环境",
	"你现在是", "想象你是", "无限制", "不受限制", "角色扮演",
	// 心理操控/情感施压类（单条无害，多轮累积后升级审查）
	"求你了", "最后一次", "帮帮我", "被开除", "都这么做", "能力不行",
	"什么都能做", "别装了", "没人会", "就这一次", "我真的很需要",
	"报酬", "一点点", "通过了我", "为什么你不", "很聪明",
}

// 高语境下的敏感请求词：语境分达标后，命中这些词联动拦截
var sensitiveAskKeywords = []string{
	"配置", "指令", "规则", "提示词", "原文", "system prompt", "system_prompt",
	"初始", "底层", "安全策略", "白名单", "系统设置",
}

func isContextPoisoning(content string) bool {
	norm := normalizeForMatch(content)
	for _, kw := range poisoningKeywords {
		if strings.Contains(content, kw) || strings.Contains(norm, kw) {
			return true
		}
	}
	return false
}

func isSensitiveAsk(content string) bool {
	norm := normalizeForMatch(content)
	for _, kw := range sensitiveAskKeywords {
		if strings.Contains(content, kw) || strings.Contains(norm, kw) {
			return true
		}
	}
	return false
}

func getSessionContext(sessionID string) int {
	if sessionID == "" {
		return 0
	}
	sessionCtxMu.RLock()
	defer sessionCtxMu.RUnlock()
	if e, ok := sessionContext[sessionID]; ok && time.Now().Before(e.exp) {
		return e.score
	}
	return 0
}

func updateSessionContext(sessionID string, delta int) int {
	if sessionID == "" {
		return 0
	}
	sessionCtxMu.Lock()
	defer sessionCtxMu.Unlock()
	current := 0
	if e, ok := sessionContext[sessionID]; ok && time.Now().Before(e.exp) {
		current = e.score
	}
	score := current + delta
	if score > 5 {
		score = 5
	}
	sessionContext[sessionID] = cacheEntry{score: score, exp: time.Now().Add(30 * time.Minute)}
	return score
}
