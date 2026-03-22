# 23 Sandbox 单服务 + 内存队列改造清单

## 目标
- sandbox 内部从“API进程 + runner进程 + sqlite轮询”改为“单服务进程 + 内存队列事件驱动”。
- 保持 backend 调用契约不变：
  - `POST /api/v1/runtime/config`
  - `DELETE /api/v1/runtime/config/{session_id}`
  - `POST /api/v1/runtime/runs/start`
  - `POST /api/v1/runtime/runs/{session_id}/cancel`
  - `DELETE /api/v1/runtime/runs/{session_id}`
  - `GET /api/v1/runtime/runs/{session_id}/events/stream`
- 保留 SSE 事件流语义与字段，backend 无需改协议。

## 约束（按 AGENTS.md）
- 不做兼容/补丁分支逻辑，不保留 sqlite 运行链路。
- 不扩展需求边界，不增加新业务接口。
- 变更最短路径：仅替换 sandbox 内部通信层。
- 全链路可验证：start -> run -> event stream -> terminal(done/error/wait) -> clear。

## 功能清单

### F1 Gateway 凭证存储改为临时文件
- 每个 session 一份凭证文件：`/tmp/manus_runtime/gateway/{session_id}.json`。
- 写入权限 `0600`。
- `clear_gateway` 删除文件。
- token 过期时自动删除文件并报错。

### F2 运行态改为内存 RunRegistry
- `RunState` 维护：
  - `session_id/agent_id/user_id/status/message/error`
  - `created_at/started_at/finished_at/last_heartbeat_at`
  - `next_seq`
  - `task_handle`（asyncio task）
  - `events`（短期事件缓存，按 seq）
  - `condition`（事件到达通知）
- 不再使用 sqlite `runs/events/commands`。

### F3 start/cancel/clear 直接驱动执行
- `start_run`：校验 gateway 配置后直接 `asyncio.create_task` 启动 agent run。
- `cancel_run`：直接 cancel 对应 task。
- `clear_run`：取消任务并删除 run 状态与事件缓存。

### F4 SSE 事件输出改为 condition + 队列语义
- `stream_events(session_id, from_seq, limit)`：
  - 优先从内存事件缓存按 seq 输出。
  - 无新事件则 await condition（带 heartbeat 定时）。
  - 终态后输出完剩余事件即结束。
- 保持输出字段：`session_id/seq/timestamp + 事件业务字段`。

### F5 Agent 与 API 同进程
- 去掉独立 runner 进程依赖。
- `runtime_runner_service` 内部直接调用 `RuntimeAgentService.run()`。
- 任务终态：`completed/failed/waiting/cancelled` 与现有语义一致。

## 非目标
- 不改 backend/gateway/fronted 协议。
- 不改业务事件模型。
- 不引入新的队列中间件。

## 验收项
- [x] backend 可正常调用 sandbox runtime 契约（接口路径/参数不变）。
- [x] SSE 输出保持 `session_id/seq/timestamp + 事件字段`。
- [x] session 可 `start/cancel/clear`，clear 会移除内存运行态。
- [x] sandbox 仅保留 `app` 服务，不再启动独立 `runner` 进程。
- [x] sandbox 运行链路移除 `runtime_store(sqlite)` 依赖。
