package main

// ============================================================
// 机器行为特征评分：检测"请求间隔过于均匀"的自动化特征
// 真实用户点击间隔随机；机器人通常按固定节拍请求
// ============================================================

import (
	"math"
	"sync"
	"time"
)

const (
	behaviorWindowSize = 8  // 记录最近 N 个请求时间戳
	behaviorMinSamples = 5  // 至少 N 个样本才判定
	behaviorCVThreshold = 0.15 // 间隔变异系数低于该值 → 机器特征
)

var (
	sessionBehavior = make(map[string][]time.Time)
	behaviorMu      sync.Mutex
)

// recordBehavior 记录一次请求时间戳，返回是否触发机器特征（间隔均匀）
// 返回 true 表示检测到机器行为特征（仅统计，拦截与否由调用方决定）
func recordBehavior(sessionID string) bool {
	if sessionID == "" {
		return false
	}
	now := time.Now()
	behaviorMu.Lock()
	defer behaviorMu.Unlock()
	history := sessionBehavior[sessionID]
	if len(history) >= behaviorWindowSize {
		history = history[len(history)-behaviorWindowSize+1:]
	}
	history = append(history, now)
	sessionBehavior[sessionID] = history

	if len(history) < behaviorMinSamples {
		return false
	}
	// 计算间隔的变异系数（CV = 标准差 / 均值）
	intervals := make([]float64, 0, len(history)-1)
	for i := 1; i < len(history); i++ {
		intervals = append(intervals, history[i].Sub(history[i-1]).Seconds())
	}
	mean := 0.0
	for _, v := range intervals {
		mean += v
	}
	mean /= float64(len(intervals))
	if mean <= 0.01 { // 间隔过密（<10ms）本身可疑
		return true
	}
	variance := 0.0
	for _, v := range intervals {
		variance += (v - mean) * (v - mean)
	}
	variance /= float64(len(intervals))
	cv := math.Sqrt(variance) / mean
	return cv < behaviorCVThreshold
}

// cleanupBehavior 清理过期会话的行为记录（janitor 调用）
func cleanupBehavior() {
	behaviorMu.Lock()
	defer behaviorMu.Unlock()
	cutoff := time.Now().Add(-SESSION_TTL)
	for sid, history := range sessionBehavior {
		if len(history) == 0 || history[len(history)-1].Before(cutoff) {
			delete(sessionBehavior, sid)
		}
	}
}

// resetBehavior 清空全部行为记录（运维/演示用）
func resetBehavior() {
	behaviorMu.Lock()
	sessionBehavior = make(map[string][]time.Time)
	behaviorMu.Unlock()
}
