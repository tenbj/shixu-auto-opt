# 测试入口与隔离边界

所有可复用测试集中于本目录。`test_*.py`是pytest回归；`*_check.py`是显式集成/浏览器验收；`auth_client.py`、`http_auth.py`和`compare_databases.py`是测试助手。

- `python tests/run_suite.py`：临时SQLite、单元/API、真实SDK、浏览器及重启保留。
- `python tests/checkout_check.py`：在Git工作树中核对Docker输入原始字节与Git存储字节一致，避免Windows/Linux换行导致证据失效。
- `python tests/dual_transport_check.py`：临时TLS证书及合成账号，HTTP/HTTPS认证与MCP兼容；同一浏览器context双入口注册、登录、业务读写和退出互不干扰。`--upstream <隔离HTTP入口> --proxy-env runtime/<本轮项目>/app.env`连接已启动隔离应用，以本机443临时TLS代理复用完整测试；该端口须空闲，不修改系统证书或生产代理。真实MySQL入口报告与SQLite源码测试报告分别记录。
- `python tests/diagrams_check.py`：离线双图几何、缩放和拖动；`--live-schema`只读核对指定数据库元数据。
- `python tests/docker_check.py --image shixu-system:3.2.1 --baseline shixu-system:3.2.0-docker.1`：独立随机Compose项目与MySQL测试库，容器/API/MCP/浏览器、恢复、回退升级、故障、秘密扫描和本项目清理。每次调用真实构建当前镜像（允许Docker缓存），要求基线镜像已存在。默认保护全部既有容器；并行验收只能用`--peer-project <确切Compose项目名>`显式排除并记录，禁止按名称前缀忽略。app/db各限制512MiB及0.75CPU且restart=no；构建与收尾同样受finally保护；超时/中断先终止回收当前命令树，再精确清理；失败在finally仅清理本项目容器/卷，私有诊断保留；首次冷启动和历史resume证据明确分开记录。清理后按确切Compose标签确认容器与卷归零。硬杀父进程无法触发finally，人工取消后必须用该项目配置执行down并回读标签；禁止仅凭旧输出推断已清理。最终源码指纹必须与构建时一致。
- `python tests/lan_check.py --url http://127.0.0.1:8765`：显式内网入口匿名烟测。
- `public_transport_check.py`：显式运维验收，要求SHIXU_VERIFY_HTTPS_URL、SHIXU_VERIFY_HTTP_URL、SHIXU_VERIFY_USERNAME、SHIXU_VERIFY_PASSWORD；会创建临时PAT/OAuth认证记录并撤销令牌，不写业务数据。不得自动指向生产。
- `codex_config_check.py --command <Codex可执行路径>`：独立临时客户端配置检查，不代表真实客户端OAuth登录。

报告和截图写入`verification/`；临时数据库、凭据、镜像扫描包放`runtime/`且不提交。迁移/运行/构建工具留在`scripts/`，不得按测试清理。
