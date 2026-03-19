# 18 Gateway 模块 API Schema 设计稿（Full）

## 范围
- 作为 runner 的唯一 LLM 出口。
- 覆盖推理代理、token 治理、策略治理、配额治理、路由治理、审计与运维接口。

## 统一响应
- 非流式：`APIResponse{code,msg,data}`
- 流式：SSE 事件流（`event/data/id`）

## 访问边界
1. `/internal/*` 仅内网可访问（runner/api/ops）。
2. `/admin/*` 仅平台管理面可访问（platform_admin）。
3. 所有请求带 `X-Trace-Id`（缺失则 gateway 生成）。

## 1. Internal 接口

## 1.1 Token
1. `POST /internal/v1/token/issue`
- 入参：`tenant_id, session_id, env_id, run_id, agent_id, ttl_seconds, scopes[]`
- 出参：`token, token_id, expire_at, scopes`

2. `POST /internal/v1/token/revoke`
- 入参：`token_id|token, reason`
- 出参：`revoked, token_id`

3. `POST /internal/v1/token/introspect`
- 入参：`token|token_id`
- 出参：`active, claims, revoked, expire_at`

## 1.2 推理
1. `POST /internal/v1/llm/ask`
- 入参：`token, messages[], model_hint, response_format, parameters, metadata`
- 出参：`request_id, answer, usage, route, latency_ms, policy_result`

2. `POST /internal/v1/llm/stream`
- 入参同 ask
- 出参（SSE）：`delta, route, usage, done, error`

3. `POST /internal/v1/llm/batch`
- 入参：`token, requests[]`
- 出参：`batch_id, results[], usage_total, route_summary`

4. `POST /internal/v1/llm/embeddings`
- 入参：`token, input, model_hint`
- 出参：`request_id, vectors_ref|vectors, usage, route`

## 1.3 策略试运行
1. `POST /internal/v1/policy/evaluate`
- 入参：`token, payload, policy_profile`
- 出参：`decision(allow|deny|redact), matched_rules[], normalized_payload`

## 1.4 健康与就绪
1. `GET /internal/v1/gateway/health`
- 出参：`status, dependencies, uptime`
2. `GET /internal/v1/gateway/ready`
- 出参：`ready, checks[]`
3. `GET /internal/v1/gateway/config/hash`
- 出参：`route_hash, policy_hash, keyring_version`

## 2. Admin 接口（完整治理）

## 2.1 路由配置
1. `GET /admin/v1/routes`
2. `PUT /admin/v1/routes/{route_id}`
3. `POST /admin/v1/routes/validate`

## 2.2 策略配置
1. `GET /admin/v1/policies`
2. `PUT /admin/v1/policies/{policy_id}`
3. `POST /admin/v1/policies/test`

## 2.3 配额与限流
1. `GET /admin/v1/quotas/{tenant_id}`
2. `PUT /admin/v1/quotas/{tenant_id}`
3. `POST /admin/v1/quotas/{tenant_id}/reset`

## 2.4 密钥与模型档案
1. `POST /admin/v1/keys/rotate`
2. `POST /admin/v1/model-profiles/{profile_id}/activate`
3. `POST /admin/v1/model-profiles/{profile_id}/deactivate`

## 2.5 审计与用量
1. `GET /admin/v1/audit-logs`
2. `GET /admin/v1/usage/tenants/{tenant_id}`
3. `GET /admin/v1/usage/sessions/{session_id}`

## 3. Token Claims
- `iss, sub, jti, iat, exp`
- `tenant_id, session_id, env_id, run_id, agent_id`
- `scopes[]`
- `route_profile, policy_profile`

## 4. 路由与策略契约
1. 路由输入：`tenant_id, agent_id, model_hint, goal_type, cost_tier, sla_tier`
2. 路由输出：`provider, model, model_profile_id, fallback_chain[]`
3. 策略阶段：
- pre: 请求前校验与脱敏
- in: 速率/并发/熔断
- post: 输出脱敏与审计标注

## 5. 错误码（完整）
- 鉴权：`GATEWAY_TOKEN_INVALID|EXPIRED|REVOKED|SCOPE_DENIED|TENANT_MISMATCH`
- 策略：`GATEWAY_POLICY_BLOCKED|POLICY_ENGINE_UNAVAILABLE`
- 治理：`GATEWAY_RATE_LIMITED|QUOTA_EXCEEDED|CIRCUIT_OPEN`
- 路由：`GATEWAY_ROUTE_NOT_FOUND|PROVIDER_UNAVAILABLE|UPSTREAM_TIMEOUT`
- 系统：`GATEWAY_INTERNAL_ERROR|CONFIG_INVALID|DEPENDENCY_UNHEALTHY`

## 6. 审计与观测
1. 审计动作
- `gateway.token.issue/revoke/introspect`
- `gateway.llm.ask/stream/batch/embeddings`
- `gateway.policy.allow/deny/redact`
- `gateway.route.selected/fallback`
- `gateway.quota.exceeded`

2. 指标
- `gateway_requests_total{api,status,provider,model}`
- `gateway_latency_ms_bucket{api,provider,model}`
- `gateway_rate_limited_total{tenant_id,scope}`
- `gateway_policy_blocked_total{rule}`
- `gateway_route_fallback_total{route_id}`
- `gateway_token_revoke_propagation_ms_bucket`

## 7. 与模块契约
1. `04`：`trigger/session/run_id` 必须映射 token claims
2. `03`：sandbox 重建必须重新签发 token
3. `01`：`model_profile_id` 来源于 agent 配置
4. `16`：gateway 不直接推 SSE，事件由 api 执行器统一落库推送
