# Security Guard Agent

安全交互守护智能体 - 面向 LLM 交互场景的多层风控网关（Go + Gin）。

## 功能特性

- **输入检测**：关键词规则（`rules.txt`）+ 内置正则规则 + 自然语言规则（`nlp_rules.json`，可热配置）+ Ollama 大模型兜底判断（可疑内容自动升级审核）
- **工具调用防护**：高危工具黑名单 → 工具白名单（管理员显式授权优先）→ 参数白名单清洗 → 参数深度校验（SQL 注入 / 路径遍历 / 批量操作 / 敏感参数）→ 30 秒 JWT 工具令牌
- **提示注入防御**：混淆变体检测（全角/空白/零宽字符/Base64/URL 编码归一化解码）+ 间接注入扫描（`tool_result` 工具返回内容）+ 会话语境分（多轮渐进式注入：铺垫词累积 → 升级审查 → 敏感请求联动拦截）+ Ollama 注入意图判断
- **反刷评**：全局内容去重（相同/相似评论拦截）+ 账号/IP 维度聚合限流 + 账号信誉分（跨会话、可持久化）
- **输出防护**：动态分级脱敏（手机 / 身份证 / 银行卡 / 邮箱 / IP / 姓名 / 地址 / 车牌 / 营业执照 / 微信号）+ 零宽字符水印（可溯源）
- **会话风控**：风险积分（30 警告 / 60 限流 / 80 终止），拦截行为也累计积分，可升级处置；内存模式下积分持久化（`sessions_cache.json`），重启不丢
- **管理面**：Web 后台（`/admin`）+ Python Tkinter 控制面板（`guard_gui.pyw`），管理 API 全部需要 Token 鉴权

## 快速开始

```bash
# 启动服务（默认绑定 127.0.0.1:8080）
go run main.go

# 或使用编译好的二进制
./guard.exe
```

Windows 用户可直接双击 `启动GUI.bat` 使用图形控制面板（启停服务、规则管理、会话监控/封禁/解封、审计日志、水印提取）。

### 管理 Token

服务首次启动时自动生成随机管理 Token，保存到 `admin_token.txt`（同时打印在服务日志中）。访问管理后台 API 或网页时需携带：

```bash
curl http://localhost:8080/admin/api/rules -H "X-Admin-Token: <token>"
```

JWT 密钥同理自动生成并持久化到 `.jwt_secret`（生产环境建议用 `JWT_SECRET` 环境变量注入）。

## 黑箱接入（推荐给非技术用户）

不懂内部机制也能接入：只需 `guard_sdk.py`，几行代码获得完整防护（输入审核 / 工具防护 / 输出脱敏水印），连 session/user 标识都不用管。

```python
from guard_sdk import Guard
guard = Guard(api_key="你的密钥")        # 服务端 guard_api_key 为空则不用填

# 方式一：一行包装你的 LLM（自动完成 输入审核→LLM→工具防护→输出审核）
safe_llm = guard.wrap_llm(my_llm_function, execute_tool=my_tool)
reply = safe_llm("用户说的话")

# 方式二：分环节手动控制
guard.check_input("用户输入")            # 违规抛 GuardBlocked
safe = guard.review_output("模型回复")    # 返回脱敏+水印后的安全文本
```

- 拦截时抛出 `GuardBlocked`（`message` 即拦截原因，可直接展示）
- 完整可运行示例见 `接入示例.py`（`python 接入示例.py` 直接跑）
- SDK 演示：`python guard_sdk.py`

## API 文档

### 风控接口

**POST /v1/guard** — 核心风控入口

请求体：
```json
{
  "session_id": "s1",
  "user_id": "u1",
  "action_type": "user_input | tool_call | tool_result | output",
  "content": "用户输入内容",
  "tool_name": "/api/weather/query",
  "tool_params": {"city": "北京"},
  "output_content": "模型输出 / 工具返回内容"
}
```

> `tool_result`：工具返回内容进模型上下文前的注入扫描（间接注入防御），命中即拦截；`output`：模型输出脱敏 + 水印。

