# 18 Gateway 与 Sandbox 集成模块

## 状态
- 已冻结（Full v1，非 MVP）。

## 目标
- 建设完整 Gateway：不仅代理推理，还承担鉴权、策略、配额、路由、审计、观测、运维治理。
- 在不改前端协议前提下，保证 runner 全量推理调用经 gateway。
- 保持 sandbox 浏览器可访问业务站点，同时严格限制 runner 出网。

## 范围（完整能力）
1. 推理能力
- 非流式、流式、批量推理、嵌入请求。
2. 鉴权能力
- 短时 token 签发/吊销/校验/自检。
3. 路由能力
- 多模型路由、降级链、回退策略、成本与 SLA 策略。
4. 策略能力
- 请求前/中/后策略检查（合规、敏感信息、动作黑白名单）。
5. 治理能力
- 多维限流、熔断、重试预算、幂等。
6. 运维能力
- 健康检查、就绪检查、指标、配置哈希与热更新审计。
7. 审计能力
- 全链路审计与请求留痕，支持按 tenant/session/run 追溯。

## 核心决策
1. runner 在 sandbox 内执行，LLM 调用强制经 gateway。
2. gateway 地址动态下发，不允许会话内容覆盖。
3. token 与 run/env 强绑定，run 结束立即吊销。
4. 网络策略按进程区分：
- 浏览器进程允许外网业务站点。
- runner/脚本仅允许访问 gateway 与必要内部地址。

## 完整运行时配置下发（冻结）
创建 sandbox 注入：
- `GATEWAY_BASE_URL`
- `GATEWAY_TOKEN`
- `GATEWAY_TOKEN_EXPIRE_AT`
- `GATEWAY_TOKEN_SCOPES`
- `GATEWAY_ROUTE_PROFILE`
- `GATEWAY_POLICY_PROFILE`

限制：
- runner 只读以上配置。
- 会话消息不得覆盖 gateway 地址、策略或路由配置。
- sandbox 重建必须重新下发地址与 token。

## Token 生命周期（完整）
1. 签发：api 执行器调用 `POST /v1/token/issue`（携带 `X-Internal-Key`）
2. 续签：长任务在有效期阈值前滚动续签（无缝替换）
3. 吊销：run 完成/取消/超时/风控触发即吊销
4. 自检：api 可调用 `POST /v1/token/introspect` 校验 token 状态（内部接口）
5. 约束：token 必须绑定 `tenant_id/env_id/run_id/agent_id/scopes`

## 完整可靠性设计
1. 高可用
- gateway 无状态多副本，前置负载均衡。
2. 一致性
- revoke 以 Redis/Mongo 一致视图为准，避免节点间接受差异。
3. 幂等
- `request_id` + `run_id` 幂等防重，防止重放。
4. 失败治理
- 上游超时预算、退避重试、熔断窗口、降级模型链。
5. 背压
- per tenant/env/run 多级限流 + 队列水位告警。

## 安全与合规（完整）
1. 零密钥暴露
- sandbox/runner 永不持有厂商 API Key 明文。
2. 加密
- API key 仅 gateway 解密使用（KMS/主密钥托管）。
3. 通信
- 内部接口 `X-Internal-Key` 校验，推荐 mTLS。
4. 脱敏
- 请求日志/异常栈/审计日志默认脱敏。
5. 可追溯
- 每次策略命中、路由决策、限流拒绝都可追溯。

## 开工前必须补齐文件
1. `backend/.env.example`
- `GATEWAY_BASE_URL`
- `GATEWAY_API_KEY`
- `SANDBOX_INTERNAL_API_KEY`
2. `sandbox/.env.example`
- `SANDBOX_INTERNAL_API_KEY`
3. `gateway/.env.example`
- `GATEWAY_INTERNAL_API_KEY`
- `GATEWAY_TOKEN_ISSUER_SECRET`
- `GATEWAY_TOKEN_TTL_SECONDS`
3. `scripts/docker-compose-development.yml`
- 新增 `gateway` 服务与健康检查、内部网络隔离、资源限制
4. 运维文档
- egress 策略、token 生命周期、密钥轮换、策略变更审计流程

## 完整验收标准
1. runner 不可直连模型厂商域名。
2. token 过期/吊销立即生效，无跨节点接受差异。
3. 流式与非流式在高并发下均满足延迟和错误率指标。
4. 路由降级可自动生效并有审计记录。
5. 策略拦截、限流、熔断均可观测可追溯。
6. sandbox 重建后可无缝继续会话（新 token + 新地址）。
7. 不影响前端会话/SSE/noVNC 协议兼容性。

## 关联文档
- [18-gateway-api-schema.md](/Users/zuos/code/github/ai-manus/md/modules/api-schema/18-gateway-api-schema.md)
- [18-gateway-dev-tasks.md](/Users/zuos/code/github/ai-manus/md/modules/dev-tasks/18-gateway-dev-tasks.md)
- [provider_md.md](/Users/zuos/code/github/ai-manus/md/provider_md.md)
