# 拾序 AI 与 MCP 接入

## 新设备快速接入

首选 [公开接入页](https://shixu.eliasliu.cc/connect) 复制提示词；AI按 `/connect.md` 检测runtime、配置远程MCP、安装独立Skill、引导用户授权并调用 `get_connection_context` 核对工作台与scope。无需获取服务端项目或数据库配置。详见 [AI快速接入](AI快速接入.md)。

## 服务端维护与本地stdio接入

3.0起，HTTP MCP默认随API在同一进程启动，地址为 `/mcp`，需要当前账号的OAuth或PAT。详见 [账号与远程接入](账号与远程接入.md)。其他电脑可以使用HTTP接入，详见 [MCP远程接入](MCP远程接入.md)。本机仍可使用下面的stdio方式，由客户端启动适配器子进程。两种方式共用29个工具和业务规则；客户端均不需要数据库密码。

在 system 目录内使用实际安装依赖的 Python：

```powershell
python scripts/configure_mcp.py --format json
python scripts/configure_mcp.py --format toml
```

脚本只输出配置片段，不写入任何客户端配置。JSON 格式给支持 `mcpServers` 的客户端；TOML 片段的服务名为 `shixu`。路径由当前 Python 和项目位置生成，复制后按客户端的 MCP 配置入口添加并重新连接。默认 stdio 命令为 `python /绝对路径/application/mcp_server.py`，环境变量 `SHIXU_API_URL=http://127.0.0.1:8765`，并在私有环境提供 `SHIXU_MCP_TOKEN`。

实现基于 [官方 MCP Python SDK v2 文档](https://py.sdk.modelcontextprotocol.io/)。版本固定在 requirements.txt；stdio 由官方 SDK 处理初始化、工具发现与调用。

## 调用顺序

1. `get_system_status` 确认 API 与数据库可用。
2. `list_issues` / `list_tasks` 定位对象，`get_issue` / `get_task` 获取详情与最新 `revision`。
3. 写工具传 `body` 对象，其中 `expected_version` 为最近读取的当前账号 `revision`，`request_id` 使用新的 UUID，`actor` 标记调用来源。
4. 保存后使用返回的 `revision` 作为下次写入版本，或重新读取目标。
5. 相同请求因超时重试时保持完整参数和 `request_id` 不变。内容变化使用新编号。409 先重读并评估冲突；422 修改参数/满足业务条件；503 或断连不声称成功，恢复后同号重试。

一个工具调用可能同时改变问题和行动，例如关闭问题批量取消行动、开始首项行动使待处理问题进入处理中。实体保存在 MySQL 的独立表中；工具返回的 `data` 是该事务提交时组装的工作台视图。旧请求重放返回原结果，如需当前状态重新读取。MCP 不读取数据库密码，也不直接连接或写入 MySQL。

## 工具决策表

| 工具 | 何时使用 | 主要输入 | 返回 | 副作用 |
|---|---|---|---|---|
| get_connection_context | 接入授权后只读核对 | runtime_name/runtime_version/skill_version可选 | account/scopes/accessId/interfaceVersion/verifiedAt | 更新接入诊断元数据，不写业务记录 |
| get_system_status | 首次调用/恢复连接 | 无 | status、revision | 无 |
| list_identities | 新建前选择人/AI身份 | 无 | items、revision | 无 |
| create_identity | 登记通用身份 | body.name/kind/via/modelName/modelProvider | resource、data、revision | 新增身份 |
| update_identity | 改名或改默认模型 | identity_id、body中的变更字段 | 同上 | 不追溯修改历史 |
| get_workspace | 跨对象查看/获取一致快照 | 无 | revision、data | 无 |
| list_issues | 搜索问题 | q/status/priority/tag/creator/created_via/model | items、revision | 无 |
| get_issue | 写入前读详情 | issue_id | item、tasks、revision | 无 |
| create_issue | 记录新困扰 | body.title等 | resource、data、revision | 创建问题 |
| update_issue | 编辑背景和属性 | issue_id、body中的变更字段 | 同上 | 更新问题 |
| transition_issue | 梳理/开始/验证/解决/暂缓/关闭/重开 | issue_id、body.action及依据 | 同上 | 状态/历史；关闭时处置行动 |
| add_followup | 记录日常进展 | issue_id、body.content | 同上 | 追加跟进，不改状态 |
| list_tasks | 浏览行动 | issue_id/status/creator/created_via/model | items、revision | 无 |
| get_task | 查看依赖/写入前取版本 | task_id | item、revision | 无 |
| create_task | 拆解下一步 | body.title/issueId/due/required | resource、data、revision | 创建行动；可能退回验证阶段 |
| update_task | 编辑安排或关联 | task_id、body中的变更字段 | 同上 | 编辑行动；可能变更问题阶段 |
| transition_task | 推进/完成/取消/重开 | task_id、body.status/reason | 同上 | 行动和关联问题状态 |
| set_task_dependencies | 明确先后约束 | task_id、body.dependsOn | 同上 | 修改依赖图 |
| reorder_task | 调整显示顺序 | task_id、body.target_id/after | 同上 | 顺序变化，编号/依赖不变 |
| list_activity | 检查哪些操作发生过 | after/limit | items | 无 |
| list_trash | 查看已删除的问题和行动 | 无 | issues、tasks、revision | 无 |
| delete_issue | 问题移入回收站 | issue_id、body | resource、data、revision | 软删除问题及当次有效关联行动 |
| restore_issue | 恢复整批问题 | issue_id、body | 同上 | 恢复同批行动，校验有效依赖与父问题 |
| delete_task | 单独删除行动 | task_id、body | 同上 | 软删除，保留编号和历史 |
| restore_task | 单独恢复行动 | task_id、body | 同上 | 校验父问题、依赖；必要行动可能退回验证 |
| export_workspace | 取得完整导出数据 | 无 | revision、data | 无；不自动写文件 |

所有写工具均带 `request_id`、`expected_version`、`actor`；都适用 409/422/503 处理规则。机器可读的实际参数 schema、描述和副作用来自 [MCP工具目录.json](MCP工具目录.json)。

## 验证依据要求

- triage：下一步 `nextStep` 和解决标准 `successCriteria`。
- verify：`successCriteria`、处理说明 `treatment`、验证方式 `verificationMethod` 必填；必要行动全部完成或有原因取消。
- resolve：仅待验证问题，`resolution` 填实际结论与证据，不能编造完成状态。
- pause：`reason` 与不早于今天的 `reviewDate`。
- close-issue：`reason`、`closeType`，有未完成行动时传 `taskPolicy=cancel|detach`；重复问题传 `duplicateOf`。
- reject/reopen/retriage：`reason`。取消行动同样必须传原因。

## 可复制安装与演示任务

> 进入拾序 system 目录，用独立 Python 环境安装 requirements.txt，启动 scripts/service.py start，检查 /api/health。运行 scripts/configure_mcp.py 获取 stdio 配置，根据我的客户端注册该 MCP，使用网页生成的账号令牌，通过私有环境SHIXU_MCP_TOKEN注入，不把凭据写入源码。重新连接后 list_tools，先检查健康与列表。若我要求演示写入，只创建新的演示对象，不修改历史真实记录；每步读取版本，重试保持 request_id，填写真实验证依据。最后回读对象与审计，不把固定 SDK 测试当作 AI 自主验收。

本项目提供 `python examples/mcp_client.py` 只读检查；加 `--write-demo` 才创建合成问题与行动。该脚本是固定序列协议测试，AI 自主任务验收仍待执行。

## 数据保留约束

删除问题、行动及移除前置关系均为软删除。不能通过任何工具永久删除或清空数据库记录；deleted_at标识失效，恢复/重新添加激活原记录。跟进、历史、日志和审计不提供删除工具。

## 2.3.0：Elias、Codex 与模型的记录方式

先调用list_identities，选择或登记人类Elias和AI Codex两个独立身份。AI身份kind=agent、via=codex，默认modelName=GPT-6.1 Sol、modelProvider=OpenAI（此处只是用户指定的示例，并非系统检测）。每次create_issue/create_task传：

```json
{"body":{"title":"示例问题","request_id":"本次新UUID","expected_version":123,"creation":{"identityId":"Codex身份ID","initiatedByPersonId":"Elias身份ID","modelInfo":{"name":"GPT-6.1 Sol","provider":"OpenAI"}}}}
```

将示例ID、UUID及revision替换为真实值。AI自主记录省略initiatedByPersonId；手动创建使用人类identityId且不传modelInfo。工具来源由所选身份推导，工具名不能推断模型。模型省略/null使用默认值；显式空对象表示未提供。应优先把每次调用已知的实际模型传入；无法确定时留空，不编造。

creation只用于创建，后续PATCH不能改写来源字段。API/MCP输出createdByActorId、initiatedByPersonId、creatorName、createdVia、createdAt、modelInfo。legacy调用不传creation仍兼容，但明确记录为unknown。actor仍仅是本次操作审计标签，不能替代创建身份。所有身份均为调用方声明，不证明登录用户、真实工具执行环境或模型真实性。

29个工具都经HTTP共用同一事务与规则。Claude Code、WorkBuddy、Codex和DeepSeek Harness以各客户端实际支持的MCP配置方式接入同一工具集（本机stdio或带密钥的HTTP入口）；这些是来源选项，未声称逐一完成四种客户端兼容验证。接入时登记对应via及真实模型，不将Codex示例用作其他工具默认值。

可运行 `python examples/creator_client.py` 只读查看身份，加 `--write-demo` 才创建合成身份与问题；`/examples/`也可选择已登记的AI和人类发起者。历史记录没有自动导入原型浏览器存储。
