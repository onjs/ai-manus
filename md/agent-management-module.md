# Agent管理模块设计冻结稿（v2）

## 1. 目标与原则
- 核心原则：每次 Agent 自动运行生成一个 `session`，不新增 `agent_runs` 主实体，不替换现有会话体系。
- 复用优先：复用现有前端会话页、中间操作时间线、右侧 `shell/file/noVNC`、SSE/WS 传输链路。
- 平台化打底：引入 `tenant_id + 业务分组 + Agent级授权 + 平台/租户两级角色`。
- 会话入口双通道：
  - `auto`：调度触发自动运行并创建会话。
  - `manual`：用户新建会话或在自动会话中介入。

## 2. 已确认范围（本模块）
### 2.1 数据模型新增/扩展
- 新增 `agent_groups`
  - 字段：`group_id, tenant_id, name, code, status, created_at, updated_at`
- 新增 `agents`
  - 增强字段：`tenant_id, group_id, status, model_profile_id, tools_config, prompts(versioned), published_version`
- 新增 `model_profiles`
  - 字段：`profile_id, tenant_id, provider, model, api_base, params, secret_ciphertext, secret_key_id, secret_masked, status`
  - 说明：`api_key` 仅密文存储，Agent 通过 `model_profile_id` 选择模型档案
- 新增 `agent_schedules`
  - 字段：`schedule_id, tenant_id, agent_id, cron_expr, timezone, enabled, next_run_at, last_run_at, last_status, created_at, updated_at`
- 新增 `agent_permissions`
  - 字段：`tenant_id, agent_id, user_id, grant_type(view|operate), created_at, updated_at`
- 扩展 `sessions`
  - 新增字段：`tenant_id, group_id, agent_id, source_type(manual|auto), schedule_id, trigger_id, run_meta`
- 扩展 `users`
  - 新增字段：`tenant_id, platform_role(platform_admin|tenant_admin|tenant_user)`
  - 采用单租户用户模型：一个用户仅属于一个 `tenant_id`

### 2.2 API与报文规范
- 新增 Agent/Group/Schedule/Permission 管理接口（REST）。
- 新增接口全部沿用统一报文：`APIResponse{code,msg,data}`。
- 扩展 `/sessions` 列表返回字段：
  - `agent_id, agent_name, group_id, group_name, source_type`
  - 旧字段保持兼容。
- 扩展 `/sessions` 查询参数：
  - `group_id, agent_id, source_type`（可选）。
- SSE 双通道（冻结）：
  - 全局摘要流：`GET /sessions/stream`（左侧会话栏常驻订阅）
  - 会话详情流：`GET /sessions/{session_id}/stream`（中间时间线按需订阅）
- 兼容保留：旧 `POST /sessions` SSE 快照流继续可用，作为过渡路径。

### 2.3 调度执行（Celery 模型）
- `Celery Beat`：扫描 `agent_schedules` 到点触发，生成 `trigger` 并投递 broker。
- `Celery Broker`：承载排队与分发（Redis/RabbitMQ）。
- `Celery Worker`：消费任务、执行 Agent Flow、持续写入 session events。
- 业务状态保留：
  - trigger：`created -> pending -> queued -> running -> finished|cancelled`
  - session：`pending|running|waiting|completed`
- 可靠性：MVP 仅做幂等防重、状态对账、健康巡检；不做调度层自动重试/死信。

### 2.4 租户与权限护栏
- 所有核心查询强制附带 `tenant_id` 过滤。
- 唯一索引改为租户内唯一（例：`(tenant_id, agent_code)`）。
- 权限规则：
  - `tenant_user`：仅可见被授权 Agent 会话
  - `tenant_admin`：管理本租户
  - `platform_admin`：全局可见
- 审计日志记录：
  - 配置变更、授权变更、调度触发、手动介入

### 2.5 调度与队列模块功能清单（已冻结）
- 调度组件拆分：
  - `Celery Beat`：按 cron 生成 `trigger` 并投递 broker。
  - `Broker`：负责任务排队与分发（Redis/RabbitMQ）。
  - `Celery Worker`：执行 Agent Flow，持续写入 session events，回传结果状态。
  - `Reconciler`：对账 trigger/session 与 Celery 任务状态，修正异常态。
