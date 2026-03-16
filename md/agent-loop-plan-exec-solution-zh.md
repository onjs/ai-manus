# Multi-Agent Plan-Exec 方案（Automaton 增强版）

## 1. 目标
- 仅采用 `automaton` 的保护算法（执行上限、无进展检测、短退避、熔断）。
- 保留 `automaton` 的 Agent 策略层思想（策略先决、统一工具入口、执行后治理）。
- 不引入 `openclaw` 运行内核方案，避免主链路复杂化。
- 不采用常驻休眠模式，仅保留 run 内短退避能力。
- 采用 `ai-manus` 的展示链路（会话时间线 + 右侧 `shell/file/noVNC` 实时查看与历史回放）。

## 2. 核心结论（冻结）
- 每次触发都是一次独立运行（run），不做常驻循环驻留。
- 触发来源仅两类：
  - `auto`：调度触发。
  - `manual`：用户新建或用户介入。
- 执行模型采用强结构化 `Plan -> Step Execute -> Step Update`。
- 前端继续复用 ai-manus：
  - 左侧会话栏（按 group + agent 聚合）
  - 中间步骤时间线
  - 右侧 `shell/file/noVNC`

## 3. 架构分层
1. `Run Coordinator`
- 接收触发（auto/manual），创建或恢复会话，启动一次 run。

2. `Plan Engine`
- 基于 `AGENTS.md + 当前上下文` 生成结构化计划（step 列表）。
- 当前上下文由双层记忆装配：`planner memory + execution memory`。

3. `Step Executor`
- 严格按 step 执行，逐步调用 tool。
- 每步产生可回放事件与快照引用。

4. `Context & Memory Manager`
- 每轮执行前重组锚点区（goal/step ledger/critical refs）。
- 浏览器观察先做剪裁再进入 LLM 上下文，截图仅用于回放。
- 执行后按 stage 策略压缩历史并更新 checkpoint。

5. `Tool Router + Policy`
- 统一工具入口，执行前做策略校验，执行后做输出清洗和审计落库。

6. `Agent Strategy Engine`
- 回合内统一执行策略决策：是否调用工具、调用哪类工具、失败后是重试/换路/等待人工。
- 固定策略管线：`intent -> policy_check -> tool_route -> post_process -> next_action`。

7. `Sandbox Manager`
- 按需创建 sandbox。
- `auto` 运行结束后自动销毁。
- 用户介入时若 sandbox 已销毁，自动重建并回绑当前会话。

8. `Event Store + Stream`
- `Mongo + GridFS` 持久化事件与大对象。
- `SSE` 推送步骤/工具事件；`WS/noVNC` 走实时桌面。

## 4. 状态机设计
### 4.1 对外会话状态（兼容 ai-manus）
- `pending / running / waiting / completed`
- `waiting` 仅用于用户介入（登录、审批、补充信息）。

### 4.2 Agent 内部状态（复用 ai-manus）
- `idle -> planning -> executing -> updating -> summarizing -> completed`
- 与现有 `PlanActFlow.AgentStatus` 对齐，不新增内部状态枚举。
- 需要人工介入时，通过 `WaitEvent + session.status=waiting` 中断执行；恢复后继续 `executing`。

### 4.3 step 状态
- 执行状态复用 `ExecutionStatus`：`pending -> running -> completed|failed`
- 时间线状态复用 `StepStatus`：`started|completed|failed`

## 5. Plan 与 Step Schema（MVP）
### 5.1 plan
- `plan_id`
- `agent_id`
- `session_id`
- `goal`
- `steps[]`
- `status`
- `created_at / updated_at`

### 5.2 step
- `step_id`
- `title`
- `objective`
- `expected_output`
- `tool_hints[]`
- `status`
- `attempt`
- `started_at / ended_at`

## 6. 事件模型（前端时间线主数据）
- 复用 ai-manus 事件类型：`plan / step / tool / message / wait / done / error / title`
- 前端时间线动作（`step_started/step_completed/step_failed`）由 `step.status` 派生，不新增事件 type。

每个事件必带：
- `session_id`
- `agent_id`
- `step_id`（可从 `step` 对象读取；计划外事件可空）
- `timestamp`
- `artifact_ref[]`（截图、shell快照、文件快照引用）

