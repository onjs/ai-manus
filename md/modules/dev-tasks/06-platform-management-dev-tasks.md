# 06 平台管理模块 开发任务清单

## M1 数据模型
1. tenants/users/agent_permissions/audit_logs 字段补齐
2. 租户内唯一索引
3. 新增 `model_profiles` 集合与索引（`tenant_id+name` 唯一）
4. `agents.model_profile_id` 外键引用约束（应用层）

## M2 RBAC
1. 平台/租户两级角色校验
2. Agent 级授权校验
3. 手动会话“绑定/不绑定 agent”规则落地

## M3 配额
1. max_agents/max_active_schedules/max_concurrency/max_storage_gb
2. 超限拒绝或业务 `pending` 行为（Celery 侧等待执行槽位）

## M4 审计
1. 配置变更审计
2. 授权变更审计
3. 手动介入审计
4. 模型档案审计（创建/更新/停用/密钥轮换）

## M5 模型配置中心
1. `GET/POST/PATCH /platform/model-profiles`
2. `POST /platform/model-profiles/{profile_id}/rotate-key`
3. API Key 加密存储落地（写入即加密，读取仅返回 mask/fingerprint）
4. Agent 创建/编辑选择 `model_profile_id` 联调打通

## M6 多模型路由（LangChain 优先）
1. 基于 `model_profiles` 实现 provider 路由器（`provider/model/api_base/params` -> LangChain Client）
2. 运行入口按 `model_profile_id` 选择模型，不再依赖全局单模型配置
3. 对接 ai-manus 现有模型调用链，保持 run/event 结构兼容，不改前端事件协议
4. 可选：引入 provider metadata 注册表（仅组织配置，不引入 nanobot provider 实现）
