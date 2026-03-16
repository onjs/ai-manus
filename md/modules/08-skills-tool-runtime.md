# 08 Skills与工具执行策略模块

## 状态
- 已确认（可冻结）。

## 目标
- 每个 Agent 有独立的 `skills` 配置、版本与生效边界。
- 每个 Agent 有独立的工具策略，尤其是 `sandbox` 工具白/黑名单。
- 工具执行链路统一收敛到“策略评估 -> 执行 -> 结果清洗 -> 事件落库”。
- 保持与现有 ai-manus 前端会话/SSE/noVNC 兼容。

## 参考输入（源码结论）
### 来自 openclaw（skills 生命周期）
- 多来源 skills 装载与优先级合并（extra/bundled/managed/personal/project/workspace）。
- skills watcher + snapshot version，按版本增量刷新会话技能快照。
- skills prompt 构建有数量/字符上限裁剪，避免上下文失控。
- 支持 `disableModelInvocation`、`userInvocable` 等调用策略。
- skills 级 env 注入可回滚，并带危险环境变量拦截。
- 支持将技能目录同步到目标工作区（可用于 sandbox 运行目录）。

### 来自 automaton（工具执行策略）
- 统一 `executeTool()` 入口，先做 policy engine 决策再执行。
- policy 决策与结果审计持久化（rule 命中、allow/deny 原因）。
- 外部来源工具结果进行注入防护清洗（例如 shell/web 输出）。
- 回合级工具调用上限、循环检测、失败治理（可借鉴其重试/退避思想）。
- 整体是“单入口策略管控 + 执行后治理”的稳定化方案。

## 我们的适配方案（MVP）
### 1. Agent 级 Skills 模型
- 在 `agents` 文档新增（或增强）：
  - `skills_config`
  - `skills_config.enabled: bool`
  - `skills_config.filter: string[]`（Agent可用 skill 名单）
  - `skills_config.sources`（MVP 固定：`project/workspace`）
  - `skills_config.entries`（按 skill 覆盖 api_key_ref/env/config/enabled）
  - `skills_config.prompt_limits`（max_count/max_chars）
  - `skills_config.version`（草稿版本）
  - `published_version`（发布版本，运行只读）
  - 约束：skills 作用域仅到 Agent，不做 tenant/group 级技能继承。

### 2. Agent 级 Tool 策略模型
- 在 `agents.tools_config` 统一定义：
  - `profile`（minimal/full/custom）
  - `allow[] / deny[]`
  - `sandbox_tools.allow[] / sandbox_tools.deny[]`
  - `loop_detection`（warning/critical 阈值）
  - `security`（危险命令、路径逃逸、敏感文件策略）

### 3. Skills 生命周期（运行态）
1. `Resolve`：任务启动时按 Agent 已发布版本解析 skills 清单。
2. `Filter`：按 `filter + eligibility` 过滤可用 skills。
3. `Snapshot`：生成 `skills_snapshot`（带 `version/hash/prompt`）。
4. `Inject`：将 snapshot prompt 注入 Planner/Executor 系统提示词。
5. `Run`：工具调用期间读取 snapshot 中的策略信息。
6. `Install/Refresh`：允许运行态动态安装 skills，安装后刷新 snapshot version。
7. `Rollback`：回合结束回收临时 env 注入（若有）。

### 3.1 Skills 8阶段生命周期（数据读写层视角）
1. `LoadAgentConfig`
- 输入：`agent_id, published_version`
- DAO：`agents`（读已发布配置）
- 输出：`skills_config_runtime`
- 失败：`AGENT_NOT_FOUND`, `PUBLISHED_VERSION_NOT_FOUND`

2. `DiscoverSkills`
- 输入：`skills_config_runtime.sources`
- 数据读写层：文件系统扫描 `skills/<skill_id>/` 目录，读取入口 `SKILL.md`（目录可包含 scripts/references/assets）
- 输出：`discovered_skills[]`
- 失败：`SKILL_SOURCE_NOT_FOUND`, `SKILL_PARSE_ERROR`

3. `ValidateEligibility`
- 输入：`discovered_skills[]`, `skills_config.filter`, `entries`
- DAO：`agent_skill_install_logs`（可选读最近安装记录）
- 输出：`eligible_skills[]`, `ineligible_reasons[]`
- 失败：`SKILL_REQUIREMENT_UNMET`（缺 bin/env/config）

4. `BuildSnapshot`
- 输入：`eligible_skills[]`, `prompt_limits`
- DAO：写 `sessions.run_meta.skills_snapshot`（Mongo）
- 输出：`skills_snapshot{version,hash,prompt,skill_names}`
- 失败：`SKILL_PROMPT_BUILD_FAILED`

5. `InjectPrompt`
- 输入：`skills_snapshot.prompt`
- DAO：无（运行内存注入）
- 输出：本轮 Planner/Executor 有效系统提示词
- 失败：`PROMPT_INJECTION_FAILED`

