# WorkBuddy适配 · 1.0

依据官方技能说明：https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market 。

先确认实际版本及MCP设置界面所接受的远程传输与授权方式。可读取当前客户端的帮助和已有非秘密配置结构，但不得猜测版本或把通用JSON当作已验证格式。支持远程HTTP时使用清单mcp地址；支持OAuth时由用户完成网页登录，否则从拾序“AI接入→手动配置”领取专属访问令牌并导入客户端私有配置。

Skill通过“技能→添加技能→上传技能”导入已校验ZIP，然后确认已安装且启用。具备工具操作能力的AI可引导完成设置；没有界面/本地执行能力时停在待用户导入，不声称自动完成。

仅合并当前用户当前客户端的拾序项，保留其他连接。重复安装先比较版本，不覆盖用户修改。新会话实际调用get_connection_context、list_issues，并确认Skill可发现后再报告。此适配为人工引导兼容路径；未验证具体WorkBuddy版本的自动配置/OAuth，不展示自动支持声明。
