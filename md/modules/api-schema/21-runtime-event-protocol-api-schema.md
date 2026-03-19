# 21 Runtime 统一事件协议 API Schema

## 状态
- 已冻结。

## 适用范围
- `gateway -> sandbox -> backend` 的 runtime SSE 事件流。

## 事件集合（固定）
- `tool_use`
- `tool_result`
- `message_delta`
- `message`
- `done`
- `error`
- `heartbeat`

## 通用规则
1. SSE 帧必须包含 `event:`。
2. `data:` 必须是 JSON object。
3. 不允许事件名漂移（禁止 `chunk/runner_event/runner_status`）。

## 事件数据结构

### `tool_use`
```json
{
  "tool_name": "browser",
  "function_name": "browser_click",
  "function_args": {"selector": "#submit"},
  "tool_call_id": "call_1",
  "status": "calling",
  "function_result": null
}
```

### `tool_result`
```json
{
  "tool_name": "file",
  "function_name": "file_read",
  "function_args": {"file": "/home/ubuntu/a.txt"},
  "tool_call_id": "call_2",
  "status": "called",
  "function_result": {"data": {"content": "hello"}}
}
```

### `message_delta`
```json
{
  "content": "正在打开页面..."
}
```

### `message`
```json
{
  "message": "页面已打开，准备填写表单。"
}
```

### `done`
```json
{}
```

### `error`
```json
{
  "error": "Gateway stream failed: 401"
}
```

### `heartbeat`
```json
{
  "status": "running"
}
```

## Runner Stream 附加字段（sandbox -> backend）
- `session_id: string`
- `seq: integer`
- `timestamp: integer`

说明：
- 附加字段由 sandbox runner SSE 注入；
- backend 映射工具/消息事件时仅消费协议字段，`seq` 仅用于游标推进。

## Backend 对前端输出（ToolEvent）
`event.py` 中 `tool` 事件稳定输出字段：
- `name`
- `function`
- `args`
- `content`
- `status`

对应结构：
```json
{
  "event": "tool",
  "data": {
    "event_id": "1742370000000-0",
    "timestamp": 1742370000,
    "tool_call_id": "call_2",
    "name": "file",
    "function": "file_read",
    "args": {"file": "/home/ubuntu/a.txt"},
    "status": "called",
    "content": {"content": "hello"}
  }
}
```
