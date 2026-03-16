# 06 平台管理模块 API Schema 设计稿

## 统一响应
- `APIResponse{code,msg,data}`。

## 接口
1. `GET/POST/PATCH /platform/tenants`
2. `GET/POST/PATCH /platform/users`
3. `GET/POST/DELETE /platform/agent-permissions`
4. `GET/POST/PATCH /platform/model-profiles`
5. `POST /platform/model-profiles/{profile_id}/rotate-key`
6. `GET/PATCH /platform/tenants/{tenant_id}/quota`
7. `GET /platform/audit-logs`

## 关键请求模型
- `CreateTenantRequest`: `code,name,plan,quota`
- `CreateUserRequest`: `email,name,platform_role,tenant_id`
- `GrantAgentPermissionRequest`: `agent_id,user_id,grant_type`
- `CreateModelProfileRequest`: `name,provider,model,api_base,params,api_key`
- `PatchModelProfileRequest`: `name?,model?,api_base?,params?,status?`
- `RotateModelProfileKeyRequest`: `api_key`

## 关键响应模型
- `ModelProfile`:
  - `profile_id,name,provider,model,api_base,params,status`
  - `secret_masked,secret_fingerprint`
  - 说明：不返回 `api_key` 明文与密文字段。

## 鉴权
- `platform_admin` 全局
- `tenant_admin` 本租户
- `tenant_user` 被授权范围
