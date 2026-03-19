# 模块交付物覆盖检查表

检查维度：
- 主模块设计文档
- API Schema 设计稿（单独文件）
- 开发任务清单（单独文件）

## 覆盖结果
1. `01 Agent管理`
- 设计文档：有
- API Schema：有
- 开发任务：有

2. `02 上下文与记忆`
- 设计文档：有
- API Schema：有（内部契约 + 可选调试接口）
- 开发任务：有

3. `03 工具与Sandbox`
- 设计文档：有
- API Schema：有
- 开发任务：有

4. `04 调度与队列`
- 设计文档：有
- API Schema：有
- 开发任务：有

5. `05 观测与告警`
- 设计文档：有
- API Schema：有（Prom/Otel 为主，REST 可选）
- 开发任务：有

6. `06 平台管理`
- 设计文档：有
- API Schema：有
- 开发任务：有

7. `07 配置发布与回滚`
- 设计文档：有
- API Schema：有
- 开发任务：有

8. `08 Skills与工具执行策略`
- 设计文档：有
- API Schema：有
- 开发任务：有

9. `15 部署拓扑与部署文档`
- 设计文档：有
- API Schema：不适用（部署模块）
- 开发任务：可选（按运维脚本拆解）

10. `16 实时双SSE改造清单`
- 设计文档：有（执行清单）
- API Schema：已合并到 01/04 模块
- 开发任务：已合并到 01/04/05 模块

11. `18 Gateway 与 Sandbox 集成`
- 设计文档：有
- API Schema：有
- 开发任务：有

12. `19 Gateway/Sandbox/Agent 代码改造图`
- 设计文档：有（代码级改造路径）
- API Schema：不适用（实现映射文档）
- 开发任务：引用 14/18 模块

13. `20 风险台账 + Ops 告警规则草案`
- 设计文档：有（风险台账）
- API Schema：不适用
- 开发任务：有（05 模块 M5）

## 索引入口
- API Schema 总目录：[/Users/zuos/code/github/ai-manus/md/modules/api-schema/README.md](/Users/zuos/code/github/ai-manus/md/modules/api-schema/README.md)
- 开发任务总目录：[/Users/zuos/code/github/ai-manus/md/modules/dev-tasks/README.md](/Users/zuos/code/github/ai-manus/md/modules/dev-tasks/README.md)