6. `ExecuteWithPolicy`
- 输入：`tool_call`, `skills_snapshot`, `tools_config`
- DAO：写 `session events` + `tool_audit_logs`
- 输出：`tool_result` + 可回放事件
- 失败：`TOOL_DENIED`, `TOOL_EXEC_FAILED`, `TOOL_TIMEOUT`

7. `DynamicInstallAndRefresh`
- 输入：`POST /agents/{id}/skills/install`
- DAO：写 `agent_skill_install_logs`；更新 `agents.skills_config.version`；刷新会话 `snapshot_version`
- 输出：`install_result` + `new_snapshot_version`
- 失败：`INSTALL_FAILED`, `INSTALL_NOT_ALLOWED`, `SKILL_SECURITY_REJECTED`

8. `FinalizeAndRollback`
- 输入：会话结束信号（`session.status=completed` 或 `session.status=waiting`）
- DAO：写最终审计；回收临时 env 注入；更新 session run_meta
- 输出：可追溯生命周期闭环
- 失败：`ROLLBACK_FAILED`（不影响会话终态，但需告警）

### 4. Tool 执行统一入口（必须）
- 新增统一执行管线（概念）：
  - `tool_router.execute(tool_call, session_ctx, agent_ctx)`
- 固定阶段：
  1) 参数校验与 JSON 修复（可复用现有 robust parser）
  2) 策略决策（tenant/group/agent 三层合并）
  3) 执行（sandbox/browser/shell/file/mcp）
  4) 输出清洗（外部文本注入防护、超长输出 artifact_ref 化）
  5) 事件写入（ToolEvent + StepEvent + 审计字段）
  6) 失败治理（回合内自纠/等待人工介入/终止本次运行）

### 5. 策略合并顺序（冻结建议）
- `global(default)` -> `tenant` -> `group` -> `agent`
- 规则：
  - `deny` 优先级高于 `allow`。
  - 显式 `allow` 仅放行命中工具，不命中即拒绝。
  - `sandbox_tools` 只影响 sandbox 侧工具，不影响消息/检索类工具。

### 6. 与 ai-manus 现有能力对齐
- 不重写现有工具事件模型与前端面板。
- `shell/file/browser` 继续写 `Session.events`，前端时间线直接复用。
- `noVNC` 仍走现有 WS 代理链路，工具层只负责补齐策略与审计字段。

## 数据落地建议（MVP）
- Mongo（持久）：
  - Agent 发布配置、会话事件、工具审计摘要、skills_snapshot 元数据。
- Redis（短态）：
  - 运行中策略缓存、会话短期上下文、调度执行态。
- GridFS（大对象）：
  - 大体量 shell/file 输出、截图与文件快照正文。

## API 清单（草案）
- `GET /agents/{id}/skills`：查看 Agent 生效 skills。
- `PUT /agents/{id}/skills`：更新草稿 skills 配置。
- `POST /agents/{id}/skills/publish`：发布 skills 版本。
- `POST /agents/{id}/skills/install`：运行态安装 skill（写审计，触发 snapshot 刷新）。
- `GET /agents/{id}/tools-policy`：查看生效工具策略。
- `PUT /agents/{id}/tools-policy`：更新工具策略。
- `POST /agents/{id}/tools-policy/validate`：策略预检（返回 allow/deny 差异）。

## 验收口径（本模块）
- 同一租户多个 Agent 同时运行时，skills 与工具策略互不串扰。
- Agent A 禁用的 tool/skill 不会在 Agent B 被误拒绝或误放行。
- 被拒绝的工具调用有明确审计事件（原因、命中规则、时间）。
- shell/file/browser 输出仍可实时查看，历史回放不依赖在线 sandbox。

## 代码参考（证据路径）
- openclaw
  - `/Users/zuos/code/github/openclaw/src/agents/skills/workspace.ts`
  - `/Users/zuos/code/github/openclaw/src/agents/skills/refresh.ts`
  - `/Users/zuos/code/github/openclaw/src/agents/skills/env-overrides.ts`
  - `/Users/zuos/code/github/openclaw/src/agents/pi-tools.policy.ts`
  - `/Users/zuos/code/github/openclaw/src/agents/tool-policy-pipeline.ts`
- automaton
  - `/Users/zuos/code/github/automaton/src/agent/tools.ts`
  - `/Users/zuos/code/github/automaton/src/agent/policy-engine.ts`
  - `/Users/zuos/code/github/automaton/src/agent/loop.ts`
