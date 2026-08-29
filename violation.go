package main

import "strings"

// ============================================================
// 涉黄涉政违规内容检测
// 输入侧：命中即拦截；输出侧：命中即停止输出并报错
// ============================================================

// violationKeywords 涉黄涉政违规关键词（规则层快速命中）
var violationKeywords = []string{
	"暴恐", "色情", "淫秽", "裸聊", "裸照", "涉黄", "涉政",
	"颠覆国家", "分裂国家", "攻击政府", "恐怖袭击", "爆炸物", "枪支弹药",
}

// checkViolation 规则层检测涉黄涉政违规内容（含编码/混淆变体）
func checkViolation(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		for _, kw := range violationKeywords {
			if strings.Contains(cand, kw) {
				return true, "命中违规关键词: " + kw
			}
		}
	}
	return false, ""
}
