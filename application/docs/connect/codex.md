# Codex适配 · 1.0

依据官方文档（2026-10-04核对）：https://learn.chatgpt.com/docs/extend/mcp?surface=cli 、https://learn.chatgpt.com/docs/build-skills 。

先识别本机实际形态和版本。桌面设置中可添加Streamable HTTP并Authenticate；不要求桌面用户安装CLI。已有CLI时先读 `codex mcp --help`，使用 `codex mcp add shixu --url <清单mcp>`，该命令可能直接启动授权；只有尚未授权时再用 `codex mcp login shixu`，交由用户网页登录。支持时用DCR注册；不擅自注册未支持的CIMD流程。

直接配置时在用户配置的 `[mcp_servers.shixu]` 设置url，保留完整已有TOML及其他表；默认路径 ~/.codex/config.toml，有CODEX_HOME时按实际配置确认。已存在同名条目先比较，不重复写入。OAuth由客户端私有存储管理，不读取凭据。PAT备用使用bearer_token_env_var指向用户私有环境变量，不把真实令牌写入聊天或公共文件。

将校验后的shixu-issues文件夹装到用户 ~/.agents/skills/shixu-issues（先核实版本支持、重复项和用户改动）。桌面可使用客户端提供的技能安装入口。重载MCP或开启新会话，然后在实际工具目录中调用get_connection_context和list_issues；技能另行验证可发现。未执行上述步骤不得标记成功。本版本未承诺全部桌面/CLI/IDE版本均已实机通过。
