from pathlib import Path
import json,yaml
root=Path('prototype-accounts')
manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
manifest['skill']='H01_原型设计'
manifest['artifacts']=[{'id':id,'path':p,'layer':layer} for id,p,layer in [('prd','prd.md','human'),('prototype','prototype.html','human'),('ui','ui.schema.json','machine'),('interaction','interaction.json','machine'),('flow','user-flow.md','human'),('api','api.yaml','machine'),('database','database.sql','machine'),('evaluation','evaluation/report.json','evaluation'),('responsive','evaluation/responsive-report.json','evaluation')]]
for r in manifest['input']['requirements']:
 if r['id']=='REQ-010':r['acceptance_criteria']=['原型旧键只读复制给test，原键保留不覆盖','新账号使用独立存储键','创建信息与内容保留']
 if r['id']=='REQ-017':r['acceptance_criteria']=[x.replace('默认Codex','默认当前登录账号') for x in r['acceptance_criteria']]
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
prd='''# 拾序账号与MCP接入原型

版本1.7.0，2026-10-03。基于现有业务原型新增账号交互，不修改当前正式应用。

## 已确定的产品规则

- 每个账号只有自己的工作台；问题、行动、身份配置、统计、接入及授权均不互通，无家庭共享和成员角色。
- 现有数据归test账号，初始密码1234（用户指定）。原型保留旧原型存储，首次只读复制给test；无旧记录时沿用原型演示内容。真实系统现有MySQL数据的归属变更在原型确认后迁移，本轮不读写生产数据。
- 注册的新账号工作台为空。登录错误不进入工作台，退出关闭详情/配置弹窗、清除当前会话，刷新恢复当前账号。
- 人类账号决定数据归属；记录身份、AI工具和模型快照仍是独立字段。已有Codex/模型创建快照不会被迁移归属改写。
- 无“超管看所有人数据”入口。MCP登录授权及令牌只能访问登录账号工作台，不支持任意ownerId切换。
- 网页可生成接入配置、选择只读/读写、复制/下载及撤销；配置仅生成时显示。手机与桌面共用逻辑。
- 个人AI客户端提供登录/授权确认预览；自动化服务器使用独立令牌。授权可拒绝、允许或切换登录账号。

## 完成标准与需求追踪

'''
for req in manifest['input']['requirements']:
 prd+='### '+req['id']+' '+req['statement']+'\n\n'+'\n'.join('- '+x for x in req['acceptance_criteria'])+'\n\n'
prd+='''## 假设与边界

账号、密码、令牌与OAuth是离线浏览器模拟，仅供交互评审。演示密码保存在原型本地状态，不能用作生产认证实现。DEMO令牌不可访问真实MCP。HTTPS URL是待落地部署配置；未新增真实OAuth端点、角色权限或账号库。正式服务必须在每一个API/MCP请求校验账号归属，关联/依赖/日志/导出/幂等/身份列表与编号均按工作台隔离；不能依靠前端过滤或只检查列表。密码存哈希、会话保存在受保护Cookie，公网使用HTTPS。

维持原有业务状态与编号、依赖、创建快照、手机导航、桌面布局。迁移不得把创建人改写成test，也不复制已有全局密钥作为所有账号可用密钥；旧全局MCP凭据需停用或明确归属test，不能跨账号绕过隔离。原型不具有真实安全隔离，生产迁移尚未执行。
'''
(root/'prd.md').write_text(prd,encoding='utf-8')
(root/'user-flow.md').write_text('''# 用户流程

START → 登录页 → [账号密码错误：保留表单/提示] → [test：现有工作台；注册：独立空工作台] → 今日/问题/行动/统计/复盘 → END。

START → 当前账号 → 账号设置 → 修改显示名称/密码 → [校验失败保留输入] → 保存 → END。

START → MCP接入 → 服务器令牌 → 输入名称/访问范围 → 生成 → 仅当前账号配置 → 复制/下载 → 已授权列表 → 撤销确认 → 后续访问失效（原型模拟）→ END。

START → AI客户端请求授权 → 登录 → 显示客户端、账号、范围 → [拒绝：不创建接入] / [切换账号：重新登录后再次确认] / [允许：仅当前账号授权] → END。

START → test工作台 → 退出 → 注册/登录另一账号 → 不能看到test记录、身份或接入 → 退出 → 登录test → 原有数据仍在 → END。

问题/行动业务流程继承既有七状态、必要行动、验证依据、依赖防环与创建快照规则。本轮原型不连接正式系统。
''',encoding='utf-8')
api=yaml.safe_load(Path('prototype/api.yaml').read_text(encoding='utf-8'))
api['info'].update(version='1.7.0',description='多账号独立工作台的后续工程合同；当前原型离线，不是已部署API。每个业务操作按认证账号隔离。')
api['components'].setdefault('securitySchemes',{}).update(session={'type':'apiKey','in':'cookie','name':'shixu_session'},mcpBearer={'type':'http','scheme':'bearer'})
api['security']=[{'session':[]}]
for path,item in api['paths'].items():
 for method,op in item.items():
  if method in ['get','post','patch','put','delete'] and isinstance(op,dict):
   op['x-workspace-scope']='authenticated-account; never trust request-supplied owner'
   op.setdefault('responses',{}).update({'401':{'description':'未登录或会话失效'},'404':{'description':'对象不存在或不属于本账号'}})
