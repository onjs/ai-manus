# 23 Sandbox 单服务 + 内存队列开发任务清单

## T1 凭证存储替换（sqlite -> 临时文件）
- [x] 新增 gateway credential 文件存储服务。
- [x] `runtime.py` 改为读取/写入临时文件。
- [x] 删除 `runtime_store` 在 runtime 凭证路径的依赖。

## T2 运行态注册表实现
- [x] 新增 `runtime_run_registry.py`（RunState + Registry）。
- [x] 支持 append_event / read_events / status update / heartbeat。
- [x] 支持 seq 递增和 timestamp 写入。

## T3 runner 服务内聚
- [x] `runtime_runner.py` 改为直接起 asyncio task。
- [x] 去掉 commands 轮询逻辑。
- [x] `cancel/clear` 改为 task 级控制。

## T4 SSE 流重写
- [x] `stream_events` 改为 condition 等待模型。
- [x] 保留 heartbeat 行为。
- [x] 保持 from_seq/limit 参数契约。

## T5 删除 sqlite 链路
- [x] 删除/停用 `runtime_store.py` 运行链路引用。
- [x] 删除 runner daemon 调度依赖。
- [x] 清理 imports 与未使用文件。

## T6 部署启动配置收口
- [x] `supervisord.conf` 去掉 runner program。
- [x] 确认 sandbox 仅保留 app 提供 runtime API + agent 执行。

## T7 测试
- [x] sandbox runtime runner API 测试通过（start/cancel/clear/stream）。
- [x] backend 端到端 smoke：chat -> done/error/wait。
- [x] 手工验证前端实时链路可用（基于真实服务链路：chat SSE + shell/file 回放接口）。