## 7. 无休眠执行策略
- 不实现 `sleep`/`sleep_until` 状态与命令。
- run 内若“无可执行事项”，直接结束：
  - 会话置 `completed`，并写 `done` 事件
- 等待下一次 cron 触发下一次 run。

## 8. 保护算法（参考 automaton，按 run 内实现）
- `MAX_ROUNDS_PER_RUN`
- `MAX_TOOL_CALLS_PER_ROUND`
- `MAX_TOOL_CALLS_PER_RUN`
- `MAX_NO_PROGRESS_ROUNDS`
- `RUN_TIMEOUT_SECONDS`
- `MAX_STEP_RETRY`（仅回合内短重试）
- `BACKOFF`（秒级短退避 + jitter）
- `LOOP_DETECTION`（重复调用、轮询无进展、ping-pong）
- `CONTEXT_COMPRESSION_STAGE`（按 token 利用率触发 Stage1~Stage5）

说明：
- 不做调度层自动重试/死信（MVP）。
- 仅允许 run 内有限自纠；失败后通过 `error` 事件表达原因，会话最终 `status=completed`（复用 ai-manus 语义）。

### 8.0 Agent 策略层（冻结）
- 策略先决：所有工具调用必须先经过 `Strategy Engine`，再进入 `Tool Router`。
- 统一决策输出：
  - `action=call_tool | ask_human | replan | finish`
  - `reason_code`
  - `risk_level`
- 执行后治理：
  - 对工具输出做注入防护与摘要化。
  - 记录策略命中与决策理由，落事件与审计字段。
- 失败分流：
  - retryable：走回合内短重试
  - non-retryable：立即 fail fast
  - human_required：转 `waiting`（`WaitEvent + session.status=waiting`）

### 8.1 错误分类（冻结）
- 可重试错误：
  - 网络抖动、上游短暂 5xx、浏览器临时加载失败、sandbox 短暂不可用
- 不可重试错误：
  - 权限拒绝、参数非法、策略拒绝、配置缺失、明确业务失败（如审批拒绝）

### 8.2 步骤重试策略（冻结）
- 仅在当前 step 内重试，且只针对可重试错误。
- `MAX_STEP_RETRY=2`，退避策略 `1s -> 2s`（带 `0~20% jitter`）。
- 超出上限后：
  - `step.status=failed`
  - 写 `error` 事件
  - run 结束，不进入调度层自动重试。

### 8.3 终止条件（冻结）
- 达成目标：`session.status=completed` + `done` 事件
- 超时/执行上限/不可恢复错误：`session.status=completed` + `error` 事件（含 `reason_code`）
- 用户取消：`session.status=completed` + `error|message` 事件标注取消原因
- 需要人工介入：`session.status=waiting` + `wait` 事件

## 9. 前端展示与回放（复用 ai-manus）
1. 中间区：
- 以 step 为主轴展示时间线。
- 点击 step 展开该步工具调用与输出摘要。

2. 右侧区：
- 若 step 正在执行且 sandbox 在线：实时 noVNC。
- 若 step 已结束或 sandbox 已销毁：读取 `Mongo + GridFS` 回放快照。

3. 介入流程：
- 用户在 `waiting` 会话发送消息后，继续同一 `session_id`。
- sandbox 不在则自动重建后恢复到当前 step。

## 10. AGENTS.md 的角色
- `AGENTS.md` 负责定义：
  - 角色职责
  - 业务判定规则
  - 工具边界
  - 人工介入规则
- 运行时先生成 plan，再按 step 执行，不允许“纯自由漂移式”长链推理。

## 11. 方案取舍（本版冻结）
- `automaton`：借鉴其 Agent 策略层 + 保护算法（执行上限、无进展、短重试、循环检测）。
- `ai-manus`：复用其会话展示、SSE/noVNC 与回放体验。
- `openclaw`：本轮不纳入 agent loop 设计，后续仅作可选对照参考。

## 12. MVP 实施顺序
1. 落地 `plan/step` 数据结构与事件类型。
2. 将现有执行链改为 step-first（每步产出标准事件）。
3. 接入 run 内执行上限/循环检测/短退避。
4. 打通“介入时 sandbox 自动重建并继续原会话”。
5. 前端按 `step_id` 渲染时间线并支持点击回放。
