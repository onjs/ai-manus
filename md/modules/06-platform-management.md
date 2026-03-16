# 06 平台管理模块（评审稿）

## 范围
- 支撑多租户平台化运营：`tenant -> user -> role -> agent_permission` 全链路管理。
- 与会话模型对齐：自动任务和人工介入均落到 `session`，权限控制按租户与 Agent 双重约束。

## 目标
- 实现租户隔离、角色边界清晰、授权可审计。
- 支持“普通用户可见多个 Agent，会话按业务组展示”的产品形态。
- 提供模型配置中心：统一管理多 LLM 档案，Agent 创建/编辑时可直接选择。
- 保持 MVP 简洁：先做单库行级隔离，不引入复杂审批流。

## 1. 领域对象与数据模型

## 1.1 租户（tenants）
- 核心字段：
  - `tenant_id, code, name, status(active|suspended|archived)`
  - `plan, quota(max_agents,max_concurrency,max_storage_gb,max_active_schedules)`
  - `created_at, updated_at`
- 约束：
  - `(code)` 全局唯一。
  - 业务查询默认强制 `tenant_id` 过滤。

## 1.2 用户（users）
- 核心字段：
  - `user_id, tenant_id, email, name`
  - `platform_role(platform_admin|tenant_admin|tenant_user)`
  - `status(invited|active|disabled|offboarded)`
  - `last_login_at, created_at, updated_at`
- 约束：
  - 用户采用“单租户用户模型”，一个用户仅属于一个租户。

## 1.3 Agent 授权（agent_permissions）
- 核心字段：
  - `tenant_id, agent_id, user_id, grant_type(view|operate), created_at`
- 约束：
  - 同一 `(tenant_id, agent_id, user_id)` 唯一。
  - `grant_type=operate` 隐含 `view`。

## 1.4 审计日志（audit_logs）
- 记录事件：
  - 租户配置变更
  - 用户角色变更
  - Agent 授权变更
  - 模型配置档案变更（创建/更新/停用/密钥轮换）
  - 手动介入/强制终止会话
  - 配额触发拦截
- 字段建议：
  - `audit_id, tenant_id, actor_user_id, action, target_type, target_id, before, after, ts, trace_id`

## 1.5 模型配置档案（model_profiles）
- 核心字段：
  - `profile_id, tenant_id, name, provider, model, api_base`
  - `params`（如 `temperature,max_tokens,top_p`）
  - `secret_ciphertext, secret_key_id, secret_fingerprint, secret_masked`
  - `status(active|disabled), created_at, updated_at`
- 约束：
  - `(tenant_id, name)` 唯一。
  - `agents.model_profile_id` 必须引用同租户且 `status=active` 的档案。
- 安全要求：
  - `api_key` 仅在写入时接收明文并立即加密，数据库不保存明文。
  - 日志与审计禁止输出密文与明文；仅展示 `secret_masked` 和指纹。

## 2. 生命周期设计

## 2.1 租户生命周期
1. `active`：正常可读写与调度。
2. `suspended`：禁止新任务调度与新会话创建；历史只读。
3. `archived`：长期归档，仅平台管理员可查看。

原则：
- MVP 不做物理删除，避免审计链断裂。

## 2.2 用户生命周期
1. `invited`：已创建账号，未激活。
2. `active`：可登录并按角色访问。
3. `disabled`：临时禁用，保留历史审计关系。
4. `offboarded`：离职态，不可登录；保留审计可追溯。

## 3. RBAC 与授权模型

## 3.1 角色矩阵
- `platform_admin`
  - 全局可见；可管理所有租户、用户、Agent、授权、配额与审计。
- `tenant_admin`
  - 仅本租户；可管理本租户 Agent/分组/调度/授权，查看本租户全部会话。
- `tenant_user`
  - 仅本租户；只能查看被授权 Agent 的会话，可在有 `operate` 权限时进行会话介入。

## 3.2 鉴权顺序
1. 身份有效（登录态、用户状态）。
2. 租户匹配（`tenant_id`）。
3. 角色权限校验（RBAC）。
4. Agent 级授权校验（ABAC 子集）。

## 3.3 关键规则
- `tenant_user` 发起“手动新会话”时，可二选一：
  - 绑定已授权 Agent 后创建会话；
  - 不绑定 Agent，直接提交 `goal` 创建会话（`agent_id` 可为空）。
- 无 Agent 绑定的手动会话归入创建者的“个人分组”（如 `personal/{user_id}`），仅创建者、tenant_admin、platform_admin 可见（MVP）。
- 当会话后续绑定 Agent 或调用 Agent 能力时，再执行该 Agent 的授权校验。

## 4. 配额与保护
- 租户配额项（MVP）：
  - `max_agents`
  - `max_active_schedules`
  - `max_concurrency`
  - `max_storage_gb`（快照与产物）
- 超限行为：
  - 创建类操作直接拒绝（4xx + 可读错误码）。
  - 调度类操作保持业务 `pending`，等待 Celery 侧可用执行槽位，不强行丢弃。

## 5. API 设计（保持统一报文）
- 统一响应：`APIResponse{code,msg,data}`
- 建议接口：
  - `GET/POST/PATCH /platform/tenants`
  - `GET/POST/PATCH /platform/users`
  - `GET/POST/DELETE /platform/agent-permissions`
  - `GET/POST/PATCH /platform/model-profiles`
  - `POST /platform/model-profiles/{profile_id}/rotate-key`
  - `GET/PATCH /platform/tenants/{tenant_id}/quota`
  - `GET /platform/audit-logs`

说明：
- 所有接口在 service 层自动注入 `tenant_id` 过滤，不依赖前端传值可信。

## 6. 前端展示对齐
- 左侧会话栏继续按 `group -> sessions` 展示。
- 普通用户看到的是“其有权限 Agent 对应会话集合”。
- 租户管理员看到本租户全部分组与会话。
- 平台管理员可切租户视角（MVP 可先后端支持，前端后续补）。

## 7. 验收标准
- 跨租户数据不可见（接口、SSE、查询、导出均隔离）。
- 越权访问被阻断，并写入审计日志。
- `tenant_user` 无授权 Agent 时不可查看或介入对应会话。
- 配额超限时行为符合设计（拒绝或进入 pending），且可观测。

## 8. 评审结论（已确认）
1. 用户模型采用“单租户用户”，不做多租户成员关系表。
2. `tenant_user` 手动新建会话支持“绑定 Agent / 不绑定 Agent”两种模式；不绑定时进入个人分组。
3. 租户停用（suspended）后，历史会话只读、禁止新调度。

## 9. 多模型路由实现策略（新增）
1. 实现原则
- 调用层优先复用 `ai-manus` 现有 LangChain 体系（`langchain-openai / deepseek / anthropic / ollama`）。
- 配置层使用 `model_profiles`（DB + 密钥加密），由 Agent 选择 `model_profile_id`。

2. 运行时策略
- 先按 `model_profile_id` 读取模型档案。
- 由 `provider + model + api_base + params` 映射到对应 LangChain Client。
- 运行态记录 `provider_name/model_name/model_profile_id` 到 `run_meta`。

3. 参考边界
- 可参考 `nanobot` 的注册表组织方式（provider metadata），用于减少 if/else 分支。
- 不直接复用 `nanobot` 的 provider 实现代码，避免引入额外调用栈与耦合。
