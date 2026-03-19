# 05 观测与告警模块 API Schema 设计稿

## 说明
- 指标首选 Prometheus/OpenTelemetry 暴露。
- REST 仅做查询聚合与告警查看（可选）。

## 可选接口
1. `GET /observability/overview`
- 返回：核心 KPI（run_success_rate, trigger_pending_wait_p95, beat_lag_seconds, reconciler_repair_count, sandbox_fail_rate...）

2. `GET /observability/alerts`
- 查询：`level(P1|P2|P3), status(active|resolved), tenant_id`

3. `GET /observability/traces/{session_id}`
- 返回：`trace_id, spans[], related_events[]`

## 数据字段规范
- 统一标签：`tenant_id, group_id, agent_id, source_type`
