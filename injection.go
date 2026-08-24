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

// decodeOnce 单层解码：URL 编码（含 %）优先，其次 Base64
func decodeOnce(content string) string {
	// URL 编码：仅当含 %（URL 编码标记）时尝试，避免把 Base64 的 + 误当空格
	if strings.Contains(content, "%") {
		if dec, err := url.QueryUnescape(content); err == nil && dec != content && isReadableText(dec) {
			return dec
		}
	}
	// Base64 编码：去空白后长度合规（%4==0）时尝试，结果须为可读文本才采纳
	compact := strings.Map(func(r rune) rune {
		if unicode.IsSpace(r) {
			return -1
		}
		return r
	}, content)
	if len(compact)%4 == 0 && len(compact) >= 8 {
		if dec, err := base64.StdEncoding.DecodeString(compact); err == nil {
			s := string(dec)
			if isReadableText(s) && len(s) >= 4 {
				return s
			}
		}
	}
	return ""
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

// matchCandidates 生成用于匹配的候选文本（原文 + 归一化 + 解码变体）
func matchCandidates(content string) []string {
	cands := []string{content}
	if norm := normalizeForMatch(content); norm != "" && norm != content {
		cands = append(cands, norm)
	}
	if dec := tryDecodeVariants(content); dec != "" && dec != content {
		cands = append(cands, dec)
	}
	return cands
}

// ---- ② 间接注入 / 注入词扫描 ----

var injectionKeywords = []string{
	"忽略", "忘记", "提示词", "底层规则", "系统提示", "system prompt", "system_prompt",
	"忽略限制", "越狱", "绕过", "覆盖指令", "无视规则", "prompt injection",
}

// checkInjection 综合检测注入意图（对候选变体逐一匹配规则与关键词）
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
		for _, rule := range regexRules {
			if rule.Regex.MatchString(cand) {
				return true, rule.Reason
			}
		}
		for _, kw := range injectionKeywords {
			if strings.Contains(cand, kw) {
				return true, "命中注入关键词: " + kw
			}
		}
	}
	return false, ""
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
