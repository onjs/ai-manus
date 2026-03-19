# 21 Runtime 统一事件协议开发任务清单

## 状态
- 开发完成，进入回归阶段。

## 目标
- 统一 `gateway/sandbox/backend` 事件协议。
- 工具事件映射闭环，保证前端 `tool` 事件字段稳定。

## 任务拆解

### T1 协议模型落地（Gateway + Sandbox）
- [x] 在 gateway 定义 `RuntimeProtocolEvent` 并做字段校验。
- [x] 在 sandbox 定义同构 `RuntimeProtocolEvent` 并做字段校验。
- [x] 固定事件集：`tool_use/tool_result/message_delta/message/done/error/heartbeat`。

### T2 SSE 严格解析
- [x] SSE 必须带 `event`，缺失直接报错。
- [x] `data` 必须是 JSON object，非对象报错。
- [x] 去除默认 `chunk` 回落行为。

### T3 Runner 事件输出统一
- [x] 去掉 `runner_event/runner_status` 包装。
- [x] sandbox 直接输出协议事件名。
- [x] 保留 `seq/timestamp/session_id` 作为 runner 附加元数据。

### T4 ToolEvent 映射闭环（Backend）
- [x] `GatewayTaskRunner` 对 `tool_use/tool_result` 做无损映射（保留 `function_result`）。
- [x] `tool_result` 按工具类型生成 `tool_content`：
  - `browser -> BrowserToolContent`
  - `search -> SearchToolContent`
  - `shell -> ShellToolContent`
  - `file -> FileToolContent`
  - 其他 -> `McpToolContent`
- [x] `event.py` 对外输出字段稳定：`name/function/args/content/status`。

### T5 测试与验收
- [x] gateway 测试通过（runtime stream/token lifecycle）。
- [x] sandbox 测试通过（runtime service/runner service/runner api/store）。
- [x] backend 测试通过（gateway task runner + event mapper + 相关回归）。
- [x] 新增字段稳定性断言（`ToolSSEEvent` 序列化含 `name/function/args/content/status`）。

## 验收标准
1. 运行链路不出现旧事件名（`chunk/runner_event/runner_status`）作为协议输出。
2. `tool_*` 事件缺字段时应快速失败，不得静默吞掉。
3. 前端工具面板能稳定依赖 `name/function/args/content/status` 渲染。
4. 全链路相关单测全部通过。
