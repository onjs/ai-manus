# 01 Agent管理模块 开发任务清单

## M1 数据与索引
1. 新增集合：`agent_groups, agents, agent_schedules, agent_permissions`
2. 扩展 `sessions/users` 字段
3. 增加租户内唯一索引与查询索引
4. `agents` 字段改为 `model_profile_id`（不再内嵌 `model_config`）

## M2 接口层
1. 实现 Group/Agent/Schedule/Permission CRUD
2. 扩展 `/sessions` 列表字段与过滤参数
3. SSE schema 兼容扩展
4. Agent 创建/编辑支持选择 `model_profile_id`
5. 运行入口对接 LangChain 模型路由器（按 `model_profile_id` 选择 provider）
6. 新增全局摘要流：`GET /sessions/stream`
7. 新增会话详情流：`GET /sessions/{session_id}/stream`

## M2.1 Agent Loop 契约对齐（新增）
1. `GET /sessions`、`GET /sessions/{id}` 返回 `run_meta.loop`
2. `run_meta.loop` 字段按冻结 schema 输出（`config_snapshot/counters/last_policy_decision`）
3. 增加 `run_meta.dispatch`（`trigger_id/celery_task_id/queue_name`）并保持向后兼容
4. 保持向后兼容：旧客户端忽略新增字段不报错

## M2.2 策略层事件对齐（新增）
1. 在事件映射层输出保护/重试/循环检测 action：
   - `guard_warning, guard_triggered, retry_scheduled, retry_exhausted, loop_detected_warning, loop_detected_critical`
2. 事件 payload 补齐：
   - `guard_name, reason_code, threshold, current_value, step_id, run_id`
3. `last_policy_decision` 与事件 action 关联可追溯

## M3 权限与审计
1. `tenant_id` 强制过滤
2. `platform_admin/tenant_admin/tenant_user` 校验
3. 配置/授权操作审计日志

## M3.1 Loop 冻结参数落地（新增）
1. 固定参数落配置（MVP 只读，不开放 Agent 级修改）：
   - `MAX_ROUNDS_PER_RUN=24`
   - `MAX_TOOL_CALLS_PER_ROUND=3`
   - `MAX_TOOL_CALLS_PER_RUN=64`
   - `MAX_NO_PROGRESS_ROUNDS=3`
   - `RUN_TIMEOUT_SECONDS=1800`
   - `THINK_TIMEOUT_SECONDS=90`
   - `TOOL_TIMEOUT_SECONDS=120`
   - `MAX_STEP_RETRY=2`
   - `BACKOFF_BASE_SECONDS=1`
   - `BACKOFF_MAX_SECONDS=2`
   - `BACKOFF_JITTER_RATIO=0.2`
2. 启动时参数快照写入 `run_meta.loop.config_snapshot`
3. 运行计数器实时更新 `run_meta.loop.counters`
4. 结果语义复用 ai-manus：
   - 仅使用 `session.status=pending|running|waiting|completed`
   - 失败/超时/取消等细粒度原因通过事件（`error/done/wait` + `reason_code`）表达

## M4 测试
1. 租户隔离测试
2. 授权可见性测试
3. 旧前端兼容测试
4. 模型绑定测试：无效或跨租户 `model_profile_id` 拒绝；有效档案可成功运行
5. 双通道 SSE 测试：全局摘要流 + 会话详情流并行连接不冲突
6. 在线自动触发测试：用户无主动 chat 时，自动会话仍可实时出现在左侧

## M4.1 Loop 契约回归测试（新增）
1. 参数快照测试：新会话启动后 `run_meta.loop.config_snapshot` 完整可读
2. 执行上限触发测试：round/tool-calls 上限触发 `guard_triggered`，会话最终 `status=completed` 且有错误事件
3. 超时测试：超过 `RUN_TIMEOUT_SECONDS` 后会话最终 `status=completed` 且有超时原因事件
4. 重试测试：retryable 错误触发 `retry_scheduled`，超过上限触发 `retry_exhausted`
5. 错误分类测试：
   - `non_retryable` 直接失败
   - `human_required` 进入 `waiting` 且 `session.status=waiting`
6. 循环检测测试：达到 warning/critical 阈值分别产出对应事件