- 任务载荷（TriggerPayload）字段：
  - `trigger_id, tenant_id, agent_id, group_id, schedule_id, fire_at, priority`
  - `idempotency_key`（默认 `schedule_id + fire_at`），用于防重复触发。
  - `loop_config_snapshot`（冻结参数快照）。
- 状态机（调度态）：
  - `created -> pending -> queued -> running -> finished`
  - 取消支路：`pending|queued|running -> cancelled`
- 状态机（会话态，保持 ai-manus 兼容）：
  - `session.status` 仅使用：`pending/running/waiting/completed`
  - `waiting` 仅用于用户介入场景（例如登录、审批确认、人工补充信息）。
- 会话映射策略（保持会话复用原则）：
  - 每次 `trigger` 进入 `running` 前创建 1 个 `session`，`source_type=auto`。
  - 用户手动新建会话创建 `source_type=manual`。
  - 用户介入自动会话时，继续写入原 `session_id`（不拆新会话）。
  - 介入时若绑定 sandbox 已销毁/不可用，自动重建 sandbox 并回绑到当前 `session_id`。
  - 失败/超时/取消原因通过事件（`error/done/wait` + `reason_code`）表达，不新增顶层 `SessionStatus` 枚举。
  - 事件投递策略（新增）：
    - worker 写会话事件后，必须同步发布会话摘要事件到全局摘要流。
    - 在线用户无需主动发起 chat，也能在左侧实时看到自动任务创建与状态变化。
  - 取消与超时：
    - `pending|queued` 取消：不创建 sandbox。
    - `running` 取消：撤销 Celery 任务后立即销毁 sandbox。
    - `waiting` 超过 `WAITING_SANDBOX_IDLE_TIMEOUT_MINUTES=30` 自动销毁 sandbox；会话保留 `waiting`，后续用户介入再重建。
- 并发控制：
  - 全局并发上限：`SCHED_MAX_RUNNING_GLOBAL`（默认 20）。
  - 租户并发上限：`SCHED_MAX_RUNNING_PER_TENANT`（默认 5）。
  - Agent 并发上限：`SCHED_MAX_RUNNING_PER_AGENT`（默认 1）。
  - 运行前由 worker 申请并发令牌；失败回写 trigger `pending`，等待后续调度补位。
- 优先级规则（MVP）：
  - `priority` 取值：`high|normal|low`，默认 `normal`。
  - 组默认优先级可覆盖 Agent 默认优先级；触发任务最终优先级取两者更高者。
- 失败处理（MVP）：
  - 不做调度层自动重试、死信队列。
  - 优先依赖 Agent 回合内自纠（模型在单次运行中自我修正）。
  - 回合内仍不可恢复时，结束本次会话并写 `error` 事件。
- 恢复与幂等：
  - 服务启动执行对账扫描：修复 `running` 长时间悬挂任务并释放运行位。
  - 基于 `idempotency_key` 防止重复触发导致重复会话。
  - 会话已创建但 worker 崩溃时，不重放本次运行；等待下一次 cron 触发新运行。
  - Reconciler 周期规则：
    - `pending` 无 `celery_task_id` 重新投递。
    - `queued` 丢任务回写 `pending`。
    - `running` 失联收敛为 `finished + error` 并补偿释放令牌。
- 并发令牌协议（闭环）：
  - worker 开始执行前申请 `global/tenant/agent` 三层令牌。
  - 任一令牌申请失败，trigger 回写 `pending` 并设置 `next_retry_at`。
  - 正常结束/取消/超时/对账修复均会释放令牌。
- 心跳与超时：
  - `celery_worker_heartbeat` 由 worker 心跳探针提供。
  - 失联阈值：`45s`（默认）。
  - 单任务最大执行时长：`TASK_MAX_DURATION_MINUTES`（默认 30），超时直接结束本次运行。
- 可观测性（调度最小指标）：
  - `trigger_pending_count, trigger_queued_count, trigger_running_count`
  - `celery_queue_depth, beat_lag_seconds`
  - `run_success_rate, run_failed_rate, waiting_rate`
  - `celery_worker_alive_count, celery_worker_stale_count`
