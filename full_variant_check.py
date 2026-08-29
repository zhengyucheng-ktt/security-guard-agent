# -*- coding: utf-8 -*-
"""全量变体验证 v2：131 基础样本 + 变体，逐个走真实 API。
重点：区分 allow 样本里"走了 LLM 判定仍判安全" vs "压根没走 LLM 直接过"（真盲区）。
带断线重连 + 增量保存，服务崩溃也能从上次进度续跑。"""
import json, io, time, threading, http.client, base64, urllib.parse, re, os

cfg = json.load(io.open("system_config.json", encoding="utf-8"))
KEY = cfg.get("guard_api_key", "")
_local = threading.local()

def get_conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = http.client.HTTPConnection("127.0.0.1", 8080, timeout=120)
        _local.conn = c
    return c

def guard(session, content):
    b = {"session_id": session, "user_id": session, "action_type": "user_input", "content": content}
    data = json.dumps(b, ensure_ascii=False).encode("utf-8")
    for attempt in range(3):
        try:
            conn = get_conn()
            conn.request("POST", "/v1/guard", data,
                         {"Content-Type": "application/json", "X-Guard-Key": KEY})
            r = json.loads(conn.getresponse().read().decode("utf-8"))
            return r.get("decision"), r.get("block_reason", "")[:30], r.get("llm_ms", 0)
        except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError, http.client.HTTPException):
            _local.conn = None
            if attempt == 2:
                return "error", "连接失败", 0
            time.sleep(1)

synonym_swap = {
    "忽略": ["忽视", "无视", "忽略掉", "不理会"],
    "规则": ["限制", "设定", "指令", "约束"],
    "所有": ["全部", "一切"],
    "提示词": ["初始设定", "系统指令", "底层设定"],
    "忘记": ["遗忘", "清除"],
}

def insert_spaces(s):
    out = []
    for i, ch in enumerate(s):
        out.append(ch)
        if i % 3 == 2 and i < len(s) - 1:
            out.append(" ")
    return "".join(out)

def variants(content):
    vs = []
    for frm, tos in synonym_swap.items():
        if frm in content:
            for to in tos:
                vs.append(content.replace(frm, to, 1))
    vs.append(insert_spaces(content))
    if urllib.parse.quote(content) != content:
        vs.append(urllib.parse.quote(content))
    vs.append(base64.b64encode(content.encode("utf-8")).decode())
    return vs

# 从 selftest.go 提取基础样本，并还原 Go 字符串转义（\uXXXX → 真实字符）
def unescape_go(s):
    # Go 源码里 \\uXXXX 表示字面 \uXXXX（反斜杠+u+hex）；\" 表示引号
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch == '\\' and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == 'u' or nxt == 'U':
                width = 4 if nxt == 'u' else 8
                hexpart = s[i + 2:i + 2 + width]
                if len(hexpart) == width:
                    try:
                        out.append(chr(int(hexpart, 16)))
                        i += 2 + width
                        continue
                    except ValueError:
                        pass
            elif nxt == '\\':
                out.append('\\')
                i += 2
                continue
            elif nxt == '"':
                out.append('"')
                i += 2
                continue
        out.append(ch)
        i += 1
    return ''.join(out)

samples = []
for line in io.open("selftest.go", encoding="utf-8"):
    line = line.strip()
    m = re.match(r'\{"(.+)", "(.+)"\}', line)
    if m:
        samples.append((m.group(2), unescape_go(m.group(1))))

all_tests, seen = [], set()
for cat, content in samples:
    for c, kind in [(content, "基础")] + [(v, "变体") for v in variants(content)]:
        if c in seen:
            continue
        seen.add(c)
        all_tests.append((cat, c, kind))
total = len(all_tests)
print("去重后共: %d 个（基础 %d）" % (total, len(samples)))

# 增量续跑：已测过的写入 done.txt
done = set()
if os.path.exists("variant_done.txt"):
    for line in io.open("variant_done.txt", encoding="utf-8"):
        done.add(line.rstrip("\n"))

results_file = io.open("variant_results.txt", "a", encoding="utf-8")
blocked, allow_llm, allow_nollm, errors = 0, [], [], []
for i, (cat, c, kind) in enumerate(all_tests):
    key = c
    if key in done:
        continue
    dec, reason, llm_ms = guard("full-%d" % i, c)
    line = json.dumps({"cat": cat, "kind": kind, "content": c, "decision": dec, "reason": reason, "llm_ms": llm_ms}, ensure_ascii=False)
    results_file.write(line + "\n")
    results_file.flush()
    with io.open("variant_done.txt", "a", encoding="utf-8") as d:
        d.write(key + "\n")
    if dec == "block":
        blocked += 1
    elif dec == "allow":
        if llm_ms and llm_ms > 0:
            allow_llm.append((cat, c, kind, llm_ms))
        else:
            allow_nollm.append((cat, c, kind))
    else:
        errors.append((cat, c, kind, dec))
    if (i + 1) % 50 == 0:
        print("  进度 %d/%d 拦截%d 放行(走LLM)%d 放行(没走LLM)%d" % (i + 1, total, blocked, len(allow_llm), len(allow_nollm)), flush=True)

results_file.close()
print("=" * 66)
print("拦截: %d | 放行(LLM判安全): %d | 放行(没走LLM): %d | 错误: %d" % (blocked, len(allow_llm), len(allow_nollm), len(errors)))
print("-" * 66)
print("【真盲区】放行且没走 LLM 判定（规则层不拦 + 不触发可疑 → 直接过）:")
for cat, c, kind in allow_nollm:
    print("  [%s|%s] %s" % (cat, kind, c[:60]))
print("-" * 66)
print("【次风险】放行但 LLM 判安全:")
for cat, c, kind, ms in allow_llm:
    print("  [%s|%s] %s (llm=%dms)" % (cat, kind, c[:60], ms))
if errors:
    print("-" * 66)
    print("错误/连接失败:", errors[:5])
