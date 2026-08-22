package main

// ============================================================
// 零宽字符水印：编码 / 添加 / 提取
// ============================================================

import (
	"fmt"
	"strings"
	"time"
)

// ============================================================
// 水印配置
// ============================================================

const (
	ZERO_WIDTH_SPACE = "\u200B"
	ZERO_WIDTH_NBSP  = "\uFEFF"
)

func encodeToZeroWidth(data string) string {
	result := ""
	for _, ch := range data {
		for i := 7; i >= 0; i-- {
			bit := (ch >> uint(i)) & 1
			if bit == 1 {
				result += ZERO_WIDTH_SPACE
			} else {
				result += ZERO_WIDTH_NBSP
			}
		}
	}
	return result
}

func addWatermark(content, sessionID, userID string) string {
	watermarkData := fmt.Sprintf("%s|%s|%d", sessionID, userID, time.Now().Unix())
	return content + encodeToZeroWidth(watermarkData)
}

func extractWatermark(content string) string {
	var result strings.Builder
	for _, ch := range content {
		if ch == '\u200B' {
			result.WriteString("1")
		} else if ch == '\uFEFF' {
			result.WriteString("0")
		}
	}
	binaryStr := result.String()
	if len(binaryStr)%8 != 0 {
		return ""
	}
	var bytes []byte
	for i := 0; i < len(binaryStr); i += 8 {
		var b byte
		for j := 0; j < 8; j++ {
			if binaryStr[i+j] == '1' {
				b |= 1 << uint(7 - j)
			}
		}
		bytes = append(bytes, b)
	}
	return string(bytes)
}
