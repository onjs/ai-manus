# ai-manus 多 Agent 企业流程化 MVP 需求梳理

## 1. 项目目标

基于 `ai-manus` 现有能力（Agent、Sandbox、SSE、VNC、MCP），实现一个“企业流程自动化”MVP，而不是“单次对话助手”。

MVP 目标场景：采购流程自动化。  
核心目标：让多个 Agent 分别扮演企业内不同岗位员工，按职责处理同一流程的不同阶段，并提供可追溯的操作记录与回放能力。

## 2. 业务抽象

### 2.1 核心实体

- `AgentEmployee`：虚拟员工（有员工编号、岗位、权限范围、可处理流程节点）。
- `WorkflowDefinition`：流程定义（如采购流程，包含状态机和转移条件）。
- `WorkflowInstance`：流程实例（一次具体采购请求，类似“工单/会话”）。
- `Session`：复用现有会话模型与 `session_id`，作为流程实例的承载容器。
- `Task/Todo`：实例中的待办项（指派给某个 AgentEmployee）。
- `OperationRecord`：操作记录（每一步操作、输入、输出、证据、快照索引）。

### 2.2 角色模型

- 普通员工：只能查看自己权限范围内 Agent 的流程与记录。
- 部门负责人（可选）：可查看部门内 Agent 与流程数据。
- 管理员：可查看所有 Agent 与全部流程记录。

## 3. 目标流程（采购）

建议的标准状态机（可裁剪）：

1. 需求触发（库存阈值命中/人工发起）
2. 采购申请创建
3. 预算与合规校验
4. 供应商检索与比价
5. 审批
6. PO 草拟/下发
7. 归档与审计

每个状态由明确 Agent 负责，状态转移由规则驱动，不依赖人工持续对话触发。

## 4. 多 Agent 运行机制

### 4.1 调度模式

- 每个 Agent 支持定时巡检（polling / cron-like）。
- 巡检内容：查询“当前是否有我可处理的待办”。
- 命中待办后自动执行对应步骤，完成后投递下游待办给下一角色 Agent。
- 自动执行由系统创建 `auto` 类型会话（无人工参与也可完整运行并留痕）。

### 4.2 Agent 交接机制

- 上游 Agent 完成后写入结构化结果（标准字段 + 附件 + 证据）。
- Orchestrator 根据状态机与规则分发给下一 Agent。
- 高风险节点支持 Human-in-the-loop 阻断（未批准不可继续）。

## 5. 可观测与回溯（重点）

### 5.1 实时可视化

- 前端实时看到每个 Agent 当前在做什么（步骤、工具调用、状态）。
- 支持并行展示多个 Agent 的执行流。

### 5.2 非实时情况下的完整记录

- 即使无人打开页面，也必须完整保存每一步操作记录。
- 每条记录至少包含：
  - `workflow_instance_id`
  - `agent_employee_id`
  - `step/state`
  - `tool/function`
  - `arguments`
  - `result/status/error`
  - `timestamp`
  - `snapshot_ref`（截图/终端输出/文件版本引用）

### 5.3 回放体验

- 左侧改为“按 Agent 分组的会话列表”：
  - 分组维度：`agent_employee_id`
  - 列表项：仍复用现有会话（`session_id`），但区分 `manual/auto`
- 中间区域保留现有对话框，同时显示操作时间线（人可以随时插话引导 Agent）。
- 点击任一操作记录可查看当时快照（浏览器视图、终端输出、文件内容快照）。

## 6. 系统能力要求

### 6.1 工具与集成

- 复用现有 `shell/file/browser/search/mcp/message` 工具能力。
- 通过 MCP 接入外部企业系统（先 mock connector，后真实 ERP/审批/邮件系统）。

### 6.2 Sandbox 策略

- 每个流程实例可绑定独立 sandbox（推荐），避免跨实例污染。
- 需要保留快照与关键执行上下文用于审计回放。

### 6.3 权限与审计

- 所有操作需带操作者标识（哪一个 AgentEmployee）。
- 所有高风险动作需记录规则命中与审批链路。
- 保证可追责：谁在何时依据什么证据做了什么动作。

### 6.4 最小字段扩展（兼容现有 session）

- `trigger_type`: `manual | auto`
- `trigger_source`: `user | scheduler | upstream_agent`
- `agent_employee_id`: 当前会话所属虚拟员工
- `workflow_instance_id`: 所属流程实例 ID（可与 session 1:1 或 1:N 映射）

## 7. MVP 范围（第一阶段）

建议先做最小闭环：

1. 3 个 Agent 角色
   - `InventoryAgent`：库存巡检并触发采购申请
   - `SourcingAgent`：供应商检索与比价
   - `POAgent`：生成 PO 草稿并提交审批
