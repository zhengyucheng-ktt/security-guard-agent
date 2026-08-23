# Security Guard Agent - 多阶段构建（~15MB 运行时镜像）
# 构建: docker build -t security-guard-agent:latest .
# 运行: docker run -d --name guard -p 8080:8080 -v /path/to/config:/app security-guard-agent
#       (config 目录放 rules.txt / whitelist.txt / system_config.json 等，可省略则用默认并自动生成)

FROM golang:1.26-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o guard .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/guard .
EXPOSE 8080
CMD ["./guard"]
