# Gateway + Sandbox Agent 迁移检查清单（Step by Step）

## 目标基线
- Agent 主循环迁移到 sandbox。
- backend 不再直接跑 Agent loop，仅负责会话、状态、SSE 转发、持久化。
- gateway 作为唯一 LLM 出口（OpenAI chat/completions）。
- 前端继续复用 ai-manus 现有 SSE 事件模型与工具视图。

---

## Step 1：LLM 出口统一（gateway）
### 检查项
- [x] 网关统一入口为 `POST /v1/chat/completions`（支持 stream/non-stream）
- [x] 仅通过 bearer token + scope 鉴权访问 LLM
- [x] 具备 `issue/revoke/introspect` 凭证生命周期
- [x] 不再保留旧 runtime stream 协议文件

### 结论
- 已完成。

---

## Step 2：backend -> sandbox 调用链收敛
### 检查项
- [x] backend 通过 sandbox `runtime_config` 下发 gateway 凭证
- [x] backend 通过 sandbox `runtime/runs/start` 启动运行
- [x] backend 通过 sandbox `runtime/runs/{session_id}/events/stream` 拉取事件
- [x] 移除旧 `runtime_stream_gateway` 直连流接口

### 结论
- 已完成（已删除旧 `/runtime/llm/stream` 链路）。

---

## Step 3：sandbox Agent loop 承接
### 检查项
- [x] sandbox 内有独立 runner daemon 进程执行任务
- [x] sandbox 内 runtime agent 基于 `PlanActFlow` 运行
- [x] sandbox 内具备 tools（browser/file/shell/search/mcp/message）调用能力
- [x] sandbox runtime 仅负责 gateway 凭证配置与 model kwargs 提供

### 结论
- 已完成（当前为 runner + runtime_agent + runtime_store 闭环）。

---

## Step 4：事件协议与前端兼容
### 检查项
- [x] sandbox 输出事件包含：`tool_use/tool_result/message/done/error/wait/plan/step/title/heartbeat`
- [x] backend 映射后输出 ai-manus 原 `tool/step/message/error/done/title/wait/plan` SSE
- [x] `tool` 事件字段保持：`name/function/args/content/status/tool_call_id`
- [x] `shell/file/browser/search/mcp` 工具内容映射保持可视化

### 结论
- 已完成（字段映射与测试通过）。

---

## Step 5：重连与幂等
### 检查项
- [x] sandbox 事件流支持 `from_seq` 续传
- [x] backend chat 请求支持 `request_id` 幂等约束
- [x] 重复请求可拒绝运行中重复调用并支持完成后回放

### 结论
- 已完成（runtime runner API + backend idempotency 已接入）。

---

## Step 6：验证证据
### 测试结果
- [x] `sandbox/tests`：20 passed
- [x] `backend/tests/domain/services/test_gateway_task_runner.py`：passed
- [x] `backend/tests/interfaces/schemas/test_gateway_tool_event_pipeline.py`：passed
- [x] `gateway/tests`：7 passed

---

## 当前偏差项（需你确认）
1. runtime 策略仍保留 `manus/openfang/gateway` 三种选择（尚未收敛为 gateway-only）。
2. sandbox browser 执行层当前是 `runtime_browser.py`（CDP 实现），不是完全 1:1 复用 backend 原 browser 适配器。
3. sandbox 进程间协调当前使用 SQLite store + 轮询命令（可运行，但不是事件总线化方案）。

---

## 下一步（建议执行顺序）
1. 收敛 runtime 策略为 `gateway-only`，删除 `manus/openfang` runtime 分支代码。
2. Browser 执行层改为与 ai-manus 原 browser 能力对齐（优先复用原工具行为定义，不改前端协议）。
3. 完整联调：`frontend -> backend -> sandbox -> gateway -> model`，验证表单录入全链路。

