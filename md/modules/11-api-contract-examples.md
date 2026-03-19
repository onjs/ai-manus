# 11 接口契约样例集（开工前必备）

## 目标
- 提供前后端联调统一样例，减少字段理解偏差。

## 统一响应样例
```json
{
  "code": "SUCCESS",
  "msg": "ok",
  "data": {}
}
```

## 样例 1：创建 Agent
`POST /agents`

请求：
```json
{
  "name": "procurement-intake",
  "code": "proc_intake",
  "group_id": "grp_01",
  "model_profile_id": "mpf_openai_gpt5_prod",
  "skills_config": {"allow": ["default/procurement-intake"]},
  "tools_config": {"profile": "custom", "allow": ["browser", "shell", "file"]},
  "prompts": {"version": 1, "agents_md": "你是采购发起岗，负责巡检并触发采购申请。"}
}
```

响应：
```json
{"code":"SUCCESS","msg":"ok","data":{"agent_id":"agt_01"}}
```

## 样例 1.1：创建模型档案（API Key 加密入库）
`POST /platform/model-profiles`

请求：
```json
{
  "name": "openai-gpt5-prod",
  "provider": "openai",
  "model": "gpt-5",
  "api_base": "https://api.openai.com/v1",
  "params": {"temperature": 0.2, "max_tokens": 4096},
  "api_key": "sk-xxxx"
}
```

## 样例 1.2：创建任务定义（Agent 绑定）
`POST /agent-task-definitions`

请求：
```json
{
  "agent_id": "agt_01",
  "name": "库存阈值巡检",
  "goal_template": "巡检库存系统，发现库存低于阈值时创建采购申请",
  "input_schema": {"type":"object","properties":{"warehouse_id":{"type":"string"}}},
  "enabled": true
}
```

响应：
```json
{"code":"SUCCESS","msg":"ok","data":{"task_id":"tsk_01","agent_id":"agt_01"}}
```

## 样例 1.3：创建任务定时任务
`POST /task-schedules`

请求：
```json
{
  "task_id": "tsk_01",
  "cron_expr": "*/5 * * * *",
  "timezone": "Asia/Shanghai",
  "enabled": true
}
```

响应：
```json
{"code":"SUCCESS","msg":"ok","data":{"task_schedule_id":"sch_01"}}
```

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "profile_id":"mpf_openai_gpt5_prod",
    "secret_masked":"sk-***9f3a",
    "secret_fingerprint":"fp_4c2d"
  }
}
```

## 样例 2：会话列表（扩展字段）
`GET /sessions?group_id=grp_01&source_type=auto`

响应片段：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "sessions":[
      {
        "session_id":"ses_01",
        "title":"采购巡检",
        "status":"running",
        "agent_id":"agt_01",
        "agent_name":"procurement-intake",
        "task_id":"tsk_01",
        "task_name":"库存阈值巡检",
        "task_schedule_id":"sch_01",
        "group_id":"grp_01",
        "group_name":"采购",
        "source_type":"auto"
      }
    ]
  }
}
```

## 样例 3：发布配置版本
`POST /agents/{agent_id}/config-versions/{version_id}/publish`

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{"published_version":"cfg_v12","effective_scope":"new_sessions_only"}
}
```

## 样例 4：全局摘要 SSE（左侧常驻）
`GET /sessions/stream`

```json
{
  "event":"session_upsert",
  "data":{
    "event_id":"evt_sum_1001",
    "timestamp":"2026-03-16T10:00:00Z",
    "session_id":"ses_01",
    "title":"采购巡检",
    "status":"running",
    "agent_id":"agt_01",
    "agent_name":"procurement-intake",
    "task_id":"tsk_01",
    "task_name":"库存阈值巡检",
    "task_schedule_id":"sch_01",
    "group_id":"grp_01",
    "group_name":"采购",
    "source_type":"auto",
    "latest_message_at":1770000000,
    "unread_message_count":1
  }
}
```

## 样例 4.1：会话详情 SSE（中间时间线）
`GET /sessions/{session_id}/stream`

```json
{
  "event":"timeline",
  "data":{
    "session_id":"ses_01",
    "step_id":"step_02",
    "action":"step_started",
    "agent_id":"agt_01",
    "group_id":"grp_01",
    "source_type":"auto",
    "timestamp":"2026-03-14T11:00:00Z"
  }
}
```

```json
{
  "event":"timeline",
  "data":{
    "session_id":"ses_01",
    "action":"sandbox_recreated",
    "old_sandbox_id":"sbx_old",
    "new_sandbox_id":"sbx_new",
    "reason":"health_check_failed"
  }
}
```

## 样例 5：错误响应
```json
{
  "code":"TENANT_QUOTA_EXCEEDED",
  "msg":"tenant concurrency limit reached",
  "data":{"retryable": true}
}
```

## 样例 6：上下文利用率（调试接口）
`GET /sessions/{session_id}/context/utilization`

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "session_id":"ses_01",
    "utilization":0.82,
    "compression_stage":2,
    "token_breakdown":{
      "anchor_tokens":620,
      "planner_tokens":540,
      "execution_tokens":1310,
      "recent_turn_tokens":880
    }
  }
}
```

