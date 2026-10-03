# MCP随服务启动与远程接入

版本2.4.0。HTTP MCP与拾序API共用一个进程、一个端口，路径为 `/mcp`。启动 `python scripts/service.py start` 即启动两者；stop同时停止，重启使用stop再start。`status`返回的 `mcp.running=true` 表示HTTP MCP生命周期已启动，完整协议检查使用下方SDK示例。本功能不负责Windows开机自启；它跟随已有拾序服务启动。

## 访问认证是什么

访问密钥相当于发给接入端的专用密码。客户端每次请求携带 `Authorization: Bearer <密钥>`，缺失、错误、已撤销密钥返回401。建议每台电脑或每个AI客户端各用一把密钥，撤销一个不影响其他接入端，无须重启服务。任何有效密钥均可访问全部25个工具和整个共享工作台，尚无只读/管理员角色区分。

密钥只控制HTTP `/mcp` 入口；网页与 `/api` 仍无账号认证，必须置于可信网络或另加网关访问控制。身份Elias、工具Codex、模型GPT-6.1 Sol仍是创建信息声明，不由接入密钥自动推导或验证。stdio属于本机进程调用，依靠本机系统权限，没有此Bearer认证。

这是私有接入的静态Bearer方案，不是OAuth授权服务器。客户端须支持Streamable HTTP和自定义Authorization请求头；只支持OAuth登录的客户端暂不能直接接入。未声称已完成Claude Code、WorkBuddy、Codex、DeepSeek Harness四种客户端逐一验证。

## 第一次启动

首次服务启动生成 `runtime/mcp-access.json`（仅密钥SHA-256摘要与管理元数据）和 `runtime/mcp-client-default.json`（含默认密钥的私有客户端配置）。已有密钥文件不会覆盖，全部撤销后也不会自动补发。文件损坏须修复或恢复备份，不能降级免认证。

默认配置URL使用 `SHIXU_API_URL` 加 `/mcp`；service.py会按实际端口设置该变量。更换服务器地址或端口后，修改客户端配置中的URL；不要修改密钥。直接运行uvicorn且使用非8765端口时，须自行设置SHIXU_API_URL。

runtime不入Git或分发包。客户端配置含明文密钥，按密码保管；不要发到聊天、提交代码或截图分享。密钥摘要文件丢失会导致原密钥失效，应备份到受保护位置。服务按单进程运行，密钥管理命令串行执行。

## 给其他电脑或客户端发放密钥

在服务电脑的application目录执行，将地址换成其他电脑实际可访问的服务器地址：

```powershell
python scripts/mcp_access.py create --label "笔记本-Codex" --url "https://你的服务域名/mcp" --output runtime/clients/laptop-codex.json
python scripts/mcp_access.py list
python scripts/mcp_access.py revoke --id "list返回的密钥ID"
```

create只显示ID与配置文件路径，不向终端输出密钥。通过可信方式把私有配置交给相应客户端。支持 `mcpServers` 的客户端可参考该JSON；其他客户端将其中URL和Authorization分别填入对应字段。它是配置样例，具体注册格式以客户端实际支持为准。

密钥泄露或设备停用时撤销对应ID；后续请求立即拒绝，已经开始执行的请求不承诺中途取消。换钥先发新密钥并验证，再撤销旧密钥。原始密钥不能从摘要恢复，配置丢失时发新密钥并撤销旧的。

## 网络条件

1. 服务配置 `SHIXU_HOST=0.0.0.0`，把服务器的实际IP或域名加入 `SHIXU_ALLOWED_HOSTS`（逗号分隔，不加协议和端口）。修改后重启。
2. 其他电脑使用服务器IP或域名，不能使用127.0.0.1；端口默认8765，路径必须为/mcp。
3. 网络、防火墙或反向代理必须允许该入口到达。MCP与已有API共用端口，无需另开MCP端口。反向代理须保留正确Host和Authorization请求头。
4. 密钥不加密传输；跨不可信网络使用HTTPS反向代理或加密隧道。项目不会自动申请TLS证书、修改防火墙或配置公网转发。已有HTTP公网转发不因增加密钥而变成安全加密连接。

## 验证

```powershell
python scripts/service.py status
python examples/http_mcp_client.py --config runtime/mcp-client-default.json
```

默认示例只读：连接、发现25工具、读取系统状态和身份列表；不会修改业务记录。仅在隔离库加 `--write-demo` 才执行合成写入、幂等重放及回读。认证拒绝、分别撤销、重启保留和同启同停由tests/test_mcp_http.py及test_service_mcp.py验证。端口可达与本机协议通过不等于已完成另一台实体电脑验收。

原有stdio客户端配置继续用 `python scripts/configure_mcp.py --format json` 或 `--format toml`，对应示例为examples/mcp_client.py。
