# 🚀 Quick Start

## Prerequisites

- Docker 20.10+
- Docker Compose

## Boot in Development Mode (recommended)

1. Copy env template:

```bash
cp .env.example .env
```

2. At minimum, set:

- `GATEWAY_API_KEY`
- `GATEWAY_INTERNAL_API_KEY`
- `SANDBOX_INTERNAL_API_KEY`
- `API_BASE`
- `API_KEY`
- `JWT_SECRET_KEY`

3. Start services:

```bash
docker compose -f docker-compose-development.yml up -d --build
```

4. Access endpoints:

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Gateway: <http://localhost:8100>
- Sandbox API: <http://localhost:8080>

## Production/Simplified Compose Example

Use [`docker-compose-example.yml`](../docker-compose-example.yml) in repository root. It is aligned with the current flow:

`frontend -> backend -> gateway -> sandbox` with MongoDB/Redis.
