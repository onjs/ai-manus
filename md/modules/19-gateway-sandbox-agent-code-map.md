# 19 Gateway + Sandbox + Agent 改造代码清单（执行图）

## 目标
- 仅推进当前范围：`gateway + sandbox + agent 执行链路`。
- 不改业务产品逻辑，不改前端交互形态，只补执行面与安全闭环。

## 阶段拆解（按落地顺序）

## S1 配置与部署基线
1. 后端配置
- `/Users/zuos/code/github/ai-manus/backend/app/core/config.py`
- `/Users/zuos/code/github/ai-manus/backend/.env.example`（需新增）
2. 沙箱配置
- `/Users/zuos/code/github/ai-manus/sandbox/app/core/config.py`
- `/Users/zuos/code/github/ai-manus/sandbox/.env.example`（需新增）
3. 编排
- `/Users/zuos/code/github/ai-manus/scripts/docker-compose-development.yml`
- 新增 `gateway` 服务、健康检查、内网访问配置。

完成标准：
- 本地一键启动包含 `web/api/worker-beat/gateway/sandbox/redis/mongo`。

## S2 Gateway 服务骨架
1. 新建服务目录（建议）
- `/Users/zuos/code/github/ai-manus/gateway/`
- `app/main.py`
- `app/interfaces/api/internal_routes.py`
- `app/application/services/token_service.py`
- `app/application/services/llm_proxy_service.py`
2. 完整接口（首批落地）
- `POST /internal/v1/token/issue`
- `POST /internal/v1/token/revoke`
- `POST /internal/v1/token/introspect`
- `POST /internal/v1/llm/ask`
- `POST /internal/v1/llm/stream`
- `POST /internal/v1/llm/batch`
- `POST /internal/v1/llm/embeddings`
- `GET /internal/v1/gateway/health`
- `GET /internal/v1/gateway/ready`
- `GET /internal/v1/gateway/config/hash`

完成标准：
- token 生命周期与 ask/stream/batch/embeddings 链路均可在本地联通。

## S3 控制面接入 Provider + Gateway 注入
1. 控制面入口
- `/Users/zuos/code/github/ai-manus/backend/app/application/services/agent_service.py`
- `/Users/zuos/code/github/ai-manus/backend/app/domain/services/flows/plan_act.py`
- `/Users/zuos/code/github/ai-manus/backend/app/interfaces/dependencies.py`
2. sandbox 注入点
- `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/external/sandbox/docker_sandbox.py`
3. 目标能力
- 创建 sandbox 时注入：`GATEWAY_BASE_URL/GATEWAY_TOKEN/GATEWAY_TOKEN_EXPIRE_AT`
- runner 与工具执行路径统一走 gateway 推理。

完成标准：
- 同一 session 可完成 `create_env -> start_run -> events -> end` 闭环，且无直连模型厂商。

## S4 沙箱内 Runner 与心跳
1. 沙箱 API/服务扩展
- `/Users/zuos/code/github/ai-manus/sandbox/app/main.py`
- `/Users/zuos/code/github/ai-manus/sandbox/app/api/router.py`
- `/Users/zuos/code/github/ai-manus/sandbox/app/services/`（新增 runner service）
2. 进程管理
- `/Users/zuos/code/github/ai-manus/sandbox/supervisord.conf`
- 新增 runner 进程及健康探针。

完成标准：
- runner 心跳可观测，异常退出可被控制面识别并收敛。

## S5 实时链路与 noVNC 映射
1. SSE/WS 路由
- `/Users/zuos/code/github/ai-manus/backend/app/interfaces/api/session_routes.py`
- `/Users/zuos/code/github/ai-manus/backend/app/interfaces/schemas/event.py`
2. 映射存储
- `/Users/zuos/code/github/ai-manus/backend/app/infrastructure/models/documents.py`
- 对齐 `session_id -> sandbox_ws_target` 共享映射读写。

完成标准：
- 多 API 副本场景下，SSE 与 noVNC 都能按 `session_id` 找到正确 sandbox。

## S6 安全与审计门禁
1. 审计与日志
- `backend` 侧审计日志 service/repository
- `gateway` 侧请求审计集合 `llm_gateway_requests`
2. 安全校验
- runner 不可直连模型厂商
- token 吊销后不可继续推理
- 日志中无明文 `api_key`

完成标准：
- 通过 `E9` 门禁后才允许进入下一阶段业务开发。

## 交付清单（本阶段）
1. 设计冻结：`18-gateway-llm-proxy.md`
2. API 冻结：`api-schema/18-gateway-api-schema.md`
3. 任务清单：`dev-tasks/18-gateway-dev-tasks.md`
4. 执行项：`14-execution-items-plan.md`（E7/E8/E9）
5. 改造代码图：本文档
