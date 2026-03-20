# AI Manus

AI Manus is a web + sandbox automation system with a gateway-routed agent runtime.

Current execution path:

`Frontend -> Backend -> Sandbox Runner -> Gateway -> Model`

## Core Services

- `frontend`: UI (session list, timeline, tool views, noVNC)
- `backend`: session API, SSE output, persistence (MongoDB/Redis), sandbox orchestration
- `gateway`: the only LLM egress (OpenAI-compatible `/v1/chat/completions`)
- `sandbox`: agent loop + tools runtime (browser/file/shell/search/mcp/message)
- `mongodb`, `redis`: storage and streaming state

## Quick Start

1. Copy env template:

```bash
cp .env.example .env
```

2. Set required keys:

- `GATEWAY_API_KEY`
- `GATEWAY_INTERNAL_API_KEY`
- `GATEWAY_REDIS_URL`
- `SANDBOX_INTERNAL_API_KEY`
- `API_BASE`
- `API_KEY`
- `JWT_SECRET_KEY`

3. Start in development:

```bash
docker compose -f scripts/docker-compose-development.yml up -d --build
```

### Incremental Sandbox Build (Recommended)

For production, split Sandbox into two image layers:

- `base`: system dependencies (Chromium/fonts/locale, low change frequency)
- `runtime`: application code (high change frequency)

Build `base` only when system dependencies change:

```bash
./scripts/build_sandbox_base.sh
```

Build `runtime` for normal code changes:

```bash
./scripts/build_sandbox_runtime.sh
```

4. Access:

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>
- Gateway: <http://localhost:8100>
- Sandbox API: <http://localhost:8080>

## Compose Example

Use [`scripts/docker-compose-example.yml`](./scripts/docker-compose-example.yml) for a simplified topology aligned to the current architecture.

## Docs

- Chinese quick start: [`docs/quick_start.md`](./docs/quick_start.md)
- English quick start: [`docs/en/quick_start.md`](./docs/en/quick_start.md)
- Chinese configuration: [`docs/configuration.md`](./docs/configuration.md)
- English configuration: [`docs/en/configuration.md`](./docs/en/configuration.md)
- MCP guide (CN): [`docs/mcp.md`](./docs/mcp.md)
- MCP guide (EN): [`docs/en/mcp.md`](./docs/en/mcp.md)
