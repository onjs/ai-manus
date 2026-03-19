# 05 观测与告警模块（已冻结）

## 范围
- 覆盖 `调度 -> 队列 -> 执行 -> 工具 -> 事件流 -> 回放` 的全链路可观测。
- 对齐我们已确认的执行语义：
  - `每次自动运行 = 一个 session`
  - 串行 step
  - step 失败即终止 run
  - 无自动恢复/重试（跨调度周期）

## 目标
- 让任何一条异常会话都能在 5 分钟内定位到根因层（调度/执行/工具/sandbox）。
- 告警不打扰但不漏报：高风险故障必须及时升级，噪声告警有抑制。
- 给租户、业务组、Agent 三个层级提供统一观测面板。

## 1. 观测维度设计

## 1.1 指标（Metrics）
- 调度层：
  - `beat_tick_latency_ms`
  - `beat_due_count`
  - `beat_emit_count`
  - `beat_miss_count`
  - `beat_lag_seconds_p50/p95/p99`
- 队列层：
  - `trigger_pending_count_total`
  - `trigger_pending_count_by_tenant`
  - `trigger_pending_wait_time_ms_p50/p95/p99`
  - `dispatch_rejected_by_concurrency_count`
  - `reconciler_repair_count`
- 执行层（session/run）：
  - `run_started_count`
  - `run_completed_count`
  - `run_failed_count`
  - `run_waiting_count`
  - `run_duration_ms_p50/p95/p99`
  - `run_timeout_count`
  - `no_progress_break_count`
- step 层：
  - `step_started_count`
  - `step_completed_count`
  - `step_failed_count`
  - `step_duration_ms_p50/p95/p99`
  - `step_retry_total`
  - `step_retry_exhausted_count`
- 工具层：
  - `tool_call_count{tool_name}`
  - `tool_call_error_count{tool_name,error_code}`
  - `tool_call_latency_ms_p50/p95/p99{tool_name}`
  - `tool_loop_warning_count`
  - `tool_loop_critical_count`
- 回放/SSE 层：
  - `sse_global_active_connections`
  - `sse_session_active_connections`
  - `sse_global_emit_rate`
  - `sse_session_emit_rate`
  - `sse_emit_error_count`
  - `sse_push_lag_ms`
  - `event_delivery_lag_ms`
- sandbox 层：
  - `sandbox_create_count`
  - `sandbox_create_fail_count`
  - `sandbox_alive_count`
  - `sandbox_reconnect_count`
  - `sandbox_stream_lag_ms`

说明：
- 指标必须至少带标签：`tenant_id, group_id, agent_id, source_type`（无值时填 `unknown`）。

## 1.2 日志（Logs）
- 全部结构化日志，JSON 单行，核心字段：
  - `ts, level, service, env`
  - `tenant_id, group_id, agent_id, session_id, step_id`
  - `trace_id, span_id, task_id, task_schedule_id, trigger_id`
  - `action, status, error_code, error_message`
  - `cost_ms, retry_count`
- 脱敏规则：
  - token/cookie/password 一律打码或丢弃。
  - 用户输入正文默认截断（例如 2KB）并支持摘要替代。

## 1.3 链路追踪（Trace）
- 统一关联主键：
  - `trace_id`: 一次 run 全程不变
  - `span_id`: 每个 step/tool 调用生成
  - `session_id`: 会话主实体
- 关联要求：
  - timeline 事件必须能反查到 trace/span。
  - 工具错误必须能回指到 step 与会话。

## 2. 告警策略（Alerting）

## 2.1 告警分级
- `P1`：全局不可用或大面积失败
  - 例如 run 失败率 5 分钟 > 40%，或 beat 停摆
- `P2`：核心能力降级
  - 例如队列积压持续超阈值，sandbox 创建失败率升高
- `P3`：局部异常/早期信号
  - 例如单 Agent 连续失败、单工具错误率升高

## 2.2 建议阈值（MVP）
- `run_failed_rate_5m > 30%` -> P2
- `trigger_pending_wait_p95 > 120s 持续 10m` -> P2
- `sandbox_create_fail_rate_5m > 20%` -> P1
- `sse_emit_error_count_5m > 100` -> P2
- `sse_push_lag_ms_p95 > 3000 持续 5m` -> P2
- `api_executor_heartbeat_missing > 90s` -> P1
- `beat_lag_seconds_p95 > 30s` -> P2
- `single_agent_fail_streak >= 5` -> P3

## 2.3 抖动抑制与升级
- 同类告警 10 分钟内去重聚合。
- P1 立即通知；P2 连续两次触发再升级；P3 仅工作时间通知。
- 告警恢复后发 `resolved` 事件，避免“黑洞”状态。

