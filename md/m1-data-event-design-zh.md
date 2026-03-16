# M1 设计评审稿：数据与事件底座（不含代码实现）

## 范围与目标
- 仅覆盖 `PLE-M1-01 ~ PLE-M1-04`。
- 输出可评审的字段设计、集合设计、事件 schema、接口草案与索引方案。
- 保持现有响应报文规范：`APIResponse{code,msg,data}`。

---

## 1. `sessions` 扩展字段定义（PLE-M1-01）

### 1.1 现状
- 当前 `Session`/`SessionDocument` 仅包含：
  - `session_id, user_id, sandbox_id, agent_id, status, events, files...`
- 对自动运行、多 Agent 分组、run 元信息支持不足。

参考：
- [session.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/session.py)
- [documents.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/models/documents.py)

### 1.2 新增字段（M1）
- `tenant_id: str`
- `group_id: Optional[str]`
- `source_type: "manual" | "auto"`  
- `run_meta: object`

### 1.3 `run_meta` 建议结构（M1 最小集）
- `run_id: str`
- `current_step_id: Optional[str]`
- `plan_id: Optional[str]`
- `attempt_no: int`（默认 `1`）
- `started_at: Optional[int]`
- `ended_at: Optional[int]`

### 1.4 兼容策略
- 旧会话缺少新字段时按默认值读取：
  - `source_type="manual"`
  - `run_meta={}`
- 前端与 SSE 对旧字段保持完全可用。

### 1.5 文件影响清单
- [session.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/session.py)
- [documents.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/models/documents.py)
- [mongo_session_repository.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/repositories/mongo_session_repository.py)
- [session.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/session.py)

---

## 2. `plan/steps` 存储模型（PLE-M1-02）

### 2.1 方案对比
1. 方案 A：嵌入 `sessions.run_meta.plan/steps`
- 优点：读会话时一次取全。
- 缺点：步骤多时文档膨胀；并发更新冲突高；步骤级查询差。

2. 方案 B：独立集合 `session_plans` + `session_steps`
- 优点：步骤级查询、排序、回放定位更清晰；写扩展性好。
- 缺点：读取需 join（应用层拼装）。

### 2.2 推荐（M1）
- 采用方案 B（独立集合），并在 `sessions.run_meta` 留摘要：
  - `plan_id`
  - `current_step_id`
  - `steps_total`
  - `steps_completed`

### 2.3 集合定义（草案）
1. `session_plans`
- `plan_id, tenant_id, session_id, agent_id, goal, status, created_at, updated_at`

2. `session_steps`
- `step_id, tenant_id, plan_id, session_id, agent_id, seq, title, objective, expected_output, tool_hints, status, attempt, started_at, ended_at`

### 2.4 文件影响清单
- 新增 `PlanDocument/StepDocument`（建议位置）：
  - [documents.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/models/documents.py)
- 新增仓储接口与实现（建议）：
  - `backend/app/domain/repositories/plan_repository.py`
  - `backend/app/infrastructure/repositories/mongo_plan_repository.py`

---

## 3. Step-first 事件 Schema（PLE-M1-03）

### 3.1 现状风险
- 当前 `AgentEvent` 是严格 Union；新增未知事件可能无法稳定映射到 SSE。
- `EventMapper` 对未知类型回退逻辑不适合直接推送 chat SSE。

参考：
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/event.py)
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/event.py)

### 3.2 事件模型建议（M1）
- 保留现有事件类型不删。
- 新增统一事件类型：`type="timeline"`，通过 `action` 区分子事件。
- `action` 枚举：
  - `plan_created`
  - `step_created`
  - `step_started`
  - `tool_calling`
  - `tool_called`
  - `step_completed`
  - `step_failed`
  - `waiting`
  - `sandbox_recreated`
  - `sandbox_destroyed`

### 3.3 `timeline` 数据字段（最小）
- `session_id: str`
- `agent_id: str`
- `step_id: Optional[str]`
- `action: str`
- `payload: object`（每个 action 的细节）
- `artifact_refs: list`
- `trace_id: Optional[str]`
- `timestamp: int`

### 3.4 SSE 兼容策略
- 新增 `TimelineSSEEvent(event="timeline")`。
- 保持旧 `message/tool/step/plan/wait/done/error/title` 不变。
- 前端不识别 `timeline` 时可忽略；识别后按 `action` 渲染 step 时间线。

### 3.5 文件影响清单
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/event.py)
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/event.py)
- [session_routes.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/api/session_routes.py)

---

## 4. `artifact_ref` 规范（PLE-M1-04）

### 4.1 原则
- 事件流只放摘要，不放大正文。
- 大文本、截图、文件正文统一走外部存储引用（现阶段优先复用 GridFS/FileStorage）。

