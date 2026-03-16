# 04 调度与队列模块

## 状态
- 已冻结（Celery 版）。

## 基线
- 调度执行采用 `Celery Beat + Broker + Worker`。
- `Beat` 负责按 cron 触发，不直接执行任务。
- `Worker` 负责执行 Agent Flow，并写回 session events。
- 业务层保留 `pending`：表示“任务已受理，等待执行资源”。
- 用户介入保留 ai-manus 语义：`session.status=waiting`（例如登录/确认）。
- 运行时部署策略：`api/worker/worker-beat` 复用同一后端镜像，通过不同启动命令区分角色。
- 服务拆分策略：`worker` 与 `worker-beat` 为两个独立服务；`worker-beat` 默认单副本。

## 核心时序（冻结）
- `trigger -> session(auto) -> celery_task -> worker -> sandbox`
- 业务状态机（trigger）：
  - `created -> pending -> queued -> running -> finished|cancelled`
- 会话状态机（session，兼容前端）：
  - `pending|running|waiting|completed`

## 设计要点（冻结）
1. 业务状态与 Celery 状态解耦
- 不直接用 Celery `PENDING/STARTED/SUCCESS/FAILURE` 作为前端业务状态。
- 以 Mongo 的 `trigger/session` 状态为真相源，Celery 状态用于运行态对账。

2. 并发控制
- 全局/租户/Agent 并发上限保留。
- 由 Worker 启动前获取并发令牌，拿不到则回写 `pending` 并延后执行。

3. 幂等与防重
- `idempotency_key = schedule_id + fire_at`（默认）。
- 同 key 仅允许一个有效自动会话进入 `running`。

4. 取消与超时
- `pending` 取消：不创建 sandbox。
- `running` 取消：撤销 Celery 任务并销毁 sandbox。
- `waiting` 空闲超时：销毁 sandbox，会话保持 `waiting`。

5. 可靠性边界（MVP）
- 不做调度层自动重试/死信策略。
- 失败由本次 run 收敛为事件原因，等待下次 cron 触发。

6. 实时分发边界（新增）
- 调度触发创建 `auto session` 后，必须发布 `session_upsert` 到全局会话摘要流。
- worker 执行态变化（running/waiting/completed）必须同步发布 `session_status_changed`。
- 不要求用户主动发起 chat 才能看到自动任务实时变化。

## 闭环设计 A：状态对账恢复（Reconciler）
1. 对账频率
- 周期任务每 `30s` 扫描一次 `agent_triggers` 与 `sessions`，并查询 Celery 任务状态。

2. 对账规则（冻结）
- `pending` 且长时间无 `celery_task_id`：
  - 重新投递 Celery，保持原 `idempotency_key`。
- `queued` 但 broker 无任务记录：
  - 回写 `pending` 并记录 `reason_code=CELERY_TASK_LOST`。
- `running` 但 worker 心跳失联/任务不存在：
  - 结束为 `finished`，会话收敛 `completed + error`，并释放并发令牌。
- `session=completed` 但 trigger 非终态：
  - trigger 强制收敛到 `finished`（成功/失败由最后事件判断）。

3. 状态迁移约束
- 所有迁移使用乐观锁版本号（`version`）CAS 更新，防止重复写覆盖。
- 每次对账修正必须写审计事件：`scheduler_reconciled`。
- 冲突优先级（冻结）：
  - `manual_cancel` > `human_waiting` > `reconciler_fix` > `normal_progress`
  - 当对账与人工操作冲突时，按优先级收敛并写 `reason_code=STATE_CONFLICT_RESOLVED`。

## 闭环设计 B：幂等键 + 并发令牌
1. 幂等键协议
- 默认：`idempotency_key = schedule_id + fire_at`。
- 约束：`(tenant_id, agent_id, idempotency_key)` 唯一。
- 重复触发命中已存在有效 trigger 时，直接返回已存在记录，不新建会话。

2. 并发令牌协议
- worker 执行前原子申请 3 级令牌：
  - 全局令牌 `global`
  - 租户令牌 `tenant:{tenant_id}`
  - Agent 令牌 `agent:{agent_id}`
- 任一级申请失败：
  - 不执行任务，trigger 回写 `pending` 并设置 `next_retry_at`。

3. 释放与补偿
- 正常结束/取消/超时：立即释放令牌。
- 人工介入进入 `waiting`：释放执行令牌（不占 worker 槽位）。
- 对账器发现“僵尸 running”时补偿释放令牌并写 `reason_code=LEASE_RECOVERED`。

## 闭环设计 C：取消语义（Deterministic Cancel）
1. 取消入口
- 统一通过 `POST /scheduler/triggers/{trigger_id}/cancel`。

2. 取消规则（冻结）
- `pending|queued`：
  - 标记 `cancelled`，不创建 sandbox，不占并发令牌。
- `running`：
  - 发起 Celery revoke（soft + hard timeout 兜底）。
  - 会话收敛为 `completed`，事件写 `error(reason_code=CANCELLED_BY_USER)`。
- `waiting`：
  - 允许取消，直接结束会话并销毁可能残留的 sandbox。

3. 取消一致性
- 若 revoke 后任务仍短暂执行，对账器二次收敛，保证最终态一致。

## 闭环设计 D：Beat 高可用（Single Active Scheduler）
1. 目标
- 多实例部署下，同一周期任务只触发一次。

2. 机制（冻结）
- 使用分布式调度锁（建议 Redis/DB lease）：`beat_leader_lock`。
- 锁持有者周期续约；续约失败立即降级为 follower。
- follower 不执行触发，仅健康探测等待接管。

3. 接管规则
- leader 失联超过阈值（建议 2x 续约周期）后，新的实例可抢占并继续触发。
- 接管期间依赖 `idempotency_key` 抵御边界重复触发。

## 主文档
- [agent-management-module.md](/Users/zuos/code/github/ai-manus/md/agent-management-module.md) 中 `2.5 调度与队列模块功能清单（已冻结）`。
