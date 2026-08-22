package main

// ============================================================
// 反刷评增强：短视频评论区 AI 机器人防御
// ① 全局内容去重（相同/高度相似评论直接拦截）
// ② 账号/IP 维度聚合限流（堵住分布式刷评）
// ③ 账号信誉分（跨会话，低信誉直接降权）
// ============================================================

import (
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"log"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// ---- ① 全局内容去重 ----

var (
	dupCache   = make(map[string]time.Time) // 指纹 -> 最近出现时间
	dupCacheMu sync.Mutex
)

var rePunct = regexp.MustCompile(`[\p{P}\p{S}\s]+`)

// contentFingerprint 归一化内容（去空白/标点/符号、转小写）后取 SHA1
func contentFingerprint(content string) string {
	norm := rePunct.ReplaceAllString(strings.ToLower(content), "")
	if norm == "" {
		return ""
	}
	sum := sha1.Sum([]byte(norm))
	return hex.EncodeToString(sum[:])
}

// checkDuplicate 判断是否近期重复内容；未重复则记录（窗口内再次出现返回 true）
func checkDuplicate(content string, window time.Duration) (bool, string) {
	fp := contentFingerprint(content)
	if fp == "" {
		return false, ""
	}
	now := time.Now()
	dupCacheMu.Lock()
	defer dupCacheMu.Unlock()
	if last, ok := dupCache[fp]; ok && now.Sub(last) <= window {
		return true, fp
	}
	dupCache[fp] = now
	return false, fp
}

// ---- ② 账号/IP 维度聚合限流 ----

var (
	userLimiters = make(map[string]*sessionLimiter)
	ipLimiters   = make(map[string]*sessionLimiter)
	aggregateMu  sync.Mutex
)

// getAggregateLimiter 获取（或创建）聚合限流器；配置变更自动调整速率
func getAggregateLimiter(store map[string]*sessionLimiter, key string, rateLimit, burst int) *rate.Limiter {
	aggregateMu.Lock()
	defer aggregateMu.Unlock()
	if sl, ok := store[key]; ok {
		sl.lastUsed = time.Now()
		sl.limiter.SetLimit(rate.Limit(rateLimit))
		sl.limiter.SetBurst(burst)
		return sl.limiter
	}
	l := rate.NewLimiter(rate.Limit(rateLimit), burst)
	store[key] = &sessionLimiter{limiter: l, lastUsed: time.Now()}
	return l
}

// ---- ③ 账号信誉分（跨会话、可持久化） ----

var (
	reputationCache = make(map[string]cacheEntry)
	repMu           sync.RWMutex
)

const reputationCacheFile = "reputation_cache.json"

type persistedReputation struct {
	Score int       `json:"score"`
	Exp   time.Time `json:"exp"`
}

// updateUserReputation 按 delta 更新账号信誉分（0-100，带 TTL）
func updateUserReputation(userID string, delta int) int {
	if userID == "" {
		return 0
	}
	repMu.Lock()
	defer repMu.Unlock()
	current := 0
	if e, ok := reputationCache[userID]; ok && time.Now().Before(e.exp) {
		current = e.score
	}
	score := current + delta
	if score < 0 {
		score = 0
	}
	if score > 100 {
		score = 100
	}
	reputationCache[userID] = cacheEntry{score: score, exp: time.Now().Add(SESSION_TTL)}
	return score
}

// getUserReputation 返回账号当前信誉分（过期视为 0）
func getUserReputation(userID string) int {
	if userID == "" {
		return 0
	}
	repMu.RLock()
	defer repMu.RUnlock()
	if e, ok := reputationCache[userID]; ok && time.Now().Before(e.exp) {
		return e.score
	}
	return 0
}

func persistReputation() {
	repMu.RLock()
	data := make(map[string]persistedReputation, len(reputationCache))
	for k, v := range reputationCache {
		data[k] = persistedReputation{Score: v.score, Exp: v.exp}
	}
	repMu.RUnlock()
	raw, err := json.Marshal(data)
	if err != nil {
		return
	}
	os.WriteFile(reputationCacheFile, raw, 0600)
}

func loadPersistedReputation() {
	data, err := os.ReadFile(reputationCacheFile)
	if err != nil {
		return
	}
	var m map[string]persistedReputation
	if err := json.Unmarshal(data, &m); err != nil {
		return
	}
	repMu.Lock()
	for k, v := range m {
		if time.Now().Before(v.Exp) {
			reputationCache[k] = cacheEntry{score: v.Score, exp: v.Exp}
		}
	}
	repMu.Unlock()
	log.Printf("💾 已从 %s 恢复 %d 个账号信誉", reputationCacheFile, len(m))
}
