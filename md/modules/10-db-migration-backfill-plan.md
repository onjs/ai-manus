# 10 DB 迁移与回填方案（开工前必备）

## 目标
- 安全引入多租户、多 Agent、版本化配置与会话扩展字段。
- 支持回滚，避免中断现网会话读写。

## 范围
- Mongo：新增集合、字段、索引。
- Redis：接入 Celery broker/result backend 与并发控制键空间。

## 迁移步骤（建议）
### Phase 0 预检
1. 备份 Mongo（全库快照）
2. 校验当前索引与集合大小
3. 评估高峰写入窗口，选择低峰执行

### Phase 1 非破坏新增
1. 新增集合：`agent_groups, agents, agent_task_definitions, task_schedules, model_profiles, agent_permissions, agent_triggers, agent_config_versions, audit_logs`
2. `sessions` 新增字段：`tenant_id, group_id, agent_id, task_id, source_type, task_schedule_id, trigger_id, run_meta`
3. `users` 新增字段：`tenant_id, platform_role`
4. `agents` 新增字段：`model_profile_id`
5. 创建索引（先后台）

### Phase 2 回填
1. 历史 `users.tenant_id` 回填（单租户默认租户）
2. 历史 `sessions.tenant_id/source_type` 回填（默认 `manual`）
3. 历史会话 `run_meta` 补默认结构
4. 历史 `agents.model_config` 迁移为 `model_profiles + model_profile_id`
   - 为每个唯一模型配置生成一个 `model_profile`
   - `api_key` 按加密策略入库（密文），并写回 `agents.model_profile_id`
5. 为历史 Agent 回填默认 `agent_task_definitions`（每个 Agent 生成 1 条默认任务定义）
6. 历史 `agent_schedules` 迁移为 `task_schedules`（补齐 `task_id`）

### Phase 3 双写与灰度
1. 服务层开启新字段双写
2. 灰度读新字段（缺失走默认值）
3. 验证后切全量读取新字段

### Phase 4 收敛
1. 清理临时脚本
2. 冻结 schema 版本

## 索引建议
1. `sessions`: `(tenant_id, latest_message_at desc)`, `(tenant_id, group_id, latest_message_at desc)`, `(tenant_id, agent_id, latest_message_at desc)`
2. `agents`: `(tenant_id, code)` unique
3. `model_profiles`: `(tenant_id, name)` unique, `(tenant_id, status)`
4. `agent_task_definitions`: `(tenant_id, agent_id, enabled)`, `(tenant_id, agent_id, name)` unique
5. `task_schedules`: `(tenant_id, task_id, enabled, next_run_at)`, `(tenant_id, agent_id, enabled, next_run_at)`
6. `agent_permissions`: `(tenant_id, agent_id, user_id)` unique
7. `agent_config_versions`: `(tenant_id, agent_id, version_no)` unique
8. `agent_triggers`:
   - `(tenant_id, status, fire_at)`
   - `(tenant_id, agent_id, status, fire_at)`
   - `(tenant_id, agent_id, task_id, idempotency_key)` unique

## Redis 键空间
- Celery 队列键（由 Celery 管理，按环境前缀区分）
- 并发控制键（建议）
  - `conc:global:running`
  - `conc:tenant:{tenant_id}:running`
  - `conc:agent:{agent_id}:running`
- 上下文热态键
  - `ctx:{session_id}:*`

## 回滚方案
1. 开关回滚：关闭新读写开关，恢复旧路径
2. 索引回滚：保留新增索引（不影响旧逻辑）
3. 数据回滚：不删字段，仅停止使用；必要时恢复 Mongo 备份
4. 模型配置回滚：保留 `model_profiles`，`agents` 可临时回读旧 `model_config`（灰度窗口内）

## 验证
1. 回填后抽样校验 1000 条会话字段完整性
2. 索引命中率与慢查询检查
3. 灰度期错误率/延迟无显著劣化
