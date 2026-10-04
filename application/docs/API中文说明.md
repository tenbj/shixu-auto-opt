# 拾序 API 中文说明

版本 3.1.0 · 基地址 http://127.0.0.1:8765 · UTF-8 JSON。在线交互文档 `/docs`，机器Schema `/openapi.json`。

## 账号认证

登录注册和OAuth协议见账号与远程接入.md。网页用HttpOnly会话Cookie，写入附X-CSRF-Token；程序用Authorization: Bearer账号令牌。401表示需要登录，403表示CSRF或权限不足，跨账号资源返回404。owner不能由调用方指定。账号管理端点不使用业务revision/request_id；OAuth token使用表单格式。

## 并发、幂等与错误

所有业务写入携带 `request_id`（8–120字符，推荐UUID）、`expected_version`（当前账号revision）与可选 `actor`（审计标签，默认未指定）。请求体不接受未声明字段。每个写入是一个MySQL InnoDB事务；返回 `revision`、`resource` 和事务提交时的 `data`。失败不改变数据、审计或版本。

同一request_id及完全相同内容重放返回原始成功响应；request_id相同但内容不同返回409。网络超时保持请求内容和编号重试。账号内版本是工作台版本，不是单个对象版本；任何对象写入都会递增。

| HTTP | 含义 | 处理 |
|---|---|---|
| 200 | 成功或幂等重放 | 读取返回版本 |
| 403 | 跨站写入被拒绝 | 从同源页面或本机程序调用 |
| 404 | 对象不存在 | 重新列表定位 |
| 409 | 版本/状态/request_id冲突 | 重读，再决定新操作 |
| 422 | 参数、依赖、证据或业务条件错误 | 修正后用新编号提交 |
| 503 | 数据库不可用 | 不确认成功，恢复后同号重试 |

列表返回 `{revision,items}`；详情返回 `{revision,item}`，问题详情另含关联tasks；完整工作台与导出返回 `{revision,data}`；审计返回 `{items}`。响应均不缓存。

## 业务流转约束

新问题只需标题，默认待梳理。triage填写nextStep和successCriteria进入待处理；start进入处理中；verify必须填写successCriteria、treatment、verificationMethod且必要行动均完成/取消；resolve只能从待验证进入，必须填resolution依据。零关联行动问题可直接提交观察验证。

pause要求reason和不早于Asia/Shanghai今天的reviewDate；resume恢复原阶段。close-issue要求closeType/reason，有未完成行动时必须传taskPolicy；重复问题要求duplicateOf。reopen/reject/retriage要求reason。取消行动必须填写reason；依赖仅限同组且不能循环，取消前置行动不视为完成。

行动编号由服务端分配，排序不改变编号或依赖；改变关联会在新组分配新编号，不复用旧号。新增/重开必要行动可使待验证或已解决问题回到处理中。

## 接口目录

### POST /api/auth/login

账号登录。MCP：`账号或公开引导，不暴露为MCP工具`。

请求体：`Credentials`；必填：username, password。

