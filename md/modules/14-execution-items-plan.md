# 14 执行项落地计划（开发前）

## 目标
- 将 Go/No-Go 清单转为可执行任务，明确顺序、产出与通过标准。

## E1 迁移脚本演练
### 步骤
1. 准备演练库与备份。
2. 执行 `10-db-migration-backfill-plan.md` 的 Phase0~Phase4。
3. 执行回滚演练（开关回退 + 版本回退）。

### 产出物
- 迁移日志（含耗时、错误、回填条数）。
- 回滚日志（含恢复时间）。
- 索引生效与慢查询报告。

### 通过标准
- 演练全流程无阻断错误。
- 回填抽样通过率 100%。
- 回滚可在目标窗口内完成（建议 < 15 分钟）。

## E2 冒烟联调
### 步骤
1. 按 `12-integration-regression-matrix.md` 执行 A 类核心链路。
2. 至少覆盖 1 个自动会话 + 1 个手动会话 + 1 个介入恢复场景。
3. 验证前端：左侧分组、中间时间线、右侧 noVNC/回放。
4. 验证上下文：`planner/execution` 记忆装配、浏览器剪裁、压缩完整性校验。
5. 验证闭环：幂等防重、并发令牌、Reconciler 对账修复。
6. 验证部署角色：`api`（含执行器）与 `worker-beat` 启动后功能角色正确。
7. 验证模型配置中心：创建 `model_profile`、Agent 绑定 `model_profile_id`、运行成功。
8. 验证任务定义链路：`agent -> task_definition -> task_schedule` 创建与触发可用。
9. 验证多模型路由：按 `model_profile_id` 走 LangChain provider 路由并通过冒烟。
10. 验证双通道 SSE：无主动 chat 时，自动任务可通过全局摘要流实时可见。

### 产出物
- 冒烟测试记录（用例、结果、截图/录屏链接）。
- 缺陷清单（按 P1/P2/P3）。

### 通过标准
- A 类核心链路全部通过。
- P1/P2 缺陷为 0。
- 双服务角色启动稳定：`api` 正常执行，`worker-beat` 仅触发不执行步骤。
- 模型密钥安全通过：数据库仅有密文/mask/fingerprint，不出现明文 `api_key`。
- Provider 路由稳定：至少覆盖 `openai/deepseek/anthropic` 三类模型档案。
- 任务调度链路稳定：`task_definition + task_schedule` 可连续触发并正确落会话。
- 双通道 SSE 稳定：全局摘要流与会话详情流并行运行，无事件冲突。

## E3 观测与告警上线
### 步骤
1. 上线关键指标埋点（beat、celery 队列、run/step、sandbox、SSE）。
2. 配置 `P1/P2/P3` 告警规则。
3. 验证告警去重、恢复通知、链路追踪。

### 产出物
- 仪表盘链接（平台/租户/Agent）。
- 告警规则配置截图或导出。
- 告警演练报告（触发与恢复）。

### 通过标准
- 关键告警可触发、可恢复、可追踪。
- 指标标签包含 `tenant_id/group_id/agent_id`。

## E4 回滚演练
### 步骤
1. 按 `13-release-rollback-runbook.md` 执行一次灰度发布。
2. 人工触发回滚条件并执行回滚流程。
3. 回滚后验证会话可读、回放可用、调度恢复。

### 产出物
- 发布记录与回滚记录。
- 回滚后健康检查报告。

### 通过标准
- 回滚操作可一次成功。
- 回滚后关键链路（会话、回放、调度）正常。

## E5 开发启动 Gate
- 仅当 `E1~E4` 全部通过，进入功能开发迭代（M1/M2/M3...）。
- 未通过项必须补救并复测，不带病进入主开发。

## 建议执行顺序
1. E1 迁移脚本演练
2. E2 冒烟联调
3. E3 观测与告警上线
4. E4 回滚演练
5. E5 开发启动 Gate

## E6 运行时打包与部署基线校验
### 步骤
1. 产出统一后端镜像（供 `api/worker-beat` 复用）。
2. 编排文件定义两个独立服务：
   - `api`（REST/SSE/执行器）
   - `worker-beat`（调度）
3. 校验副本策略：
   - `api` 可横向扩容
   - `worker-beat` 保持单副本

### 产出物
- 镜像构建记录（tag、构建参数）。
- 部署编排片段（compose/k8s）。
- 角色分离验证记录（日志/指标截图）。

### 通过标准
- 单镜像可稳定承载两角色（api/worker-beat）。
- `api` 扩容后吞吐提升，`worker-beat` 不出现重复触发。

## E7 Gateway + Sandbox Runner 完整闭环（新增）
### 步骤
1. 新增 `gateway` 服务并接入内部鉴权中间件。
2. 打通 `token issue/revoke/verify` 与短时令牌校验链路。
3. 控制面创建 sandbox 时注入 `GATEWAY_BASE_URL/GATEWAY_TOKEN/GATEWAY_TOKEN_EXPIRE_AT`。
4. 验证 runner 推理仅走 gateway，不直连模型厂商。

### 产出物
- gateway 启动与健康检查记录。
- token 生命周期联调记录（签发、续期、吊销）。
- runner 推理链路抓包/日志（证明经 gateway 转发）。

### 通过标准
- sandbox 内无模型厂商明文 key。
- token 过期或吊销后推理请求被拒绝并返回可识别错误码。
- 手动会话与自动会话均可通过 gateway 正常完成一次推理。

## E8 实时链路与 noVNC 映射校验（新增）
### 步骤
1. 校验 `api_executor -> mongo(session_events) -> api -> SSE` 双通道可用。
2. 落地共享映射：`session_id -> sandbox_ws_target`（Mongo 真相源，Redis 缓存）。
3. 多 API 节点下验证前端重连与会话归属重绑。

### 产出物
- SSE 双通道联调记录（全局摘要流 + 会话详情流）。
- noVNC 路由验证记录（含 sandbox 重建场景）。
- 多副本 API 下的会话迁移测试记录。

### 通过标准
- 用户不主动发 chat 时，自动任务在左侧可实时可见。
- 任意 API 副本可基于共享映射转发到正确 sandbox。
- sandbox 重建后前端可继续查看实时画面（无需手工刷新链路配置）。

## E9 安全门禁与上线前检查（新增）
### 步骤
1. 校验进程级 egress：
- 浏览器进程允许访问外部业务站点。
- runner 进程仅允许访问内部 gateway。
2. 执行凭证泄漏扫描（日志、环境变量、数据库）。
3. 按 `13-release-rollback-runbook.md` 做一次灰度与回滚演练。

### 产出物
- 网络策略验证报告（含失败拦截图）。
- 凭证安全扫描报告。
- 灰度发布与回滚演练记录。

### 通过标准
- 不存在可绕过 gateway 的 runner 出网路径。
- 不存在明文 API Key 落盘或日志输出。
- 回滚在目标窗口内完成，回滚后会话/SSE/noVNC 关键链路可用。
