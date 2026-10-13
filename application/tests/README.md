# 测试入口与隔离边界

所有可复用测试集中于本目录。`test_*.py`是pytest回归；`*_check.py`是显式集成/浏览器验收；`auth_client.py`、`http_auth.py`和`compare_databases.py`是测试助手。

- `python tests/run_suite.py`：临时SQLite、单元/API、真实SDK、浏览器及重启保留。
- `python tests/dual_transport_check.py`：临时TLS证书及合成账号，HTTP/HTTPS认证与MCP兼容。
- `python tests/diagrams_check.py`：离线双图几何、缩放和拖动；`--live-schema`只读核对指定数据库元数据。
- `python tests/docker_check.py --image shixu-system:3.2.1 --baseline shixu-system:3.2.0-docker.1`：独立随机Compose项目与MySQL测试库，容器/API/MCP/浏览器、恢复、回退升级、故障、秘密扫描和本项目清理。须先构建目标镜像并确保基线镜像存在。
- `python tests/lan_check.py --url http://127.0.0.1:8765`：显式内网入口匿名烟测。
- `public_transport_check.py`：显式运维验收，要求SHIXU_VERIFY_HTTPS_URL、SHIXU_VERIFY_HTTP_URL、SHIXU_VERIFY_USERNAME、SHIXU_VERIFY_PASSWORD；会创建临时PAT/OAuth认证记录并撤销令牌，不写业务数据。不得自动指向生产。
- `codex_config_check.py --command <Codex可执行路径>`：独立临时客户端配置检查，不代表真实客户端OAuth登录。

报告和截图写入`verification/`；临时数据库、凭据、镜像扫描包放`runtime/`且不提交。迁移/运行/构建工具留在`scripts/`，不得按测试清理。
