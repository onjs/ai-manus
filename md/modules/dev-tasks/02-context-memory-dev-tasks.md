# 02 上下文与记忆模块 开发任务清单

## M1 双层记忆装配
1. 复用 `AgentDocument.memories` 并拆分读取 `planner/execution` 两层。
2. 实现锚点区重组（`goal_anchor/step_ledger/critical_refs`）。
3. 实现预算计算与 utilization 评估。
4. 装配时改为覆盖重组，禁止历史全文逐轮追加。

## M2 浏览器上下文剪裁
1. 新增 `BrowserClipper` 组件（playwright/browser_use 统一出口）。
2. 实现 DOM/markdown 结构化剪裁与 token 限额。
3. 超限内容转 `artifact_ref`，仅保留摘要文本入上下文。
4. 保留截图用于回放，不进入 LLM 主上下文。

## M3 分级压缩
1. Stage1~Stage5 动作实现（在现有 `compact_memory` 基础上增强）。
2. 大输出统一 `artifact_ref` 化。
3. checkpoint 生成与恢复。

## M4 完整性保护
1. `goal_hash / step_ledger / critical_refs` 校验。
2. 校验失败自动回滚到最近 checkpoint。
3. 记录 `compression_warning` 与降级策略事件。

## M5 存储与恢复
1. Redis 热态键管理（token/stage/recent refs）。
2. Mongo checkpoints/events 联合恢复。
3. 恢复时合并 `planner/execution` 记忆并继续原 `session_id`。

## M6 测试
1. 长会话压缩不漂移。
2. 压缩后恢复一致性。
3. 浏览器上下文剪裁有效（不灌入整页 DOM/截图）。
4. sandbox 销毁后回放可用。
