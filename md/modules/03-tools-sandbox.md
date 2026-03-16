# 03 工具与Sandbox模块

## 状态
- 已冻结。

## 评审结论
- 结论：`可以过`（进入开发），但需按本文件的 `P0 改造清单` 补齐“超时销毁后自动重建并恢复”闭环。

## 设计目标
- 复用 `ai-manus` 现有 Browser/File/Shell/noVNC 能力，不重写 sandbox。
- 满足“每次自动运行可实时查看，结束后可历史回放”的产品要求。
- 与现有前端会话页、SSE 与 noVNC 交互保持兼容。
- 明确“模型上下文”和“回放快照”分层：浏览器截图用于回放，LLM 使用剪裁后的浏览器文本。

## 核心原则（冻结）
- `每次 Agent 自动运行 = 1 个 session + 1 个 sandbox`。
- session 生命周期与 sandbox 生命周期解耦：
  - session 可长期保留用于回放与审计；
  - sandbox 在运行结束后自动销毁。
- 会话入口支持 `auto + manual`：
  - `auto` 会话：调度触发创建运行态 sandbox。
  - `manual` 会话：按需创建 sandbox（首次使用 browser/file/shell 时创建）。
- 能复用的全部复用：
  - 前端中间时间线、右侧 `shell/file/noVNC` 面板复用；
  - 后端事件流写法与会话体系复用。

## ai-manus 现状核查（已验证）
- 可复用项（直接复用）
  - 会话事件持久化（`Session.events`）与时间线回放链路可用。
  - shell/file/browser 的工具输出已写入会话事件，截图与文件走 GridFS 存储引用。
  - 前端 SSE 会话流、右侧 noVNC WebSocket 代理链路可复用。
  - 浏览器工具本身支持“文本观察优先”（`browser_view` 文本表示用于推理，截图用于可视化）。
- 已知差距（必须改造）
  - 开发模式默认 `SANDBOX_ADDRESS=sandbox`，本质是单固定 sandbox，不是“每任务独立 sandbox”。
  - 任务创建时对旧 sandbox 的 `get` 失败缺少可靠兜底，无法保证“销毁后自动重建”。
  - `ensure_sandbox` 失败当前只记录日志，不抛错，可能带来后续隐式失败。
  - 任务正常结束后不会自动销毁 sandbox（当前销毁主要发生在全局 destroy 路径）。
  - 缺少“重建 sandbox 后恢复上下文”的显式恢复事件与状态标记。

## 代码证据定位（2026-03-14）
- 会话写事件与回放基础
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/agent_task_runner.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/repositories/mongo_session_repository.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/models/documents.py`
- sandbox 创建/获取与当前行为
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/agent_domain_service.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/external/sandbox/docker_sandbox.py`
  - `/Users/zuos/code/github/ai-manus/docker-compose-development.yml`
- timeout 机制（sandbox 侧）
  - `/Users/zuos/code/github/ai-manus/sandbox/app/services/supervisor.py`
  - `/Users/zuos/code/github/ai-manus/sandbox/app/core/middleware.py`
- agent 记忆恢复基础
  - `/Users/zuos/code/github/ai-manus/backend/app/domain/services/agents/base.py`
  - `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/repositories/mongo_agent_repository.py`

## 生命周期（冻结）
1. 会话入口：
- 调度触发创建自动会话（`source_type=auto`）。
- 用户新建会话创建手动会话（`source_type=manual`）。
2. sandbox 创建：
- `auto` 会话在 Worker 开始执行时创建 sandbox。
- `manual` 会话在首次使用 browser/file/shell 时按需创建 sandbox。
3. Agent 在 sandbox 内执行 Browser/File/Shell 工具。
4. 事件与快照实时写入后端并推送前端。
5. `auto` 运行结束（成功/失败/取消）后销毁 sandbox。
6. 用户介入时若 sandbox 已销毁或不可用，自动重建 sandbox 并继续原 `session_id`。
7. 历史查看时从 `Mongo + GridFS` 回放，不依赖 sandbox 存活。

## 取消与超时销毁规则（冻结）
- 会话取消：
  - `pending` 会话取消：不创建 sandbox，直接结束。
  - `running` 会话取消：立即取消 worker 并触发 sandbox 销毁，记录取消原因事件。
- 等待人工超时销毁：
  - 当会话进入 `waiting`，sandbox 只保留有限时间窗口用于用户接管。
  - 默认 `WAITING_SANDBOX_IDLE_TIMEOUT_MINUTES=30`，超时后自动销毁 sandbox。
  - 会话保持可继续（`session.status=waiting`）；用户后续发消息时自动重建 sandbox 并恢复执行。
- 运行超时销毁：
  - 单次运行超过 `RUN_TIMEOUT_SECONDS=1800` 结束为 `timeout`，并触发 sandbox 销毁。

## P0 改造清单（必须完成）
1. sandbox 模式开关
- 增加运行模式：`shared`（兼容旧模式）和 `per_run`（目标模式）。
- `per_run` 下每次自动运行创建独立 sandbox 并绑定 `session_id`。

