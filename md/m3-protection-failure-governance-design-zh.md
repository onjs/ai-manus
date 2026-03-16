# M3 设计评审稿：保护算法与失败治理（不含代码实现）

## 范围与目标
- 覆盖 `PLE-M3-01 ~ PLE-M3-04`。
- 在不引入调度层自动重试的前提下，建立 run 内稳定保护机制：
  - 执行上限守卫
  - 无进展检测
  - 回合内短重试
  - 工具循环检测
- 保持你已确认的决策：
  - 串行 step
  - step 失败即终止 run
  - 结束事件复用 `done/error/wait`，不新增终态枚举

---

## 1. 设计原则
1. 失败优先可解释
- 每次中断必须能回答“为什么停”。

2. 限制在 run 内自纠
- 不跨调度周期自动重试，不进入死信模型。

3. 防止无意义消耗
- 超出执行上限、循环、无进展必须尽早熔断。

4. 保持前端可观察
- 关键保护动作必须发事件并可回放。

---

## 2. 保护层级（从外到内）
1. `Run Limit Guard`（全局硬上限）
2. `Step Limit Guard`（单步硬上限）
3. `No-Progress Guard`（连续无进展熔断）
4. `Retry/Backoff Guard`（仅瞬时错误短重试）
5. `Tool Loop Guard`（重复调用/轮询/乒乓）

说明：
- 任一 guard 命中 critical 都可终止当前 step 或 run。

---

## 3. 参数与默认值（M3）

## 3.1 Run 级参数
- `MAX_ROUNDS_PER_RUN=24`
- `MAX_TOOL_CALLS_PER_RUN=64`
- `RUN_TIMEOUT_SECONDS=1800`
- `MAX_NO_PROGRESS_ROUNDS=3`

## 3.2 Step 级参数
- `MAX_TOOL_CALLS_PER_ROUND=3`
- `MAX_STEP_RETRY=2`
- `STEP_TIMEOUT_SECONDS=420`（建议 7 分钟，后续可按工具覆盖）

## 3.3 Backoff 参数
- `RETRY_BACKOFF_BASE_MS=1000`
- `RETRY_BACKOFF_MULTIPLIER=2.0`
- `RETRY_BACKOFF_MAX_MS=4000`
- `RETRY_JITTER=0.2`

---

## 4. 失败分类与处理策略

## 4.1 可重试（run 内）
- 网络抖动、上游短暂 5xx、浏览器瞬时加载失败、sandbox 短暂不可用
- 处理：
  - 当前 step 内重试
  - 采用短退避（jitter）
  - 超出 `MAX_STEP_RETRY` -> step failed -> run failed

## 4.2 不可重试
- 策略拒绝（tool denied）
- 参数错误（invalid args/schema）
- 权限拒绝
- 配置缺失
- 明确业务失败（例如审批被拒）
- 处理：
  - 直接 step failed -> run failed

## 4.3 等待人工（非失败）
- 登录、二次确认、审批输入等
- 处理：
  - `waiting`
  - `session.status=waiting`
  - 发 `wait` 事件，等待用户介入

---

## 5. 算法定义（伪流程）

## 5.1 Run 主循环保护
1. 每轮开始先检查：
- `run_elapsed > RUN_TIMEOUT_SECONDS` -> timeout
- `round_count > MAX_ROUNDS_PER_RUN` -> failed(limit)
- `tool_calls_total > MAX_TOOL_CALLS_PER_RUN` -> failed(limit)

2. 执行当前 step 后计算进展：
- 若状态推进、有效输出、证据新增任一成立 -> `progress=true`
- 否则 `no_progress_count += 1`

3. 当 `no_progress_count >= MAX_NO_PROGRESS_ROUNDS`：
- 触发 `run_guard_triggered(action=no_progress_breaker)`
- 终止 run（failed/noop 取决于上下文）

## 5.2 Step 内重试流程
1. step 执行失败
2. 分类错误：
- retryable -> backoff -> retry
- non-retryable -> fail fast
3. 当 `retry_count > MAX_STEP_RETRY`：
- step failed -> run failed

## 5.3 Loop Detection（参考 automaton）

### 检测器
1. `generic_repeat`
- 同工具 + 同参数 hash 连续重复

2. `known_poll_no_progress`
- 轮询工具连续输出同结果 hash

3. `ping_pong`
- 两个工具 A/B 交替重复且无进展

4. `global_circuit_breaker`
- 累积工具调用达到全局阈值且无进展

### 阈值
- `warning_threshold=10`
- `critical_threshold=20`
- `global_circuit_breaker_threshold=30`

### 动作
- warning：写事件，不中断
- critical：中断当前 step 并标记 failed

---

## 6. 事件与可观测性设计

## 6.1 新增保护事件（timeline.action）
- `guard_warning`
- `guard_triggered`
- `retry_scheduled`
- `retry_exhausted`
- `loop_detected_warning`
- `loop_detected_critical`

## 6.2 payload 最小字段
- `guard_name`
- `reason_code`
- `threshold`
- `current_value`
- `step_id`
- `run_id`

## 6.3 指标建议（M3）
- `run_timeout_count`
- `run_limit_exceeded_count`
- `step_retry_total`
- `step_retry_exhausted_count`
- `no_progress_break_count`
- `loop_warning_count`
- `loop_critical_count`

---

## 7. 与现有结构的对接点（设计级）
- [plan_act.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/flows/plan_act.py)
  - 插入 run/step guard 检查点
- [base.py](/Users/zuos/code/github/ai-manus/backend/app/domain/services/agents/base.py)
  - 保留现有 tool retry，但升级为可配置化并回传 retry 元信息
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/domain/models/event.py)
  - 新增 guard/retry/loop 事件 payload
- [event.py](/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/event.py)
  - 增加 SSE 映射

---

## 8. 验收场景（只定义，不写代码）

### 8.1 Run 超时
- 构造长任务超过 `RUN_TIMEOUT_SECONDS`
- 预期：
  - 触发 `guard_triggered(run_timeout)`
  - run 结束为 `timeout`

### 8.2 Step 重试成功
- 第一次失败（retryable），第二次成功
- 预期：
  - 出现 `retry_scheduled`
  - step 最终 `completed`

### 8.3 Step 重试耗尽
- 持续 retryable 失败超过 `MAX_STEP_RETRY`
- 预期：
  - `retry_exhausted`
  - step failed，run failed

### 8.4 无进展熔断
- 连续多轮无状态推进
- 预期：
  - `guard_triggered(no_progress_breaker)`
  - run 终止

### 8.5 工具循环熔断
- 同一工具同参重复调用超过 critical 阈值
- 预期：
  - `loop_detected_critical`
  - 当前 step 终止

---

## 9. M3 评审结论（已确认）
1. `STEP_TIMEOUT_SECONDS=420`：采用。
2. 无进展熔断终态：默认 `failed`，仅“确实无任务”场景标记 `noop`。
3. 循环检测阈值：采用 `warning=10 / critical=20 / global=30`，后续可配置化。
