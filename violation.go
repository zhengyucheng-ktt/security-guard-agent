package main

import "strings"

// ============================================================
// 涉黄涉政违规内容检测
// 输入侧：命中即拦截；输出侧：命中即停止输出并报错
// 策略：明显违规词直接截断；"负面词+政治名词"组合触发大模型判定
// ============================================================

// violationKeywords 涉黄涉政明显违规词（规则层直接截断）
var violationKeywords = []string{
	"暴恐", "色情", "淫秽", "裸聊", "裸照", "涉黄", "涉政",
	"颠覆国家", "分裂国家", "攻击政府", "恐怖袭击", "爆炸物", "枪支弹药",
}

// checkViolation 规则层检测涉黄涉政明显违规内容（含编码/混淆变体）→ 直接截断
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

// negativeWords 精选强负面词（不含"批评/反对/不满"等正常监督表达，避免误伤）
var negativeWords = []string{
	"攻击", "诋毁", "侮辱", "辱骂", "谩骂", "抹黑", "推翻",
	"颠覆", "煽动", "仇恨", "污蔑", "丑化", "造谣", "贬损",
}

// politicalNouns 政治名词（与负面词组合才触发判定）
var politicalNouns = []string{
	"国家", "政府", "中国", "共产党", "领导人", "主席",
	"政权", "体制", "台湾", "西藏", "新疆", "民族",
}

// checkSuspiciousPolitics 负面词 + 政治名词组合检测（整句，顺序无关）→ 疑似涉政
// 命中后由调用方触发大模型判定，避免误伤正常批评/讨论
func checkSuspiciousPolitics(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		hasNeg, hasPol := false, false
		for _, w := range negativeWords {
			if strings.Contains(cand, w) {
				hasNeg = true
				break
			}
		}
		for _, w := range politicalNouns {
			if strings.Contains(cand, w) {
				hasPol = true
				break
			}
		}
		if hasNeg && hasPol {
			return true, "负面表述结合政治名词（疑似涉政）"
		}
	}
	return false, ""
}
