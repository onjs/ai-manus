# 开发前准备清单（Go/No-Go）

## 一、设计与边界
- [x] 01-08 模块设计文档冻结
- [x] 18 gateway+sandbox+runner 集成文档冻结
- [x] 19 gateway+sandbox+agent 代码改造图已产出
- [x] 20 sandbox+agent+gateway 风险台账已产出
- [x] 关键时序锁定：`task_schedule -> trigger -> session -> api_executor -> sandbox`
- [x] 取消与超时销毁规则冻结
- [x] 上下文策略锁定：`planner/execution 双层记忆 + 浏览器剪裁 + 分级压缩`
- [x] 调度闭环锁定：`Reconciler 对账恢复 + 幂等键 + 并发令牌补偿释放`
- [x] 部署拓扑锁定（当前）：`web/api/worker-beat/gateway/sandbox/redis/mongo`（MVP 不含 ssrf）
- [x] 实时通道锁定：`全局摘要SSE + 会话详情SSE` 双通道
- [x] 实时改造执行清单：`16-realtime-sse-retrofit-checklist.md`

## 二、API 与任务拆解
- [x] 核心模块独立 API Schema（01-08）
- [x] 核心模块独立开发任务清单（01-08）
- [x] 契约样例文档
- [x] gateway API Schema（18）与开发任务清单（18）已补齐
- [x] gateway 错误码与错误响应样例已补齐

## 三、工程治理
- [x] 全局错误码字典
- [x] DB 迁移与回填方案
- [x] 联调与回归测试矩阵
- [x] 发布与回滚 Runbook

## 四、上线门禁（执行时）
- [ ] 迁移脚本演练通过
- [ ] 冒烟联调通过
- [ ] 观测与告警上线
- [ ] 回滚演练通过
- [ ] `backend/.env.example`、`sandbox/.env.example`、`scripts/docker-compose-development.yml` 已补齐 gateway 配置
- [ ] E7（Gateway+Runner 完整闭环）验收通过
- [ ] E8（SSE + noVNC 映射）验收通过
- [ ] E9（安全门禁）验收通过

## 结论
- 文档侧已满足进入开发条件。
- 建议先执行“迁移演练 + 冒烟联调”后正式进入功能开发分支。

## 执行项详情
- 见 [14-execution-items-plan.md](/Users/zuos/code/github/ai-manus/md/modules/14-execution-items-plan.md)（E1~E9）。
