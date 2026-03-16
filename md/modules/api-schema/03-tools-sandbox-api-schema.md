# 03 工具与Sandbox模块 API Schema 设计稿

## 统一响应
- `APIResponse{code,msg,data}`。

## 复用现有接口
1. `POST /sessions/{session_id}/stop`
2. `GET /sessions/{session_id}/files`
3. `GET /sessions/{session_id}/vnc`（WS）
4. `POST /sessions/{session_id}/vnc/signed-url`

## 建议新增（P0）
1. `POST /sessions/{session_id}/sandbox/recreate`
- 用于手动触发重建（运维/调试）

2. `GET /sessions/{session_id}/sandbox/status`
- 返回：`sandbox_id, healthy, last_seen_at, source_type, sandbox_status, sandbox_ws_target`

3. `GET /sessions/{session_id}/sandbox/ws-target`
- 语义：供 `api` websocket forward 查询当前会话的 sandbox 转发目标。
- 返回：`session_id, sandbox_id, sandbox_ws_target, sandbox_status, updated_at`
- 错误码：
  - `SANDBOX_NOT_READY`
  - `SANDBOX_EXPIRED`
  - `SANDBOX_MAPPING_NOT_FOUND`

## 事件扩展
- `sandbox_recreated`
- `sandbox_destroyed`
- `sandbox_destroy_failed`
- `context_restored`
- `sandbox_mapping_updated`
