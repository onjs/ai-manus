# 04 调度与队列模块 API Schema 设计稿

## 范围
- Celery 调度触发、队列执行、运行态观测与取消。
- 与 Agent loop 冻结参数的传递契约（避免调度层与执行层参数漂移）。

## 统一响应
- `APIResponse{code,msg,data}`。

## 接口
1. `GET /scheduler/overview`
- 返回：
  - `trigger_pending_count, trigger_queued_count, trigger_running_count`
  - `celery_queue_depth{queue}`
  - `celery_worker_alive_count, celery_worker_stale_count`
  - `beat_lag_seconds_p50/p95`
  - `loop_guard_triggered_count, run_timeout_count, retry_exhausted_count`

2. `POST /scheduler/triggers/{trigger_id}/cancel`
- 返回：`trigger_id, status(cancelled|not_found|already_finished), cancel_scope(pending|queued|running|waiting), finalized_session_status`

3. `GET /scheduler/triggers`
- 查询：`agent_id, status, from, to`
- `status` 枚举：`created|pending|queued|running|finished|cancelled`
- 返回补充：
  - `session_id`
  - `session_status(pending|running|waiting|completed)`
  - `celery_task_id`
  - `started_at, ended_at`

4. `GET /scheduler/tasks/{celery_task_id}`（可选）
- 返回：`broker_status, worker_id, queue, retries, started_at, ended_at`

5. `POST /scheduler/reconcile/run`（运维/手动触发，可选）
- 返回：`scanned_count, repaired_count, released_leases, details[]`

## 内部消息模型
- `TriggerPayload`
  - `trigger_id, tenant_id, agent_id, group_id, schedule_id, fire_at, priority, idempotency_key`
  - `session_id`（创建后回填）
  - `loop_config_snapshot`（冻结参数快照）
    - `max_rounds_per_run=24`
    - `max_tool_calls_per_round=3`
    - `max_tool_calls_per_run=64`
    - `max_no_progress_rounds=3`
    - `run_timeout_seconds=1800`
    - `think_timeout_seconds=90`
    - `tool_timeout_seconds=120`
    - `max_step_retry=2`
    - `backoff_base_seconds=1`
    - `backoff_max_seconds=2`
    - `backoff_jitter_ratio=0.2`

- `DispatchMeta`
  - `celery_task_id, queue_name, eta, worker_id(optional)`

- `ReconcileReport`
  - `run_id, scanned_count, repaired_count, released_leases`
  - `details[]`（`trigger_id, from_status, to_status, reason_code`）

- `ConcurrencyLease`
  - `lease_id`
  - `scope(global|tenant|agent)`
  - `scope_key`
  - `owner(celery_task_id)`
  - `acquired_at, expires_at`

- `AcquireLeaseRequest`
  - `tenant_id, agent_id, celery_task_id`
  - `limits(global, tenant, agent)`

- `AcquireLeaseResponse`
  - `success`
  - `denied_scope(optional)`
  - `retry_after_seconds(optional)`

- `BeatLeaderLease`
  - `lock_name=beat_leader_lock`
  - `owner_instance_id`
  - `acquired_at, expires_at`
  - `renew_interval_seconds`

## 调度到执行映射契约（冻结）
- `trigger -> session -> celery_task -> worker -> sandbox` 必须写可追溯关联键：
  - `trigger_id, session_id, celery_task_id, worker_id, sandbox_id`
- 调度到前端实时映射（新增）：
  - 调度创建会话时发布：`session_upsert`（全局摘要流）。
  - 运行状态变化发布：`session_status_changed`、`session_unread_changed`（全局摘要流）。
  - 细粒度 `step/tool/message` 进入会话详情流：`GET /sessions/{session_id}/stream`。
- 调度层不做自动重试/死信（MVP）：
  - `retryable/non_retryable/human_required` 仅由 Agent loop 内部处理。
- 结果表达规则：
  - 对外仅暴露 `session.status`（复用 ai-manus）。
  - 细粒度原因通过事件流表达（`wait/done/error` + `reason_code`）。
  - 不新增 `agent_runs` 主实体。
- 对账恢复规则：
  - 由 `Reconciler` 周期修正 `pending/queued/running` 异常态。
  - 每次修正必须记录 `scheduler_reconciled` 事件。
- 冲突优先级规则：
  - `manual_cancel > human_waiting > reconciler_fix > normal_progress`。