| 字段 | 约束/默认 |
|---|---|
| `username` | {"type": "string", "maxLength": 40, "minLength": 2} |
| `password` | {"type": "string", "maxLength": 128, "minLength": 1} |
| `displayName` | {"type": "string", "maxLength": 60, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/auth/register

注册独立空工作台。MCP：`账号或公开引导，不暴露为MCP工具`。

请求体：`Credentials`；必填：username, password。

| 字段 | 约束/默认 |
|---|---|
| `username` | {"type": "string", "maxLength": 40, "minLength": 2} |
| `password` | {"type": "string", "maxLength": 128, "minLength": 1} |
| `displayName` | {"type": "string", "maxLength": 60, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/auth/me

当前登录账号。MCP：`账号或公开引导，不暴露为MCP工具`。

### POST /api/auth/logout

退出并撤销当前会话。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`X-CSRF-Token`（header）。

### PATCH /api/account

修改账号显示名称。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`X-CSRF-Token`（header）。

请求体：`Profile`；必填：displayName。

| 字段 | 约束/默认 |
|---|---|
| `displayName` | {"type": "string", "maxLength": 60, "minLength": 1} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/account/password

修改密码并撤销全部网页登录会话。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`X-CSRF-Token`（header）。

请求体：`Password`；必填：oldPassword, newPassword。

| 字段 | 约束/默认 |
|---|---|
| `oldPassword` | {"type": "string", "maxLength": 128} |
| `newPassword` | {"type": "string", "maxLength": 128, "minLength": 8} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/account/mcp-access

当前账号的MCP接入列表。MCP：`账号或公开引导，不暴露为MCP工具`。

### POST /api/account/mcp-access

发放独立访问令牌（仅本次返回明文）。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`X-CSRF-Token`（header）。

请求体：`Access`；必填：name。

| 字段 | 约束/默认 |
|---|---|
| `name` | {"type": "string", "maxLength": 60, "minLength": 1} |
| `scope` | {"type": "string", "default": "write"} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/account/mcp-access/{access_id}/revoke

撤销当前账号的接入。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`access_id`（path）；`X-CSRF-Token`（header）。

### PATCH /api/account/mcp-access/{access_id}

重命名当前账号的接入设备。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`access_id`（path）；`X-CSRF-Token`（header）。

请求体：`Profile`；必填：displayName。

| 字段 | 约束/默认 |
|---|---|
| `displayName` | {"type": "string", "maxLength": 60, "minLength": 1} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /.well-known/oauth-protected-resource/mcp

MCP资源元数据。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /.well-known/oauth-protected-resource

受保护资源元数据。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /.well-known/oauth-authorization-server

授权服务器元数据。MCP：`账号或公开引导，不暴露为MCP工具`。

### POST /oauth/register

注册公共OAuth客户端。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /oauth/authorize

开始客户端授权。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`client_id`（query）；`redirect_uri`（query）；`code_challenge`（query）；`resource`（query）；`response_type`（query）；`code_challenge_method`（query）；`scope`（query）；`state`（query）。

### GET /api/oauth/requests/{key}

读取待确认授权。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`key`（path）。

### POST /api/oauth/requests/{key}

允许或拒绝客户端授权。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`key`（path）；`X-CSRF-Token`（header）。

### POST /oauth/token

交换授权码或轮换刷新令牌。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /connect/manifest.json

公开AI接入版本清单。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /connect.md

公开AI接入指南。MCP：`账号或公开引导，不暴露为MCP工具`。

### GET /connect/runtimes/{name}.md

运行环境适配说明。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`name`（path）。

### GET /downloads/{filename}

下载固定版本的拾序Skill包。MCP：`账号或公开引导，不暴露为MCP工具`。

参数：`filename`（path）。

### GET /api/connection-context

读取认证账号、权限和MCP连接证据。MCP：`get_connection_context`。

参数：`runtime_name`（query）；`runtime_version`（query）；`skill_version`（query）。

### GET /api/health

检查服务与数据库状态。MCP：`get_system_status`。

### GET /api/workspace

读取完整工作台与并发版本。MCP：`get_workspace`。

### GET /api/identities

查询通用人类与AI记录身份。MCP：`list_identities`。

### POST /api/identities

创建记录身份与默认工具模型。MCP：`create_identity`。

参数：`X-CSRF-Token`（header）。

请求体：`IdentityCreate`；必填：request_id, expected_version, name, kind。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `name` | {"type": "string", "maxLength": 60, "minLength": 1} |
| `kind` | {"type": "string", "enum": ["person", "agent"]} |
| `via` | {"type": "string", "enum": ["manual", "claude_code", "workbuddy", "codex", "deepseek_harness"], "default": "manual"} |
| `modelName` | {"type": "string", "maxLength": 160, "default": ""} |
| `modelProvider` | {"type": "string", "maxLength": 80, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### PATCH /api/identities/{identity_id}

修改身份名称与新建默认值，保留历史快照。MCP：`update_identity`。

参数：`identity_id`（path）；`X-CSRF-Token`（header）。

请求体：`IdentityUpdate`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `name` | {"anyOf": [{"type": "string", "maxLength": 60, "minLength": 1}, {"type": "null"}]} |
| `via` | {"anyOf": [{"type": "string", "enum": ["manual", "claude_code", "workbuddy", "codex", "deepseek_harness"]}, {"type": "null"}]} |
| `modelName` | {"anyOf": [{"type": "string", "maxLength": 160}, {"type": "null"}]} |
| `modelProvider` | {"anyOf": [{"type": "string", "maxLength": 80}, {"type": "null"}]} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/issues

查询问题列表。MCP：`list_issues`。

参数：`q`（query）；`status`（query）；`priority`（query）；`tag`（query）；`creator`（query）；`created_via`（query）；`model`（query）。

### GET /api/issues/{issue_id}

读取问题详情及关联行动。MCP：`get_issue`。

参数：`issue_id`（path）。

### POST /api/issues

创建待梳理问题。MCP：`create_issue`。

参数：`X-CSRF-Token`（header）。

请求体：`IssueCreate`；必填：request_id, expected_version, title。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `creation` | {"anyOf": [{"$ref": "#/components/schemas/CreationInput"}, {"type": "null"}]} |
| `title` | {"type": "string", "maxLength": 160, "minLength": 1} |
| `description` | {"type": "string", "maxLength": 5000, "default": ""} |
| `priority` | {"type": "string", "enum": ["高", "中", "低"], "default": "中"} |
| `tag` | {"type": "string", "maxLength": 40, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### PATCH /api/issues/{issue_id}

编辑问题内容与属性。MCP：`update_issue`。

参数：`issue_id`（path）；`X-CSRF-Token`（header）。

请求体：`IssueUpdate`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `title` | {"anyOf": [{"type": "string", "maxLength": 160, "minLength": 1}, {"type": "null"}]} |
| `description` | {"anyOf": [{"type": "string", "maxLength": 5000}, {"type": "null"}]} |
| `priority` | {"anyOf": [{"type": "string", "enum": ["高", "中", "低"]}, {"type": "null"}]} |
| `tag` | {"anyOf": [{"type": "string", "maxLength": 40}, {"type": "null"}]} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/issues/{issue_id}/transitions

按七状态规则流转问题。MCP：`transition_issue`。

参数：`issue_id`（path）；`X-CSRF-Token`（header）。

请求体：`IssueTransition`；必填：request_id, expected_version, action。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `action` | {"type": "string", "enum": ["triage", "start", "verify", "resolve", "reject", "pause", "resume", "close-issue", "reopen", "retriage"]} |
| `reason` | {"type": "string", "maxLength": 5000, "default": ""} |
| `nextStep` | {"type": "string", "maxLength": 5000, "default": ""} |
| `successCriteria` | {"type": "string", "maxLength": 5000, "default": ""} |
| `treatment` | {"type": "string", "maxLength": 5000, "default": ""} |
| `verificationMethod` | {"type": "string", "maxLength": 5000, "default": ""} |
| `resolution` | {"type": "string", "maxLength": 5000, "default": ""} |
| `reviewDate` | {"type": "string", "maxLength": 10, "default": ""} |
| `closeType` | {"type": "string", "maxLength": 40, "default": ""} |
| `duplicateOf` | {"type": "string", "maxLength": 120, "default": ""} |
| `taskPolicy` | {"type": "string", "enum": ["", "detach", "cancel"], "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/issues/{issue_id}/followups

追加问题跟进记录。MCP：`add_followup`。

参数：`issue_id`（path）；`X-CSRF-Token`（header）。

请求体：`Followup`；必填：request_id, expected_version, content。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `content` | {"type": "string", "maxLength": 5000, "minLength": 1} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/tasks

查询行动列表。MCP：`list_tasks`。

参数：`issue_id`（query）；`status`（query）；`creator`（query）；`created_via`（query）；`model`（query）。

### GET /api/tasks/{task_id}

读取行动详情。MCP：`get_task`。

参数：`task_id`（path）。

### POST /api/tasks

创建关联或独立行动。MCP：`create_task`。

参数：`X-CSRF-Token`（header）。

请求体：`TaskCreate`；必填：request_id, expected_version, title。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `creation` | {"anyOf": [{"$ref": "#/components/schemas/CreationInput"}, {"type": "null"}]} |
| `title` | {"type": "string", "maxLength": 160, "minLength": 1} |
| `issueId` | {"anyOf": [{"type": "string", "maxLength": 120}, {"type": "null"}]} |
| `due` | {"type": "string", "maxLength": 10, "default": ""} |
| `required` | {"type": "boolean", "default": true} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### PATCH /api/tasks/{task_id}

编辑行动内容与关联。MCP：`update_task`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`TaskUpdate`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `title` | {"anyOf": [{"type": "string", "maxLength": 160, "minLength": 1}, {"type": "null"}]} |
| `issueId` | {"anyOf": [{"type": "string", "maxLength": 120}, {"type": "null"}]} |
| `due` | {"anyOf": [{"type": "string", "maxLength": 10}, {"type": "null"}]} |
| `required` | {"anyOf": [{"type": "boolean"}, {"type": "null"}]} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/transitions

推进取消或重新打开行动。MCP：`transition_task`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`TaskTransition`；必填：request_id, expected_version, status。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `status` | {"type": "string", "enum": ["待办", "进行中", "已完成", "已取消"]} |
| `reason` | {"type": "string", "maxLength": 5000, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/dependencies

设置行动依赖并检查循环。MCP：`set_task_dependencies`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`Dependencies`；必填：request_id, expected_version, dependsOn。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `dependsOn` | {"items": {"type": "string"}, "type": "array", "maxItems": 100} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/reorder

调整同组行动显示顺序。MCP：`reorder_task`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`Reorder`；必填：request_id, expected_version, target_id。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |
| `target_id` | {"type": "string", "maxLength": 120, "minLength": 1} |
| `after` | {"type": "boolean", "default": false} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/trash

读取回收站问题与行动。MCP：`list_trash`。

### POST /api/issues/{issue_id}/trash

软删除问题及关联行动。MCP：`delete_issue`。

参数：`issue_id`（path）；`X-CSRF-Token`（header）。

请求体：`Write`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/issues/{issue_id}/restore

恢复问题及同批行动。MCP：`restore_issue`。

参数：`issue_id`（path）；`X-CSRF-Token`（header）。

请求体：`Write`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/trash

软删除行动并检查依赖。MCP：`delete_task`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`Write`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/restore

恢复独立删除的行动。MCP：`restore_task`。

参数：`task_id`（path）；`X-CSRF-Token`（header）。

请求体：`Write`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "未指定"} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/activity

读取操作审计事件。MCP：`list_activity`。

参数：`after`（query）；`limit`（query）。

### GET /api/export

导出全部问题行动与版本。MCP：`export_workspace`。

## 通用记录身份与创建快照

身份保存在服务端identityProfiles；GET/POST/PATCH /api/identities 查询、新增、编辑。kind=person时via必须manual且模型为空；kind=agent时via为claude_code/workbuddy/codex/deepseek_harness，模型可选。kind不可修改；名字或默认模型变更仅影响新记录。

创建问题/行动可带creation={identityId,initiatedByPersonId,modelInfo:{name,provider}}。identityId是实际提交身份；initiatedByPersonId仅允许AI代录时指向人。modelInfo省略或null使用身份默认值；空对象清空模型（显示模型未提供），每次调用可显式覆盖。工具不能推导模型。手动创建不能携带模型或发起者。

服务端输出createdByActorId、initiatedByPersonId、creatorName、createdVia、createdAt和modelInfo。creatorName取人类发起者或提交者当时名称；createdAt由服务器生成UTC。Elias委托Codex时显示Elias 经 Codex 创建 · GPT-6.1 Sol。这是请求声明的来源快照，并非认证或运行模型自动探测。

普通PATCH不接受创建字段。改名、编辑内容、删除恢复不会修改创建快照。关联行动使用本次提交身份，不继承所属问题。兼容旧客户端不传creation时来源unknown，创建时间仍为服务器时间；迁移历史记录的时间保持NULL，不猜测。

问题/行动列表支持creator（人类发起者优先，否则实际提交者ID；unknown筛选历史未知）、created_via和model（模型名称不区分大小写子串）组合筛选。返回及导出包含快照、身份列表；当前选中身份ID只保存于该浏览器。

identity_profiles与问题/行动的身份ID为历史逻辑引用，由领域层创建时校验，不定义物理外键；独立保存名称、来源与model_info JSON，避免默认配置变化污染历史。

## AI快速接入与授权续期

公开入口 /connect、/connect.md、/connect/manifest.json 和 /downloads/{filename} 提供无凭据引导与固定版本Skill。三Tab分别处理快速接入、设备证据和手动配置。get_connection_context读取当前账号与scope，HTTP直接调用不能生成MCP验证标志。

OAuth接受read、write或空格分隔集合，兼容write包含read。刷新令牌绑定客户端与resource，最长30天；每次刷新轮换，旧刷新令牌重放撤销同access_id授权族。PAT有效期1年。撤销即时阻止访问与刷新。设备最近访问不等于在线，runtime与Skill版本为客户端声明。具体请求体和返回见OpenAPI、docs/AI快速接入.md。

## MCP访问认证

HTTP MCP随服务启动于 /mcp，需要 Authorization: Bearer 访问密钥；无效密钥返回401。stdio仍为本机子进程。密钥按接入端分发、逐次校验、可分别撤销，详见 MCP远程接入.md。网页/API使用会话或账号访问令牌；每个账号独立工作台。Cookie写入需要CSRF，令牌按read/write范围校验。creation仍是调用方声明。

## 示例与边界

只读：`python examples/api_client.py`。合成写入：加 `--write-demo`。浏览器示例：服务运行后访问 `/examples/`。

本版为账号隔离工作台，支持显式配置0.0.0.0监听与内网Host允许列表；actor不是身份认证。正式存储为用户配置的MySQL专属新库，实体分表保存；SQLite仅用于隔离测试。提供回收站软删除与恢复，依赖关系移除也是软删除，数据库19表DELETE触发器与运行时SQL防护阻止物理删除。提供登录注册、会话管理、OAuth与访问令牌；没有永久删除、导入或离线跨设备同步API。完整工作台/导出包含回收站，普通列表和详情仅限有效记录。恢复必要行动可重开验证，删除问题/恢复问题均原子处理同批关联行动。审计分页使用after=最后一条revision继续查询。完整备份使用MySQL专属库备份，页面JSON不含幂等表。
