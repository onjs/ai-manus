# AI Manus

AI Manus 是一个 Web + Sandbox 自动化系统，Agent 运行时通过 Gateway 统一出模。

当前执行链路：

`Frontend -> Backend -> Sandbox Runner -> Gateway -> Model`

## 核心服务

- `frontend`：前端界面（会话列表、时间线、工具视图、noVNC）
- `backend`：会话 API、SSE 输出、MongoDB/Redis 持久化与状态、沙箱编排
- `gateway`：唯一 LLM 出口（OpenAI 兼容 `/v1/chat/completions`）
- `sandbox`：Agent loop 与工具运行时（browser/file/shell/search/mcp/message）
- `mongodb`、`redis`：存储与流状态

## 快速启动

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 至少配置以下参数：

- `GATEWAY_API_KEY`
- `GATEWAY_INTERNAL_API_KEY`
- `GATEWAY_REDIS_URL`
- `SANDBOX_INTERNAL_API_KEY`
- `API_BASE`
- `API_KEY`
- `JWT_SECRET_KEY`

3. 开发模式启动：

```bash
docker compose -f scripts/docker-compose-development.yml up -d --build
```

### Sandbox 增量构建（推荐）

生产部署建议将 Sandbox 拆成两层镜像：

- `base`：系统依赖（Chromium/字体/locale 等，变更频率低）
- `runtime`：应用代码（变更频率高）

首次或系统依赖变更时构建 `base`：

```bash
./scripts/build_sandbox_base.sh
```

日常仅改代码时构建 `runtime`：

```bash
./scripts/build_sandbox_runtime.sh
```

4. 访问地址：

- 前端：<http://localhost:5173>
- 后端：<http://localhost:8000>
- Gateway：<http://localhost:8100>
- Sandbox API：<http://localhost:8080>

## Compose 示例

可使用 [`scripts/docker-compose-example.yml`](./scripts/docker-compose-example.yml) 作为简化部署示例，已与当前架构保持一致。

## 文档

- 快速上手（中文）：[`docs/quick_start.md`](./docs/quick_start.md)
- Quick start (English): [`docs/en/quick_start.md`](./docs/en/quick_start.md)
- 配置说明（中文）：[`docs/configuration.md`](./docs/configuration.md)
- Configuration (English): [`docs/en/configuration.md`](./docs/en/configuration.md)
- MCP 文档（中文）：[`docs/mcp.md`](./docs/mcp.md)
- MCP docs (English): [`docs/en/mcp.md`](./docs/en/mcp.md)
