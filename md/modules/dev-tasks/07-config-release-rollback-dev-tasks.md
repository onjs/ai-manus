# 07 配置发布与回滚模块 开发任务清单

## M1 版本化
1. `agent_config_versions` 集合与索引
2. `agents.published_version` 指针

## M2 校验与发布
1. Schema 校验
2. 引用校验（skills/tools）
3. dry-run 预检
4. publish 指针切换

## M3 回滚
1. 手动回滚接口
2. 新版本号回滚策略
3. 运行中会话不受影响

## M4 审计与diff
1. 字段级 diff
2. before/after hash
3. publish/rollback 审计链
