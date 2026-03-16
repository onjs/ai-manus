# 01 Agent管理模块 API Schema 设计稿

## 范围
- Agent/Group/Schedule/Permission 管理。
- 会话列表字段扩展（兼容旧前端）。
- Agent loop 冻结参数与运行态字段契约（避免实现偏移）。

## 统一响应
- `APIResponse{code,msg,data}`。

## 接口
1. `GET /agent-groups`
- 查询参数：`tenant_id(optional by auth), status, keyword, page, page_size`
- 返回：`groups[]`

2. `POST /agent-groups`
- 请求：`name, code, status`
- 返回：`group_id`

3. `PATCH /agent-groups/{group_id}`
- 请求：`name?, status?`

4. `GET /agents`
- 查询参数：`group_id, status, keyword, page, page_size`
- 返回字段补充：`model_profile_id, model_profile_name`

5. `POST /agents`
- 请求：`name, code, group_id, model_profile_id, tools_config, prompts`
- 说明：MVP 不开放 loop 参数写入接口，采用系统冻结默认值。

6. `PATCH /agents/{agent_id}`
- 请求：`group_id?, status?, model_profile_id?, tools_config?, prompts?`
- 说明：MVP 不支持按 Agent 覆盖 loop 冻结参数。

7. `GET /agent-schedules`
- 查询参数：`agent_id, enabled`

8. `POST /agent-schedules`
- 请求：`agent_id, cron_expr, timezone, enabled`

9. `PATCH /agent-schedules/{schedule_id}`
- 请求：`cron_expr?, timezone?, enabled?`

10. `GET /agent-permissions`
- 查询参数：`agent_id, user_id, grant_type`

11. `POST /agent-permissions`
- 请求：`agent_id, user_id, grant_type(view|operate)`

12. `DELETE /agent-permissions/{permission_id}`

13. `GET /sessions`
- 扩展返回字段：`agent_id, agent_name, group_id, group_name, source_type`
- 扩展查询参数：`group_id, agent_id, source_type`
- 扩展返回字段（运行态）：`run_meta.summary, run_meta.loop, run_meta.dispatch`

14. `GET /sessions/{session_id}`
- 返回补充：`run_meta` 完整对象（含 loop 快照、计数器、最近策略决策、celery 分发信息）

15. `GET /sessions/stream`
- 语义：全局会话摘要 SSE（左侧常驻订阅）。
- 查询参数：`group_id?, agent_id?, source_type?, since?(optional)`
- 事件类型：
  - `session_upsert`（新增或更新会话摘要）
  - `session_remove`
  - `session_unread_changed`
  - `session_status_changed`
- payload 最小字段：
  - `session_id, title, status, latest_message_at`
  - `agent_id, agent_name, group_id, group_name, source_type`
  - `unread_message_count, event_id, timestamp`

16. `GET /sessions/{session_id}/stream`
- 语义：会话详情 SSE（中间时间线订阅）。
- 查询参数：`from_event_id?(optional)`
- 事件类型：`message/tool/step/plan/wait/done/error/timeline`
- 说明：不要求用户先调用 `chat` 才可订阅，用于接收调度触发的后台执行实时事件。

## 模型配置中心对齐
- 模型档案管理接口在平台模块：
  - `GET/POST/PATCH /platform/model-profiles`
  - `POST /platform/model-profiles/{profile_id}/rotate-key`
- `agents` 仅引用 `model_profile_id`，不接收/返回明文 `api_key`。

## Agent Loop 冻结参数契约（MVP）
- 参数来源：系统配置冻结值，运行时写入 `run_meta.loop.config_snapshot`。
- 冻结默认值：
  - `MAX_ROUNDS_PER_RUN=24`
  - `MAX_TOOL_CALLS_PER_ROUND=3`
  - `MAX_TOOL_CALLS_PER_RUN=64`
  - `MAX_NO_PROGRESS_ROUNDS=3`
  - `RUN_TIMEOUT_SECONDS=1800`
  - `THINK_TIMEOUT_SECONDS=90`
  - `TOOL_TIMEOUT_SECONDS=120`
  - `MAX_STEP_RETRY=2`
  - `BACKOFF_BASE_SECONDS=1`
  - `BACKOFF_MAX_SECONDS=2`
  - `BACKOFF_JITTER_RATIO=0.2`

## run_meta.loop Schema（新增）
- `run_meta.loop.config_snapshot`
  - `max_rounds_per_run`
  - `max_tool_calls_per_round`
  - `max_tool_calls_per_run`
  - `max_no_progress_rounds`
  - `run_timeout_seconds`
  - `think_timeout_seconds`
  - `tool_timeout_seconds`
  - `max_step_retry`
  - `backoff_base_seconds`
  - `backoff_max_seconds`
  - `backoff_jitter_ratio`
- `run_meta.loop.counters`
  - `round_count`
  - `tool_calls_current_round`
  - `tool_calls_total`
  - `no_progress_rounds`
  - `step_retry_count`
- `run_meta.loop.last_policy_decision`
  - `action(call_tool|ask_human|replan|finish)`
  - `reason_code`
  - `risk_level(low|medium|high)`
  - `timestamp`
- `run_meta.dispatch`
  - `trigger_id`
  - `celery_task_id`
  - `queue_name`
  - `worker_id(optional)`
  - `dispatched_at`
## 事件/SSE 扩展
- 兼容保留：旧 `POST /sessions` SSE 快照流继续可用。
- 新推荐：
  - `GET /sessions/stream` 用于左侧会话摘要增量更新。
  - `GET /sessions/{session_id}/stream` 用于会话详情实时更新。
- `/sessions` SSE payload 同步扩展：`agent_id, group_id, source_type`。
- 新增 timeline action：
  - `guard_warning`
  - `guard_triggered`
  - `retry_scheduled`
  - `retry_exhausted`
  - `loop_detected_warning`
  - `loop_detected_critical`
- 新增保护事件 payload 字段：
  - `guard_name`
  - `reason_code`
  - `threshold`
  - `current_value`
  - `step_id`
  - `run_id`

## 错误分类契约（MVP）
- `retryable`：进入回合内短重试（最多 `MAX_STEP_RETRY`）。
- `non_retryable`：直接失败并终止本次 run。
- `human_required`：进入 `waiting`，会话置 `waiting` 等待用户介入。
- 结果表达：仅复用 `session.status(pending/running/waiting/completed)` 与事件类型（`wait/done/error`），不新增状态枚举。
