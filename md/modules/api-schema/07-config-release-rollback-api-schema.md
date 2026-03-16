# 07 配置发布与回滚模块 API Schema 设计稿

## 统一响应
- `APIResponse{code,msg,data}`。

## 接口
1. `POST /agents/{agent_id}/config-versions`
2. `PATCH /agents/{agent_id}/config-versions/{version_id}`
3. `POST /agents/{agent_id}/config-versions/{version_id}/validate`
4. `POST /agents/{agent_id}/config-versions/{version_id}/publish`
5. `POST /agents/{agent_id}/config-versions/{version_id}/rollback`
6. `GET /agents/{agent_id}/config-versions`
7. `GET /agents/{agent_id}/config-versions/{version_id}/diff?base=...`

## 关键模型
- `ConfigVersion`: `version_id,version_no,status,content,content_hash,validation_report`
  - `content.model_binding`: `model_profile_id,override_params(optional)`
  - 约束：不允许出现明文 `api_key`
- `PublishResult`: `published_version,effective_scope(new_sessions_only)`
