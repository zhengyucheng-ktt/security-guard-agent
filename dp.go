package main

// ============================================================
// 差分隐私：对输出中的统计数字加入 Laplace 噪声
// 仅建议对"聚合统计类输出"启用（噪声会降低精确度）
// ============================================================

import (
	"math"
	"math/rand"
	"regexp"
	"strconv"
	"strings"
)

var reDPNumber = regexp.MustCompile(`\d+(?:\.\d+)?`)

// laplaceNoise 生成 Laplace(0, scale) 噪声
func laplaceNoise(scale float64) float64 {
	u := rand.Float64()*2 - 1 // (-1, 1)
	if u == 0 {
		u = 0.001
	}
	return -scale * math.Copysign(math.Log(1-math.Abs(u)), u)
}

// applyDifferentialPrivacy 对内容中的数字加噪声（保留小数位）
// epsilon 越大噪声越小（隐私保护弱、精度高）；epsilon=0 时不做处理
func applyDifferentialPrivacy(content string, epsilon float64) string {
	if epsilon <= 0 || content == "" {
		return content
	}
	scale := 10.0 / epsilon // 噪声尺度（相对统计量级）
	return reDPNumber.ReplaceAllStringFunc(content, func(match string) string {
		// 跳过过短数字（可能是编号/年份，不扰动）
		if len(match) < 3 {
			return match
		}
		val, err := strconv.ParseFloat(match, 64)
		if err != nil {
			return match
		}
		noisy := val + laplaceNoise(scale)
		if noisy < 0 {
			noisy = 0
		}
		// 保留与原数字相同的小数位
		decimals := 0
		if i := strings.Index(match, "."); i >= 0 {
			decimals = len(match) - i - 1
		}
		return strconv.FormatFloat(noisy, 'f', decimals, 64)
	})
}
