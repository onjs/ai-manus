# 04 调度与队列模块 开发任务清单

## M1 调度基础设施（Worker Beat + API Executor）
1. `worker-beat` 按 `task_schedule` cron 创建 trigger（仅调度，不执行）
2. API 内置执行器（Executor Loop）认领 pending trigger 并执行
3. Beat leader 选举与续约（单活调度）
4. 镜像与服务策略落地：
   - `api/worker-beat` 复用同一后端镜像
   - `worker-beat` 默认仅 1 副本

## M1.1 Loop 参数传递对齐
1. Beat 触发时附带 `loop_config_snapshot` 到 `TriggerPayload`
2. API 执行器启动 run 时写入 `run_meta.loop.config_snapshot`
3. 保障快照与冻结参数一致，不允许运行中漂移

## M2 业务状态机与幂等
1. trigger 状态机：`created|pending|running|finished|cancelled`
2. `idempotency_key` 防重（`task_schedule_id + fire_at` 唯一键）
3. 保留业务 `pending`
4. 状态写入采用 CAS 版本号，避免并发覆盖

## M2.1 状态与关联映射
1. 会话态复用 ai-manus：`pending|running|waiting|completed`
2. 关联链落库：`task_schedule_id -> task_id -> trigger_id -> session_id -> executor_run_id -> sandbox_id`
3. `executor_run_id` 写入 `run_meta.dispatch`
4. 会话摘要事件：`session_upsert/session_status_changed/session_unread_changed`

## M3 并发与配额控制
1. 全局/租户/Agent 并发上限
2. API 执行器执行前申请并发令牌（原子 Lua/事务），失败回写 `pending`
3. `waiting` 会话不占执行槽位
4. 令牌释放补偿（完成/取消/超时/对账回收）

## M4 取消、超时、恢复
1. 取消 `pending|running|waiting` 任务并收敛会话状态
2. 任务超时（`run_timeout_seconds`）后强制结束并释放令牌
3. 启动恢复扫描：对账 trigger/session 与执行 lease 状态
4. Reconciler 规则落地：
   - `pending` 长期无 lease 重新入待执行集合
   - `running` 失联收敛 `finished + error`
5. 冲突决议：
   - `manual_cancel > human_waiting > reconciler_fix > normal_progress`

## M5 运维接口与指标
1. `GET /scheduler/overview`
2. `POST /scheduler/triggers/{trigger_id}/cancel`
3. 指标：`trigger_pending_wait_p95/api_executor_heartbeat_missing/beat_lag/run_timeout/retry_exhausted`

## M6 回归测试
1. 参数快照测试：`TriggerPayload.loop_config_snapshot` 完整
2. 幂等测试：同 `idempotency_key` 不产生重复会话
3. 并发测试：超限任务保持 `pending`，释放槽位后可继续执行
4. 超时测试：会话 `status=completed` 且有超时原因事件
5. 人工介入测试：`waiting` 后不被调度层重复执行
6. 取消测试：`pending/running` 取消后资源清理完成
7. 对账测试：人为制造失联执行器，Reconciler 自动修正状态并补偿释放令牌
8. Beat HA 测试：多实例下单周期仅触发一次，leader 切换后可继续触发
9. 镜像复用测试：同一镜像拉起 `api` 与 `worker-beat`，角色行为正确且日志可区分
10. 在线可见性测试：用户仅保持左侧常驻摘要流，不发 chat 也能实时看到自动任务变化
