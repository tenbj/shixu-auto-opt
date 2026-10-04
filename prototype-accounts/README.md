# 拾序账号与AI接入原型 · 1.8.0

打开prototype.html，登录演示账号后从右上账号下拉进入AI接入。快速接入 / 已连接设备 / 手动配置使用Tab弹窗。登录前也可查看公开接入指引。

体验“复制给AI”与“体验接入流程”：允许/拒绝/只读、验证失败重试、重载恢复、成功后的记录示例、设备改名撤销、TOML/JSON演示配置。

所有授权、安装、验证及设备状态都是离线模拟；不访问正式服务，不创建真实问题，DEMO令牌无效。提示词中connect.md为待上线设计。账号卡片、二级工作台工具和业务界面保持。

在仓库根运行 scripts/generate_accounts.py 的正确路径为：
`python prototype-accounts/scripts/generate_accounts.py --html-only`
增量合同：`python prototype-accounts/scripts/update_ai_contracts.py`。
本次不要运行早期write_contracts.py覆盖增量设计。H01响应式与合同报告在evaluation内。
