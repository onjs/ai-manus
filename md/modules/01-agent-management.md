# 01 Agent管理模块

## 状态
- 已冻结。

## 基线
- 采用 `Session扩展`，不新增 `agent_runs` 主实体。
- 自动执行：每次触发创建 1 个 `source_type=auto` 会话。
- 手动执行：用户新建会话为 `source_type=manual`，用户介入自动会话沿用原 `session_id`。
- 多租户：`tenant_id` 行级隔离。
- 权限：`platform_admin / tenant_admin / tenant_user` + `Agent级授权`。
- 前端左侧会话按 `业务分组(group)` 展示。
- SSE 通道采用“双通道”：
  - 全局会话摘要流（左侧常驻，接收自动/手动会话变化）
  - 会话详情流（中间时间线按当前会话订阅）
- 用户介入保留 ai-manus 语义：`session.status=waiting`（如登录/审批确认）。
- 介入时若 sandbox 已销毁/不可用，自动新建并回绑当前会话。
- 调度执行采用 `Celery Beat + Broker + Worker`，业务层保留 `pending`。
- Agent loop 使用内部状态机（写 `run_meta`），保留 automaton 策略层（策略先决/统一工具入口/执行后治理），并支持每轮上限、超时、回合内重试与终止条件。
- 上下文层采用 `planner + execution` 双层记忆，浏览器内容先剪裁再入 LLM。
- 模型配置采用“配置中心”：
  - `agents` 仅保存 `model_profile_id`；
  - 各类 LLM 的 `api_key` 在 `model_profiles` 中加密存储。

## 主文档
- [agent-management-module.md](/Users/zuos/code/github/ai-manus/md/agent-management-module.md)
- [agent-loop-plan-exec-solution-zh.md](/Users/zuos/code/github/ai-manus/md/agent-loop-plan-exec-solution-zh.md)