newops=[('/auth/login','post','登录账号'),('/auth/register','post','注册独立账号与空工作台'),('/auth/logout','post','注销当前会话'),('/account','get','读取当前账号'),('/account','patch','修改显示名称'),('/account/password','post','校验原密码并修改密码'),('/account/mcp-access','get','列出本账号接入'),('/account/mcp-access','post','创建本账号独立只读/读写令牌，仅一次返回秘密'),('/account/mcp-access/{access_id}/revoke','post','撤销属于当前账号的接入'),('/oauth/authorize','get','经认证显示客户端与账号范围'),('/oauth/authorize','post','确认或拒绝授权，授权码绑定用户/客户端/重定向/PKCE'),('/oauth/token','post','按OAuth规范交换授权码/刷新令牌'),('/.well-known/oauth-protected-resource','get','MCP受保护资源发现'),('/.well-known/oauth-authorization-server','get','授权服务发现'),('/mcp','post','通过Bearer令牌调用本账号授权范围内工具')]
for path,method,summary in newops:
 op={'summary':summary,'responses':{'200':{'description':'成功'},'400':{'description':'输入或授权请求无效'},'401':{'description':'凭据失效'},'403':{'description':'未授权操作范围'}}}
 if '{access_id}' in path:op['parameters']=[{'name':'access_id','in':'path','required':True,'schema':{'type':'string'}}]
 if path in ['/auth/login','/auth/register','/oauth/token'] or path.startswith('/.well-known'):op['security']=[]
 if path=='/mcp':op['security']=[{'mcpBearer':[]}]
 if method=='post' and path!='/mcp':
  props={'/auth/login':{'username':{'type':'string'},'password':{'type':'string','writeOnly':True}},'/auth/register':{'username':{'type':'string'},'password':{'type':'string','writeOnly':True},'displayName':{'type':'string'}},'/account/mcp-access':{'name':{'type':'string','maxLength':60},'scope':{'type':'string','enum':['read','write']}}}.get(path)
  if props:op['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','properties':props,'additionalProperties':False}}}}
 api['paths'].setdefault(path,{})[method]=op
