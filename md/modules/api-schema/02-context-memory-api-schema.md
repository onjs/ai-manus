# 02 上下文与记忆模块 API Schema 设计稿

## 说明
- 本模块以内部服务契约为主，MVP 不强制新增外部 REST。
- 外部接口仅提供调试/排障能力，前端主链路继续走现有会话接口。

## 内部契约（必须）

### 1) `AssembleContextRequest`
- `session_id`
- `agent_id`
- `model_context_window`
- `reserve_tokens`
- `recent_turns[]`
- `events[]`
- `planner_memory`（来自 `memories.planner`）
- `execution_memory`（来自 `memories.execution`）
- `anchors`
  - `goal_anchor`
  - `step_ledger`
  - `critical_refs[]`

### 2) `AssembleContextResponse`
- `messages[]`
- `utilization`
- `budget`
- `token_breakdown`
  - `anchor_tokens`
  - `planner_tokens`
  - `execution_tokens`
  - `recent_turn_tokens`

### 3) `BrowserClipRequest`
- `session_id`
- `step_id`
- `source_type`（`browser_use|playwright`）
- `raw_content`（DOM/markdown）
- `artifact_ref`（可选）
- `clip_policy`
  - `max_chars`
  - `max_tokens`
  - `include_interactives`

### 4) `BrowserClipResponse`
- `clip_text`（给 LLM）
- `dropped_sections[]`
- `clip_ratio`
- `artifact_ref`（回放/审计）

### 5) `CompressionPlan`
- `max_stage`
- `actions[]`
- `estimated_tokens_saved`
- `reason`

### 6) `CompressionResult`
- `success`
- `stage`
- `tokens_saved`
- `compression_ratio`
- `latency_ms`

### 7) `IntegrityCheckResult`
- `goal_hash_ok`
- `step_ledger_ok`
- `critical_refs_ok`
- `rollback_applied`

### 8) `IngestMemoryRequest`
- `session_id`
- `agent_id`
- `planner_delta`（可选）
- `execution_delta`（可选）
- `checkpoint`（可选）
- `events[]`

### 9) `IngestMemoryResponse`
- `planner_version`
- `execution_version`
- `checkpoint_id`
- `persisted_event_count`

## 可选调试接口（非 P0）
1. `GET /sessions/{id}/context/checkpoints`
2. `GET /sessions/{id}/context/utilization`
3. `POST /sessions/{id}/context/reassemble`
4. `POST /sessions/{id}/context/clip-browser-preview`
