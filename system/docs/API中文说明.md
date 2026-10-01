# 拾序 API 中文说明

版本 2.0.0 · 基地址 http://127.0.0.1:8765 · UTF-8 JSON。在线交互文档 `/docs`，机器Schema `/openapi.json`。

## 并发、幂等与错误

所有写入携带 `request_id`（8–120字符，推荐UUID）、`expected_version`（当前全局revision）与可选 `actor`（审计标签，默认我）。请求体不接受未声明字段。每个写入是一个MySQL InnoDB事务；返回 `revision`、`resource` 和事务提交时的 `data`。失败不改变数据、审计或版本。

同一request_id及完全相同内容重放返回原始成功响应；request_id相同但内容不同返回409。网络超时保持请求内容和编号重试。全局版本是工作台版本，不是单个对象版本；任何对象写入都会递增。

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

### GET /api/health

检查服务与数据库状态。MCP：`get_system_status`。

### GET /api/workspace

读取完整工作台与并发版本。MCP：`get_workspace`。

### GET /api/issues

查询问题列表。MCP：`list_issues`。

参数：`q`（query）；`status`（query）；`priority`（query）；`tag`（query）。

### GET /api/issues/{issue_id}

读取问题详情及关联行动。MCP：`get_issue`。

参数：`issue_id`（path）。

### POST /api/issues

创建待梳理问题。MCP：`create_issue`。

请求体：`IssueCreate`；必填：request_id, expected_version, title。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `title` | {"type": "string", "maxLength": 160, "minLength": 1} |
| `description` | {"type": "string", "maxLength": 5000, "default": ""} |
| `priority` | {"type": "string", "enum": ["高", "中", "低"], "default": "中"} |
| `tag` | {"type": "string", "maxLength": 40, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### PATCH /api/issues/{issue_id}

编辑问题内容与属性。MCP：`update_issue`。

参数：`issue_id`（path）。

请求体：`IssueUpdate`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `title` | {"anyOf": [{"type": "string", "maxLength": 160, "minLength": 1}, {"type": "null"}]} |
| `description` | {"anyOf": [{"type": "string", "maxLength": 5000}, {"type": "null"}]} |
| `priority` | {"anyOf": [{"type": "string", "enum": ["高", "中", "低"]}, {"type": "null"}]} |
| `tag` | {"anyOf": [{"type": "string", "maxLength": 40}, {"type": "null"}]} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/issues/{issue_id}/transitions

按七状态规则流转问题。MCP：`transition_issue`。

参数：`issue_id`（path）。

请求体：`IssueTransition`；必填：request_id, expected_version, action。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
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

参数：`issue_id`（path）。

请求体：`Followup`；必填：request_id, expected_version, content。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `content` | {"type": "string", "maxLength": 5000, "minLength": 1} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/tasks

查询行动列表。MCP：`list_tasks`。

参数：`issue_id`（query）；`status`（query）。

### GET /api/tasks/{task_id}

读取行动详情。MCP：`get_task`。

参数：`task_id`（path）。

### POST /api/tasks

创建关联或独立行动。MCP：`create_task`。

请求体：`TaskCreate`；必填：request_id, expected_version, title。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `title` | {"type": "string", "maxLength": 160, "minLength": 1} |
| `issueId` | {"anyOf": [{"type": "string", "maxLength": 120}, {"type": "null"}]} |
| `due` | {"type": "string", "maxLength": 10, "default": ""} |
| `required` | {"type": "boolean", "default": true} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### PATCH /api/tasks/{task_id}

编辑行动内容与关联。MCP：`update_task`。

参数：`task_id`（path）。

请求体：`TaskUpdate`；必填：request_id, expected_version。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `title` | {"anyOf": [{"type": "string", "maxLength": 160, "minLength": 1}, {"type": "null"}]} |
| `issueId` | {"anyOf": [{"type": "string", "maxLength": 120}, {"type": "null"}]} |
| `due` | {"anyOf": [{"type": "string", "maxLength": 10}, {"type": "null"}]} |
| `required` | {"anyOf": [{"type": "boolean"}, {"type": "null"}]} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/transitions

推进取消或重新打开行动。MCP：`transition_task`。

参数：`task_id`（path）。

请求体：`TaskTransition`；必填：request_id, expected_version, status。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `status` | {"type": "string", "enum": ["待办", "进行中", "已完成", "已取消"]} |
| `reason` | {"type": "string", "maxLength": 5000, "default": ""} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/dependencies

设置行动依赖并检查循环。MCP：`set_task_dependencies`。

参数：`task_id`（path）。

请求体：`Dependencies`；必填：request_id, expected_version, dependsOn。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `dependsOn` | {"items": {"type": "string"}, "type": "array", "maxItems": 100} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### POST /api/tasks/{task_id}/reorder

调整同组行动显示顺序。MCP：`reorder_task`。

参数：`task_id`（path）。

请求体：`Reorder`；必填：request_id, expected_version, target_id。

| 字段 | 约束/默认 |
|---|---|
| `request_id` | {"type": "string", "maxLength": 120, "minLength": 8, "description": "同一次请求重试使用同号，内容改变须换号"} |
| `expected_version` | {"type": "integer", "minimum": 0.0, "description": "GET /api/workspace 返回的全局 revision"} |
| `actor` | {"type": "string", "maxLength": 80, "minLength": 1, "description": "审计标签，不代表认证身份", "default": "我"} |
| `target_id` | {"type": "string", "maxLength": 120, "minLength": 1} |
| `after` | {"type": "boolean", "default": false} |

写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。

### GET /api/activity

读取操作审计事件。MCP：`list_activity`。

参数：`after`（query）；`limit`（query）。

### GET /api/export

导出全部问题行动与版本。MCP：`export_workspace`。

## 示例与边界

只读：`python examples/api_client.py`。合成写入：加 `--write-demo`。浏览器示例：服务运行后访问 `/examples/`。

本版为单人工作台，支持显式配置0.0.0.0监听与内网Host允许列表；actor不是身份认证。正式存储为用户配置的MySQL专属新库，实体分表保存；SQLite仅用于隔离测试。没有删除、导入、上传、登录或离线跨设备同步API。审计分页使用after=最后一条revision继续查询。完整备份使用MySQL专属库备份，页面JSON不含幂等表。
