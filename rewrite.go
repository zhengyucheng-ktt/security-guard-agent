package main

// ============================================================
// 低风险自动改写：输入中的 PII（手机号/邮箱/身份证等）自动脱敏后继续对话
// 适用于"内容含敏感信息但不构成拦截"的低风险场景
// ============================================================

// rewriteContent 将内容中的 PII 脱敏（与输出侧一致的脱敏规则）
func rewriteContent(content string) string {
	result := rePhone.ReplaceAllStringFunc(content, desensitizePhone)
	result = reID.ReplaceAllStringFunc(result, desensitizeIDCard)
	result = reEmail.ReplaceAllStringFunc(result, desensitizeEmail)
	result = reBank.ReplaceAllStringFunc(result, desensitizeBankCard)
	result = reIP.ReplaceAllStringFunc(result, desensitizeIP)
	return result
}
