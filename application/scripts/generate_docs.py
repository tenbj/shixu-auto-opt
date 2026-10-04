"""从实际 FastAPI 与 MCP 目录生成中文文档和逐操作合同。"""
import asyncio
import hashlib
import html
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['SHIXU_BACKEND'] = 'sqlite'
os.environ['SHIXU_DB'] = str(ROOT / 'runtime/docs-test.sqlite3')
from app.main import app
from mcp_server import server

MAPPING = dict(context='get_connection_context',identities='list_identities', identity_create='create_identity', identity_update='update_identity', health='get_system_status', workspace='get_workspace', issues='list_issues', issue='get_issue',
               issue_create='create_issue', issue_update='update_issue', issue_transition='transition_issue', issue_followup='add_followup',
               tasks='list_tasks', task='get_task', task_create='create_task', task_update='update_task', task_transition='transition_task',
               task_dependencies='set_task_dependencies', task_reorder='reorder_task', activity='list_activity', export='export_workspace', trash='list_trash', issue_delete='delete_issue', issue_restore='restore_issue', task_delete='delete_task', task_restore='restore_task')


def write_json(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    schema = app.openapi()
    tools = asyncio.run(server.list_tools())
    write_json('docs/openapi.json', schema)
    catalog = {'server': 'shixu', 'transport': 'streamable-http', 'transports': ['streamable-http', 'stdio'], 'authentication': 'HTTP OAuth/PAT bound to account; stdio SHIXU_MCP_TOKEN', 'command': 'python /absolute/path/application/mcp_server.py', 'url': 'https://shixu.eliasliu.cc/mcp',
               'instructions': server.instructions, 'tools': []}
    for tool in tools:
        entry = tool.model_dump(mode='json', by_alias=True)
        read = entry['annotations']['readOnlyHint']
        catalog['tools'].append(dict(name=tool.name, kind='read' if read else 'write', purpose=tool.description,
                                    when_to_use=tool.description, input=entry['inputSchema'], returns='见API响应；写入返回resource/data/revision',
                                    side_effect='无' if read else '经API写MySQL实体表并追加审计；具体关联状态变化见工具描述',
                                    order='先health，再list/get版本，再写入', error_handling='404检查ID；409重读；422修正输入；503不确认成功、同号重试', protocol=entry))
    write_json('docs/MCP工具目录.json', catalog)
    operations = []
    doc = ['# 拾序 API 中文说明', '', '版本 3.1.0 · 基地址 http://127.0.0.1:8765 · UTF-8 JSON。在线交互文档 `/docs`，机器Schema `/openapi.json`。', '',
           '## 账号认证', '', '登录注册和OAuth协议见账号与远程接入.md。网页用HttpOnly会话Cookie，写入附X-CSRF-Token；程序用Authorization: Bearer账号令牌。401表示需要登录，403表示CSRF或权限不足，跨账号资源返回404。owner不能由调用方指定。账号管理端点不使用业务revision/request_id；OAuth token使用表单格式。', '', '## 并发、幂等与错误', '',
           '所有业务写入携带 `request_id`（8–120字符，推荐UUID）、`expected_version`（当前账号revision）与可选 `actor`（审计标签，默认未指定）。请求体不接受未声明字段。每个写入是一个MySQL InnoDB事务；返回 `revision`、`resource` 和事务提交时的 `data`。失败不改变数据、审计或版本。', '',
           '同一request_id及完全相同内容重放返回原始成功响应；request_id相同但内容不同返回409。网络超时保持请求内容和编号重试。账号内版本是工作台版本，不是单个对象版本；任何对象写入都会递增。', '',
           '| HTTP | 含义 | 处理 |', '|---|---|---|', '| 200 | 成功或幂等重放 | 读取返回版本 |', '| 403 | 跨站写入被拒绝 | 从同源页面或本机程序调用 |', '| 404 | 对象不存在 | 重新列表定位 |', '| 409 | 版本/状态/request_id冲突 | 重读，再决定新操作 |', '| 422 | 参数、依赖、证据或业务条件错误 | 修正后用新编号提交 |', '| 503 | 数据库不可用 | 不确认成功，恢复后同号重试 |', '',
           '列表返回 `{revision,items}`；详情返回 `{revision,item}`，问题详情另含关联tasks；完整工作台与导出返回 `{revision,data}`；审计返回 `{items}`。响应均不缓存。', '',
           '## 业务流转约束', '',
           '新问题只需标题，默认待梳理。triage填写nextStep和successCriteria进入待处理；start进入处理中；verify必须填写successCriteria、treatment、verificationMethod且必要行动均完成/取消；resolve只能从待验证进入，必须填resolution依据。零关联行动问题可直接提交观察验证。', '',
           'pause要求reason和不早于Asia/Shanghai今天的reviewDate；resume恢复原阶段。close-issue要求closeType/reason，有未完成行动时必须传taskPolicy；重复问题要求duplicateOf。reopen/reject/retriage要求reason。取消行动必须填写reason；依赖仅限同组且不能循环，取消前置行动不视为完成。', '',
           '行动编号由服务端分配，排序不改变编号或依赖；改变关联会在新组分配新编号，不复用旧号。新增/重开必要行动可使待验证或已解决问题回到处理中。', '',
           '## 接口目录', '']
    mapping = ['# 原型需求与系统能力映射', '', '原型五视图复用到 static/index.html；页面使用下表 API，MCP 经 HTTP 复用相同业务规则。', '', '| 页面/业务操作 | API | MCP | Python示例 |', '|---|---|---|---|']
    for route in app.routes:
        if not getattr(route, 'path', '').startswith(('/api/','/oauth/','/.well-known/','/connect','/downloads/')):
            continue
        for method in sorted(route.methods):
            if method not in ['GET', 'POST', 'PATCH']:
                continue
            if route.path not in schema['paths']:
                continue
            op = dict(id=route.name, method=method, path=route.path, mcp_tool=MAPPING.get(route.name), python_example='examples/creator_client.py' if route.name in ['identities','identity_create','identity_update'] else 'examples/api_client.py')
            operations.append(op)
            definition = schema['paths'][route.path][method.lower()]
            doc += ['### ' + method + ' ' + route.path, '', definition.get('summary', route.name) + '。MCP：`' + (MAPPING.get(route.name) or '账号或公开引导，不暴露为MCP工具') + '`。', '']
            params = definition.get('parameters', [])
            if params:
                doc += ['参数：' + '；'.join('`'+p['name']+'`（'+p['in']+'）' for p in params) + '。', '']
            request = definition.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
            if '$ref' in request:
                name = request['$ref'].rsplit('/', 1)[1]
                model = schema['components']['schemas'][name]
                doc += ['请求体：`'+name+'`；必填：'+', '.join(model.get('required', []))+'。', '', '| 字段 | 约束/默认 |', '|---|---|']
                for key, prop in model['properties'].items():
                    doc += ['| `'+key+'` | '+json.dumps({k:v for k,v in prop.items() if k!='title'}, ensure_ascii=False).replace('|','\\|')+' |']
                doc += ['', '写入返回 `{revision,resource,data}`。参数与响应详见 OpenAPI。', '']
            mapping.append('| '+definition.get('summary', route.name)+' | `'+method+' '+route.path+'` | `'+(MAPPING.get(route.name) or '账号管理')+'` | `examples/api_client.py` |')
    doc += ['## 通用记录身份与创建快照', '',
            '身份保存在服务端identityProfiles；GET/POST/PATCH /api/identities 查询、新增、编辑。kind=person时via必须manual且模型为空；kind=agent时via为claude_code/workbuddy/codex/deepseek_harness，模型可选。kind不可修改；名字或默认模型变更仅影响新记录。', '',
            '创建问题/行动可带creation={identityId,initiatedByPersonId,modelInfo:{name,provider}}。identityId是实际提交身份；initiatedByPersonId仅允许AI代录时指向人。modelInfo省略或null使用身份默认值；空对象清空模型（显示模型未提供），每次调用可显式覆盖。工具不能推导模型。手动创建不能携带模型或发起者。', '',
            '服务端输出createdByActorId、initiatedByPersonId、creatorName、createdVia、createdAt和modelInfo。creatorName取人类发起者或提交者当时名称；createdAt由服务器生成UTC。Elias委托Codex时显示Elias 经 Codex 创建 · GPT-6.1 Sol。这是请求声明的来源快照，并非认证或运行模型自动探测。', '',
            '普通PATCH不接受创建字段。改名、编辑内容、删除恢复不会修改创建快照。关联行动使用本次提交身份，不继承所属问题。兼容旧客户端不传creation时来源unknown，创建时间仍为服务器时间；迁移历史记录的时间保持NULL，不猜测。', '',
            '问题/行动列表支持creator（人类发起者优先，否则实际提交者ID；unknown筛选历史未知）、created_via和model（模型名称不区分大小写子串）组合筛选。返回及导出包含快照、身份列表；当前选中身份ID只保存于该浏览器。', '',
            'identity_profiles与问题/行动的身份ID为历史逻辑引用，由领域层创建时校验，不定义物理外键；独立保存名称、来源与model_info JSON，避免默认配置变化污染历史。', '']
    doc += ['## AI快速接入与授权续期', '', '公开入口 /connect、/connect.md、/connect/manifest.json 和 /downloads/{filename} 提供无凭据引导与固定版本Skill。三Tab分别处理快速接入、设备证据和手动配置。get_connection_context读取当前账号与scope，HTTP直接调用不能生成MCP验证标志。', '', 'OAuth接受read、write或空格分隔集合，兼容write包含read。刷新令牌绑定客户端与resource，最长30天；每次刷新轮换，旧刷新令牌重放撤销同access_id授权族。PAT有效期1年。撤销即时阻止访问与刷新。设备最近访问不等于在线，runtime与Skill版本为客户端声明。具体请求体和返回见OpenAPI、docs/AI快速接入.md。', '']
    doc += ['## MCP访问认证', '', 'HTTP MCP随服务启动于 /mcp，需要 Authorization: Bearer 访问密钥；无效密钥返回401。stdio仍为本机子进程。密钥按接入端分发、逐次校验、可分别撤销，详见 MCP远程接入.md。网页/API使用会话或账号访问令牌；每个账号独立工作台。Cookie写入需要CSRF，令牌按read/write范围校验。creation仍是调用方声明。', '']
    doc += ['## 示例与边界' , '', '只读：`python examples/api_client.py`。合成写入：加 `--write-demo`。浏览器示例：服务运行后访问 `/examples/`。', '',
            '本版为账号隔离工作台，支持显式配置0.0.0.0监听与内网Host允许列表；actor不是身份认证。正式存储为用户配置的MySQL专属新库，实体分表保存；SQLite仅用于隔离测试。提供回收站软删除与恢复，依赖关系移除也是软删除，数据库19表DELETE触发器与运行时SQL防护阻止物理删除。提供登录注册、会话管理、OAuth与访问令牌；没有永久删除、导入或离线跨设备同步API。完整工作台/导出包含回收站，普通列表和详情仅限有效记录。恢复必要行动可重开验证，删除问题/恢复问题均原子处理同批关联行动。审计分页使用after=最后一条revision继续查询。完整备份使用MySQL专属库备份，页面JSON不含幂等表。']
    text = '\n'.join(doc) + '\n'
    (ROOT / 'docs/API中文说明.md').write_text(text, encoding='utf-8')
    (ROOT / 'docs/API中文说明.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>拾序API中文说明</title><style>body{max-width:1100px;margin:32px auto;padding:20px;background:#f6f8f2;color:#214636}pre{white-space:pre-wrap;font:15px/1.8 system-ui;overflow-wrap:anywhere}</style><h1>拾序 API 中文说明</h1><pre>'+html.escape(text)+'</pre></html>', encoding='utf-8')
    mapping += ['', '所有业务删除均为软删除；依赖移除保留原行并标记deleted_at。19表DELETE触发器和运行时SQL防护禁止物理删除。', '', '数据层：MySQL issues/tasks/task_dependencies/issue_followups/issue_history/issue_logs保存实体；workspace_meta保存版本与编号；activity/idempotency_requests保存审计与幂等。所有业务修改在同一InnoDB事务提交，行锁保护账号内版本。', '',
                '未实现原型记录自动导入，源HTML与其localStorage均未改动。所有可写入口由后端规则校验，旧原型脚本不具有写库权限。', '',
                '验证分别见 verification/api-report.json、browser-report.json、mcp-report.json、persistence-report.json；AI自主任务未验收。']
    (ROOT / 'docs/需求与能力映射.md').write_text('\n'.join(mapping)+'\n', encoding='utf-8')
    contract = json.loads((ROOT / 'project-contract.json').read_text(encoding='utf-8'))
    # Application docs validate their frozen design input, independently of newer prototypes.
    source = ROOT / 'reference' / 'accounts-source.html'
    if source.exists():
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != contract['prototype'].get('snapshot_sha256',contract['prototype']['sha256']):
            raise RuntimeError('源原型hash变化，停止生成合同')
    contract['prototype']['path'] = '../prototype-accounts/prototype.html（原始源；分发快照已脱敏）'
    contract['prototype']['source_modified'] = False
    contract['version']='3.1.0'
    contract['operations'] = operations
    checks = {'business':'api-report.json', 'api':'api-report.json', 'mcp':'mcp-report.json', 'http_mcp':'http-mcp-report.json', 'browser':'browser-report.json', 'persistence':'persistence-report.json', 'portable':'portable-report.json', 'release_scan':'release-scan.json', 'trash_browser':'trash-browser-report.json', 'diagrams':'diagrams/report.json', 'architecture':'diagrams/architecture-report.json', 'erd':'diagrams/erd-report.json', 'creators':'creator-browser-report.json', 'accounts':'account-browser-report.json', 'account_mcp':'account-mcp-report.json', 'dual_transport':'dual-transport-report.json', 'public_http':'public-http-report.json', 'f02':'f02-report.json', 'onboarding':'onboarding-report.json'}
    contract['checks'] = []
    for name, file in checks.items():
        path = ROOT / 'verification' / file
        passed = path.exists() and json.loads(path.read_text(encoding='utf-8')).get('delivery_id')==contract['delivery_id'] and json.loads(path.read_text(encoding='utf-8')).get('passed', json.loads(path.read_text(encoding='utf-8')).get('status') == 'pass') is True
        contract['checks'].append(dict(name=name, status='passed' if passed else 'not_run', evidence='verification/'+file if path.exists() else ''))
    contract['checks'].append(dict(name='ai_task', status='not_run', evidence='', reason='已完成固定SDK序列，不等同于AI自主选择工具验收'))
    contract['storage'] = {'production':'mysql-entity-tables', 'schema':'data/mysql-schema.sql', 'tables':19, 'test_adapter':'SQLite仅用于隔离测试与无凭据分发包检查'}
    mysql_report = ROOT / 'verification/mysql-report.json'
    if mysql_report.exists():
        contract['checks'].append(dict(name='mysql', status='passed' if json.loads(mysql_report.read_text(encoding='utf-8')).get('passed') and json.loads(mysql_report.read_text(encoding='utf-8')).get('delivery_id')==contract['delivery_id'] else 'not_run', evidence='verification/mysql-report.json'))
    contract['limits'] = ['HTTP兼容开关支持网页登录和PAT/API/MCP；标准远程OAuth仍要求HTTPS。HTTPS优先入口shixu.eliasliu.cc，HTTP明文兼容入口保留',
        'OAuth动态注册与S256 PKCE、read/write集合兼容；访问令牌1小时、刷新轮换最长30天，重放/撤销使授权整组失效；PAT1年',
        '当前MySQL连接未启用TLS；凭据仅从私有环境读取',
        'Windows/Python3.11服务端与SDK验收；干净实体电脑及全部runtime实机、AI自主安装任务未验收，支持矩阵不得冒充验证通过',
        '账号归属在应用事务校验，ER仅展示数据库真实物理外键，owner_id为逻辑关联',
        '未选择开放许可证；脱敏源快照使用独立hash，原始原型保持未修改']
    retention = ROOT / 'verification/retention-report.json'
    contract['checks'].append(dict(name='retention_mysql',status='passed' if retention.exists() and json.loads(retention.read_text(encoding='utf-8')).get('passed') and json.loads(retention.read_text(encoding='utf-8')).get('delivery_id')==contract['delivery_id'] else 'not_run',evidence='verification/retention-report.json' if retention.exists() else ''))
    contract['status'] = 'ready' if all(c['status']=='passed' for c in contract['checks'] if c['name']!='ai_task') else 'draft'
    contract.pop('next_action', None)
    write_json('project-contract.json', contract)
    print('Generated OpenAPI, 26-tool catalog, Chinese docs and contract: '+contract['status'])


if __name__ == '__main__':
    main()
