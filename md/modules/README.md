# 模块设计文档目录

## 当前决策
- 核心数据关系（冻结）：
  - `tenant 1:n users`
  - `tenant 1:n groups`
  - `group 1:n agents`
  - `agent 1:n task_definitions`（MVP 默认每个 agent 至少 1 个默认任务定义）
  - `task_definition 1:n task_schedules`
  - `task_schedule 1:n sessions`
  - `session 1:n events/artifacts`
  - `user n:m agents`（通过 `agent_permissions` 授权）
- 记忆/上下文层：先复用 `Mongo + Redis`。
- 调度执行层：采用 `Worker Beat + API内置执行器`，业务层保留 `pending`。
- 调度闭环：`Reconciler 对账恢复 + 幂等键 + 并发令牌`。
- 记忆结构：复用 ai-manus `planner + execution` 双层记忆。
- 浏览器上下文：默认剪裁文本入 LLM，截图/大块 DOM 只做回放与审计引用。
- 暂不引入 Mem0 作为主存储；后续可作为辅助经验层评估。

## 模块清单
- [01-agent-management.md](/Users/zuos/code/github/ai-manus/md/modules/01-agent-management.md)
- [02-context-memory.md](/Users/zuos/code/github/ai-manus/md/modules/02-context-memory.md)
- [03-tools-sandbox.md](/Users/zuos/code/github/ai-manus/md/modules/03-tools-sandbox.md)
- [04-scheduler-queue.md](/Users/zuos/code/github/ai-manus/md/modules/04-scheduler-queue.md)
- [05-observability-alerting.md](/Users/zuos/code/github/ai-manus/md/modules/05-observability-alerting.md)
- [06-platform-management.md](/Users/zuos/code/github/ai-manus/md/modules/06-platform-management.md)
- [07-config-release-rollback.md](/Users/zuos/code/github/ai-manus/md/modules/07-config-release-rollback.md)
- [08-skills-tool-runtime.md](/Users/zuos/code/github/ai-manus/md/modules/08-skills-tool-runtime.md)
- [15-deployment-topology.md](/Users/zuos/code/github/ai-manus/md/modules/15-deployment-topology.md)
- [16-realtime-sse-retrofit-checklist.md](/Users/zuos/code/github/ai-manus/md/modules/16-realtime-sse-retrofit-checklist.md)
- [17-browser-engine.md](/Users/zuos/code/github/ai-manus/md/modules/17-browser-engine.md)
- [18-gateway-llm-proxy.md](/Users/zuos/code/github/ai-manus/md/modules/18-gateway-llm-proxy.md)
- [19-gateway-sandbox-agent-code-map.md](/Users/zuos/code/github/ai-manus/md/modules/19-gateway-sandbox-agent-code-map.md)
- [20-sandbox-agent-gateway-risk-register.md](/Users/zuos/code/github/ai-manus/md/modules/20-sandbox-agent-gateway-risk-register.md)
- [21-runtime-event-protocol.md](/Users/zuos/code/github/ai-manus/md/modules/21-runtime-event-protocol.md)

## 单独稿目录
- [api-schema/README.md](/Users/zuos/code/github/ai-manus/md/modules/api-schema/README.md)
- [dev-tasks/README.md](/Users/zuos/code/github/ai-manus/md/modules/dev-tasks/README.md)

## 方案补充
- [agent-loop-plan-exec-solution-zh.md](/Users/zuos/code/github/ai-manus/md/agent-loop-plan-exec-solution-zh.md)
- [agent-loop-plan-exec-implementation-tasks-zh.md](/Users/zuos/code/github/ai-manus/md/agent-loop-plan-exec-implementation-tasks-zh.md)
- [m1-data-event-design-zh.md](/Users/zuos/code/github/ai-manus/md/m1-data-event-design-zh.md)
- [m2-plan-step-execution-design-zh.md](/Users/zuos/code/github/ai-manus/md/m2-plan-step-execution-design-zh.md)
- [m3-protection-failure-governance-design-zh.md](/Users/zuos/code/github/ai-manus/md/m3-protection-failure-governance-design-zh.md)
- [09-error-code-dictionary.md](/Users/zuos/code/github/ai-manus/md/modules/09-error-code-dictionary.md)
- [10-db-migration-backfill-plan.md](/Users/zuos/code/github/ai-manus/md/modules/10-db-migration-backfill-plan.md)
- [11-api-contract-examples.md](/Users/zuos/code/github/ai-manus/md/modules/11-api-contract-examples.md)
- [12-integration-regression-matrix.md](/Users/zuos/code/github/ai-manus/md/modules/12-integration-regression-matrix.md)
- [13-release-rollback-runbook.md](/Users/zuos/code/github/ai-manus/md/modules/13-release-rollback-runbook.md)
- [14-execution-items-plan.md](/Users/zuos/code/github/ai-manus/md/modules/14-execution-items-plan.md)
- [ops/README.md](/Users/zuos/code/github/ai-manus/md/modules/ops/README.md)

## 状态
- `01`、`02`、`03`、`04`：已冻结（以主文档为准）。
- `05`：已冻结。
- `06`：已冻结。
- `07`：已冻结。
- `08`：已冻结并已转开发任务清单。
- `17`：待评审。
- `18`：已冻结（gateway+sandbox+runner 集成范围）。
- `21`：已冻结（统一事件协议与字段级对照）。

## 剩余推进顺序（当前冻结执行序）
1. `P0 基线补齐`：
- 补齐 `backend/.env.example`、`sandbox/.env.example`、`scripts/docker-compose-development.yml` 的 `gateway` 服务段。
- 固化 `token issue/revoke` 的 Redis key 规范与失效策略。
2. `P1 Gateway 完整闭环`：
- 完成 `ask/stream/batch/embeddings + issue/revoke/introspect`。
- 完成路由/策略/配额/熔断/审计全链能力。
- runner 仅通过 `GATEWAY_BASE_URL + GATEWAY_TOKEN` 推理，禁止直连模型厂商。
3. `P2 Provider + Runner 联调`：
- 控制面经 `ProviderManager` 创建 env 并注入 gateway 地址与短时 token。
- env 内 runner 上报心跳、事件流、结束态，完成 `trigger -> session -> api_executor -> sandbox` 闭环。
4. `P3 实时与转发链路`：
- 打通 `api_executor -> mongo(session_events) -> api -> SSE` 链路。
- 打通 `session_id -> sandbox_ws_target` 共享映射，确保多 API 副本下 noVNC 可路由。
5. `P4 验收与灰度`：
- 完成安全验收（进程级 egress、无明文 key）、压测、回滚演练。
- 通过门禁后再进入多 Agent 自动巡检功能开发。
