# 拾序 Docker 部署

沿用正式 3.2.1 的 FastAPI、内置 HTTP MCP、MySQL 和全部路由。网页 `/`、API `/api`、MCP `/mcp`、API 文档 `/docs`、双图 `/static/diagrams/architecture.html` 与 `/static/diagrams/erd.html`，以及 `/connect`、`/downloads`、OAuth 均随同一镜像交付。

## 已有 MySQL 环境

先确认专属数据库的 application_id、20 张表、6 个物理外键和当前增量迁移已完成。Docker 化不改变数据库模型，不自动建库、播种或重放迁移。首次建库仅对已创建空库显式执行 `scripts/init_mysql.py`；非空库会拒绝。

Docker Desktop Linux amd64 已验证。需 Docker Compose v2、可访问所配置的 MySQL；首次构建需联网安装锁定依赖。应用非 root，runtime 命名卷归 UID/GID 10001，业务、账号和令牌摘要仍在外部 MySQL。

将 `.env.docker.example` 复制到私有配置目录。其 `SHIXU_DOCKER_ENV_FILE` 指向容器环境文件：从原配置安全导出 DB_HOST、DB_PORT、DB_NAME、DB_USER、DB_PASSWORD、DB_SSL、SHIXU_PUBLIC_URL、SHIXU_ALLOWED_HOSTS、SHIXU_HTTPS_PROXY_SECRET 和原有认证策略。不要复制 Windows SHIXU_ENV_FILE 或宿主机绝对路径；CA 需要另行验证只读挂载并使用容器内路径。秘密不能进入镜像、Git、ZIP 或日志。Compose 插值文件决定镜像/端口；env_file 提供应用环境。

```text
docker compose --env-file <私有Compose配置> -p shixu-production build
docker compose --env-file <私有Compose配置> -p shixu-production up -d --wait --wait-timeout 180
docker compose --env-file <私有Compose配置> -p shixu-production ps
docker compose --env-file <私有Compose配置> -p shixu-production logs --tail 100 app
```

默认只映射回环 8765，保留现有 FRP/HTTPS 代理链。应用容器监听 0.0.0.0 不代表宿主机公开端口。代理证明密钥、公开 URL、Host/Origin 校验保持原策略；不信任任意 forwarded headers。无需改动 FRP。

## 升级与恢复

先在合成隔离库完成本轮测试，记录镜像 ID、代码指纹及上版镜像。切换前隔离全部旧实例写入，验证真实库一致性备份和文件备份；核对兼容后只更新应用。命名卷不会随重建删除，且不等于数据库备份。不要使用 `down -v` 处理生产。

回退使用明确旧镜像 ID 和同一私有配置；只有兼容已证明时才切回。数据库模型本轮未变，因此不需要生产 DDL。不得用旧库备份覆盖新业务数据。停止仅用明确项目名的 Compose stop；保留数据与镜像。restart unless-stopped 在引擎运行后恢复已启动的容器，不代表宿主机自动登录、Docker Desktop开机就绪或高可用。

## 验收

执行 `tests/docker_check.py` 做独立 Compose 项目、独立 MySQL 库/卷及合成账号的14阶段演练，包含真实浏览器、MCP SDK和恢复。正式实例只读验收健康、版本、网页/API、现有认证 MCP、OAuth发现和分发摘要。隔离测试配置只是测试资源，不承诺第二种生产数据库组合。完整报告位于 verification；生产备份留 runtime 私有目录。
