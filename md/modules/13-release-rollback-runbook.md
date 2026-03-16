# 13 发布与回滚 Runbook（开工前必备）

## 目标
- 规范发布、灰度、观测、回滚步骤。

## 发布前
1. 核对迁移脚本与备份状态
2. 核对 feature flags 默认值
3. 核对告警规则已启用

## 灰度步骤
1. 灰度 10%
- 开启新字段写入与新接口读
- 观察 15-30 分钟

2. 灰度 50%
- 观察错误率、Celery 队列延迟、sandbox 失败率

3. 全量 100%
- 固定发布版本，记录变更单

## 核心观测指标（门禁）
1. `run_failed_rate_5m`
2. `celery_queue_wait_p95`
3. `sandbox_create_fail_rate_5m`
4. `sse_emit_error_count_5m`
5. `celery_worker_heartbeat_missing`
6. `beat_lag_seconds_p95`
7. `reconciler_repair_count`

## 回滚触发
- 任一 P1 告警持续 > 5 分钟
- 或 P2 告警持续 > 15 分钟且趋势恶化

## 回滚步骤
1. 关闭新路径 feature flags
2. 停止新调度入口（保留运行中会话）
3. 回切到上一稳定版本
4. 校验会话可读、回放可用
5. 发布回滚公告与复盘任务

## 事后复盘
1. 时间线（发生-检测-处置-恢复）
2. 根因与修复
3. 预防项与 owner