2. 2 类系统接入
   - 供应商与库存（mock 数据源）
   - 审批系统（mock）
3. 1 条前端主路径
   - 左侧按 Agent 分组会话列表（含 `manual/auto` 标记）
   - 中间对话 + 操作时间线混合视图
   - 右侧实时面板/回放面板（点击时间线节点查看）

## 8. 验收标准（MVP）

- 可以自动从“库存阈值命中”触发一条采购流程实例。
- 至少 3 个 Agent 能按顺序自动处理并完成交接。
- 前端可实时看到步骤推进与工具调用。
- 在未打开前端时，所有操作仍被完整记录。
- 可按流程实例回放历史记录并查看关键快照。
- 权限控制生效：普通用户看不到未授权 Agent 的记录；管理员可见全部。

## 9. 非目标（当前阶段不做）

- 不追求一次性接入真实 SAP/Oracle/Workday 全链路。
- 不追求复杂跨组织审批编排。
- 不追求全量 BI 报表系统，仅保留核心可观测指标。

## 10. 后续迭代建议

1. 接入真实 ERP/合同/邮件系统（MCP 生产化）。
2. 引入规则引擎（预算、合规、供应商准入）可配置化。
3. 支持多流程模板（采购、报销、合同审核、人事入转调离）。
4. 增加 SLA、失败重试、告警与运营看板。

## 11. 当前确认方案（2026-03-13）

- 不推翻现有会话体系，直接复用 `session_id`。
- Agent 可以自动发起会话并自动执行，用户不在线也照常落记录。
- 左侧从“全量会话平铺”改为“按 Agent 分组会话”。
- 中间保留对话输入能力，支持 Human-in-the-loop 引导。
- 本阶段本质是“在现有 ai-manus 上增加自动操作能力”，不是重写前端交互框架。

## 12. OpenFang 接入 MVP（2026-03-13）

### 12.1 已接入能力（当前分支）

- 后端新增运行时开关：`AGENT_RUNTIME=manus | openfang`。
- 当 `AGENT_RUNTIME=openfang` 时，`Session -> Chat` 执行链会切到 `OpenFangTaskRunner`。
- 新增 OpenFang HTTP/SSE 客户端桥接：
  - `POST /api/agents/{id}/message/stream`
  - 解析 `chunk/tool_use/tool_result/done` 事件并映射为 ai-manus 原生 SSE 事件。
- 会话新增 `openfang_agent_id` 字段，用于绑定 OpenFang agent（跨多轮消息复用）。

### 12.2 当前映射策略（最小可跑）

- `chunk`：拼接为最终 assistant 消息。
- `tool_use/tool_result`：映射为 ai-manus 的 `tool` 事件（暂统一按 `mcp` 类型展示，避免依赖 sandbox 回读接口）。
- `done`：补充 usage 工具事件，并输出 `done` 事件。

### 12.3 当前限制

- 右侧实时面板暂不复用 OpenFang 原生浏览器/shell/file 实时画面（仍沿用 ai-manus 现有渲染协议）。
- OpenFang 工具事件先按通用记录展示，不做 shell/file 专属快照回放。
- 若要达到“逐字符终端回放 + 文件版本快照 + 点击时间线还原”，需要后续补充统一快照仓储与事件协议适配层。

### 12.4 下一步建议

1. 先验证端到端：ai-manus 前端发消息 -> OpenFang 执行 -> ai-manus 时间线展示。
2. 增加 Agent 分组视图（左侧）并标注 `runtime=manus/openfang`。
3. 设计统一 `OperationRecord` 结构，把 OpenFang 事件与 ai-manus tool 事件都归一化入库。

## 13. 实施顺序调整（2026-03-14）

为降低耦合风险并加快验证速度，当前实施顺序调整为两阶段：

### 阶段 A：先做 Backend + Agent 脚手架（不先接前端/沙箱）

- 先完成多 Agent 后端与调度框架。
- 先打通本地能力闭环：`browser / file / shell` 在本地执行成功。
- 验证重点：
  - Agent 生命周期与调度是否稳定。
  - 多模型配置是否按 Agent 独立生效。
  - 任务执行、事件记录、失败重试是否可闭环。

### 阶段 B：再接入 ai-manus Frontend + Sandbox

- 在阶段 A 验证通过后，再接入现有 `ai-manus frontend` 与 `ai-manus sandbox`。
- 接入时必须保持 API 前后兼容，重点包括：
  - 会话与事件流接口兼容（SSE 事件结构不破坏现有渲染）。
  - VNC / shell / file 相关接口路径与返回结构兼容。
  - 历史回放数据结构兼容（前端可继续读取旧会话数据）。

该策略优先保证“核心 Agent 框架先可跑、再对接 UI 与运行环境”，避免同时改动过多导致定位困难。
