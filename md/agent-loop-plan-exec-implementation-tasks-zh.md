# Multi-Agent Plan-Exec 实施任务拆解（MVP）

## 1. 目标
- 将融合方案落地为可迭代开发任务。
- 保证 `Plan -> Step Execute -> Step Update` 闭环可运行。
- 兼容现有 ai-manus 前端展示链路（会话、时间线、noVNC、回放）。

## 2. 里程碑
1. `M1 数据与事件底座`
2. `M2 Plan/Step 执行主链`
3. `M3 保护算法与失败治理`
4. `M4 介入与 sandbox 重建`
5. `M5 前端映射与联调验收`

## 3. 任务清单
### M1 数据与事件底座
1. `PLE-M1-01` 会话扩展字段补齐
- 范围：`sessions` 增加 `source_type, agent_id, group_id, run_meta` 运行态字段。
- 验收：老会话兼容读取；新会话可写入 run 元信息。

2. `PLE-M1-02` Plan/Step 持久化模型
- 范围：新增 `plan`、`steps` 结构（可嵌入 session 或独立集合）。
- 验收：可按 `session_id` 查询计划与步骤，支持状态更新。

3. `PLE-M1-03` Step-first 事件模型
- 范围：新增事件类型：
  - `plan_created`
  - `step_created`
  - `step_started`
  - `tool_calling`
  - `tool_called`
  - `step_completed`
  - `step_failed`
  - `sandbox_recreated`
  - `sandbox_destroyed`
- 验收：每个事件强制包含 `session_id, agent_id, step_id, timestamp`。

4. `PLE-M1-04` artifact 引用规范
- 范围：大输出统一 `artifact_ref`（GridFS），事件只存摘要+引用。
- 验收：会话查询不因大输出变慢，回放可取正文。

### M2 Plan/Step 执行主链
1. `PLE-M2-01` Plan 生成器
- 范围：基于 `AGENTS.md + 当前上下文` 生成结构化步骤。
- 约束：上下文由 `planner/execution` 双层记忆装配。
- 验收：run 启动时必产出 `plan_created + step_created*` 事件。

2. `PLE-M2-02` Step 执行器
- 范围：严格按 step 顺序执行工具调用，按事件回写。
- 验收：每步至少经过 `step_started -> (tool_*)* -> step_completed|step_failed`。

3. `PLE-M2-03` Step 更新器
- 范围：执行后根据结果更新后续 step（状态/补充信息）。
- 验收：计划可前进，失败步可终止本 run。

4. `PLE-M2-04` run 结束归档
- 范围：复用 ai-manus 语义收敛会话结束：
  - 成功/失败/超时/取消 -> `session.status=completed`（通过 `done/error` 事件区分原因）
  - 需人工介入 -> `session.status=waiting` + `wait` 事件
- 验收：前端会话状态保持 `pending/running/waiting/completed` 兼容。

5. `PLE-M2-05` Agent 策略层接入
- 范围：在回合主链加入固定策略管线：
  - `intent -> policy_check -> tool_route -> post_process -> next_action`
- 验收：每次工具调用前都有策略判定结果；拒绝原因可追溯。

6. `PLE-M2-06` 浏览器上下文剪裁接入
- 范围：browser 工具结果先剪裁再入 LLM，上下文与回放分层。
- 验收：LLM 上下文不出现整页 DOM/截图二进制；回放仍可读。

### M3 保护算法与失败治理
1. `PLE-M3-01` 执行上限守卫
- 范围：支持上限参数：
  - `MAX_ROUNDS_PER_RUN`
  - `MAX_TOOL_CALLS_PER_ROUND`
  - `MAX_TOOL_CALLS_PER_RUN`
  - `RUN_TIMEOUT_SECONDS`
- 验收：触顶后稳定退出并给出明确错误事件。

2. `PLE-M3-02` 无进展检测
- 范围：支持 `MAX_NO_PROGRESS_ROUNDS`。
- 验收：连续无进展时终止并产出对应 `error/done` 事件。

3. `PLE-M3-03` 回合内短重试
- 范围：`MAX_STEP_RETRY` + 短退避（jitter）。
- 验收：仅 run 内重试，不触发调度层重试。

4. `PLE-M3-04` 工具循环检测
- 范围：接入重复调用/轮询无进展/ping-pong 检测。
- 验收：触发 warning/critical 事件，critical 可中断当前 step。

