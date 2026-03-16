# 07 配置发布与回滚模块（评审稿）

## 范围
- 管理 Agent 配置从草稿到发布、回滚的全生命周期。
- 配置对象包含：
  - `prompts`（如 `agents.md / tools.md / identity.md / heartbeat.md` 的逻辑内容）
  - `model_binding`（`model_profile_id` + 可覆盖参数）
  - `tools_config`
  - `skills_enabled`
  - `policy_config`（风控阈值、保护参数）
  - `schedule_binding`（可选，是否与调度绑定发布）

## 目标
- 让配置“可发布、可回滚、可审计、可复现”。
- 保证发布/回滚不会打断运行中会话（session 级配置快照不变）。
- 兼容我们当前执行模型：`每次运行=一个session`，新会话加载最新已发布版本。

## 1. 配置版本模型

## 1.1 实体设计
- `agent_config_versions`（Mongo）
  - `version_id`
  - `tenant_id, agent_id`
  - `version_no`（单 Agent 递增）
  - `status(draft|published|archived|rollback_marker)`
  - `content`（配置正文）
  - `content_hash`
  - `created_by, created_at`
  - `published_by, published_at`
  - `base_version_id`（由哪个版本演进）
  - `change_summary`
  - `validation_report`

- `agents.published_version`（指针）
  - 指向当前生产生效版本 `version_id`

## 1.2 状态规则
- `draft`：可编辑，不会被运行时加载。
- `published`：可被新会话加载；每个 Agent 同时仅一个当前发布版本（通过指针保证）。
- `archived`：历史归档版本，只读。
- `rollback_marker`：记录一次回滚动作来源（可选，便于审计）。

## 2. 生效策略

## 2.1 MVP 生效语义
- 发布成功后“立即对新会话生效”。
- 运行中会话继续使用其创建时快照，不热更新。
- 下次调度触发的新会话加载新版本。

## 2.2 会话快照原则
- 在创建 session 时固化：
  - `run_meta.config_version_id`
  - `run_meta.config_hash`
- 用途：
  - 回放复现
  - 故障归因
  - 版本对比分析

## 3. 发布校验与闸门

## 3.1 发布前静态校验
- Schema 校验：
  - `model_binding/tools_config/policy_config` 字段完整性与类型合法性
- 引用校验：
  - `skills_enabled` 是否存在于技能目录并可加载
  - 工具名是否在允许清单
  - `model_profile_id` 是否存在、同租户且 `active`
- 风险校验：
  - 禁止明显危险配置（例如关闭关键 guard）

## 3.2 发布前运行时预检（轻量）
- dry-run 级检查（不执行真实业务动作）：
  - 配置可被 runtime 解析
  - 必要依赖可达（例如模型档案可读取且凭据可解密）

安全约束（冻结）：
- 配置版本中不得内嵌明文 `api_key`。
- 模型密钥仅保存在 `model_profiles` 密文字段。

## 3.3 发布结果
- 校验失败：保持 `draft`，返回结构化错误列表。
- 校验通过：生成 `published`，并更新 `agents.published_version` 指针。

## 4. 回滚策略

## 4.1 MVP 回滚方式
- 仅手动回滚（平台管理员/租户管理员触发）。
- 回滚本质：
  - 将历史某个 `published/archived` 版本重新设为当前 `published_version`。
  - 可生成新版本号（推荐）或指针直切（不推荐）。

## 4.2 回滚边界
- 不影响运行中会话。
- 仅影响回滚后新创建会话。
- 回滚动作必须写审计日志并记录原因。

## 4.3 自动回滚（后续）
- MVP 不做自动回滚。
- 后续可基于失败率阈值触发建议回滚（先建议，后自动化）。

## 5. 审计与变更可追溯

## 5.1 必记审计事件
- 创建草稿
- 更新草稿
- 发布
- 回滚
- 归档
- 指针变更（`published_version`）

## 5.2 审计字段
- `tenant_id, agent_id, version_id`
- `actor_user_id, actor_role`
- `action`
- `before_hash, after_hash`
- `diff_summary`
- `reason`
- `ts, trace_id`

## 5.3 Diff 展示
- MVP 做“字段级 diff + 摘要”。
- 大文本（prompts）支持按段落 diff。

## 6. API 设计（统一报文）
- 统一响应：`APIResponse{code,msg,data}`
- 建议接口：
  - `POST /agents/{agent_id}/config-versions`（创建 draft）
  - `PATCH /agents/{agent_id}/config-versions/{version_id}`（更新 draft）
  - `POST /agents/{agent_id}/config-versions/{version_id}/validate`
  - `POST /agents/{agent_id}/config-versions/{version_id}/publish`
  - `POST /agents/{agent_id}/config-versions/{version_id}/rollback`
  - `GET /agents/{agent_id}/config-versions`
  - `GET /agents/{agent_id}/config-versions/{version_id}/diff?base=...`

## 7. 与执行/调度模块对齐
- 调度器在创建会话时读取 `agents.published_version`。
- worker 启动时把 `config_version_id/hash` 写入 `session.run_meta`。
- timeline 可展示“本次运行使用的配置版本”。

## 8. 验收标准
- 发布失败不会污染当前生产版本。
- 回滚后新会话使用回滚版本，运行中会话不受影响。
- 任意一次线上运行都可追溯到具体配置版本与差异。
- 跨租户配置不可见，且所有操作均可审计。

## 9. 评审结论（已确认）
1. 生效策略采用“发布后仅新会话生效，运行中会话不热更新”。
2. 回滚采用“手动回滚，仅影响新会话”，MVP 不做自动回滚。
3. 回滚实现采用“生成新版本号指向旧内容”。
