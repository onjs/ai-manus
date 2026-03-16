# 17 BrowserEngine 开发任务清单

## M1 领域模型与存储层
1. 新增集合与索引：
- `browser_tasks`
- `browser_steps`
- `browser_snapshots`
- `browser_routes`
- `browser_recovery_records`
2. 建立 Repository 层接口与实现（Mongo）。
3. 建立 Redis 运行态键规范：
- `be:lock:session:{session_id}`
- `be:token:tenant:{tenant_id}`
- `be:ctx:{task_id}`
- `be:idem:{task_id}:{step_seq}`
4. 建立 Artifact 引用策略（截图/HTML/A11y/日志走 ref，不内联大文本）。

## M2 BrowserEngine 核心运行时
1. 新建 `BrowserEngineFacade`。
2. 实现 `PerceptionPipeline`：
- `DOM/A11y/Screenshot/URL/Console/Network` 采集。
3. 实现 `DecisionPlanner`：
- `replay-first` 与 `agentic` 两种模式。
4. 实现 `ActionExecutor`：
- `navigate/click/hover/input/select/wait/switch_tab/switch_frame/upload/download`。
5. 实现 `Verifier`：
- postcondition 断言执行与证据输出。
6. 实现 `RecoveryManager`：
- 统一恢复链（重定位、hover、滚动、换定位、局部重规划、人工接管）。

## M3 动态页面与复杂表单能力
1. 动态菜单策略落地：
- `hover(trigger) -> verify(expanded) -> click(item) -> verify(postcondition)`。
2. `PageGraph` 支持：
- 多 tab 管理
- frame 上下文管理
- 激活页切换。
3. `FormOrchestrator` 落地：
- 字段发现
- 字段映射
- 分阶段填写
- 校验扫描
- 提交后验证
- 失败字段回填。
4. 复杂输入脱敏策略：
- 运行日志写 masked 值。

## M4 与现有 ai-manus 集成
1. 扩展 `Browser` 协议高阶入口：
- `execute_goal`
- `execute_plan`
- `replay_route`
2. `BrowserToolkit` 接入 BrowserEngine，不允许 Agent 直接拼长链原子动作。
3. `ExecutionAgent` 浏览器步骤改造：
- 输出业务目标
- 调用 BrowserEngine
- 回写结构化结果。
4. `AgentTaskRunner` 扩展事件映射：
- `browser_task_upsert`
- `browser_step_upsert`
- `browser_verify_result`
- `browser_recovery_attempt`
- `browser_waiting_user`
- `browser_task_done`

## M5 API 与 SSE
1. 实现 `POST/GET /browser-engine/tasks*` 系列接口。
2. 实现 routes 管理与 replay 接口。
3. 扩展 `GET /sessions`、`GET /sessions/{id}` 的浏览器任务摘要字段。
4. SSE 兼容扩展：
- 旧客户端忽略新字段不报错。
- 新客户端可完整展示 phase/verify/recovery。

## M6 路线沉淀与复放
1. RouteRegistry：
- 成功路径入库
- 版本化管理
- 失效率统计。
2. Replay 策略：
- 首次失败自动降级 agentic。
- 成功后更新路线版本与成功率。
3. 路线治理：
- `active/deprecated/invalid` 状态切换。

## M7 风控与治理
1. 域名白名单与风险动作护栏。
2. 高风险提交动作审计（删除、审批、支付等）。
3. `WAITING_USER` 接管流程：
- 进入等待事件
- 用户恢复执行
- 全链路审计。

## M8 观测与压测
1. 指标：
- 步骤成功率
- 恢复成功率
- 恢复平均次数
- 表单提交成功率
- Route replay 命中率与成功率
- 人工接管率。
2. 告警：
- 长时间卡在同一 phase
- 恢复链耗尽
- 沙箱连接异常率超阈值。
3. 压测：
- 单租户高并发任务
- 多租户并发
- 长链路跨页流程。

## M9 测试矩阵
1. 动态菜单用例（hover 展开、延迟渲染、遮挡）。
2. 复杂表单用例（依赖字段、必填缺失、错误回填）。
3. 多页面/多 tab/frame 用例。
4. 人工接管恢复用例（登录/captcha/2fa）。
5. replay-first 回退 agentic 用例。
6. SSE 兼容用例（旧前端与新前端）。
7. 租户隔离与授权用例。

## 交付标准（DoD）
1. 连续多步骤流程在动态页面可稳定完成，不出现“动作成功但业务失败未感知”。
2. 复杂表单可完成字段依赖处理、提交校验、错误回填。
3. 失败可恢复或进入明确人工接管，不出现长期无状态卡死。
4. 历史回放可按步骤查看快照、验证结果、恢复轨迹。
5. 回放数据不依赖 sandbox 存活。

## 风险与依赖
1. 目标站点频繁改版可能导致 route 失效，需要治理策略持续运行。
2. 复杂站点 anti-bot 机制会影响自动化稳定性，需要策略白名单与人工兜底。
3. BrowserEngine 运行时增加后，需关注 Mongo 写放大与存储成本。
