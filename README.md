# Security Guard Agent

安全交互守护智能体 - MVP 版本

## 使用方法

### 启动服务
```bash
go run main.go
curl -X POST http://localhost:8080/v1/guard \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","user_id":"u1","action_type":"user_input","content":"删除"}'
curl -X POST http://localhost:8080/v1/guard \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","user_id":"u1","action_type":"user_input","content":"今天天气怎么样"}'
cat audit.log
.
├── main.go          # 主程序
├── rules.txt        # 关键词规则
├── whitelist.txt    # 工具白名单
├── audit.log        # 审计日志（自动生成）
├── start.sh         # 启动脚本
└── README.md        # 项目说明