### 4.2 `artifact_ref` 结构（草案）
- `artifact_id: str`（对应 `file_id` 或独立 id）
- `kind: "screenshot"|"shell_output"|"file_snapshot"|"browser_snapshot"|"other"`
- `mime_type: str`
- `size: int`
- `preview_text: Optional[str]`
- `created_at: int`

### 4.3 阈值建议（M1）
- 文本输出超过 `8KB` 不内联，转 `artifact_ref`
- shell console 超过 `100` 行仅内联摘要
- 文件正文超过 `16KB` 仅内联摘要

### 4.4 读取路径
- 实时：SSE 先给摘要 + `artifact_ref`
- 详情：前端按 `artifact_id` 调现有文件查看接口或新增 artifact 查询接口

### 4.5 文件影响清单
- [mongo_session_repository.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/repositories/mongo_session_repository.py)
- [session_routes.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/api/session_routes.py)
- [file.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/file.py)

---

## 5. API 草案（仅契约，不实现）

### 5.1 `GET /sessions/{session_id}/plan`
- 作用：获取会话的 plan 与 steps
- 响应：
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "session_id": "s_xxx",
    "plan": { "plan_id": "p_xxx", "status": "running", "goal": "..." },
    "steps": [
      { "step_id": "st_1", "seq": 1, "title": "...", "status": "completed" },
      { "step_id": "st_2", "seq": 2, "title": "...", "status": "running" }
    ]
  }
}
```

### 5.2 `POST /sessions/{session_id}/runs/resume`
- 作用：用户在 `waiting` 后恢复同一会话运行
- 请求：
```json
{
  "message": "我已登录完成，继续",
  "event_id": "optional"
}
```
- 响应：
```json
{
  "code": 0,
  "msg": "success",
  "data": { "session_id": "s_xxx", "run_id": "r_xxx" }
}
```

### 5.3 `GET /sessions/{session_id}/steps/{step_id}/artifacts`
- 作用：读取某一步关联快照/输出引用
- 响应：
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "session_id": "s_xxx",
    "step_id": "st_xxx",
    "artifacts": [
      { "artifact_id": "f_xxx", "kind": "screenshot", "mime_type": "image/png" }
    ]
  }
}
```

### 5.4 现有接口扩展
1. `GET /sessions`
- 增加可选字段：
  - `agent_id, group_id, source_type, run_meta.summary`

2. `POST /sessions`（SSE sessions 流）
- `sessions` payload 同步增加上述字段，旧字段保持不变

### 5.5 报文规范
- 全部沿用 [base.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/base.py) 的 `APIResponse`。

---

## 6. 索引与查询设计（Mongo + Redis）

### 6.1 Mongo 索引建议
1. `sessions`
- `(user_id, latest_message_at desc)`
- `(tenant_id, group_id, latest_message_at desc)`
- `(tenant_id, agent_id, latest_message_at desc)`

2. `session_plans`
- `(tenant_id, session_id)`
- `(tenant_id, agent_id, created_at desc)`

3. `session_steps`
- `(tenant_id, session_id, seq asc)`
- `(tenant_id, plan_id, status, seq asc)`
- `(tenant_id, step_id)` 唯一

### 6.2 Redis 热态建议（M1）
- `run:{session_id}:state`：当前 run 内部状态
- `run:{session_id}:budget`：轮次/工具调用计数
- `run:{session_id}:locks`：会话级运行锁

说明：
- Redis 仅热态，不作为最终真相源。
- 真相源以 Mongo 事件与 plan/steps 为准。

---

## 7. 验收场景（只定义测试，不写代码）

### 7.1 数据兼容
- 给定旧会话（无新增字段），读取 `/sessions` 与 `/sessions/{id}` 均成功，默认值正确。

### 7.2 Plan 可读
- run 启动后 `GET /sessions/{id}/plan` 可返回 `plan + ordered steps`。

### 7.3 事件闭环
- 每个 step 都有 `step_started` 与终态事件（`step_completed|step_failed`）。
- 需要人工介入时由 `wait` 事件表达（不扩展 step 终态枚举）。
- 事件均带 `session_id/agent_id/step_id/timestamp`。

### 7.4 Artifact 引用
- 大输出不内联，事件中出现 `artifact_ref`；可通过接口回读正文。

### 7.5 SSE 兼容
- 旧前端可继续消费现有事件。
- 新前端可消费 `timeline` 并按 `action` 渲染步骤时间线。

### 7.6 用户恢复
- `waiting` 会话调用 `runs/resume` 后继续同一 `session_id`，并继续追加标准事件流。

---

## 附：M1 评审决策点（待你拍板）
1. `plan/steps` 是否采用独立集合（推荐：是）。
2. 事件是否采用统一 `type="timeline"+action`（推荐：是）。
3. `artifact_ref` 阈值是否按文档默认值执行（推荐：先按默认，后续可配置化）。
4. `/sessions/{id}/plan` 是否在 M1 就提供（推荐：是，便于前端并行开发）。