api['x-authorization-design']={'account-isolation':'all API, MCP, audit, export, identities, idempotency and counters scoped to authenticated user','oauth':'OAuth 2.1 discovery/PKCE; verify real clients; never accept arbitrary redirect','legacy':'Existing records assigned test; preserve snapshots; legacy global keys revoked or bound test; no unsecured bypass','csrf':'Authenticated cookie write endpoints require CSRF protection'}
(root/'api.yaml').write_text(yaml.safe_dump(api,allow_unicode=True,sort_keys=False),encoding='utf-8')
(root/'database.sql').write_text('''-- Multi-account SQLite reference design, NOT a production migration script.
-- Production migration must backup and preserve every existing MySQL record and creation snapshot.
-- Existing workspace assigned user test; user-specified initial password set through hashed provisioning.
PRAGMA foreign_keys=ON;
CREATE TABLE app_user(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE workspace(owner_id TEXT PRIMARY KEY REFERENCES app_user(id),revision INTEGER NOT NULL DEFAULT 0,next_issue_number INTEGER NOT NULL DEFAULT 1,next_task_numbers TEXT NOT NULL DEFAULT '{}');
CREATE TABLE identity_profile(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL,via TEXT NOT NULL,model_name TEXT,model_provider TEXT,PRIMARY KEY(owner_id,id));
CREATE TABLE issue(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,number INTEGER NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT '中',tag TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT '待梳理',workflow_json TEXT NOT NULL DEFAULT '{}',created_by_actor_id TEXT,initiated_by_person_id TEXT,creator_name TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_info TEXT,deleted_at TEXT,PRIMARY KEY(owner_id,id),UNIQUE(owner_id,number));
CREATE TABLE task(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,issue_id TEXT,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT '待办',due TEXT,required_action INTEGER NOT NULL DEFAULT 1,sequence_number INTEGER NOT NULL,number_group TEXT NOT NULL,created_by_actor_id TEXT,initiated_by_person_id TEXT,creator_name TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_info TEXT,deleted_at TEXT,PRIMARY KEY(owner_id,id),UNIQUE(owner_id,number_group,sequence_number),FOREIGN KEY(owner_id,issue_id) REFERENCES issue(owner_id,id));
CREATE TABLE task_dependency(owner_id TEXT NOT NULL,task_id TEXT NOT NULL,dependency_id TEXT NOT NULL,deleted_at TEXT,PRIMARY KEY(owner_id,task_id,dependency_id),FOREIGN KEY(owner_id,task_id) REFERENCES task(owner_id,id),FOREIGN KEY(owner_id,dependency_id) REFERENCES task(owner_id,id));
CREATE TABLE issue_event(owner_id TEXT NOT NULL,issue_id TEXT NOT NULL,id TEXT NOT NULL,event_kind TEXT NOT NULL,content_json TEXT NOT NULL,PRIMARY KEY(owner_id,id),FOREIGN KEY(owner_id,issue_id) REFERENCES issue(owner_id,id));
CREATE TABLE idempotency_request(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,response_json TEXT NOT NULL,PRIMARY KEY(owner_id,request_id));
CREATE TABLE activity(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),revision INTEGER NOT NULL,operation TEXT NOT NULL,resource_id TEXT,actor TEXT,created_at TEXT NOT NULL,PRIMARY KEY(owner_id,revision));
CREATE TABLE auth_session(id_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),expires_at TEXT NOT NULL,revoked_at TEXT);
CREATE TABLE mcp_access(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),label TEXT NOT NULL,method TEXT NOT NULL CHECK(method IN ('oauth','token')),scope TEXT NOT NULL CHECK(scope IN ('read','write')),secret_hash TEXT,client_id TEXT,created_at TEXT NOT NULL,expires_at TEXT,revoked_at TEXT);
CREATE TABLE oauth_authorization_code(code_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),client_id TEXT NOT NULL,redirect_uri TEXT NOT NULL,pkce_challenge TEXT NOT NULL,scope TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
-- Tenant scope from verified session/token, not submitted owner_id. Prevent cross-owner access for get/write/restore/export/audit/MCP.
-- Soft deletion remains mandatory for business records; no physical deletion operations are exposed.
''',encoding='utf-8')
(root/'README.md').write_text('''# 拾序独立账号与MCP接入原型 · 1.7.0

打开prototype.html。体验账号test，初始密码按用户指定为1234。可以注册任意新账号验证空工作台与隔离，再退出并登录test确认原记录保留。

新增：登录/注册/退出、显示名称/密码设置、网页MCP接入配置生成/复制/下载/撤销、客户端授权允许/拒绝及切换账号。桌面侧栏有账号设置和MCP接入；手机点击顶部账号进入设置，再管理接入。

旧原型保持在../prototype。新原型独立存储键shixu-account-preview-v1；如果同一来源已有旧原型记录，首次只读复制给test，旧键不覆盖。没有旧记录时使用既有虚构种子。账号、密码与OAuth仅本地交互模拟，不能代替生产认证；DEMO令牌不能调用真实服务。生产MySQL现有数据尚未迁移，未来全部归test且保留创建快照。

[需求](prd.md)、[流程](user-flow.md)、[接口](api.yaml)、[数据模型](database.sql)、[验证](evaluation/report.json)。手机和桌面检查见evaluation/responsive-report.json。本原型没有共享或跨账号授权。
''',encoding='utf-8')
print('PRD, flows, auth/API and tenant model completed')
