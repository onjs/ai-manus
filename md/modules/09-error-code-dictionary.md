# 09 全局错误码字典（开工前必备）

## 目标
- 跨模块统一错误码命名、HTTP 状态、可重试语义、用户可读提示。

## 规范
- 统一格式：`<DOMAIN>_<SCENARIO>_<DETAIL>`
- 统一响应：`APIResponse{code,msg,data}`，其中 `code` 为业务错误码。
- 可重试字段：`retryable: true|false`

## 错误码分组
### A. 通用
1. `INVALID_REQUEST` -> HTTP 400 -> retryable=false
2. `UNAUTHORIZED` -> HTTP 401 -> retryable=false
3. `FORBIDDEN` -> HTTP 403 -> retryable=false
4. `RESOURCE_NOT_FOUND` -> HTTP 404 -> retryable=false
5. `CONFLICT` -> HTTP 409 -> retryable=false
6. `RATE_LIMITED` -> HTTP 429 -> retryable=true
7. `INTERNAL_ERROR` -> HTTP 500 -> retryable=true

### B. Agent 管理
1. `AGENT_NOT_FOUND` -> 404 -> false
2. `AGENT_CODE_CONFLICT` -> 409 -> false
3. `AGENT_GROUP_NOT_FOUND` -> 404 -> false
4. `SCHEDULE_CONFLICT` -> 409 -> false
5. `SCHEDULE_CRON_INVALID` -> 400 -> false
6. `PERMISSION_DUPLICATED` -> 409 -> false

### C. 调度与队列
1. `TRIGGER_NOT_FOUND` -> 404 -> false
2. `TRIGGER_ALREADY_RUNNING` -> 409 -> false
3. `DISPATCH_CONCURRENCY_LIMIT` -> 429 -> true
4. `WORKER_HEARTBEAT_TIMEOUT` -> 503 -> true
5. `IDEMPOTENCY_CONFLICT` -> 409 -> false

### D. 上下文与压缩
1. `CONTEXT_ASSEMBLE_FAILED` -> 500 -> true
2. `CONTEXT_BUDGET_EXCEEDED` -> 422 -> true
3. `COMPRESSION_FAILED` -> 500 -> true
4. `CONTEXT_INTEGRITY_CHECK_FAILED` -> 409 -> true
5. `CHECKPOINT_RESTORE_FAILED` -> 500 -> true

### E. Sandbox/工具
1. `SANDBOX_CREATE_FAILED` -> 503 -> true
2. `SANDBOX_UNHEALTHY` -> 503 -> true
3. `SANDBOX_RECREATE_FAILED` -> 503 -> true
4. `TOOL_DENIED` -> 403 -> false
5. `TOOL_TIMEOUT` -> 504 -> true
6. `TOOL_EXEC_FAILED` -> 500 -> true
7. `ARTIFACT_NOT_FOUND` -> 404 -> false

### F. Skills/策略
1. `SKILL_ID_CONFLICT` -> 409 -> false
2. `SKILL_SOURCE_NOT_FOUND` -> 404 -> false
3. `SKILL_PARSE_ERROR` -> 422 -> false
4. `SKILL_REQUIREMENT_UNMET` -> 422 -> false
5. `SKILL_SECURITY_REJECTED` -> 403 -> false
6. `PROMPT_INJECTION_FAILED` -> 500 -> true

### G. 平台与权限
1. `TENANT_NOT_FOUND` -> 404 -> false
2. `TENANT_SUSPENDED` -> 403 -> false
3. `TENANT_QUOTA_EXCEEDED` -> 429 -> true
4. `USER_ROLE_FORBIDDEN` -> 403 -> false
5. `AGENT_PERMISSION_DENIED` -> 403 -> false

### H. 配置发布回滚
1. `CONFIG_VERSION_NOT_FOUND` -> 404 -> false
2. `CONFIG_VALIDATE_FAILED` -> 422 -> false
3. `CONFIG_PUBLISH_FAILED` -> 500 -> true
4. `CONFIG_ROLLBACK_FAILED` -> 500 -> true
5. `CONFIG_PUBLISHED_VERSION_MISSING` -> 409 -> false

## 备注
- 首次开发阶段按本字典落实现；新增错误码必须补本文件。
