package main

// ============================================================
// 编码规范化：确保进入检测链路的内容是合法 UTF-8
// 兼容业务智能体在 GBK 等非 UTF-8 环境下输出的内容
// ============================================================

import (
	"strings"
	"unicode/utf8"

	"golang.org/x/text/encoding/simplifiedchinese"
)

// normalizeToUTF8 将内容规范化为合法 UTF-8：
//  1. 已是合法 UTF-8 → 原样返回
//  2. 否则尝试 GBK → UTF-8 转码
//  3. 仍失败 → 替换非法字节（\ufffd），保证后续链路不产生乱码
func normalizeToUTF8(content string) string {
	if content == "" || utf8.ValidString(content) {
		return content
	}
	// 尝试 GBK → UTF-8（覆盖中文 Windows/GBK 环境输出的内容）
	if dec, err := simplifiedchinese.GBK.NewDecoder().Bytes([]byte(content)); err == nil && utf8.Valid(dec) {
		return string(dec)
	}
	// 兜底：替换非法 UTF-8 字节，保证结果合法
	return strings.ToValidUTF8(content, "\ufffd")
}
