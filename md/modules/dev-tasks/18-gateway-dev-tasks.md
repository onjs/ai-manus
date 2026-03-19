# 18 Gateway 模块 开发任务清单（Full，含 G0/G1/G2 文件级拆解）

## 约束
1. 仅推进 `sandbox + runner + gateway` 主链路。
2. 不改前端协议。
3. gateway 为独立服务，目录固定在 `/Users/zuos/code/github/ai-manus/gateway`。

## G0 基础工程（文件级）

## G0.1 目录与工程脚手架
1. 新增目录：
- `/Users/zuos/code/github/ai-manus/gateway/app/core`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/api`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/schemas`
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/repositories`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/providers`
- `/Users/zuos/code/github/ai-manus/gateway/tests`

2. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/pyproject.toml`
- `/Users/zuos/code/github/ai-manus/gateway/Dockerfile`
- `/Users/zuos/code/github/ai-manus/gateway/app/main.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/core/config.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/core/logging.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/core/middleware.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/api/routes.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/schemas/response.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_health.py`

3. 依赖建议：
- `fastapi`, `uvicorn`, `pydantic-settings`
- `redis`, `pymongo`
- `httpx`（上游模型调用）
- `python-jose` 或 `pyjwt`（token）
- `prometheus-client`

## G0.2 编排与配置接入
1. 更新：
- `/Users/zuos/code/github/ai-manus/docker-compose-development.yml`
- `/Users/zuos/code/github/ai-manus/.env.example`
- `/Users/zuos/code/github/ai-manus/backend/.env.example`
- `/Users/zuos/code/github/ai-manus/sandbox/.env.example`

2. 关键配置项：
- `GATEWAY_INTERNAL_BASE_URL`
- `GATEWAY_TOKEN_ISSUER_SECRET`
- `GATEWAY_TOKEN_TTL_SECONDS`
- `GATEWAY_TOKEN_REFRESH_THRESHOLD_SECONDS`
- `GATEWAY_REDIS_PREFIX`
- `GATEWAY_MONGO_DATABASE`

## G0.3 基础接口与探针
1. 实现：
- `GET /internal/v1/gateway/health`
- `GET /internal/v1/gateway/ready`
- `GET /internal/v1/gateway/config/hash`

2. 测试：
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_health.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_ready.py`

验收：
- gateway 独立容器可启动。
- health/ready/hash 接口可用。

## G1 鉴权与 Token 全生命周期（文件级）

## G1.1 Schema 与路由
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/schemas/token.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/api/internal_token_routes.py`

2. 接口：
- `POST /internal/v1/token/issue`
- `POST /internal/v1/token/revoke`
- `POST /internal/v1/token/introspect`

## G1.2 服务层
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/token_service.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/token_validator.py`

2. 能力：
- claims 生成：`tenant/session/env/run/agent/scopes/jti`
- 签名与过期校验
- revoke 校验优先于 exp 校验
- 续签策略（阈值触发）

## G1.3 存储层
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/repositories/token_state_repository.py`

2. Redis 键：
- `gw:token:active:{jti}`
- `gw:token:revoked:{jti}`

## G1.4 中间件
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/core/auth_middleware.py`

2. 行为：
- internal 路由统一鉴权
- scope 校验
- trace_id 透传

## G1.5 测试
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_token_issue.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_token_revoke.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_token_introspect.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_scope_guard.py`

2. 覆盖场景：
- 正常签发/校验/吊销
- 过期 token 拒绝
- 跨 run/env token 拒绝
- 吊销后跨副本立即失效

验收：
- token 生命周期完整闭环。
- revoke 实时生效，无“已吊销可用”窗口。

## G2 推理接口全量能力（文件级）

## G2.1 Schema 与路由
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/schemas/llm.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/interfaces/api/internal_llm_routes.py`

2. 接口：
- `POST /internal/v1/llm/ask`
- `POST /internal/v1/llm/stream`
- `POST /internal/v1/llm/batch`
- `POST /internal/v1/llm/embeddings`

## G2.2 服务层
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/llm_proxy_service.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/stream_service.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/idempotency_service.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/application/services/usage_service.py`

2. 行为：
- ask/stream/batch/embeddings 统一入口
- request_id 幂等
- 上游取消传播（runner 断开即取消）
- latency/usage/route/policy 结构化输出

## G2.3 Provider 适配层
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/providers/base_provider.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/providers/openai_provider.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/providers/anthropic_provider.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/providers/deepseek_provider.py`

2. 目标：
- 统一 provider 适配接口
- 支持流式与非流式
- 标准化错误码映射

## G2.4 审计与请求落库
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/repositories/gateway_request_repository.py`
- `/Users/zuos/code/github/ai-manus/gateway/app/infrastructure/repositories/audit_repository.py`

2. 集合：
- `llm_gateway_requests`
- `gateway_route_decisions`
- `gateway_policy_hits`

## G2.5 测试
1. 新增文件：
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_llm_ask.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_llm_stream.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_llm_batch.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_llm_embeddings.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_idempotency.py`
- `/Users/zuos/code/github/ai-manus/gateway/tests/test_upstream_cancel.py`

2. 覆盖场景：
- 多 provider 正常响应
- 上游超时/断流/5xx
- stream 中断恢复
- 幂等重复请求不重复记账

验收：
- 四类推理接口可用。
- 输出字段与 schema 一致。
- 高并发下稳定。

## 建议提交切分
1. `feat(gateway): scaffold + health/ready/hash`
2. `feat(gateway): token lifecycle (issue/revoke/introspect)`
3. `feat(gateway): llm ask/stream/batch/embeddings`
4. `feat(gateway): provider adapters + request audit`
5. `test(gateway): token and llm integration suite`

## 开发完成门禁（G0-G2）
1. 所有 gateway 单测通过。
2. 与 sandbox runner 联调通过：
- issue -> ask/stream -> revoke。
3. 关键指标可见：
- `gateway_requests_total`
- `gateway_latency_ms_bucket`
- `gateway_token_revoke_propagation_ms_bucket`
