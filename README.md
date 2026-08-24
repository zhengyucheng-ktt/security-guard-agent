# Security Guard Agent

安全交互守护智能体 - 面向 LLM 交互场景的多层风控网关（Go + Gin）。

## 功能特性

- **输入检测**：关键词规则（`rules.txt`）+ 内置正则规则 + 自然语言规则（`nlp_rules.json`，可热配置）+ Ollama 大模型兜底判断（可疑内容自动升级审核）
- **工具调用防护**：高危工具黑名单 → 工具白名单（管理员显式授权优先）→ 参数白名单清洗 → 参数深度校验（SQL 注入 / 路径遍历 / 批量操作 / 敏感参数）→ 30 秒 JWT 工具令牌
- **提示注入防御**：混淆变体检测（全角/空白/零宽字符/多层 Base64/URL 编码归一化解码）+ 间接注入扫描（`tool_result` 工具返回内容）+ 会话语境分（多轮渐进式注入：铺垫词累积 → 升级审查 → 敏感请求联动拦截）+ 判定引擎注入意图判断
- **反刷评**：全局内容去重（相同/相似评论拦截）+ 账号/IP 维度聚合限流 + 账号信誉分（跨会话、可持久化）+ 机器行为特征检测（请求间隔均匀性，可选）
- **对抗自测**：内置绕过变体生成器（同义词/空白/编码/角色/引用式）+ 87 样本规则层回归，穿透样本自动记录（`bypass_samples.json`），发现盲区即补规则（GUI「🛡 对抗自测」按钮）
- **输出防护**：动态分级脱敏（手机 / 身份证 / 银行卡 / 邮箱 / IP / 姓名 / 地址 / 车牌 / 营业执照 / 微信号）+ 零宽字符水印（可溯源）+ 差分隐私（对统计数字加 Laplace 噪声，可选）
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
| `GET/PUT /admin/api/config` | 系统配置（差分隐私/限流/脱敏级别/会话超时/判定引擎） |
| `POST /admin/api/extract-watermark` | 水印提取（溯源） |

## 判定引擎模式选择指南

安全审核 LLM（判定模型）支持三种模式，由用户自行选择（GUI「⚙️ 系统配置」或 `system_config.json` 的 `llm_judge_mode`），配置热加载即生效：

| 模式 | 逻辑 | 优点 | 缺点 | 适合 |
|---|---|---|---|---|
| **local** | 只用本地 Ollama 模型 | 数据不出网（隐私/合规安全）、零 API 成本、断网可用、无 Key 泄露风险 | 判定力受本地模型与显存限制（7B 对复杂攻击有盲区）、需自己维护模型 | 数据敏感（金融/医疗/政务）、离线或内网环境 |
| **cloud** | 只用云端 API（OpenAI 兼容） | 判定能力最强、模型免维护自动升级、响应快 | 用户内容出网（隐私/合规风险）、按量付费、依赖网络与供应商、Key 泄露会被盗刷 | 判定力优先、数据敏感性低、预算充足 |
| **hybrid** | 本地初筛 + 云端终审 | 隐私与能力平衡——本地先判（大多数据不出网），本地判安全才升级云端复核，双保险更安全 | 可疑请求两次调用更慢、需同时配置两个引擎、云端不可达时依赖失败策略 | 兼顾隐私与判定力（推荐默认） |

**失败策略**（`llm_judge_fail_policy`，引擎不可用时）：

| 策略 | 行为 | 安全性 |
|---|---|---|
| `fallback` | 降级到另一引擎（本地↔云端互为备份） | 推荐默认 |
| `block` | 拦截（"审核服务不可用"） | fail-closed，最安全 |
| `allow` | 放行 | fail-open，有风险 |

配置示例：
```json
"llm_judge_mode": "hybrid",
"llm_judge_url": "http://localhost:11434/v1/chat/completions",
"llm_judge_model": "qwen2.5:7b",
"cloud_judge_url": "https://api.deepseek.com/v1/chat/completions",
"cloud_judge_model": "deepseek-chat",
"cloud_judge_api_key": "sk-xxx",
"llm_judge_fail_policy": "fallback"
```

> 提示：接云端前确认云厂商数据处理政策（是否留存/用于训练）与数据出境合规；GUI 中切换模式会实时显示各模式的优缺点说明。

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

## Docker 部署

```bash
docker build -t security-guard-agent:latest .     # 多阶段构建（~15MB）
docker run -d --name guard -p 8080:8080 \
  -v /path/to/config:/app security-guard-agent     # config 目录放 rules.txt 等配置（可省略，首次自动生成）
```

> 需在装有 Docker 的机器上执行（本仓库已含 `Dockerfile` / `.dockerignore` / `build-docker.bat`）。

## 多实例部署（水平扩展时）

guard 默认单实例即可（内存模式 + 本地文件持久化）。**只有当你要部署多个实例做负载均衡时**才需要 Redis 共享会话状态：

```bash
# 1. 启动 Redis
# 2. 每个实例指向同一 Redis
REDIS_ADDR=redis:6379 ./guard
REDIS_ADDR=redis:6379 ./guard   # 第二个实例
```

- 多实例共享：会话积分 / 限流 / 信誉分 / 封禁状态（Redis 模式）
- 运行中 Redis 异常会自动降级内存模式并本地持久化，功能不失效
- 单实例场景完全不需要 Redis（自动内存模式，启动 1.7s）

## 安全注意事项

- 服务默认只监听 `127.0.0.1`（可用 `BIND_ADDR` 覆盖）；对外暴露前务必设置强 `JWT_SECRET` / `ADMIN_TOKEN` 并配置 HTTPS
- 管理 API 无内置 RBAC，Token 即全部管理权限，请妥善保管 `admin_token.txt`
- 判定引擎为可选增强（`isSuspicious`/触发词命中时调用），不可用时按失败策略降级/放行/拦截