- ai-manus（对齐实现位）
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/agent_task_runner.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/flows/plan_act.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/agents/base.py`

## 已确认项
- skills 只做到 Agent 级，不做 tenant/group 继承。
- 允许运行态动态安装 skills。
- 不做 `session override`（指管理员临时授权 skill/工具不做）。
- 管理员角色保留：`platform_admin / tenant_admin` 仍负责配置与发布管理。
- `skill_id` 同名冲突策略：同名拒绝（不覆盖）。
- 动态安装安全增强（来源白名单/大小限制/恶意扫描）MVP 暂不做，仅记录安装审计日志。
- 安装后生效策略：仅新会话生效，不影响当前运行中会话。
- sandbox 不存放 skills 目录（当前阶段 skills 仅在后端侧加载与注入）。

## 实现约束（冻结）
1. 命名与冲突
- `skills/<skill_id>/` 唯一，创建或安装时若 `skill_id` 已存在则直接拒绝，返回 `SKILL_ID_CONFLICT`。

2. 动态安装（MVP）
- 允许安装，但不做高级安全能力（来源白名单、大小限制、深度恶意扫描）。
- 必须记录审计：安装人、来源、时间、结果、错误信息。

3. 生效时机
- 安装成功仅提升 `skills_config.version`。
- 已在运行中的会话继续使用原 `skills_snapshot`。
- 下一次新会话在 `LoadAgentConfig` 阶段读取新版本并生效。

4. 与 sandbox 边界
- sandbox 当前不同步 skill 目录。
- skill 解析、prompt 注入、策略选择均在后端完成。

## 开发任务清单（可执行）
### 阶段划分
1. `M1 数据与接口底座`
- 目标：先打通配置存储、查询与发布，不改执行链路。

2. `M2 运行态加载与快照`
- 目标：会话启动时能按 Agent 配置加载 skill 并生成 snapshot。

3. `M3 动态安装与版本生效`
- 目标：支持安装 skill，且仅新会话生效。

4. `M4 执行策略接线与审计`
- 目标：工具执行链路接入策略校验和审计日志。

### M1 任务
1. `SKL-M1-01` AgentDocument 扩展
- 内容：新增 `skills_config`、`tools_config`、`published_version` 字段。
- 验收：旧数据兼容；新字段默认值可回填。

2. `SKL-M1-02` API Schema 扩展
- 内容：新增 `GET/PUT /agents/{id}/skills`、`POST /agents/{id}/skills/publish` 请求与响应模型。
- 验收：统一 `APIResponse{code,msg,data}`；参数校验覆盖空值/非法值。

3. `SKL-M1-03` Repository 能力补齐
- 内容：Agent 仓储增加读取/更新 skills 配置、发布版本方法。
- 验收：有单测，支持并发更新的版本检查。

### M2 任务
1. `SKL-M2-01` Skill 目录扫描器
- 内容：扫描 `skills/<skill_id>/SKILL.md`，解析 metadata，返回 `discovered_skills`。
- 验收：可识别无效目录；同名冲突返回 `SKILL_ID_CONFLICT`。

2. `SKL-M2-02` 过滤与资格校验
- 内容：按 `skills_config.filter` 与依赖条件（bin/env/config）筛选 `eligible_skills`。
- 验收：输出可用与不可用原因列表；错误码标准化。

3. `SKL-M2-03` Snapshot 生成与会话落库
- 内容：生成 `skills_snapshot{version,hash,prompt,skill_names}` 并写入 `sessions.run_meta`。
- 验收：会话内可追溯 snapshot；prompt 长度受限。

4. `SKL-M2-04` Prompt 注入接线
- 内容：在 Planner/Executor 调用前注入 snapshot prompt。
- 验收：仅当前会话生效，不影响其他会话。

### M3 任务
1. `SKL-M3-01` 安装接口
- 内容：`POST /agents/{id}/skills/install`，支持将 skill 安装到 `skills/<skill_id>/`。
- 验收：同名拒绝；返回安装结果与版本变化。

2. `SKL-M3-02` 安装审计日志
- 内容：新增 `agent_skill_install_logs` 集合，记录安装人、来源、结果、错误。
- 验收：接口可查询最近安装记录；失败也落审计。

3. `SKL-M3-03` 生效时机控制
- 内容：安装成功仅提升 `skills_config.version`，不刷新运行中会话。
- 验收：运行中会话使用旧 snapshot；新会话使用新版本。

### M4 任务
1. `SKL-M4-01` 工具策略合并器
- 内容：实现 `global -> tenant -> group -> agent` 策略合并。
- 验收：`deny` 优先级高于 `allow`；策略结果可追踪。

2. `SKL-M4-02` 统一执行入口封装
- 内容：封装 `tool_router.execute(...)` 六阶段流水线。
- 验收：策略拒绝、执行成功、执行失败三类路径均落事件。

3. `SKL-M4-03` 审计日志与回放字段
- 内容：落 `tool_audit_logs` 与 session events 扩展字段（命中规则、拒绝原因）。
- 验收：前端回放不受影响，新增字段向后兼容。

### 测试任务（并行）
1. `SKL-TST-01` 单元测试
- 覆盖：扫描器、过滤器、snapshot 生成、策略合并器。

2. `SKL-TST-02` 集成测试
- 覆盖：安装 -> 发布 -> 新会话生效链路；运行中会话不热更新。

3. `SKL-TST-03` 回归测试
- 覆盖：现有会话、SSE、shell/file/noVNC 不回归。

### 交付定义（DoD）
1. 所有 M1-M4 任务完成并通过测试。
2. 关键错误码可在 API 层稳定复现。
3. 回放兼容：旧前端不改也可正常展示。
4. 文档同步：接口、字段、错误码与实现一致。
