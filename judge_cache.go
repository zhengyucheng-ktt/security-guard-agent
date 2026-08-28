package main

// ============================================================
// 判定引擎结果缓存：相同内容 30 秒内命中缓存，降低判定延迟与成本
// ============================================================

import (
	"sync"
	"time"
)

type judgeCacheEntry struct {
	hasRisk bool
	action  string
	reason  string
	exp     time.Time
}

var (
	judgeCache   = make(map[string]judgeCacheEntry)
	judgeCacheMu sync.Mutex
)

func getJudgeCache(content string) (bool, string, string, bool) {
	fp := contentFingerprint(content)
	if fp == "" {
		return false, "", "", false
	}
	judgeCacheMu.Lock()
	defer judgeCacheMu.Unlock()
	if e, ok := judgeCache[fp]; ok && time.Now().Before(e.exp) {
		return e.hasRisk, e.action, e.reason, true
	}
	return false, "", "", false
}

func setJudgeCache(content string, hasRisk bool, action, reason string) {
	fp := contentFingerprint(content)
	if fp == "" {
		return
	}
	judgeCacheMu.Lock()
	defer judgeCacheMu.Unlock()
	judgeCache[fp] = judgeCacheEntry{hasRisk: hasRisk, action: action, reason: reason, exp: time.Now().Add(30 * time.Second)}
}

func cleanupJudgeCache() {
	judgeCacheMu.Lock()
	defer judgeCacheMu.Unlock()
	now := time.Now()
	for fp, e := range judgeCache {
		if now.After(e.exp) {
			delete(judgeCache, fp)
		}
	}
}
