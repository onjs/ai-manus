# 17 BrowserEngine API Schema 设计稿

## 范围
- BrowserEngine 任务生命周期接口。
- 与现有 `sessions`/SSE 兼容的事件扩展。
- BrowserEngine 路由复放、人工接管恢复、运行态查询契约。

## 统一响应
- `APIResponse{code,msg,data}`。

## 兼容约束
- 不替换现有 `sessions` 主实体。
- 不删除现有 `tool/step/message/plan` 事件结构，仅增加可选扩展字段。
- 前端旧版本忽略新增字段时不报错。

## 接口清单

1. `POST /browser-engine/tasks`
- 语义：创建并启动浏览器任务（绑定现有 `session_id`）。
- 请求：
  - `session_id`
  - `agent_id`
  - `goal`
  - `constraints(optional)`：
    - `domain_whitelist[]`
    - `max_steps`
    - `task_timeout_seconds`
    - `risk_level`
    - `replay_first`
  - `input_payload(optional)`：复杂表单输入数据。
- 返回：
  - `task_id`
  - `session_id`
  - `status(created|running)`
  - `run_mode(replay_first|agentic)`

2. `GET /browser-engine/tasks/{task_id}`
- 语义：查询任务运行态。
- 返回：
  - `task_id, session_id, tenant_id, agent_id`
  - `status(created|running|waiting_user|completed|failed|cancelled|timeout)`
  - `current_phase(observe|plan|act|verify|recover|commit)`
  - `current_step_seq`
  - `started_at, updated_at, ended_at`
  - `counters`：
    - `steps_total`
    - `steps_completed`
    - `recovery_attempts_total`
    - `verify_failed_count`
  - `route_meta(optional)`：`route_id, route_version, replay_hit`

3. `GET /browser-engine/tasks/{task_id}/steps`
- 语义：查询步骤明细与恢复轨迹。
- 查询参数：`page, page_size, status(optional)`
- 返回：
  - `steps[]`
    - `step_id, seq, action, target`
    - `status(pending|running|verifying|recovering|completed|failed|waiting_user)`
    - `verify_rule`
    - `verify_result`
    - `recover_strategy(optional)`
    - `attempt_no`
    - `error_code(optional)`
    - `started_at, ended_at`

4. `GET /browser-engine/tasks/{task_id}/snapshots`
- 语义：查询页面快照索引（用于回放）。
- 查询参数：`step_id(optional), page, page_size`
- 返回：
  - `snapshots[]`
    - `snapshot_id`
    - `step_id`
    - `page_id, frame_id(optional)`
    - `url, title`
    - `dom_digest_ref`
    - `a11y_digest_ref`
    - `screenshot_ref`
    - `created_at`

5. `POST /browser-engine/tasks/{task_id}/resume`
- 语义：人工接管完成后恢复自动执行。
- 请求：
  - `resume_from_step(optional)`
  - `note(optional)`
- 返回：
  - `task_id`
  - `status(running|completed|failed)`
  - `resumed_at`

6. `POST /browser-engine/tasks/{task_id}/cancel`
- 语义：取消当前浏览器任务。
- 返回：
  - `task_id`
  - `status(cancelled|already_finished|not_found)`
  - `final_session_status(completed|waiting|running)`

7. `POST /browser-engine/routes/{route_id}/replay`
- 语义：执行历史成功路线复放。
- 请求：
  - `session_id`
  - `agent_id`
  - `inputs(optional)`
  - `expected_version(optional)`
- 返回：
  - `task_id`
  - `route_id`
  - `route_version`
  - `status(created|running)`

8. `GET /browser-engine/routes`
- 查询参数：`site_key, flow_key, status, page, page_size`
- 返回：
  - `routes[]`：
    - `route_id, site_key, flow_key, version`
    - `status(active|deprecated|invalid)`
    - `success_rate`
    - `last_validated_at`

9. `PATCH /browser-engine/routes/{route_id}`
- 语义：路由治理（启停/废弃）。
- 请求：`status(active|deprecated|invalid)`

## Session 接口扩展

1. `GET /sessions`
- 新增可选返回字段：
  - `browser_task_summary(optional)`：
    - `latest_task_id`
    - `latest_task_status`
    - `latest_phase`
    - `latest_error_code(optional)`

2. `GET /sessions/{session_id}`
- 新增可选返回字段：
  - `browser_engine_state(optional)`：
    - `active_task_id`
    - `active_phase`
    - `page_context`：`page_id, frame_id, url`
    - `wait_reason(optional)`

## SSE 事件扩展契约

### 事件类型
- `browser_task_upsert`
- `browser_step_upsert`
- `browser_snapshot_created`
- `browser_verify_result`
- `browser_recovery_attempt`
- `browser_route_matched`
- `browser_waiting_user`
- `browser_task_done`

### 统一事件字段
- `event_id`
- `session_id`
- `task_id`
- `step_id(optional)`
- `timestamp`
- `phase`
- `status`
- `reason_code(optional)`
- `error_code(optional)`

### 关键 payload 示例字段
- `browser_step_upsert`：
  - `seq, action, target, attempt_no, verify_rule`
- `browser_verify_result`：
  - `pass`
  - `evidence_refs[]`
- `browser_recovery_attempt`：
  - `strategy`
  - `attempt_no`
  - `result(success|failed|exhausted)`
- `browser_waiting_user`：
  - `wait_reason(login|captcha|2fa|risk_blocked|unknown)`
  - `hint(optional)`

## 数据模型契约（持久化）

### `browser_tasks`
- `task_id`
- `tenant_id, session_id, agent_id, group_id(optional)`
- `goal`
- `status`
- `run_mode`
- `route_id(optional), route_version(optional)`
- `current_phase, current_step_seq`
- `counters`
- `created_at, started_at, ended_at, updated_at`

### `browser_steps`
- `task_id, step_id, seq`
- `action, target, input_masked`
- `status`
- `verify_rule, verify_result`
- `recover_strategy(optional), attempt_no`
- `error_code(optional), reason_code(optional)`
- `started_at, ended_at`

### `browser_snapshots`
- `snapshot_id, task_id, step_id`
- `page_id, frame_id(optional)`
- `url, title`
- `dom_digest_ref, a11y_digest_ref, screenshot_ref`
- `created_at`

### `browser_routes`
- `route_id`
- `tenant_id, site_key, flow_key, version`
- `status`
- `steps_ref`
- `success_rate`
- `last_validated_at`

## 错误码契约（BrowserEngine 域）
- `BE-001` 元素未找到
- `BE-002` 元素不可操作
- `BE-003` 动作超时
- `BE-004` 校验失败
- `BE-005` 页面上下文丢失
- `BE-006` 恢复链路耗尽
- `BE-007` 路由复放失败
- `BE-008` 风控阻断
- `BE-009` 需要人工接管
- `BE-010` 沙箱连接异常

## 鉴权与租户隔离
- 全部接口强制按 `tenant_id` 过滤。
- `tenant_user`：
  - 可查询已授权 agent 的 task/step/snapshot。
  - 可触发 `resume/cancel`（需 `operate` 授权）。
- `tenant_admin`：
  - 可管理本租户 routes。
- `platform_admin`：
  - 全局可见。