## 样例 7：浏览器剪裁预览（调试接口）
`POST /sessions/{session_id}/context/clip-browser-preview`

请求：
```json
{
  "step_id":"step_03",
  "source_type":"playwright",
  "raw_content":"<html>...</html>",
  "clip_policy":{"max_chars":6000,"max_tokens":1800,"include_interactives":true}
}
```

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "clip_text":"页面摘要 ...",
    "clip_ratio":0.27,
    "artifact_ref":"art_browser_123"
  }
}
```

## 样例 8：调度触发记录（API Executor 映射）
`GET /scheduler/triggers?agent_id=agt_01&task_id=tsk_01&status=running`

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "triggers":[
      {
        "trigger_id":"trg_1001",
        "status":"running",
        "task_id":"tsk_01",
        "task_schedule_id":"sch_01",
        "session_id":"ses_01",
        "session_status":"running",
        "executor_run_id":"exe_9f3e",
        "executor_node_id":"api-node-01",
        "started_at":"2026-03-15T09:10:00Z"
      }
    ]
  }
}
```

## 样例 9：手动对账修复结果
`POST /scheduler/reconcile/run`

响应：
```json
{
  "code":"SUCCESS",
  "msg":"ok",
  "data":{
    "run_id":"rec_20260315_01",
    "scanned_count":128,
    "repaired_count":3,
    "released_leases":2,
    "details":[
      {"trigger_id":"trg_102","from_status":"pending","to_status":"pending","reason_code":"EXECUTOR_LEASE_RETRY"},
      {"trigger_id":"trg_108","from_status":"running","to_status":"finished","reason_code":"EXECUTOR_STALE"}
    ]
  }
}
```

## 样例 10：Gateway 错误响应样例

### 10.1 Token 过期
`POST /internal/v1/llm/ask`

```json
{
  "code":"GATEWAY_TOKEN_EXPIRED",
  "msg":"token expired",
  "data":{"retryable": false},
  "trace_id":"trc_01"
}
```

### 10.2 Scope 不足
`POST /internal/v1/llm/stream`

```json
{
  "code":"GATEWAY_SCOPE_DENIED",
  "msg":"scope llm:stream required",
  "data":{"retryable": false},
  "trace_id":"trc_02"
}
```

### 10.3 策略拦截
`POST /internal/v1/llm/ask`

```json
{
  "code":"GATEWAY_POLICY_BLOCKED",
  "msg":"request blocked by policy",
  "data":{
    "retryable": false,
    "policy_rule":"sensitive_action_v1"
  },
  "trace_id":"trc_03"
}
```

### 10.4 限流触发
`POST /internal/v1/llm/ask`

```json
{
  "code":"GATEWAY_RATE_LIMITED",
  "msg":"rate limit exceeded",
  "data":{
    "retryable": true,
    "retry_after_seconds": 10
  },
  "trace_id":"trc_04"
}
```

### 10.5 熔断窗口
`POST /internal/v1/llm/ask`

```json
{
  "code":"GATEWAY_CIRCUIT_OPEN",
  "msg":"upstream circuit open",
  "data":{
    "retryable": true,
    "retry_after_seconds": 30
  },
  "trace_id":"trc_05"
}
```

### 10.6 上游超时
`POST /internal/v1/llm/stream`

```json
{
  "code":"GATEWAY_UPSTREAM_TIMEOUT",
  "msg":"upstream model timeout",
  "data":{"retryable": true},
  "trace_id":"trc_06"
}
```