响应：
```json
{
  "decision": "allow | block",
  "risk_level": "low | medium | high | critical",
  "block_reason": "拦截原因",
  "safe_output": "脱敏+水印后的输出",
  "current_score": 30,
  "session_status": "正常 | 警告 | 已限流 | 已终止"
}
```

**POST /v1/guard/validate-token** — 工具令牌校验（工具端自证授权）

```bash
# body 方式
curl -X POST http://localhost:8080/v1/guard/validate-token \
  -H "Content-Type: application/json" \
  -d '{"token": "<JWT>"}'
# 或 Authorization: Bearer 方式
```

**GET /health** — 健康检查

### 管理接口（需 `X-Admin-Token`）

| 接口 | 说明 |
|---|---|
| `GET/POST /admin/api/rules`、`DELETE /rules/:index` | 关键词/正则规则管理 |
| `GET/POST /admin/api/whitelist`、`DELETE /whitelist/:index` | 工具白名单管理 |
| `GET/POST /admin/api/nlp-rules`、`DELETE /nlp-rules/:index`、`PUT /nlp-rules/:index/toggle` | 自然语言规则管理 |
| `GET /admin/api/sessions` | 会话列表（积分/状态） |
| `PUT /admin/api/sessions/:id/reset` | 解封（重置积分与限流） |
| `PUT /admin/api/sessions/:id/ban` | 手动封禁（积分置 100） |
| `GET /admin/api/sessions/:id/audit` | 会话风险明细（审计记录） |
| `GET /admin/api/logs?tail=N&date=YYYYMMDD` | 审计日志（末尾 N 行 / 历史日期） |
| `GET/PUT /admin/api/config` | 系统配置（差分隐私/限流/脱敏级别/会话超时） |
| `POST /admin/api/extract-watermark` | 水印提取（溯源） |

## 配置说明

| 文件 | 说明 |
|---|---|
| `rules.txt` | 关键词规则（每行一个，`#` 注释），启动时加载，管理端增删自动保存 |
| `whitelist.txt` | 工具白名单（每行一个） |
| `nlp_rules.json` | 自然语言规则（描述 → 关键词自动提取 → block/warning/allow） |
| `desensitize_policies.json` | 按角色脱敏策略：`level`（full/partial/minimal）+ `fields`（字段门控，列出才脱敏；留空则全部脱敏） |
| `system_config.json` | 系统配置（3 秒轮询热加载，无需重启） |
| `admin_token.txt` / `.jwt_secret` | 管理 Token / JWT 密钥（自动生成，勿提交仓库） |
| `sessions_cache.json` | 内存模式下会话积分持久化缓存 |

## 审计日志

- **JSON 行格式**：每行一条结构化记录（time/session_id/user_id/action_type/content/decision/risk_level/reason/score），便于程序解析
- **按天轮转**：`audit.log` 始终为当日文件，跨天自动归档为 `audit-YYYYMMDD.log`（历史文件可用 `?date=` 查询）
- 异步写入（队列满降级同步，不丢审计）

## 模块结构

```
main.go            入口、路由（setupRouter）、核心 guardHandler、管理接口
desensitize.go     数据脱敏：正则、脱敏函数、字段门控策略
watermark.go       零宽字符水印：编码 / 添加 / 提取
audit.go           审计日志：JSON 行、按天轮转、异步写入
sessions.go        会话积分：读写、缓存清理、持久化恢复
rules.txt / whitelist.txt / *.json   配置
guard_gui.pyw      Tkinter 控制面板（增强版）
main_test.go       单元 + 集成测试（go test ./...）
```

## 测试

```bash
go test ./...     # 33 个测试：核心逻辑单元测试 + 完整 HTTP 链路集成测试
```

测试自动备份/恢复配置文件，不会污染真实配置（`whitelist.txt` 等）。

## 安全注意事项

- 服务默认只监听 `127.0.0.1`（可用 `BIND_ADDR` 覆盖）；对外暴露前务必设置强 `JWT_SECRET` / `ADMIN_TOKEN` 并配置 HTTPS
- 管理 API 无内置 RBAC，Token 即全部管理权限，请妥善保管 `admin_token.txt`
- Ollama 大模型判断为可选增强（`isSuspicious` 命中时调用 `localhost:11434`，10 秒超时），无 Ollama 时自动跳过不阻塞
