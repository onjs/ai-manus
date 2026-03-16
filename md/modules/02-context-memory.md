# 02 上下文与记忆模块

## 状态
- 已冻结。

## 设计目标
- 在 `Mongo + Redis` 前提下实现多 Agent 会话的上下文闭环。
- 复用 `ai-manus` 的 `Planner + Execution` 双层记忆机制，不改主语义。
- 复用 `automaton` 的分级压缩策略（Python 重写），控制长会话上下文增长。
- 浏览器上下文默认走“剪裁后文本”，截图用于回放，不直接塞入 LLM 上下文。
- 保证可追溯、可恢复、可审计，不依赖 sandbox 长期存活。

## 与现状对齐（ai-manus）
- 现状记忆入口：`BaseAgent.ask_with_messages()` 读取并写回 `AgentDocument.memories`。
- 现状压缩入口：`PlanActFlow` 每步执行后调用 `executor.compact_memory()`。
- 现状浏览器工具：`browser_view/browser_navigate` 大内容会被压缩替换为 `(removed)`。
- 本模块改造原则：
  - 保留上述调用链，不重写 agent 主循环。
  - 在原有 compact 基础上增加“分级压缩 + 锚点重组 + 完整性校验”。

## 存储分层（冻结）
- `L0 运行内存（Worker进程）`
  - 当前回合工作集：系统提示词、最近 turns、待执行工具结果、临时推理状态。
  - 生命周期：单次运行期内。
- `L1 Redis 热态`
  - 会话热上下文索引、最近事件引用、token 计数、压缩阶段、调度恢复游标。
  - 生命周期：小时级到天级 TTL，用于快速读取与并发控制。
- `L2 Mongo 持久态`
  - 会话事件流、压缩事件、检查点快照、长期记忆条目、工具输出索引。
  - 生命周期：业务策略级长期保留。

## 双层记忆模型（冻结）
- `planner_memory`
  - 用途：保存目标、约束、步骤账本、决策依据。
  - 特征：低频更新，高稳定性，优先保留。
- `execution_memory`
  - 用途：保存工具调用结果、中间观察、错误修复经验。
  - 特征：高频更新，可压缩可裁剪。
- 装配规则：
  - 每轮先注入 `planner_memory` 的锚点块，再注入 `execution_memory` 的最近窗口。
  - 不把整段历史重复追加到 prompt，采用覆盖重组。

## 上下文闭环流程（冻结）
1. `Assemble`
- 按预算组装上下文（系统提示词 + 锚点区 + 最近 turns + 压缩引用 + 关键记忆）。
2. `Clip Browser Context`
- 对浏览器内容做结构化剪裁（正文、可交互元素、关键字段）。
- 截图与原始大块 DOM 仅生成 `artifact_ref`，不直接拼入上下文。
3. `Evaluate`
- 计算 utilization，基于阈值产出压缩计划。
4. `Compress`
- 执行 Stage 压缩动作并写压缩事件。
5. `Re-Assemble`
- 压缩后重新组装上下文，确保不超窗。
6. `Infer + Tool`
- 执行模型调用与工具调用。
7. `Ingest`
- 将本回合输入、输出、工具结果、摘要与经验落库。
8. 下一回合重复 1-7，形成稳定闭环。

## 浏览器上下文剪裁（冻结）
- 输入来源：
  - `browser_use`：`llm_representation(include_screenshot=False)`。
  - `playwright`：可见 DOM -> markdown 文本。
- 剪裁规则：
  - 仅保留当前任务相关区域（标题、关键正文、表单/按钮/输入框、错误提示）。
  - 去除样式、脚本、冗余导航、重复区块。
  - 单次浏览器观察设置 `max_chars/max_tokens` 上限，超限部分转引用。
- 产物：
  - `browser_clip_text`（给 LLM）。
  - `browser_artifact_ref`（给回放/审计）。

## 融合算法（ai-manus + automaton，冻结）
- 目标：
  - 保留 ai-manus 当前每步 compact 的轻量清理能力。
  - 增加 automaton 风格 5-stage 渐进压缩级联。
  - 增加“锚点不可压缩 + 每轮重组”机制，防止 goal drift。

### A. 锚点区（不可压缩、每轮必注入）
- `goal_anchor`
  - `goal_statement`
  - `done_criteria[]`
  - `hard_constraints[]`
- `step_ledger`
  - `current_step_id`
  - `steps_status_map`（`pending/running/completed/failed/waiting`）
  - `blocked_reasons[]`
