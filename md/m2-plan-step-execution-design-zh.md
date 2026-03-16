# M2 设计评审稿：Plan/Step 执行主链（不含代码实现）

## 范围与目标
- 覆盖 `PLE-M2-01 ~ PLE-M2-04`。
- 定义可执行的 `Plan -> Step Execute -> Step Update -> Run Finalize` 主链。
- 保持当前会话状态兼容：`pending/running/waiting/completed`。

---

## 1. M2 要解决的问题
- 当前链路虽然有 `plan + step` 概念，但仍偏“事件混合流”，不够 step-first。
- 需要将“每一步”显式化为可查询、可回放、可恢复的主实体。
- 需要保证用户介入后可以继续同一 `session_id` 的 step 语义。

参考现状：
- [plan_act.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/flows/plan_act.py)
- [agent_task_runner.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/agent_task_runner.py)
- [execution.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/agents/execution.py)

---

## 2. 主链目标形态（M2）

### 2.1 运行主流程
1. `Run Coordinator` 启动 run（同 `session_id`）。
2. `Plan Builder` 生成结构化 `plan + ordered steps`。
3. `Step Executor` 严格按 `seq` 执行每一步。
4. `Step Updater` 根据执行结果更新后续 step 状态或补充信息。
5. `Run Finalizer` 收敛到 ai-manus 会话语义与事件语义。

### 2.2 状态约束
- 会话对外状态：
  - 运行中：`running`
  - 需人工：`waiting`
  - 结束：`completed`
- Agent 内部状态复用 `PlanActFlow.AgentStatus`：
  - `idle/planning/executing/updating/summarizing/completed`

---

## 3. 组件契约（接口草案）

## 3.1 Plan Builder（PLE-M2-01）
- 输入：
  - `session_id, agent_id`
  - `AGENTS.md` 角色定义摘要
  - 最近上下文（session events 摘要、`planner/execution` 双层 memory 摘要）
- 输出：
  - `plan_id`
  - `steps[]`（至少含 `step_id, seq, title, objective, expected_output, tool_hints`）
- 事件：
  - `plan_created`
  - `step_created`（每个 step 一条）

### 3.2 Step Executor（PLE-M2-02）
- 输入：
  - `session_id, plan_id, step_id`
  - `step payload`
- 输出：
  - `step_result`（成功/失败/等待人工）
  - `artifact_refs[]`
  - `context_clip_refs[]`（浏览器剪裁引用，可选）
- 事件：
  - `step_started`
  - `tool_calling`
  - `tool_called`
  - `step_completed | step_failed`（需人工介入时由 `wait` 事件表达）

### 3.3 Step Updater（PLE-M2-03）
- 输入：
  - 当前 step 结果
  - 计划上下文
- 输出：
  - 后续 step 状态变更（例如 `created -> skipped` 或补充 `objective`）
- 事件：
  - 可选 `step_updated`（M2 可先不对外暴露，写入内部审计即可）

### 3.4 Run Finalizer（PLE-M2-04）
- 输入：
  - run 全量执行结果
- 输出：
  - 会话最终状态映射：
    - 需人工介入 -> `session.status=waiting` + `wait` 事件
    - 其他情况 -> `session.status=completed` + `done/error` 事件

---

## 4. Step 执行策略（M2 冻结建议）

### 4.1 顺序策略
- MVP 默认串行：按 `seq asc` 执行。
- 不并发执行 step（减少状态复杂度）。

### 4.2 选择策略
- 每次只选择一个 `next runnable step`：
  - `status in {created, retry_ready}`
  - `seq` 最小优先
- 一旦触发人工介入，当前 run 立即暂停并退出 worker，`session.status=waiting`。

### 4.3 结果分类
1. `SUCCESS`
- step -> `completed`
- 推进到下一 step

2. `FAILURE`
- step -> `failed`
- M2 默认终止当前 run（不跨 step 自动恢复）

3. `WAIT_HUMAN`
- step -> 保持 `running`（等待用户输入后继续）
- session -> `waiting`

4. `NOOP`
- 若 plan 为空或 step 全部不可执行
- session -> `completed`（通过 `done` 事件表达）

---

## 5. 事件发射矩阵（M2）

### 5.1 必发事件
1. 计划阶段
- `plan_created`
- `step_created` * N

2. 步骤阶段（每个 step）
- `step_started`
- `tool_calling` * k
- `tool_called` * k
- `step_completed | step_failed`
- 人工介入由 `wait` 事件单独表达

3. 收尾阶段
- 复用现有 `done/error/wait` 事件，不新增 run 终态字段

### 5.2 字段约束
- 所有时间线事件必须带：
  - `session_id`
  - `agent_id`
  - `step_id`（计划级事件可空）
  - `timestamp`

---

## 6. 与现有实现的最小侵入改造边界

## 6.1 保留
- 保留当前会话实体与状态枚举：
  - [session.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/session.py)
- 保留当前 chat/SSE 路由入口：
  - [session_routes.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/api/session_routes.py)

### 6.2 调整
1. `PlanActFlow`
- 从“内部状态循环”升级为“显式 step-first 执行编排”。
- `AgentStatus` 可保留但仅作为内部 transient 状态，不作为前端主状态来源。

2. `AgentTaskRunner`
- 在 `_run_flow` 级别绑定当前 `step_id`，确保 tool 事件可回写到 step 时间线。
- `WaitEvent` 保持现有语义（用户介入）。

3. `EventMapper`
- 增加 timeline 事件映射（兼容旧事件）。

---

## 7. 失败处理与回退策略（M2）

### 7.1 M2 默认策略
- step 失败即 run 失败（不做跨 step 自动补救）。
- 工具级小重试留给 M3。

### 7.2 安全回退
- 若新 step 事件映射失败：
  - 回落写旧 `step/tool/message` 事件，保证会话不中断。
- 若 plan 持久化失败：
  - run 直接 `failed`，并写 `error` 事件。

---

## 8. M2 验收场景（只定义，不写代码）

### 8.1 计划生成
- 触发 run 后可看到：
  - `plan_created`
  - 至少 1 条 `step_created`

### 8.2 步骤执行
- 每个步骤都能看到开始和终态事件。
- 工具调用事件与 `step_id` 关联正确。

### 8.3 等待人工
- 出现 `waiting` 时：
  - `session.status=waiting`
  - run 停止继续执行后续 step

### 8.4 结束归档
- run 结束后：
  - `session.status` 正确映射为 `completed` 或 `waiting`
  - 结束原因可从 `done/error/wait` 事件读取

### 8.5 兼容验证
- 旧前端仍可渲染核心会话流（不因新增字段报错）。

---

## 9. 文件影响清单（设计级）
- [plan_act.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/flows/plan_act.py)
- [agent_task_runner.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/agent_task_runner.py)
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/event.py)
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/event.py)
- [mongo_session_repository.py](/Users/zuos/code/github/ai-manus/backend/app/infrastructure/repositories/mongo_session_repository.py)
- [session.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/session.py)

---

## 附：M2 评审决策点（待确认）
1. M2 是否强制串行 step 执行（推荐：是）。
2. step 失败是否立即终止 run（推荐：是，复杂恢复放 M3）。
3. `run_finished` 事件是否本期新增（推荐：否，先复用 `done/error/wait`）。