5. `PLE-M3-05` 错误分流与策略协同
- 范围：将 `retryable / non-retryable / human_required` 与策略引擎输出对齐。
- 验收：可重试错误进入回合内短重试；人工需求进入 `session.status=waiting`；不可重试直接失败并产出错误事件。

### M4 介入与 sandbox 重建
1. `PLE-M4-01` 双入口统一
- 范围：`auto` 与 `manual` 入口统一进入 run coordinator。
- 验收：用户介入自动会话不拆新 session。

2. `PLE-M4-02` waiting 语义闭环
- 范围：需要登录/确认时发 `wait` 事件并置 `session.status=waiting`。
- 验收：用户消息后可恢复执行（沿用同一 `session_id`）。

3. `PLE-M4-03` sandbox 自动重建
- 范围：介入或执行时发现 sandbox 不可用，自动创建并回绑当前会话。
- 验收：写 `sandbox_recreated` 事件，继续同一 `session_id`。

4. `PLE-M4-04` auto 会话结束销毁
- 范围：`source_type=auto` 的会话结束后销毁 sandbox。
- 验收：写 `sandbox_destroyed` 审计事件。

### M5 前端映射与联调验收
1. `PLE-M5-01` step 时间线映射
- 范围：前端中间区按 `step_id` 展示时间线。
- 验收：步骤状态、工具调用、失败信息可读。

2. `PLE-M5-02` 右侧实时与回放切换
- 范围：
  - 运行中 step：noVNC 实时查看
  - 已结束 step：Mongo/GridFS 回放
- 验收：sandbox 销毁后回放仍可用。

3. `PLE-M5-03` SSE 兼容扩展
- 范围：增加 step 字段，不破坏旧解析。
- 验收：旧页面不报错，新页面可消费 step 事件。

4. `PLE-M5-04` E2E 回归
- 范围：自动运行、用户介入、sandbox 重建、回放完整性。
- 验收：关键链路通过。

## 4. 依赖关系
1. `M1` 是 `M2/M3/M4/M5` 前置。
2. `M2` 完成（含策略层接入）后可并行推进 `M3` 与 `M4`。
3. `M5` 依赖 `M2 + M4` 至少完成主链路。

## 5. API 拆解（MVP）
1. `GET /sessions/:id/plan`
- 返回当前会话 plan + steps。

2. `POST /sessions/:id/resume`
- 用户介入恢复执行（同 `session_id`）。

3. `GET /sessions/:id/steps/:step_id/artifacts`
- 拉取 step 关联快照与大输出引用。

4. 扩展 `GET /sessions` 与 SSE payload
- 增加 `agent_id/group_id/source_type/run_meta.summary`。

## 6. 配置项（MVP 默认）
- `MAX_ROUNDS_PER_RUN=24`
- `MAX_TOOL_CALLS_PER_ROUND=3`
- `MAX_TOOL_CALLS_PER_RUN=64`
- `MAX_NO_PROGRESS_ROUNDS=3`
- `RUN_TIMEOUT_SECONDS=1800`
- `MAX_STEP_RETRY=2`

## 7. 风险与控制
1. 风险：step 事件过多导致会话膨胀
- 控制：artifact_ref 化 + 事件摘要化。

2. 风险：sandbox 重建后上下文断裂
- 控制：恢复前重放最近 step 上下文与关键工具状态。

3. 风险：前端兼容回归
- 控制：SSE 扩展字段向后兼容，旧字段不变。

## 8. 完成定义（DoD）
1. 任一自动 run 都能看到结构化 step 时间线。
2. 运行中可实时 noVNC；结束后可回放。
3. 用户介入时 sandbox 若已销毁可自动重建并继续。
4. run 内保护算法生效，且不依赖调度层重试。

## 9. 建议开工顺序（两周版）
1. 第 1-2 天
- 完成 `PLE-M1-01 ~ PLE-M1-04`。

2. 第 3-5 天
- 完成 `PLE-M2-01 ~ PLE-M2-04`，打通最小 run 闭环。

3. 第 6-7 天
- 完成 `PLE-M4-01 ~ PLE-M4-04`，先打通介入与 sandbox 重建。

4. 第 8-9 天
- 完成 `PLE-M3-01 ~ PLE-M3-04`，补齐保护算法。

5. 第 10 天
- 完成 `PLE-M5-01 ~ PLE-M5-04` 联调与回归。
