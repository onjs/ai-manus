# 🚀 快速上手

## 环境准备

- Docker 20.10+
- Docker Compose

## 一键启动（推荐）

1. 复制示例环境变量：

```bash
cp .env.example .env
```

2. 至少修改以下配置：

- `GATEWAY_API_KEY`
- `GATEWAY_INTERNAL_API_KEY`
- `GATEWAY_REDIS_URL`
- `SANDBOX_INTERNAL_API_KEY`
- `API_BASE`
- `API_KEY`
- `JWT_SECRET_KEY`

3. 启动：

```bash
docker compose -f docker-compose-development.yml up -d --build
```

4. 打开：

- 前端: <http://localhost:5173>
- 后端 API: <http://localhost:8000>
- Gateway: <http://localhost:8100>
- Sandbox API: <http://localhost:8080>

## 生产/简化编排示例

可直接使用仓库根目录的 [`docker-compose-example.yml`](../docker-compose-example.yml)，其拓扑已对齐当前链路：

`frontend -> backend -> gateway -> sandbox`，并包含 MongoDB/Redis。
