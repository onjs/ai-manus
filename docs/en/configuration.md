# Configuration Guide (Gateway + Sandbox Architecture)

This document reflects the current active path only: `frontend -> backend -> gateway -> sandbox`.

## Backend

| Key | Default | Required | Description |
|---|---|---|---|
| `GATEWAY_BASE_URL` | - | Yes | Gateway endpoint (for example `http://gateway:8100`) |
| `GATEWAY_API_KEY` | - | Yes | Internal key for backend -> gateway |
| `GATEWAY_TIMEOUT_SECONDS` | `300` | No | Backend-to-gateway timeout |
| `SANDBOX_INTERNAL_API_KEY` | - | Yes | Internal key for backend -> sandbox runtime API |
| `SANDBOX_ADDRESS` | - | No | Fixed sandbox address (single-sandbox mode) |
| `SANDBOX_IMAGE` | - | No | Sandbox image used in dynamic sandbox mode |
| `SANDBOX_NAME_PREFIX` | - | No | Dynamic sandbox container prefix |
| `SANDBOX_TTL_MINUTES` | `30` | No | Dynamic sandbox TTL |
| `SANDBOX_NETWORK` | - | No | Dynamic sandbox docker network |
| `SANDBOX_CHROME_ARGS` | - | No | Chrome args passed into sandbox |
| `SANDBOX_HTTPS_PROXY` | - | No | Sandbox HTTPS proxy |
| `SANDBOX_HTTP_PROXY` | - | No | Sandbox HTTP proxy |
| `SANDBOX_NO_PROXY` | - | No | Sandbox NO_PROXY |
| `BROWSER_ENGINE` | `playwright` | No | Browser driver used when backend connects to sandbox CDP |
| `MONGODB_URI` | `mongodb://mongodb:27017` | No | MongoDB URI |
| `MONGODB_DATABASE` | `manus` | No | MongoDB database |
| `MONGODB_USERNAME` | - | No | MongoDB username |
| `MONGODB_PASSWORD` | - | No | MongoDB password |
| `REDIS_HOST` | `redis` | No | Redis host |
| `REDIS_PORT` | `6379` | No | Redis port |
| `REDIS_DB` | `0` | No | Redis database index |
| `REDIS_PASSWORD` | - | No | Redis password |
| `AUTH_PROVIDER` | `password` | No | Auth mode: `password` / `none` / `local` |
| `PASSWORD_SALT` | - | No | Password salt |
| `PASSWORD_HASH_ROUNDS` | `10` | No | Password hash rounds |
| `LOCAL_AUTH_EMAIL` | `admin@example.com` | No | Local-auth email |
| `LOCAL_AUTH_PASSWORD` | `admin` | No | Local-auth password |
| `JWT_SECRET_KEY` | - | Yes | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | No | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | No | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | No | Refresh token TTL |
| `EMAIL_HOST` | - | No | SMTP host |
| `EMAIL_PORT` | - | No | SMTP port |
| `EMAIL_USERNAME` | - | No | SMTP username |
| `EMAIL_PASSWORD` | - | No | SMTP password |
| `EMAIL_FROM` | - | No | Sender |
| `LOG_LEVEL` | `INFO` | No | Log level |

## Gateway

| Key | Default | Required | Description |
|---|---|---|---|
| `GATEWAY_INTERNAL_API_KEY` | - | Yes | Internal gateway key (issue/revoke/introspect routes) |
| `GATEWAY_TOKEN_ISSUER_SECRET` | `dev-gateway-secret` | Yes | Secret used to sign gateway-issued tokens |
| `GATEWAY_JWT_ALGORITHM` | `HS256` | No | Gateway JWT algorithm |
| `GATEWAY_TOKEN_TTL_SECONDS` | `1800` | No | Issued token TTL for sandbox runtime |
| `GATEWAY_REDIS_URL` | - | No | Token state store (falls back to in-process when empty) |
| `GATEWAY_REDIS_PREFIX` | `gw` | No | Token state prefix |
| `API_BASE` | - | Yes | Upstream OpenAI-compatible endpoint |
| `API_KEY` | - | No | Upstream model API key |
| `MODEL_NAME` | `gpt-4o-mini` | No | Default model name |
| `MODEL_PROVIDER` | `openai` | No | Provider label (currently OpenAI-compatible flow) |
| `TEMPERATURE` | `0.7` | No | Default temperature |
| `MAX_TOKENS` | `2000` | No | Default max tokens |
| `EXTRA_HEADERS` | - | No | Extra upstream headers (JSON) |
| `GATEWAY_TIMEOUT_SECONDS` | `120` | No | Gateway-to-upstream timeout |
| `LOG_LEVEL` | `INFO` | No | Log level |

## Sandbox

| Key | Default | Required | Description |
|---|---|---|---|
| `SANDBOX_INTERNAL_API_KEY` | - | Yes | Internal key for sandbox runtime API |
| `RUNTIME_DB_PATH` | `/tmp/sandbox_runtime.db` | No | Local runtime store path |
| `SEARCH_PROVIDER` | `duckduckgo` | No | Search provider for sandbox tools |
| `BING_SEARCH_API_KEY` | - | No | Bing key (optional) |
| `GOOGLE_SEARCH_API_KEY` | - | No | Google key (optional) |
| `GOOGLE_SEARCH_ENGINE_ID` | - | No | Google CSE ID (optional) |
| `TAVILY_API_KEY` | - | No | Tavily key (optional) |
| `MCP_CONFIG_PATH` | `/etc/mcp.json` | No | MCP config path |
| `MODEL_NAME` | `gpt-4o` | No | Default model name for sandbox agent |
| `MODEL_PROVIDER` | `openai` | No | Model provider for sandbox agent |
| `TEMPERATURE` | `0.7` | No | Default temperature for sandbox agent |
| `MAX_TOKENS` | `2000` | No | Default max tokens for sandbox agent |
| `AGENT_MODEL_MAX_ITERATIONS` | `100` | No | Per-step model iteration cap |
| `AGENT_MODEL_MAX_RETRIES` | `3` | No | Model retry limit |
| `AGENT_MODEL_RETRY_INTERVAL_SECONDS` | `1.0` | No | Model retry interval |
| `AGENT_LOOP_MAX_ROUNDS` | `40` | No | Agent loop round cap |
| `AGENT_LOOP_TIMEOUT_SECONDS` | `1800` | No | Agent loop timeout |
| `SERVICE_TIMEOUT_MINUTES` | - | No | Sandbox service timeout |
| `LOG_LEVEL` | `INFO` | No | Log level |
