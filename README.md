# 拾序 · 个人问题与行动工作台

> 把困扰理清，把今天过好。

拾序帮助个人记录问题，把问题拆成行动，并在完成后验证是否真正改善。

## 项目入口

| 目录 | 用途 | 使用说明 |
|---|---|---|
| [prototype/](prototype/) | v1.9.0 交互原型、需求、设计合同与验证材料 | [原型说明](prototype/README.md)，直接用浏览器打开 [prototype.html](prototype/prototype.html) |
| [prototype-accounts/](prototype-accounts/) | v1.9.0 自定义AI工具原型 | [账号原型说明](prototype-accounts/README.md) |
| [application/](application/) | v3.2.0 自定义AI工具与接入更新应用、HTTP API、MCP、测试与部署文档 | [应用安装与运行](application/README.md) |

应用使用 Python 3.11+ 与独立 MySQL 8.0，页面、业务及账号 API 与 29 个 MCP 工具共用后端规则。默认入口 http://127.0.0.1:8765/，API 文档 `/docs`，MCP 默认随服务提供 `/mcp` HTTP 入口与账号OAuth/PAT认证，同时保留 stdio。

进入 `application/` 后执行安装、启动、验证和打包命令。应用的页面入口是 `application/static/index.html`，原型入口是 `prototype/prototype.html`。

- [交互 ER 图](application/static/diagrams/erd.html)
- [系统架构图](application/static/diagrams/architecture.html)
- [版本记录](CHANGELOG.md)

根目录保留 Git、CI、忽略配置和产品总说明；各自专用的设计、代码、测试与文档位于对应目录。

原型记录保存在浏览器本地，应用记录保存到 MySQL，两者不会自动互相迁移。原型文件位置变化可能影响原有浏览器记录的访问，可在旧入口导出 JSON 留存。

已发布的历史 ZIP 保持原有目录结构；当前源码采用上述并列目录。

移动端预览：[mobile-preview.html](prototype/mobile-preview.html)，可切换360/390/430px并直接点击体验；应用已同步手机导航、紧凑菜单、回收站与下一步显示切换；本次冻结输入位于 application/reference/accounts-source.html（账号原型脱敏快照），并保留创建身份与回收站基线。


新电脑从 [公开AI接入页](https://shixu.eliasliu.cc/connect) 复制提示词开始，无需服务端源码。系统说明见 [AI快速接入](application/docs/AI快速接入.md)。
