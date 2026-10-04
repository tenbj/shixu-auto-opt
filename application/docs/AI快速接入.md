# AI快速接入 · 3.2.0

## 用户操作

陌生电脑打开 https://shixu.eliasliu.cc/connect，无需登录即可选择Codex、WorkBuddy、Claude Code或其他runtime，复制一段提示词交给AI。已登录用户也可从右上角账号菜单 → AI接入 → 快速接入完成同一操作。复制不包含密码或令牌。

AI先读取 `/connect.md` 和 `/connect/manifest.json`，检查目标runtime已有配置，保留其他MCP；远程服务优先使用 https://shixu.eliasliu.cc/mcp。原HTTP入口继续保留。未安装runtime时，页面提供官方安装入口；无法自动完成的步骤明确交给用户操作。

支持OAuth的runtime由用户在浏览器登录自己的账号并确认权限，AI不索要密码；服务支持动态注册、S256 PKCE、一次性授权码以及绑定客户端和资源的轮换刷新令牌。不支持OAuth的runtime或服务器，在“手动配置”创建只读/读写访问令牌，将其保存在目标机器私有配置或环境变量中。凭据不放入提示词、Skill、日志或公共文件。

## Skill、runtime与MCP的分工

| 层 | 职责 | 分发方式 |
|---|---|---|
| 页面 | 复制提示词、人工授权、查看/撤销设备 | /connect和账号弹窗 |
| 服务 | 公开指南、接入能力、令牌验证、账号隔离、真实工具调用 | HTTPS /mcp及API |
| runtime | 读取配置、保存授权、发现工具、执行调用 | 适配说明，按本机版本检测 |
| 独立Skill | 记录规则、分类、身份与模型来源、幂等写入及回读 | shixu-issues-1.5.0.zip |
| 工作区F02 | 保留本工作区记忆与备份规则，并复用上述业务规则 | 本地技能入口 |

独立Skill没有E盘路径或B系列工作区依赖，包内只有文本。manifest公布版本、文件名和SHA256；下载端点仅允许清单中的文件且核对摘要。更新本地F02后，运行其 `scripts/build_portable.py --help` 查看构建参数，重新打包并同步manifest。先核对哈希再安装。

## 接入验证和设备证据

授权后调用 `get_connection_context` 核对当前账号、read/write权限、接口版本和授权ID，可携带runtime、runtime版本及Skill版本。该调用不创建问题、行动或身份，不增加业务revision。HTTP MCP路径的真实调用由服务端记录MCP验证时间；直接访问诊断API只返回认证上下文，不能伪造MCP验证标志。本地stdio转发普通HTTP，不记录此HTTP MCP验证标志。

“我的设备”实际展示当前账号的授权连接；可重命名、撤销，显示授权状态、最近访问和MCP验证时间。最近访问不等于在线。runtime与Skill版本为客户端声明，未作为身份凭证或可信硬件识别。安装成功也不等于业务写入成功；用户要求记录后仍须调用创建工具并回读结果。

## 协议与接口

- 公开GET：`/connect`、`/connect.md`、`/connect/manifest.json`、`/connect/runtimes/{runtime}.md`、`/downloads/{filename}`。
- 认证GET `/api/connection-context`：诊断当前会话/令牌权限；不接受owner输入。
- PATCH `/api/account/mcp-access/{access_id}`：会话认证加CSRF，JSON `{ "displayName": "我的电脑" }`，只允许本人授权。
- POST `/oauth/token`：表单 `grant_type=refresh_token`、`refresh_token`、`client_id`；resource若提供须匹配，scope可保持或缩小。返回新access_token、refresh_token、token_type、expires_in和scope，响应禁止缓存。

访问令牌1小时、刷新授权最长30天、PAT一年。刷新同时替换旧访问令牌，每个刷新令牌仅能使用一次；重复提交已消费的刷新令牌会撤销整个授权族，客户端需串行刷新。撤销立即阻止访问与续期。标准错误包括invalid_grant、invalid_scope。scope支持read、write或空格分隔集合，兼容既有write包含read。

## 升级与验证范围

从3.0升级须先停服，运行 `python scripts/migrate_onboarding.py`；脚本私有备份原表、添加access_metadata/oauth_refresh_tokens及禁止DELETE触发器、核对原17表内容，之后再启动。MySQL DDL不是整体事务，失败时保留快照并在独立库核对恢复。SQLite仅用于隔离测试。

自动化覆盖临时数据库、专用MySQL测试库、OAuth轮换/重放/范围/并发、真实MCP SDK、HTTP与TLS浏览器、公开下载摘要和五种视口。支持矩阵区分官方文档支持与实机验证；未把SDK测试当成Codex/WorkBuddy完整安装测试，未声称所有runtime或空白实体电脑已验收。公开矩阵中的verifiedVersions为空时应按本机能力检测并报告人工步骤。

## 用户驱动更新（3.2）

用户要求更新或修复时，先读取当前公开清单或调用get_connection_updates。Skill1.5.0带可选更新脚本，默认只读，--apply执行哈希校验、修改保护、备份与替换。MCP地址以当前清单为准，由客户端原生能力合并拾序配置；跨域需核实并重新授权，不转移旧令牌。完成后重载并回读账号和权限，Skill可发现状态单独确认。详见 [更新指南](connect/updates.md)。
