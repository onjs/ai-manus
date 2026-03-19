# 20 Sandbox + Agent + Gateway 改造风险台账

## 适用范围
- 仅覆盖本轮改造：`sandbox + agent + gateway`。
- 不覆盖多租户管理台、业务流程编排、向量记忆等后续模块。

## 风险分级
- `P1`：影响全局可用性或安全边界。
- `P2`：影响核心链路稳定性或数据一致性。
- `P3`：影响体验或局部性能。

## 风险台账（7项）

| 风险ID | 风险描述 | 等级 | 触发条件 | 检测指标/阈值 | 应急动作 |
|---|---|---|---|---|---|
| R-01 | Runner 绕过 Gateway 直连模型厂商 | P1 | Runner 进程出现任何对模型厂商域名的出网请求 | `runner_direct_provider_egress_count > 0`；或网络审计命中 `api.openai.com/deepseek/...` | 1) 立即阻断 runner 所在策略组出网；2) 将当前 run 置 `failed` 并吊销 token；3) 触发安全告警并保留审计证据 |
| R-02 | 短期 token 在重建/取消时存在竞态窗口 | P1 | sandbox 重建、任务取消或 run 结束后旧 token 仍可调用 gateway | `gateway_token_revoked_but_accepted_count > 0`；`token_revoke_propagation_ms p95 > 1000` | 1) 临时将 token TTL 下调；2) 启用 `jti` 强校验与黑名单优先；3) 对涉事 session 强制重新签发并回收旧 token |
| R-03 | Gateway 单点或拥塞导致全局推理降级 | P1 | gateway 单副本故障、上游超时堆积、限流配置不当 | `gateway_5xx_rate_5m > 5%`；`gateway_latency_ms_p95 > 3000`；`gateway_queue_depth` 持续增长 | 1) 切流到健康副本并扩容；2) 开启熔断与降级路由；3) 暂停低优先级 run，保障核心会话 |
| R-04 | 新增一跳导致端到端延迟显著上升 | P2 | 长链路任务中 ask/stream 慢，step 长时间无进展 | `run_no_progress_seconds > 60`；`step_duration_ms_p95` 超基线 30% | 1) 打开流式优先与连接复用；2) 下调单轮 token 上限；3) 超时 run 进入失败收敛并记录瓶颈 trace |
| R-05 | sandbox 内 runner 生命周期失控（僵尸进程/悬挂） | P2 | runner 崩溃未回收、心跳丢失、任务长时间卡死 | `runner_heartbeat_gap_seconds > 30`；`zombie_runner_count > 0` | 1) supervisor 强制拉起或 kill；2) api 执行器侧回收并发令牌；3) session 收敛为 `completed+error`，防止悬挂 |
| R-06 | 密钥或敏感数据通过日志/异常泄漏 | P1 | 网关日志、trace、异常栈出现明文 key 或敏感载荷 | `secret_leak_detected_count > 0`（扫描器/规则） | 1) 立刻轮换受影响 key；2) 下线问题实例并清理日志副本；3) 开启严格脱敏开关后再恢复流量 |
| R-07 | 与现有 ai-manus 执行链兼容回归 | P2 | 改造后 plan/exec/tool/event 与原行为不一致 | 回归用例失败率 > 0；`session_event_schema_error_count > 0` | 1) 切回 `legacy` 开关；2) 暂停灰度并锁定变更；3) 按失败用例回放定位后再小流量重试 |

## 值班处置优先级
1. 先处理 `P1`（R-01/R-02/R-03/R-06）。
2. 再处理 `P2`（R-04/R-05/R-07）。
3. 所有应急动作完成后，24小时内补 RCA 与永久修复项。

## 发布门禁（与 E7/E8/E9 对齐）
- E7 未通过：禁止进入联调灰度。
- E8 未通过：禁止开启自动任务实时可见能力。
- E9 未通过：禁止生产发布。