## 2.4 Sandbox+Agent+Gateway 风险映射告警（冻结）
| 风险ID | 告警名称 | 触发规则（MVP） | 等级 | 主责值班组 | 备用值班组 | 首个应急动作 |
|---|---|---|---|---|---|---|
| R-01 | `ALERT_RUNNER_DIRECT_PROVIDER_EGRESS` | `runner_direct_provider_egress_count > 0`（任意 1 次即触发） | P1 | Security | Runtime | 立即阻断 runner 出网策略并吊销当前 run token |
| R-02 | `ALERT_GATEWAY_REVOKED_TOKEN_ACCEPTED` | `gateway_token_revoked_but_accepted_count > 0` 或 `token_revoke_propagation_ms_p95 > 1000` 持续 5m | P1 | Gateway | Security | 临时下调 token TTL，并启用黑名单优先校验 |
| R-03 | `ALERT_GATEWAY_GLOBAL_DEGRADED` | `gateway_5xx_rate_5m > 5%` 或 `gateway_latency_ms_p95 > 3000` 持续 5m | P1 | Gateway | Runtime | 扩容 gateway 并开启降级路由，暂停低优先级 run |
| R-04 | `ALERT_RUN_PROGRESS_STALLED` | `run_no_progress_seconds > 60` 持续 3m 且 `step_duration_ms_p95` 超基线 30% | P2 | Runtime | Gateway | 切流式优先并下调单轮 token 上限 |
| R-05 | `ALERT_RUNNER_HEARTBEAT_LOST` | `runner_heartbeat_gap_seconds > 30` 或 `zombie_runner_count > 0` | P2 | Runtime | Scheduler | supervisor 强制拉起/kill，回收并发令牌 |
| R-06 | `ALERT_SECRET_LEAK_DETECTED` | `secret_leak_detected_count > 0` | P1 | Security | Gateway | 立即轮换泄露 key，下线问题实例并封存证据 |
| R-07 | `ALERT_EXECUTION_COMPAT_REGRESSION` | `session_event_schema_error_count > 0` 或回归用例失败率 > 0 | P2 | Runtime | QA | 立即切回 `legacy` 执行开关并冻结灰度 |

## 3. 仪表盘视图
- 平台总览：
  - 总运行数、成功率、失败率、队列深度、活跃 sandbox、SSE 连接数
- 租户视图：
  - 租户运行趋势、失败 Top Agent、平均处理时长
- 业务组视图：
  - 组内 Agent 分布、会话状态分布、等待人工占比
- Agent 视图：
  - 触发次数、成功率、失败原因 TopN、常用工具与错误率
- 会话诊断页：
  - timeline + trace + tool 调用 + sandbox 状态同屏联查

## 4. 落地边界（MVP）
- 先做：
  - 指标埋点（调度、队列、run/step、工具、SSE、sandbox）
  - 结构化日志 + trace_id
  - 基础告警规则
  - 3 层仪表盘（平台/租户/Agent）
- 后做：
  - 异常聚类与自动根因分析
  - 成本分析（token/工具/沙箱资源）
  - 告警智能降噪

## 5. 验收标准
- 任意失败会话可在 5 分钟内定位到调度、执行或工具层根因。
- API 执行器失联、队列积压、sandbox 创建故障均能在阈值内告警。
- 任一会话 timeline 事件能通过 `trace_id` 追到工具调用日志。
- 租户间观测数据严格隔离（按 `tenant_id`）。

## 6. 评审结论（已确认）
1. 告警分级采用 `P1/P2/P3`。
2. 指标标签强制带 `tenant_id/group_id/agent_id`。
3. MVP 阶段只做基础仪表盘，不做自动根因分析。

## 7. 值班与升级路径（新增）
1. `P1`：
- 5 分钟内主责值班组响应，10 分钟内备用组自动升级拉群。
- 若涉及安全事件（R-01/R-06），必须同步安全负责人并冻结相关发布。
2. `P2`：
- 15 分钟内主责值班组响应；30 分钟内未恢复则升级到平台负责人。
3. `P3`：
- 工作时段处理，若 24 小时内连续触发超过 3 次，自动升级为 `P2` 排查。

## 8. Runbook 索引（新增）
- 风险台账：[/Users/zuos/code/github/ai-manus/md/modules/20-sandbox-agent-gateway-risk-register.md](/Users/zuos/code/github/ai-manus/md/modules/20-sandbox-agent-gateway-risk-register.md)
- 发布回滚：[/Users/zuos/code/github/ai-manus/md/modules/13-release-rollback-runbook.md](/Users/zuos/code/github/ai-manus/md/modules/13-release-rollback-runbook.md)
- Prometheus 规则草案：[/Users/zuos/code/github/ai-manus/md/modules/ops/prometheus-rules-sandbox-agent-gateway.yaml](/Users/zuos/code/github/ai-manus/md/modules/ops/prometheus-rules-sandbox-agent-gateway.yaml)
- Alertmanager 路由草案：[/Users/zuos/code/github/ai-manus/md/modules/ops/alertmanager-routing-sandbox-agent-gateway.yaml](/Users/zuos/code/github/ai-manus/md/modules/ops/alertmanager-routing-sandbox-agent-gateway.yaml)
