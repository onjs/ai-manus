# 21 Runtime 统一事件协议对照表（Gateway/Sandbox/Backend）

## 状态
- 已冻结（代码已落地并通过链路测试）。

## 目标
- 统一 `sandbox/gateway -> backend` 事件协议，消除历史包装事件与字段漂移。
- 固定事件类型与字段约束，作为后续前后端联调唯一真相源。

## 事件类型（全量）
- `tool_use`
- `tool_result`
- `message_delta`
- `message`
- `done`
- `error`
- `heartbeat`

## 总体约束（强校验）
1. SSE 必须带 `event:` 名称；缺失直接报错。
2. SSE `data` 必须是 JSON object；非对象直接报错。
3. 不允许 `runner_event/runner_status/chunk` 这类包装或旧事件名。
4. `tool_*` 事件必须包含完整字段：
- `tool_name`
- `function_name`
- `function_args`
- `tool_call_id`
- `status`
- `function_result`

## 字段对照（协议层）

| 事件 | 必填字段 | 字段类型 | 语义 |
|---|---|---|---|
| `tool_use` | `tool_name,function_name,function_args,tool_call_id,status,function_result` | `str,str,dict,str,str,any` | 工具开始调用事件，`status` 通常为 `calling` |
| `tool_result` | `tool_name,function_name,function_args,tool_call_id,status,function_result` | `str,str,dict,str,str,any` | 工具调用完成事件，`status` 通常为 `called` |
| `message_delta` | `content` | `str` | 增量文本 |
| `message` | `message` | `str` | 完整文本（可覆盖聚合结果） |
| `done` | 无 | - | 终止事件（成功） |
| `error` | `error` | `str` | 终止事件（失败） |
| `heartbeat` | `status` | `str` | 链路心跳（非业务输出） |

## 链路映射（代码实现）
1. `gateway`
- 协议模型与校验：`gateway/app/interfaces/schemas/runtime_event.py`
- 流输出：`gateway/app/application/services/runtime_stream_service.py`
- Provider 输出协议事件：`gateway/app/infrastructure/providers/openai_provider.py`

2. `sandbox`
- 协议模型与校验：`sandbox/app/schemas/runtime_event.py`
- 网关流消费与校验：`sandbox/app/services/runtime.py`
- runner 事件持久化与转发：`sandbox/app/runner/daemon.py`
- SSE 直出统一事件名：`sandbox/app/services/runtime_runner.py`

3. `backend`
- sandbox SSE 读取：`backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- 事件映射到域事件：`backend/app/domain/services/gateway_task_runner.py`

## Backend 映射规则（冻结）
1. `message_delta`
- 累积到内存 `chunks`，不立即出 `MessageEvent`。

2. `message`
- 要求字段 `message`；清空 `chunks` 后写入完整文本。

3. `done`
- 输出 `MessageEvent(assistant, ''.join(chunks))`（若有）+ `DoneEvent`，然后终止。

4. `error`
- 输出 `ErrorEvent(error)`，然后终止。

5. `tool_use/tool_result`
- 严格读取完整字段；
- `status` 映射到 `ToolStatus`；
- `tool_result` 的 `function_result` 同时写入 `tool_content`（当前为 `McpToolContent(result=...)`）。

6. `heartbeat`
- 仅链路保活，backend 忽略，不写会话事件。

## 传输扩展元数据（Runner Stream）
`sandbox runtime runner stream` 在协议 `data` 基础上附加：
- `session_id: str`
- `seq: int`
- `timestamp: int`

backend 处理时只把 `seq` 用于游标推进，业务映射只消费协议字段。

## 标准 SSE 示例

```text
event: tool_use
data: {"tool_name":"browser","function_name":"click","function_args":{"selector":"#submit"},"tool_call_id":"call_1","status":"calling","function_result":null,"session_id":"s1","seq":12,"timestamp":1710000000}

event: message_delta
data: {"content":"已打开页面","session_id":"s1","seq":13,"timestamp":1710000001}

event: tool_result
data: {"tool_name":"browser","function_name":"click","function_args":{"selector":"#submit"},"tool_call_id":"call_1","status":"called","function_result":{"ok":true},"session_id":"s1","seq":14,"timestamp":1710000002}

event: done
data: {"session_id":"s1","seq":15,"timestamp":1710000003}
```

## 验收清单
- [x] gateway 仅输出协议内事件名
- [x] sandbox 对非法 `event/data` 直接报错
- [x] backend 不再依赖 `runner_event/runner_status/chunk`
- [x] tool 事件字段缺失时可观测失败（非静默）
- [x] 现有测试全绿（gateway/sandbox/backend）

## 关联文档
- [21-runtime-event-protocol-api-schema.md](/Users/zuos/code/github/ai-manus/md/modules/api-schema/21-runtime-event-protocol-api-schema.md)
- [21-runtime-event-protocol-dev-tasks.md](/Users/zuos/code/github/ai-manus/md/modules/dev-tasks/21-runtime-event-protocol-dev-tasks.md)