2. 自动重建与恢复闭环
- 在创建/获取 sandbox 时加入兜底：
- `get(sandbox_id)` 失败或健康检查失败时，自动 `create()` 新 sandbox 并更新会话绑定。
- 写入恢复事件：`sandbox_recreated`（包含 old/new sandbox_id、原因、时间）。
- 适用范围：`auto` 运行中恢复 + `manual/介入` 场景恢复（同一会话继续）。

3. 健康检查失败即失败快返
- `ensure_sandbox` 超时必须抛错，当前运行内优先由 Agent 回合内自纠；无法恢复则结束本次运行并记录错误事件，禁止“仅记录日志后继续”。

4. 任务结束自动销毁策略
- `source_type=auto` 会话在 `completed` 后触发 sandbox 销毁（失败/取消通过事件区分原因）。
- 销毁结果写审计事件：`sandbox_destroyed` 或 `sandbox_destroy_failed`。

5. 上下文恢复
- 重建后按 `Mongo session_events + agent memory(planner/execution)` 重建上下文，继续原 `session_id`。
- 恢复动作写事件：`context_restored`。

6. 回放保障
- 历史回放只读 `Mongo + GridFS`，禁止回放阶段依赖在线 sandbox。
- shell/file 大输出统一 `artifact_ref` 化，配合事件流压缩策略。

## P1 改造清单（稳定性增强）
1. 断线重连
- noVNC 连接断开后支持会话内重连，不影响后台执行。

2. 回收守护
- Watchdog 扫描“孤儿 sandbox”（会话已终态但容器仍存活）并强制回收。

3. 容量保护
- 增加每租户 sandbox 上限与排队策略，避免资源被单租户耗尽。

## 实时链路（冻结）
- `事件流`：sandbox/worker -> backend -> frontend（SSE）。
- `实时桌面`：frontend -> sandbox（noVNC/WebSocket），backend 负责鉴权与会话映射。
- `api+worker` 分离映射规则（新增）：
  - `worker` 负责创建/销毁/重建 sandbox，并把 `session_id -> sandbox` 映射写入共享存储（Mongo，Redis可缓存）。
  - `api` WebSocket Forward 只按 `session_id` 查询共享映射，不依赖进程内存。
  - sandbox 重建必须原子更新映射并发 `sandbox_recreated` 事件。
- 前端展示策略：
  - 中间区域展示步骤/操作时间线；
  - 右侧展示实时桌面或历史快照。

## 回放链路（冻结）
- 回放数据来源：
  - `Mongo`：会话事件、步骤索引、快照元数据；
  - `GridFS`：截图、文件快照正文、长工具输出。
- 回放原则：
  - 即使 sandbox 和容器卷已清理，历史会话仍完整可读。
  - 回放不反查 sandbox 临时文件路径。

## 工具执行与可观测性（冻结）
- Browser 工具：
  - 页面操作产生关键截图与状态事件（导航、点击、输入、结果）。
  - 推理侧默认使用剪裁后的浏览器文本，不直接灌入整页 DOM 与截图二进制。
- Shell 工具：
  - 记录命令、退出码、stdout/stderr 摘要；
  - 大输出落 GridFS，事件中保存引用。
- File 工具：
  - 记录文件路径、读写动作、变更摘要；
  - 文件正文按阈值内联或转 GridFS 引用。

## 事件流压缩与裁剪（本模块约束）
- 压缩（必做）：
  - 长文本输出转 `artifact_ref`，保留事件主链。
- 裁剪（延后）：
  - MVP 不做物理删除；
  - 稳定期再做离线 prune，仅清理可替代低价值正文。

## 权限与安全（冻结）
- 工具权限按 `tenant -> group -> agent` 叠加白名单控制。
- 普通用户仅可查看被授权 Agent 的会话与回放。
- 手动接管（human-in-the-loop）写审计事件：
  - 接管人、时间、操作类型、恢复时间。

## 兼容性约束（冻结）
- 保持现有会话主实体与 API 兼容，不引入 `agent_runs` 主列表。
- SSE 采用兼容扩展字段，不破坏旧前端解析。
- noVNC 入口与会话侧边栏交互保持现有模式。

## 验收口径（冻结）
- 自动会话运行中可实时查看 `shell/file/noVNC`。
- 自动会话结束并销毁 sandbox 后，历史回放仍可完整查看。
- 手动会话首次工具调用可按需拉起 sandbox。
- 用户介入自动会话且 sandbox 已销毁时，可自动重建并继续当前会话。
- 超大工具输出不会拖垮会话查询性能。
- 越权工具调用被拦截并有审计记录。

## 本模块通过门槛（Go/No-Go）
- `Go` 条件
  - P0 全部完成并通过联调测试。
  - 随机杀掉运行中 sandbox 后，系统可自动重建并继续原会话。
  - sandbox 销毁后历史回放 100% 可读（含 shell/file/截图）。
- `No-Go` 条件
  - 仍依赖单固定 sandbox 承载多会话。
  - sandbox 故障后会话不可恢复或需要人工重建。
