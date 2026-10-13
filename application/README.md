# 拾序 · 系统 + API + MCP

版本3.2.1，按已确认的自定义AI工具原型v1.9.0更新。保留五视图、七状态流转、回收站、编号、依赖、日历、跟进及创建来源；页面、API与MCP共用按账号隔离的MySQL事务。

右上角账号卡片打开下拉菜单，账号设置和AI接入采用弹窗Tab。手机工作台工具放在二级菜单，退出登录放在账号菜单。关闭弹窗保留页面与筛选。

账号决定数据归属，记录身份说明创建人、AI工具和模型。迁移前记录归到test，原有创建快照不改变；注册账号从空工作台开始。

## 部署和使用

安装Python3.11+及requirements.txt，连接私有MySQL8.0专属库。执行 scripts/service.py start、status、stop 管理服务。从2.4升级须停服、私有输入初始密码并执行 scripts/migrate_accounts.py，详见下方账号说明。通过SHIXU_ALLOW_HTTP_AUTH=true显式开启公网HTTP登录及PAT/API/MCP；HTTPS继续支持，标准远程OAuth仍需HTTPS。

- [账号、迁移和远程接入](docs/账号与远程接入.md)
- [MySQL部署](docs/MySQL部署说明.md)
- [中文API](docs/API中文说明.md)
- [AI调用指南](docs/AI接入与调用指南.md)
- [需求映射](docs/需求与能力映射.md)
- [机器合同](project-contract.json)

本机系统 http://127.0.0.1:8765/，MCP /mcp，API交互 /docs，Schema /openapi.json，示例 /examples/，双图 /static/diagrams/architecture.html 与 /static/diagrams/erd.html。

支持OAuth的客户端填写HTTPS MCP地址后登录授权；其他客户端和服务器在网页AI接入弹窗生成只读/读写PAT配置。新机器不需要项目源码或发放脚本。旧全局文件密钥停用。Python/stdio示例读取私有环境SHIXU_MCP_TOKEN；网页示例复用登录会话。

## 验证与交付

依次执行 tests/run_suite.py --mysql、scripts/generate_diagrams.py、tests/diagrams_check.py --live-schema、scripts/generate_docs.py、scripts/build_release.py。默认check使用SQLite测试适配器，MySQL验证只写专属_test库。证据在verification，20表定义在data/mysql-schema.sql。源原型未修改，分发的冻结快照已脱敏。

业务删除与依赖移除保留原行，数据库DELETE触发器阻止物理删除。每个账号独立revision、编号、身份、审计和幂等，数据归属只能来自认证上下文。

本次为Windows/Python3.11单机交付。未做AI自主任务、各客户端OAuth兼容性、大负载或高可用验收；不支持共享账号工作台、管理员角色、找回密码、永久删除。MySQL连接尚未启用TLS。项目包排除凭据、真实数据及依赖；未授予开放许可证。

## 3.1 快速接入

新设备打开 [公开接入页](https://shixu.eliasliu.cc/connect)，选择runtime并复制提示词交给AI。网页提供公开指南、能力矩阵及带SHA256的固定版本独立Skill包；OAuth由用户在浏览器完成。账号菜单 → AI接入，使用快速接入、我的设备、手动配置三个Tab。

从3.0升级先停服，运行 `python scripts/migrate_onboarding.py`，确认原有17表保留核对通过，再启动服务。新增设备证据和刷新令牌两表；迁移前自动保存私有快照。详见 [AI快速接入](docs/AI快速接入.md)。

## 3.2 自定义工具与接入更新

AI身份支持预设工具和“其他 / 自定义工具”；名称1至80字、trim及大小写去重，在账号内保存。工具目录随导出返回，身份切换默认工具不丢失历史来源。API新增GET/POST /api/ai-tools；MCP新增list_ai_tools、create_ai_tool及get_connection_updates，共29项。

从3.1升级：暂停写入、停止服务，运行 `python scripts/migrate_custom_tools.py`，脚本先备份全部表并核对原数据，再新增ai_tools、扩展identity_profiles.via、issues/tasks.created_via及activity.resource_id为80字符。确认报告passed后重启。重复执行幂等；DDL不是事务性回滚，失败保持停服，检查私有备份后完成迁移；回退应用时保留新增表和扩宽字段，禁止删除新工具或历史记录。

[接入更新指南](docs/connect/updates.md)说明用户驱动的Skill/MCP更新。服务发布包内skills/shixu-issues为独立可安装Skill的维护源，1.5.0包含可选标准库更新脚本；由1.4.0便携包派生，工作区F02入口仍独立管理。脚本默认只读计划，显式--apply才安装；校验摘要、保留用户修改、备份旧版。MCP由当前客户端原生能力合并配置并验证，不通过服务端远程写客户端文件。


## Docker部署

正式3.2.1业务保持不变，Docker交付修订为3.2.1。网页、API、内置MCP、双图和接入资源随单个非root应用镜像运行，生产继续使用现有MySQL。详见 [Docker部署、升级与恢复](docs/Docker部署.md)。