- `critical_refs`
  - 关键证据 `artifact_ref[]`（每条一行摘要）

规则：
- 锚点区来自 `Mongo 真相源`（plan/steps/session），不是从旧 prompt 回读。
- 锚点区采用覆盖重组，不做每轮追加。

### B. 非锚点区（可压缩）
- 最近 turns（短窗口）
- 工具输出（大文本优先引用化）
- 历史事件与观察
- `execution_memory` 历史块

### C. 预算与触发
- `prompt_capacity = model_context_window - reserve_tokens`
- `compression_headroom = total_tokens * 10%`
- 当 `used_tokens >= prompt_capacity - compression_headroom` 时进入压缩评估。
- 阶段阈值：
  - Stage1 `>70%`
  - Stage2 `>80%`
  - Stage3 `>85%`
  - Stage4 `>90%`
  - Stage5 `>95%`

### D. 阶段动作
- Stage1 `compact_tool_results`
  - 压缩旧工具大输出为 `artifact_ref + 摘要`。
- Stage2 `compress_turns`
  - 压缩旧 turns 为结构化短摘要（动作/结果/异常/结论）。
- Stage3 `summarize_batch`
  - 按批总结（建议批大小 5，summary max tokens 220）。
- Stage4 `checkpoint_and_reset`
  - 生成 checkpoint，保留最近窗口（建议最近 5 turns）并重建上下文。
  - 必须保留 active tasks/spec 与锚点区。
- Stage5 `emergency_truncate`
  - 紧急截断非锚点历史（建议仅保留最近 3 turns）。
  - 锚点区与关键引用不参与截断。

### E. 压缩后完整性校验（硬约束）
- `goal_hash` 不变。
- `step_ledger` 一致（步骤总数、各状态计数、`current_step_id` 一致）。
- `critical_refs` 可达（引用仍可读取）。
- 若任一校验失败：
  - 回滚到最近 checkpoint。
  - 本轮降级为更保守压缩策略并记录 `compression_warning`。

### F. 高关注注入
- 每轮推理前把“锚点摘要块”放在系统消息高注意区域。
- 摘要块只放当前最小必要状态，不放历史全文。

## 事件流压缩/裁剪定义（冻结）
- `压缩（Compaction）`
  - 不删除事件，只将大内容替换为紧凑表示：
  - `content -> compacted_ref`（摘要文本、artifact id、snapshot id）。
  - 保留事件主键、时间、类型、关联对象，保证审计链不断裂。
- `裁剪（Prune）`
  - 在满足“已压缩且可回放”的前提下，按策略物理清理低价值旧内容。
  - MVP 默认不开启物理裁剪，仅保留策略与离线任务入口。

## 数据模型建议（冻结）
- `session_events`（Mongo）
  - `event_id, tenant_id, session_id, agent_id, type, content, compacted_ref, token_count, created_at`
- `context_checkpoints`（Mongo）
  - `checkpoint_id, tenant_id, session_id, turn_no, summary, active_tasks, key_decisions, created_at`
- `agent_memories`（Mongo）
  - `agent_id, tenant_id, memories.planner, memories.execution, updated_at`
- `memory_items`（Mongo，可选扩展）
  - `memory_id, tenant_id, agent_id, scope(session|agent|tenant), kind(working|episodic|semantic|procedural), content, score, created_at`
- `context_hot_state`（Redis）
  - `ctx:{session_id}:token_usage`
  - `ctx:{session_id}:compression_stage`
  - `ctx:{session_id}:recent_event_refs`

## 恢复策略（冻结）
- Worker 重启或任务恢复时：
  - 先读 `context_checkpoints` 最新快照。
  - 再补齐快照之后的 `session_events`。
  - 读取 `agent_memories.memories.planner/execution`。
  - 重建 `L0` 运行上下文并继续当前 `session`，不新建会话。

## 边界约束（冻结）
- 本期不引入 Mem0、向量数据库、MCP 记忆插件。
- 不强依赖 `md` 文件作为主记忆存储；若需要仅可做“可读镜像”，真相源为 Mongo/Redis。

## 验收口径（冻结）
- 长会话可持续运行且上下文不漂移。
- 压缩触发后无爆窗，且关键步骤成功率可接受。
- 浏览器观察不会把整页 DOM/截图直接灌入 LLM 上下文。
- sandbox 销毁后，历史回放完整可读。
- 任务中断恢复后，能在原 `session_id` 继续执行。
- 压缩前后 `goal_hash` 与 `step_ledger` 一致，若不一致可自动回滚到最近 checkpoint。
