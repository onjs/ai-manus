# Runtime Toolchain 集成验证（Search + MCP）

## 目标
验证 `gateway -> sandbox runner -> backend event mapper` 链路在 `search/mcp` 工具场景下字段稳定。

## 执行命令
1. Sandbox 侧（daemon 真执行 tool 链路）
```bash
uv run --project sandbox pytest -q sandbox/tests/test_runtime_runner_daemon_toolchain.py
```

2. Backend 侧（GatewayTaskRunner + EventMapper 联合验证）
```bash
uv run --project backend pytest -q \
  backend/tests/interfaces/schemas/test_gateway_tool_event_pipeline.py \
  backend/tests/interfaces/schemas/test_event_mapper.py \
  backend/tests/domain/services/test_gateway_task_runner.py
```

3. 端到端流回归（从 backend 发起，到 frontend 可消费字段）
```bash
uv run --project backend python scripts/e2e_stream_regression.py \
  --base-url http://localhost:8000/api/v1 \
  --message "请打开浏览器并访问一个页面，然后总结结果"
```

## 验收点
- `tool_use/tool_result` 事件都能落到 runtime store。
- `search` 工具 `function_args.query` 稳定存在。
- `mcp` 工具 `content.result` 稳定存在。
- SSE 对外字段稳定：`name/function/args/content/status`。
- `tool/step/message/wait/error/done` 事件流可被前端同一套解析逻辑消费。
