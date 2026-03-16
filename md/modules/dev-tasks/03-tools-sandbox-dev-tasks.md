# 03 工具与Sandbox模块 开发任务清单

## P0 必做
1. per-run sandbox 模式开关（shared/per_run）
2. 运行结束自动销毁（会话 `status=completed`；失败/取消/超时由事件区分）
3. get/health 失败自动重建 + 事件落库
4. 用户介入恢复：同 session_id 自动重建继续
5. 回放链路只依赖 Mongo + GridFS

## P1 增强
1. noVNC 断线重连
2. 孤儿 sandbox 回收守护
3. 租户级 sandbox 容量保护

## 测试
1. 随机杀 sandbox 后可恢复
2. 销毁后历史回放完整
3. 取消/超时销毁行为一致
