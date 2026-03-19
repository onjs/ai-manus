# 配置说明（Gateway + Sandbox 架构）

本文档仅描述当前生效配置：`frontend -> backend -> gateway -> sandbox`。

## Backend

| 配置项 | 默认值 | 必需 | 说明 |
|---|---|---|---|
| `GATEWAY_BASE_URL` | - | 是 | Gateway 地址（如 `http://gateway:8100`） |
| `GATEWAY_API_KEY` | - | 是 | Backend 调用 Gateway 的内部密钥 |
| `GATEWAY_TIMEOUT_SECONDS` | `300` | 否 | Backend 到 Gateway 超时 |
| `SANDBOX_INTERNAL_API_KEY` | - | 是 | Backend 调用 Sandbox Runtime API 的内部密钥 |
| `SANDBOX_ADDRESS` | - | 否 | 固定 sandbox 地址（单沙箱模式） |
| `SANDBOX_IMAGE` | - | 否 | 动态创建沙箱容器时使用的镜像 |
| `SANDBOX_NAME_PREFIX` | - | 否 | 动态沙箱容器名前缀 |
| `SANDBOX_TTL_MINUTES` | `30` | 否 | 动态沙箱容器 TTL |
| `SANDBOX_NETWORK` | - | 否 | 动态沙箱容器网络 |
| `SANDBOX_CHROME_ARGS` | - | 否 | 传递给 sandbox chrome 参数 |
| `SANDBOX_HTTPS_PROXY` | - | 否 | sandbox HTTPS 代理 |
| `SANDBOX_HTTP_PROXY` | - | 否 | sandbox HTTP 代理 |
| `SANDBOX_NO_PROXY` | - | 否 | sandbox NO_PROXY |
| `BROWSER_ENGINE` | `playwright` | 否 | backend 连接 sandbox CDP 时使用的浏览器驱动 |
| `MONGODB_URI` | `mongodb://mongodb:27017` | 否 | MongoDB 连接串 |
| `MONGODB_DATABASE` | `manus` | 否 | MongoDB 库名 |
| `MONGODB_USERNAME` | - | 否 | MongoDB 用户名 |
| `MONGODB_PASSWORD` | - | 否 | MongoDB 密码 |
| `REDIS_HOST` | `redis` | 否 | Redis 地址 |
| `REDIS_PORT` | `6379` | 否 | Redis 端口 |
| `REDIS_DB` | `0` | 否 | Redis DB |
| `REDIS_PASSWORD` | - | 否 | Redis 密码 |
| `AUTH_PROVIDER` | `password` | 否 | 认证模式：`password` / `none` / `local` |
| `PASSWORD_SALT` | - | 否 | 密码加盐 |
| `PASSWORD_HASH_ROUNDS` | `10` | 否 | 密码哈希轮数 |
| `LOCAL_AUTH_EMAIL` | `admin@example.com` | 否 | 本地认证邮箱 |
| `LOCAL_AUTH_PASSWORD` | `admin` | 否 | 本地认证密码 |
| `JWT_SECRET_KEY` | - | 是 | JWT 密钥 |
| `JWT_ALGORITHM` | `HS256` | 否 | JWT 算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 否 | Access Token 过期时间 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | 否 | Refresh Token 过期时间 |
| `EMAIL_HOST` | - | 否 | SMTP 主机 |
| `EMAIL_PORT` | - | 否 | SMTP 端口 |
| `EMAIL_USERNAME` | - | 否 | SMTP 用户名 |
| `EMAIL_PASSWORD` | - | 否 | SMTP 密码 |
| `EMAIL_FROM` | - | 否 | 发件人 |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别 |

## Gateway

| 配置项 | 默认值 | 必需 | 说明 |
|---|---|---|---|
| `GATEWAY_INTERNAL_API_KEY` | - | 是 | Gateway 内部调用密钥（用于 issue/revoke/introspect 等） |
| `GATEWAY_TOKEN_ISSUER_SECRET` | `dev-gateway-secret` | 是 | Gateway 签发 token 的密钥 |
| `GATEWAY_JWT_ALGORITHM` | `HS256` | 否 | Gateway JWT 算法 |
| `GATEWAY_TOKEN_TTL_SECONDS` | `1800` | 否 | 下发给 sandbox 的 token TTL |
| `GATEWAY_REDIS_URL` | - | 否 | token 状态存储（未配置时使用进程内） |
| `GATEWAY_REDIS_PREFIX` | `gw` | 否 | token 状态前缀 |
| `API_BASE` | - | 是 | 上游 OpenAI 兼容接口地址 |
| `API_KEY` | - | 否 | 上游模型 API Key |
| `MODEL_NAME` | `gpt-4o-mini` | 否 | 默认模型名 |
| `MODEL_PROVIDER` | `openai` | 否 | 提供商标识（当前走 OpenAI 兼容协议） |
| `TEMPERATURE` | `0.7` | 否 | 默认温度 |
| `MAX_TOKENS` | `2000` | 否 | 默认 max tokens |
| `EXTRA_HEADERS` | - | 否 | 上游请求附加 Header（JSON） |
| `GATEWAY_TIMEOUT_SECONDS` | `120` | 否 | Gateway 到上游超时 |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别 |

## Sandbox

| 配置项 | 默认值 | 必需 | 说明 |
|---|---|---|---|
| `SANDBOX_INTERNAL_API_KEY` | - | 是 | Sandbox Runtime API 内部密钥 |
| `RUNTIME_DB_PATH` | `/tmp/sandbox_runtime.db` | 否 | sandbox 本地运行时存储 |
| `SEARCH_PROVIDER` | `duckduckgo` | 否 | sandbox 搜索工具提供商 |
| `BING_SEARCH_API_KEY` | - | 否 | Bing API Key（按需） |
| `GOOGLE_SEARCH_API_KEY` | - | 否 | Google API Key（按需） |
| `GOOGLE_SEARCH_ENGINE_ID` | - | 否 | Google CSE ID（按需） |
| `TAVILY_API_KEY` | - | 否 | Tavily API Key（按需） |
| `MCP_CONFIG_PATH` | `/etc/mcp.json` | 否 | MCP 配置文件 |
| `MODEL_NAME` | `gpt-4o` | 否 | sandbox agent 默认模型名 |
| `MODEL_PROVIDER` | `openai` | 否 | sandbox agent 模型提供商 |
| `TEMPERATURE` | `0.7` | 否 | sandbox agent 默认温度 |
| `MAX_TOKENS` | `2000` | 否 | sandbox agent 默认 max tokens |
| `AGENT_MODEL_MAX_ITERATIONS` | `100` | 否 | 单轮模型迭代上限 |
| `AGENT_MODEL_MAX_RETRIES` | `3` | 否 | 模型重试次数 |
| `AGENT_MODEL_RETRY_INTERVAL_SECONDS` | `1.0` | 否 | 模型重试间隔 |
| `AGENT_LOOP_MAX_ROUNDS` | `40` | 否 | Agent loop 轮次上限 |
| `AGENT_LOOP_TIMEOUT_SECONDS` | `1800` | 否 | Agent loop 超时 |
| `SERVICE_TIMEOUT_MINUTES` | - | 否 | sandbox 服务级超时 |
| `LOG_LEVEL` | `INFO` | 否 | 日志级别 |
