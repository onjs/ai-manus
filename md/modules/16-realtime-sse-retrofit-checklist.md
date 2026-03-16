# 16 实时双SSE改造清单（开发执行版）

## 目标
- 解决“定时调度任务非用户主动触发时，前端无法实时可见”的问题。
- 保持现有会话体系与前端交互不推翻，采用兼容增量改造。

## 范围
- 后端：事件发布链路、SSE 接口、Redis fanout、幂等与补偿。
- 前端：左侧全局摘要订阅、会话详情订阅、路由切换状态机。
- 观测：SSE 双通道指标、告警、联调与回归。

## 非范围（MVP）
- 不改 noVNC 协议。
- 不改会话主实体与事件持久化主结构。
- 不引入新消息中间件（继续 Redis）。

## 改造总原则
1. 兼容优先：保留旧 `POST /sessions` SSE 作为过渡。
2. 双通道分层：
- 全局摘要流：`GET /sessions/stream`（左侧常驻）
- 会话详情流：`GET /sessions/{session_id}/stream`（中间按需）
3. 自动/手动统一：不要求用户先发 chat，自动任务也必须实时可见。

## P0（必须完成）

### A. 契约冻结
- [ ] 冻结摘要流事件：`session_upsert/session_status_changed/session_unread_changed/session_remove`
- [ ] 冻结详情流事件：`message/tool/step/plan/wait/done/error/timeline`
- [ ] 冻结公共字段：`event_id,timestamp,tenant_id,session_id,source_type,agent_id,group_id`
- [ ] 冻结重连字段：`since/from_event_id`

验收：
- API 文档、样例、前端类型定义一致。

### B. 后端发布链路
- [ ] 调度创建 `auto session` 时发布 `session_upsert`（摘要流）
- [ ] worker 会话状态变化发布 `session_status_changed`
- [ ] 未读数变化发布 `session_unread_changed`
- [ ] 详情事件按 `session_id` 推送到会话详情流
- [ ] API 节点订阅 Redis 并 fanout 到在线 SSE 连接

验收：
- 用户在线且不发 chat，自动任务触发后左侧可实时出现。

### C. 前端订阅状态机
- [ ] 登录后建立 1 条全局摘要 SSE，页面生命周期内常驻
- [ ] 打开会话时建立 1 条详情 SSE，切换会话自动重绑
- [ ] 路由切换/登出时正确清理连接
- [ ] 按 `event_id` 去重，避免重复渲染
- [ ] 摘要流只更新左侧，不误触发中间详情渲染

验收：
- 全局摘要流 + 详情流并行运行无冲突、无串流。

### D. 兼容与回退
- [ ] 保留旧 `POST /sessions` SSE 路径（可开关）
- [ ] 新老路径并行期间可配置切换
- [ ] 失败回退到旧路径不影响核心聊天功能

验收：
- 开关切换后页面功能可用，无白屏与死连接。

### D.1 WebSocket Forward 与 Sandbox 映射（新增，必须）
- [ ] `worker` 创建/销毁/重建 sandbox 时，实时更新共享映射（Mongo 为真相源，Redis 可缓存）：
  - `sessions.sandbox_id`
  - `sessions.sandbox_status`
  - `sessions.sandbox_ws_target`（或等价连接目标）
  - `sessions.updated_at`
- [ ] `api` websocket forward 仅按 `session_id` 查询共享映射，不依赖本地进程内存。
- [ ] sandbox 重建后发布 `sandbox_recreated`，并原子更新会话映射。
- [ ] `api` 未查到可用映射时返回可识别错误（如 `SANDBOX_NOT_READY`），前端可重试。

验收：
- `api+worker` 分离部署下，任意 api 副本都能定位并转发到正确 sandbox。
- worker 重启后，已有会话 noVNC 仍可通过共享映射恢复访问。

## P1（稳定性增强）

### E. 重连与补偿
- [ ] SSE 断线重连支持 `since/from_event_id`
- [ ] 重连后先快照再增量（防丢失）
- [ ] 事件缓冲窗口与过期策略（Redis + Mongo 补拉）

验收：
- 人为断网 30s 后恢复，左侧与详情状态最终一致。

### F. 观测与告警
- [ ] 指标拆分：`sse_global_*`、`sse_session_*`
- [ ] 增加 `sse_fanout_queue_lag_ms`
- [ ] 告警阈值落地（emit error、fanout lag）
- [ ] trace_id 贯通到 SSE 推送日志

验收：
- 可定位“任务执行正常但前端不可见”的根因层级。

### G. 压测与容量
- [ ] 压测在线用户 + 多 agent 并发调度场景
- [ ] 验证 API 副本横向扩容后的 fanout 一致性
- [ ] 验证 Redis pub/sub 峰值下延迟与丢包风险

验收：
- 达到目标阈值（由压测报告给出）且无事件大面积丢失。

## 开发顺序（建议）
1. A 契约冻结
2. B 后端发布链路
3. C 前端订阅状态机
4. D 兼容与回退
5. E/F 稳定性与观测
6. G 压测与上线门禁

## 联调用例（最小集）
1. 用户在线不发 chat，定时任务触发后左侧 3s 内可见。
2. 点击自动会话后，详情流实时展示 step/tool 事件。
3. 同时打开页面 + 多 agent 并发触发，左侧分组更新正确。
4. 断网重连后，摘要与详情状态一致。
5. 切旧路径开关后，手动聊天与自动任务都可用。

## 上线门禁
- [ ] 双通道 SSE 联调通过
- [ ] 观测告警上线
- [ ] 压测通过
- [ ] 回滚脚本演练通过

## 回滚策略
1. 关闭新 SSE 双通道开关，回退旧 `POST /sessions` SSE。
2. 保留新事件写入，不做数据回删。
3. 观察 30 分钟核心指标后再决定是否重新灰度。
