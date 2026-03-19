# 12 联调与回归测试矩阵（开工前必备）

## 目标
- 覆盖后端、前端、sandbox 三端联动关键路径。

## A. 核心联调链路
1. 调度触发链路
- `task_schedule -> trigger -> session(auto) -> api_executor -> sandbox`
- 预期：左侧会话入组、时间线更新、noVNC 可看

1.1 在线自动触发可见性
- 用户仅保持左侧常驻摘要流，不主动发 chat
- 预期：调度触发后 3s 内左侧出现新会话并展示 `running` 状态

2. 手动会话链路
- 绑定 Agent/不绑定 Agent 两种创建
- 预期：不绑定进入 `personal/{user_id}`

2.1 双 SSE 并行
- 全局摘要流 + 当前会话详情流并行连接
- 预期：事件按 `session_id/event_id` 正确路由，无串流或覆盖

3. 介入恢复链路
- `waiting` 后用户输入恢复
- 预期：同 `session_id` 继续，必要时自动重建 sandbox

4. 取消与超时链路
- pending 取消、running 取消、run timeout、waiting idle timeout
- 预期：状态与 sandbox 销毁行为符合文档

5. 对账恢复链路
- 人为制造 `queued` 丢任务与 `running` 失联
- 预期：Reconciler 自动修正 trigger/session，并补偿释放并发令牌

## B. 模块回归
1. 多租户隔离
- 跨租户不可见（API/SSE/回放）

2. 权限回归
- tenant_user 仅见授权 Agent
- tenant_admin 可见租户全量

3. 配置发布回滚
- 发布仅新会话生效
- 回滚仅影响新会话

4. 技能与工具策略
- deny 优先生效
- 安装后仅新会话生效

5. 上下文与记忆
- `planner/execution` 双层记忆装配正确
- 压缩后 `goal_hash/step_ledger` 一致
- checkpoint 恢复后可在原 `session_id` 继续

6. 浏览器上下文剪裁
- LLM 上下文不包含整页 DOM 与截图二进制
- 回放仍可看到截图与关键页面快照

## C. 非功能
1. 性能
- sessions 列表、timeline、回放接口 p95
2. 稳定性
- 随机 kill sandbox 后恢复成功率
- 随机 kill api executor 进程后对账收敛成功率
3. 观测
- trace_id/span_id 贯通

## D. 出口准入
- 关键链路全绿
- P1/P2 已知问题为 0
- 回归报告归档
