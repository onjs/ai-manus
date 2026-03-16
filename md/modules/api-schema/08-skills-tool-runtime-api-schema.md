# 08 Skills与工具执行策略模块 API Schema 设计稿

## 统一响应
- `APIResponse{code,msg,data}`。

## 接口
1. `GET /agents/{id}/skills`
2. `PUT /agents/{id}/skills`
3. `POST /agents/{id}/skills/publish`
4. `POST /agents/{id}/skills/install`
5. `GET /agents/{id}/tools-policy`
6. `PUT /agents/{id}/tools-policy`
7. `POST /agents/{id}/tools-policy/validate`

## 关键模型
- `SkillsConfig`: `enabled,filter,sources,entries,prompt_limits,version`
- `SkillsSnapshot`: `version,hash,prompt,skill_names`
- `ToolsPolicy`: `allow,deny,sandbox_tools,loop_detection,security`
