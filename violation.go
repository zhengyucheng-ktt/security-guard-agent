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

// violationHomophones 明显违规词的常见谐音写法（命中后进大模型判定，不直接截断，避免误伤）
var violationHomophones = map[string][]string{
	"色情":   {"se情", "seqing", "色qing", "涩情"},
	"暴恐":   {"bao恐", "bo恐", "暴kong"},
	"裸聊":   {"luo聊", "裸liao"},
	"裸照":   {"luo照", "裸zhao"},
	"涉政":   {"she政", "涉zheng"},
	"颠覆国家": {"颠fu国jia", "颠fu国家", "颠覆guojia"},
	"分裂国家": {"分lie国jia", "分裂guojia"},
	"恐怖袭击": {"恐bu袭ji", "恐怖xi ji"},
	"爆炸物":  {"爆zha物", "爆炸wu"},
	"枪支弹药": {"枪支dan药", "qiang弹药"},
}

// checkViolationHomophone 明显违规词的谐音变体检测（命中返回原词，由调用方进大模型判定）
func checkViolationHomophone(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		cl := strings.ToLower(cand)
		for orig, variants := range violationHomophones {
			for _, v := range variants {
				if strings.Contains(cl, v) {
					return true, "命中违规词谐音: " + orig + "（" + v + "）"
				}
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

// homophoneVariants 高频谐音写法（同音归一化：先识别谐音变体，再走组合判定+大模型裁定）
// 命中变体不直接拦截——仍须"负面+政治"组合且大模型确认，避免误伤
var homophoneVariants = map[string][]string{
	"攻击": {"攻ji", "攻鸡", "公鸡", "工机", "工击"},
	"诋毁": {"诋hui", "底毁", "抵毁", "地毁"},
	"侮辱": {"wu辱", "吾辱", "无辱", "污辱"},
	"辱骂": {"ru骂", "如骂", "汝骂"},
	"国家": {"guojia", "国jia", "国嘉", "果家"},
	"政府": {"zhengfu", "正fu", "政fu", "正府", "郑府"},
	"中国": {"zhongguo", "中guo", "种国", "中果"},
	"共产党": {"gongchandang", "gong产党", "工产党"},
	"主席": {"zhuxi", "主xi", "主习"},
	"台湾": {"taiwan", "台wan", "太湾"},
}

// hasHomophonePair 检查内容是否同时命中"负面词(含谐音) + 政治名词(含谐音)"
func hasHomophonePair(content string) (bool, bool) {
	lower := strings.ToLower(content)
	hasNeg := false
	for _, w := range negativeWords {
		if strings.Contains(lower, w) {
			hasNeg = true
			break
		}
		for _, v := range homophoneVariants[w] {
			if strings.Contains(lower, v) {
				hasNeg = true
				break
			}
		}
	}
	hasPol := false
	for _, w := range politicalNouns {
		if strings.Contains(lower, w) {
			hasPol = true
			break
		}
		for _, v := range homophoneVariants[w] {
			if strings.Contains(lower, v) {
				hasPol = true
				break
			}
		}
	}
	return hasNeg, hasPol
}

// checkSuspiciousPolitics 负面词 + 政治名词组合检测（整句，顺序无关，含同音变体）→ 疑似涉政
// 命中后由调用方触发大模型判定，避免误伤正常批评/讨论
func checkSuspiciousPolitics(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		hasNeg, hasPol := hasHomophonePair(cand)
		if hasNeg && hasPol {
			return true, "负面表述结合政治名词（疑似涉政）"
		}
	}
	return false, ""
}

// pornActionWords 涉黄性行为词（与传播场景词组合才触发判定）
var pornActionWords = []string{
	"性交", "做爱", "口交", "自慰", "手淫", "淫秽",
	"下体", "性器", "射精", "裸体", "脱衣",
}

// pornSceneWords 涉黄传播场景词（与性行为词组合才触发判定）
var pornSceneWords = []string{
	"视频", "直播", "网站", "图片", "小说", "平台",
	"录像", "表演", "交易", "群聊", "教程",
}

// strongPornActionWords 高置信涉黄性行为词：与传播场景词组合时直接拦截（无健康语义，如"做爱视频"）
var strongPornActionWords = []string{
	"性交", "做爱", "口交", "自慰", "手淫", "淫秽", "射精",
}

// checkStrongPorn 高置信涉黄组合：强性行为词 + 传播场景词 同现 → 直接拦截（不走 LLM，避免判定波动）
func checkStrongPorn(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		hasA, hasS := false, false
		for _, w := range strongPornActionWords {
			if strings.Contains(cand, w) {
				hasA = true
				break
			}
		}
		for _, w := range pornSceneWords {
			if strings.Contains(cand, w) {
				hasS = true
				break
			}
		}
		if hasA && hasS {
			return true, "高置信涉黄内容（性行为词结合传播场景）"
		}
	}
	return false, ""
}

// checkSuspiciousPorn 性行为词 + 传播场景词组合检测（整句，顺序无关）→ 疑似涉黄
// 命中后由调用方触发大模型判定，区分"健康性教育"与"涉黄传播"
func checkSuspiciousPorn(content string) (bool, string) {
	for _, cand := range matchCandidates(content) {
		hasA, hasS := false, false
		for _, w := range pornActionWords {
			if strings.Contains(cand, w) {
				hasA = true
				break
			}
		}
		for _, w := range pornSceneWords {
			if strings.Contains(cand, w) {
				hasS = true
				break
			}
		}
		if hasA && hasS {
			return true, "性行为词结合传播场景（疑似涉黄）"
		}
	}
	return false, ""
}

// checkSuspiciousViolation 统一"可疑违规"入口：明显违规词谐音 / 涉政组合 / 涉黄组合，
// 任一命中即返回疑似信号，由调用方触发大模型判定（不直接拦截，避免误伤）
func checkSuspiciousViolation(content string) (bool, string) {
	if risk, r := checkViolationHomophone(content); risk {
		return true, r
	}
	if risk, r := checkSuspiciousPolitics(content); risk {
		return true, r
	}
	if risk, r := checkSuspiciousPorn(content); risk {
		return true, r
	}
	return false, ""
}

// readableForJudge 取用于大模型判定的可读内容：优先解码后的明文（URL/Base64/HTML 实体等），
// 避免 LLM 面对编码乱码误判为安全；解码失败则用原文
func readableForJudge(content string) string {
	if dec := tryDecodeVariants(content); dec != "" {
		return dec
	}
	return content
}