- 最小运维接口（REST，统一 `APIResponse`）：
  - `GET /scheduler/overview`：触发积压、队列深度、worker状态。
  - `POST /scheduler/triggers/{trigger_id}/cancel`：取消 `pending|queued|running` 任务。

### 2.5.1 调度闭环四点（冻结）
1. `Lease 生命周期`
- 三层令牌（global/tenant/agent）必须有申请、续约、释放、补偿回收全链路。
2. `取消语义`
- `cancel` 必须覆盖 `pending|queued|running`，并保证最终会话状态收敛。
3. `Beat 高可用`
- 仅允许一个有效调度者触发同一周期任务，避免重复触发。
4. `Reconciler 冲突决议`
- 对账修复与人工介入/手动取消冲突时，采用固定优先级与事件留痕，保证幂等可重放。

### 2.6 Agent Loop 状态机（本轮新增冻结）
- 说明：
  - 该状态机直接复用 ai-manus `PlanActFlow.AgentStatus`，前端主状态仍保持 `session.status=pending/running/waiting/completed`。
  - 保留 `automaton` 的 Agent 策略层（策略先决、统一工具入口、执行后治理）。
  - 保护策略参考 `automaton`（执行上限、无进展、短重试、循环检测），本轮不引入 `openclaw` loop 内核。
  - 不做调度层自动重试；仅允许 `Agent loop` 回合内有限自纠重试。
- 内部状态：
  - `idle`
  - `planning`
  - `executing`
  - `updating`
  - `summarizing`
  - `completed`
- 轮转主链：
  - `idle -> planning -> executing -> updating -> summarizing -> completed`
  - 执行过程中如需用户介入：发 `wait` 事件并置 `session.status=waiting`，用户消息后恢复 `executing`。
- 上限与限额（建议默认值）：
  - `MAX_ROUNDS_PER_RUN=24`
  - `MAX_TOOL_CALLS_PER_ROUND=3`
  - `MAX_TOOL_CALLS_PER_RUN=64`
  - `MAX_NO_PROGRESS_ROUNDS=3`（连续无进展则终止）
  - `RUN_TIMEOUT_SECONDS=1800`（30 分钟）
  - `THINK_TIMEOUT_SECONDS=90`
  - `TOOL_TIMEOUT_SECONDS=120`（可按工具覆盖）
- 重试策略（仅回合内）：
  - `MAX_STEP_RETRY=2`（同一回合同类瞬时错误最多重试 2 次）
  - 退避：`1s -> 2s`，带 `0~20%` jitter。
  - 可重试：网络抖动、页面临时不可达、sandbox 短暂不可用。
  - 不可重试：权限拒绝、参数非法、策略拒绝、配置缺失。
  - 超出重试上限：写 `error` 事件并结束会话（`session.status=completed`）。
- Agent 策略层（每轮固定管线）：
  - `intent`：基于目标与当前 step 形成动作意图。
  - `policy_check`：策略引擎评估 allow/deny、风险级别与兜底动作。
  - `tool_route`：统一入口执行被放行工具。
  - `post_process`：输出清洗、摘要化、审计落库。
  - `next_action`：继续执行 / 重新规划 / 人工介入 / 结束。
- 终止条件：
  - 短退避仅作为回合内计时器，不作为状态，不写 `sleep*` 语义。
  - 巡检无可处理事项：直接结束本次运行并写 `done` 事件（不长睡，等待下次 cron）。
  - 达成目标：会话 `status=completed`，写 `done` 事件。
  - 用户介入需求：`waiting`（会话保持可继续，后续用户消息恢复运行）。
  - 达到执行上限或超时：会话 `status=completed`，写 `error` 事件（含原因码）。
  - 用户取消：会话 `status=completed`，写取消原因事件。
- 用户介入恢复规则：
  - 用户在 `waiting` 会话发消息后，创建新的执行 attempt，沿用同一 `session_id`。
  - 若原 sandbox 已销毁/不可用，先自动重建 sandbox，再恢复到 `executing`。

