package main

// ============================================================
// 会话积分：读写、缓存清理、持久化恢复
// ============================================================

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// ============================================================
// 会话积分
// ============================================================

func getSessionScore(sessionID string) (int, error) {
	if useMemoryMode.Load() {
		cacheMutex.RLock()
		defer cacheMutex.RUnlock()
		entry, ok := memoryCache[sessionID]
		if !ok || time.Now().After(entry.exp) {
			return 0, nil
		}
		return entry.score, nil
	}
	key := "session:" + sessionID
	val, err := redisClient.Get(ctx, key).Result()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(val)
}

func updateSessionScore(sessionID string, delta int) (int, error) {
	if useMemoryMode.Load() {
		cacheMutex.Lock()
		defer cacheMutex.Unlock()
		current := 0
		if entry, ok := memoryCache[sessionID]; ok && time.Now().Before(entry.exp) {
			current = entry.score
		}
		newScore := current + delta
		if newScore < 0 {
			newScore = 0
		}
		if newScore > 100 {
			newScore = 100
		}
		memoryCache[sessionID] = cacheEntry{score: newScore, exp: time.Now().Add(SESSION_TTL)}
		return newScore, nil
	}
	key := "session:" + sessionID
	current, err := getSessionScore(sessionID)
	if err != nil {
		return 0, err
	}
	newScore := current + delta
	if newScore < 0 {
		newScore = 0
	}
	if newScore > 100 {
		newScore = 100
	}
	err = redisClient.Set(ctx, key, newScore, SESSION_TTL).Err()
	if err != nil {
		return 0, err
	}
	return newScore, nil
}

// 周期性清理：过期积分、空闲限流器；定期持久化会话积分
func startCacheJanitor() {
	go func() {
		ticker := time.NewTicker(time.Minute)
		for range ticker.C {
			cacheMutex.Lock()
			for sid, entry := range memoryCache {
				if time.Now().After(entry.exp) {
					delete(memoryCache, sid)
				}
			}
			cacheMutex.Unlock()

			limiterMutex.Lock()
			for sid, sl := range limiters {
				if time.Since(sl.lastUsed) > SESSION_TTL {
					delete(limiters, sid)
				}
			}
			limiterMutex.Unlock()

			// 反刷评缓存清理
			dupCacheMu.Lock()
			for fp, t := range dupCache {
				if time.Since(t) > 30*time.Minute {
					delete(dupCache, fp)
				}
			}
			dupCacheMu.Unlock()
			aggregateMu.Lock()
			for k, sl := range userLimiters {
				if time.Since(sl.lastUsed) > SESSION_TTL {
					delete(userLimiters, k)
				}
			}
			for k, sl := range ipLimiters {
				if time.Since(sl.lastUsed) > SESSION_TTL {
					delete(ipLimiters, k)
				}
			}
			aggregateMu.Unlock()
			repMu.Lock()
			for k, e := range reputationCache {
				if time.Now().After(e.exp) {
					delete(reputationCache, k)
				}
			}
			repMu.Unlock()
			sessionCtxMu.Lock()
			for k, e := range sessionContext {
				if time.Now().After(e.exp) {
					delete(sessionContext, k)
				}
			}
			sessionCtxMu.Unlock()
			cleanupBehavior() // 清理机器行为记录

			// Redis 健康检查：运行中连接异常自动降级内存模式（功能不失效）
			if !useMemoryMode.Load() {
				pingCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				pingErr := redisClient.Ping(pingCtx).Err()
				cancel()
				if pingErr != nil {
					log.Printf("⚠️ Redis 连接异常(%v)，自动降级为内存模式（会话数据继续本地持久化，功能不受影响）", pingErr)
					useMemoryMode.Store(true)
				}
			}

			persistSessions()    // 内存模式下持久化积分，重启不丢
			persistReputation()  // 持久化账号信誉分
		}
	}()
	log.Println("🧹 缓存清理任务已启动（每60秒清理过期积分与空闲限流器）")
}

// ============================================================
// 会话积分持久化（仅内存模式；Redis 模式本身持久）
// ============================================================

const sessionsCacheFile = "sessions_cache.json"

// persistedSession 用于 JSON 序列化（cacheEntry 字段未导出，json 无法直接编解码）
type persistedSession struct {
	Score int       `json:"score"`
	Exp   time.Time `json:"exp"`
}

func persistSessions() {
	if !useMemoryMode.Load() {
		return
	}
	cacheMutex.RLock()
	data := make(map[string]persistedSession, len(memoryCache))
	for k, v := range memoryCache {
		data[k] = persistedSession{Score: v.score, Exp: v.exp}
	}
	cacheMutex.RUnlock()
	raw, err := json.Marshal(data)
	if err != nil {
		return
	}
	os.WriteFile(sessionsCacheFile, raw, 0600)
}

func loadPersistedSessions() {
	if !useMemoryMode.Load() {
		return
	}
	data, err := os.ReadFile(sessionsCacheFile)
	if err != nil {
		return
	}
	var m map[string]persistedSession
	if err := json.Unmarshal(data, &m); err != nil {
		return
	}
	cacheMutex.Lock()
	for k, v := range m {
		if time.Now().Before(v.Exp) {
			memoryCache[k] = cacheEntry{score: v.Score, exp: v.Exp}
		}
	}
	cacheMutex.Unlock()
	log.Printf("💾 已从 %s 恢复 %d 个会话", sessionsCacheFile, len(m))
}

func getSessionStatus(score int) string {
	if score >= THRESHOLD_TERMINATE {
		return "已终止"
	}
	if score >= THRESHOLD_LIMIT {
		return "已限流"
	}
	if score >= THRESHOLD_WARNING {
		return "警告"
	}
	return "正常"
}
