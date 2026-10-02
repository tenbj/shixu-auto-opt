# 拾序 · 系统 + API + MCP

版本 2.2.1 · 基于拾序 当前回收站与紧凑菜单原型 · 单机服务 + MySQL 实体存储

系统保留今日概览、问题池、行动看板、统计分析、复盘记录，以及七状态流转、问题与行动固定编号、依赖、排序、日历、跟进和背景/属性编辑。页面和 MCP 共用同一套 API 与 MySQL 实体数据库。每次读取来自数据库，每次写入事务提交；内存仅作为单次请求的计算空间。

## 移动端

700px以内使用底部五视图导航、今日行动卡片、按日期分组的日程及全屏详情。手机新增、编辑、流转、跟进和导出均使用真实服务端工作台；顶部显示同步状态，更多菜单可刷新数据。桌面布局保持原有操作方式。

从2.1升级先停止服务，执行 python scripts/migrate_trash.py，再重启。迁移仅追加可空软删除字段与索引，保留业务记录、编号和历史。新增回收站支持同批恢复，操作菜单在桌面就地展开、手机使用底部操作面板；问题列表下一步默认隐藏。

## 安装与运行

要求 Python 3.11+、MySQL 8.0 和现代浏览器。无 Node 构建步骤。首次安装须配置仓库外私有连接，并新建专属数据库；分发包不包含任何使用者的连接凭据。

在当前 `application` 目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# 新环境先配置仓库外私有环境文件及专属空MySQL库，见 docs/MySQL部署说明.md。
.venv\Scripts\python scripts/service.py start
.venv\Scripts\python scripts/service.py status
# 结束时
.venv\Scripts\python scripts/service.py stop
```

macOS/Linux 使用 `.venv/bin/python` 代替 `.venv\Scripts\python`。本次实际验证环境为 Windows / Python 3.11；未声称已在其他操作系统实测。

- 系统：http://127.0.0.1:8765/
- API 交互文档：http://127.0.0.1:8765/docs
- OpenAPI：http://127.0.0.1:8765/openapi.json
- 健康检查：http://127.0.0.1:8765/api/health
- HTML 示例：http://127.0.0.1:8765/examples/
- MCP：客户端以 stdio 启动 `python /绝对路径/application/mcp_server.py`
- ER 图：http://127.0.0.1:8765/static/diagrams/erd.html
- 架构图：http://127.0.0.1:8765/static/diagrams/architecture.html

### 内网访问

在本机 `.env` 或私有环境文件中配置：

```dotenv
SHIXU_HOST=0.0.0.0
SHIXU_ALLOWED_HOSTS=192.168.1.138,0.0.0.0
```

将示例 IP 替换为服务器实际内网 IP，然后执行 `service.py stop`、`service.py start`。也可用 `python scripts/service.py start --host 0.0.0.0` 临时覆盖监听地址。`0.0.0.0` 表示监听全部 IPv4 网卡；其他设备用服务器内网 IP 访问，本机仍可使用 `127.0.0.1`。默认未配置时只监听回环地址。Host 允许列表和同源写入检查继续生效。

当前为无账号认证的个人工作台，内网访问面向可信网络。MCP 默认仍通过本机 HTTP API 调用。

新环境初始化后为空工作台。可选合成演示（仅空库可用）：

```powershell
.venv\Scripts\python scripts/seed_demo.py
```

前台调试：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`，Ctrl+C 停止。更换端口时，service 的 start/status/stop 都传同一个 `--port`。

## 数据与使用

正式记录保存到配置的专属 MySQL 库，实体分为 issues、tasks、task_dependencies、issue_followups、issue_history、issue_logs，另有 workspace_meta、activity、idempotency_requests。关闭服务、刷新页面和重启后保留。InnoDB 事务同时提交实体、审计和幂等结果，元数据行锁保护并发版本。操作人是审计标签，本版没有账号身份认证。按中国时区判断“今天”和回看日期。

浏览器只保存布局偏好。其他页面或 MCP 修改后，点击“刷新数据”读取最新版本；并发写入冲突会拒绝并提示重新检查，不覆盖他人修改。若网络中断导致保存结果未知，保留页面并重试相同操作，客户端会复用幂等编号。

导出记录可从页面右上角下载 JSON。完整备份使用 MySQL 对专属库进行一致性备份，恢复只面向该专属库。当前系统原有 SQLite 数据已只读迁入新库，源 SQLite 文件保留；API 提供软删除和恢复端点，没有永久删除或导入端点，原型浏览器内的历史记录未自动读取或迁移。

## 接入与验证

- [中文 API 文档](docs/API中文说明.md)
- [中文 AI/MCP 接入与工具决策表](docs/AI接入与调用指南.md)
- [需求与能力映射](docs/需求与能力映射.md)
- [MySQL部署与数据边界](docs/MySQL部署说明.md)
- [机器合同](project-contract.json)
- [验证报告](verification/summary.json)

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/check.py
# 已配置MySQL且对应_test库已初始化时，执行真实MySQL集成测试：
python scripts/check.py --mysql
python scripts/generate_docs.py
python scripts/build_release.py
```

`check.py` 默认使用显式 SQLite 测试适配器和随机端口，让无私有凭据的 CI 可运行；正式服务默认使用 MySQL。`--mysql` 在专门新建的 `_test` 库执行真实 HTTP、浏览器、22 个 MCP 工具、MySQL 并发/回滚/实体表及进程重启持久化检查。浏览器响应丢失场景通过网络拦截模拟；其余核心链路连接真实 MySQL。测试记录不会进入日常工作台。

## 交付边界

这是单服务、单人数据模型的系统，默认绑定 127.0.0.1，可显式配置 0.0.0.0 用于可信内网访问，并拒绝外站浏览器写入；数据写入指定 MySQL。未实现多人账号、认证授权、离线跨设备同步、附件、通知服务、自动 AI 拆解或高可用。全局版本适合个人规模，大数据/多人场景需分资源并发控制。MySQL TLS 条件由部署配置指定，默认校验证书。

已交付 MCP 协议与工具调用验证；AI 自主选择工具完成任务的验收尚未执行。AI 客户端需按接入文档自行配置，项目尚未授予开放源代码许可。分发 ZIP 排除本机数据库、日志、私有原型副本、凭据、真实工作台访问截图和依赖缓存；只保留合成数据与验证证据。

所有业务删除均为软删除，包括移除行动依赖。deleted_at为空表示有效，非空表示删除；恢复清空标识，编号与历史保留。数据库9表DELETE触发器与应用SQL防护阻止物理删除，不提供永久清空功能。已有2.2.0库先停止服务，执行 scripts/migrate_trash.py 追加依赖删除字段和数据库保护，再启动。