## 3. 前端改动（小改，强复用）
### 3.1 左侧会话栏分组展示
- 基于 `sessions[]` 的扩展字段，在前端聚合为：`group -> sessions`。
- 分组排序：按组内最近活跃会话时间倒序。
- 默认展开：当前会话所属组展开，其余折叠。
- 用户手动会话支持两种入口：绑定 Agent / 不绑定 Agent（仅 `goal`）。
- 无 `agent/group` 的手动会话归入创建者个人分组：`personal/{user_id}`。

### 3.2 兼容性
- 复用现有 `SessionItem` 行为：点击跳转、删除、未读、运行态动画、SSE刷新。
- SSE 连接策略（冻结）：
  - 每个在线前端保持 1 条全局摘要 SSE。
  - 当前打开会话额外保持 1 条会话详情 SSE。
  - 两条连接并行不冲突，按 `session_id/event_id` 路由。
- 中间对话框保留，用户可对自动会话继续发送消息介入。
- 右侧工具面板保持现有交互：shell/file/noVNC 复用。

## 4. 测试验收清单（本模块）
- 会话流：自动触发后进入正确分组，点击后时间线/工具面板正常。
- 在线感知流：用户停留页面且未发 chat 时，自动任务触发后左侧可实时看到新会话与运行状态。
- 介入流：自动运行中用户发消息，事件写入同一会话。
- 手动流：用户新建会话可运行；首次使用 browser/file/shell 时按需创建 sandbox。
- 重建流：用户介入时若 sandbox 已销毁，系统自动重建并在同一会话继续。
- 权限流：普通用户仅见授权 Agent 分组与会话；租户管理员可见租户内全部。
- 隔离流：不同租户数据互不可见；查询均命中 `tenant_id` 过滤。
- 调度流：并发上限生效，超限 pending，空槽自动补位。
- 兼容流：旧会话接口可继续使用，新字段不破坏旧逻辑。

## 5. 当前默认假设（冻结）
- 运行实体：`Session扩展`
- 调度模式：`Celery Beat + Broker + Worker`
- Agent配置：`Mongo版本化`
- 多租户：`单库行级隔离`
- 角色：`platform_admin / tenant_admin / tenant_user`
- 授权粒度：`Agent级`
- 用户模型：`单租户用户`

## 6. 剩余模块待确认清单（下一轮逐项确认）
### 6.1 上下文与记忆模块
- 已冻结，见 [02-context-memory.md](/Users/zuos/code/github/ai-manus/md/modules/02-context-memory.md)。
- 冻结要点：
  - 复用 ai-manus `planner/execution` 双层记忆。
  - 浏览器内容先剪裁后入 LLM，上下文与回放快照分层。
  - 分级压缩采用 `ai-manus compact + automaton stage` 融合策略。

### 6.2 工具与执行沙箱模块
- 已冻结并通过评审，见 [03-tools-sandbox.md](/Users/zuos/code/github/ai-manus/md/modules/03-tools-sandbox.md)。
- 通过前提：`03` 中 `P0 改造清单` 必须完成（含 sandbox 自动重建与上下文恢复闭环）。

### 6.3 调度与可靠性模块
- 已冻结，见 `2.5 调度与队列模块功能清单（已冻结）`。

### 6.4 观测与告警模块
- 指标清单（成功率、延迟、pending时长、人工介入率）。
- 日志与链路追踪标准（trace_id 在 session/event/tool 全链路透传）。
- 告警阈值与通知渠道（企业微信/飞书/邮件）。

### 6.5 平台管理模块
- 租户创建/停用流程。
- 用户邀请与账号生命周期（激活、禁用、离职交接）。
- 权限审批流（谁有权授予 Agent 访问权限）。

### 6.6 配置发布与回滚模块
- Agent 配置发布流程（草稿、发布、回滚）。
- 配置生效策略（立即生效或下次任务生效）。
- 变更审计可视化（对比 diff 与操作人）。

### 6.7 Skills与工具执行策略模块
- 参考 openclaw 的 skills 生命周期与策略合并机制。
- 参考 automaton 的统一工具执行入口与 policy engine。
- 草案文档见 [08-skills-tool-runtime.md](/Users/zuos/code/github/ai-manus/md/modules/08-skills-tool-runtime.md)。
