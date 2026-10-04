from pathlib import Path
import json
import sys
root=Path('prototype-accounts'); source=Path('prototype/prototype.html').read_text(encoding='utf-8')
pre="""const ACCOUNT_KEY='shixu-account-preview-v1',SESSION_KEY=ACCOUNT_KEY+'-session',WORKSPACE_KEY=ACCOUNT_KEY+'-workspace:';
let accountModel;try{accountModel=JSON.parse(localStorage.getItem(ACCOUNT_KEY)||'null')}catch{}
if(!accountModel||!Array.isArray(accountModel.users))accountModel={version:1,users:[{id:'test',username:'test',displayName:'test',password:'1234',connections:[]}]};
for(const u of accountModel.users)if(!Array.isArray(u.connections))u.connections=[];
let signedInId=sessionStorage.getItem(SESSION_KEY);if(!accountModel.users.some(x=>x.id===signedInId))signedInId=null;
let lastPreviewConfig=null;
try{const target=WORKSPACE_KEY+'test',legacy='shixu-creator-prototype-v2';if(!localStorage.getItem(target)&&localStorage.getItem(legacy))localStorage.setItem(target,localStorage.getItem(legacy));if(!localStorage.getItem(target+'-profiles')&&localStorage.getItem(legacy+'-profiles'))localStorage.setItem(target+'-profiles',localStorage.getItem(legacy+'-profiles'));localStorage.setItem(ACCOUNT_KEY,JSON.stringify(accountModel))}catch{}
let KEY=WORKSPACE_KEY+(signedInId||'test');
"""
source=source.replace("const KEY='shixu-creator-prototype-v2',$=",pre+"const $=",1)
source=source.replace("db=normalizeData(saved?JSON.parse(saved):structuredClone(seed))", "db=normalizeData(saved?JSON.parse(saved):(KEY===WORKSPACE_KEY+'test'?structuredClone(seed):{version:1,issues:[],tasks:[]}))",1)
source=source.replace("review:'复盘记录'},icons=", "review:'复盘记录',settings:'账号设置',connections:'MCP接入'},icons=",1)
source=source.replace("review:'↺'};", "review:'↺',settings:'⚙',connections:'↗'};",1)
source=source.replace("function render(){\n renderDesktop();", "function render(){\n if(!accountNow()){showLogin();return;}\n renderDesktop();",1)
source=source.replace("document.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')", "document.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')",1)
# Render all common workspace widgets first, then add account chrome and account views.
marker="\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')"
assert marker in source
source=source.replace(marker,"\n renderAccountChrome();\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')",1)
source=source.replace("// MOBILE-DESIGN-END",(root/'scripts/accounts-layer.js').read_text(encoding='utf-8-sig')+'\n'+(root/'scripts/ai-access.js').read_text(encoding='utf-8-sig')+"\n// MOBILE-DESIGN-END",1)
source=source.replace('</style>',(root/'scripts/accounts-style.css').read_text(encoding='utf-8-sig')+'\n'+(root/'scripts/ai-access.css').read_text(encoding='utf-8-sig')+'\n</style>',1)
source=source.replace('交互原型 · 初始内容为演示数据，可自由编辑。','账号与授权交互原型 · 独立工作台体验，未连接真实服务。')
# Restoring a session must also restore that account's profile configuration.
source=source.replace('if(numberingMigrated&&!storageBlocked)save();\nrender();', 'if(signedInId)loadAccountWorkspace(accountNow());\nelse if(numberingMigrated&&!storageBlocked)save();\nrender();')
(root/'prototype.html').write_text(source,encoding='utf-8')
if '--legacy-contracts' not in sys.argv:
 print('Account + AI connection preview HTML generated')
 sys.exit(0)
u=json.loads(Path('prototype/ui.schema.json').read_text(encoding='utf-8'));u['version']='1.7.0'
u['page']['states']+=['signed_out','registering','account_settings','access_management','authorizing','access_issued','access_revoked']
u['page']['views'] += [{'id':'settings','title':'账号设置'},{'id':'connections','title':'MCP接入'}]
u['components'].append({'id':'account-control','type':'account-and-access-control','selector':'[data-event-id="EVT-ACCOUNT"]','events':['EVT-ACCOUNT'],'states':['signed_out','registering','ready','account_settings','access_management','authorizing','access_issued','access_revoked','error'],'requirement_ids':['REQ-018','REQ-019','REQ-020','REQ-021']})
login=[{'action':'fill','selector':'#account-auth [name="username"]','value':'test'},{'action':'fill','selector':'#account-auth [name="password"]','value':'1234'},{'action':'click','selector':'#account-auth button[type="submit"]'}]
def step(action,selector,value=None):
 d={'action':action,'selector':selector}
 if value is not None:d['value']=value
 return d
u['responsive']['scenarios']=[
 {'id':'account-login-error-success','requirement_ids':['REQ-018','REQ-019'],'steps':[step('fill','#account-auth [name="password"]','wrong'),step('click','#account-auth button[type="submit"]'),step('expect_text','#account-auth-error','账号或密码不正确')]+login+[step('expect_visible','#mobile-identity:visible [data-account-action="toggle-menu"],#account-menu:visible [data-account-action="toggle-menu"]'),step('click','nav:visible [data-action="nav"][data-id="issues"]'),step('expect_text','#app','重复复制粘贴')]},
 {'id':'workspace-create','requirement_ids':['REQ-001','REQ-019','REQ-017'],'steps':login+[step('click','nav:visible [data-action="nav"][data-id="issues"]'),step('click','#app .pagehead>.primary'),step('fill','#modal[open] [name="title"]','账号独立的问题'),step('click','#modal[open] button[type="submit"]'),step('expect_text','#app','账号独立的问题')]},
 {'id':'access-issue-revoke','requirement_ids':['REQ-020'],'steps':login+[step('click','#mobile-identity:visible [data-account-action="toggle-menu"],#account-menu:visible [data-account-action="toggle-menu"]'),step('click','#account-dropdown [data-account-action="connections"]'),step('click','#account-app [role="tab"][data-id="server"]'),step('click','#account-app [data-account-action="new-access"]'),step('fill','#modal[open] [name="name"]','自动化服务器'),step('select','#modal[open] [name="scope"]','read'),step('click','#modal[open] button[type="submit"]'),step('expect_text','#issued-config','DEMO_'),step('click','#modal[open] .modal-actions [data-action="close"]'),step('expect_text','#account-app','自动化服务器'),step('click','#account-app [data-account-action="revoke-access"]'),step('click','#modal[open] [data-account-action="confirm-revoke"]'),step('expect_text','#account-app','已撤销')]},
 {'id':'oauth-scope-consent','requirement_ids':['REQ-021','REQ-019'],'steps':login+[step('click','#mobile-identity:visible [data-account-action="toggle-menu"],#account-menu:visible [data-account-action="toggle-menu"]'),step('click','#account-dropdown [data-account-action="connections"]'),step('click','#account-app [data-account-action="account-tab"][data-id="client"]'),step('click','#account-app [data-account-action="oauth-preview"]'),step('expect_text','#modal[open]','Codex 请求访问拾序'),step('expect_text','#modal[open] .scope-card','test'),step('select','#modal[open] [name="scope"]','read'),step('click','#modal[open] button[type="submit"]'),step('expect_text','#account-app','登录授权')]},
 {'id':'new-account-empty','requirement_ids':['REQ-018','REQ-019'],'steps':[step('click','#account-auth [data-account-action="register-mode"]'),step('fill','#account-auth [name="username"]','reader'),step('fill','#account-auth [name="displayName"]','新用户'),step('fill','#account-auth [name="password"]','preview-pass'),step('fill','#account-auth [name="confirm"]','preview-pass'),step('click','#account-auth button[type="submit"]'),step('click','nav:visible [data-action="nav"][data-id="issues"]'),step('expect_text','#app','这里还没有匹配的问题')]}
]
u['responsive']['layouts']={'desktop':'登录左右分区；工作台侧栏；账号/MCP双栏卡片','mobile':'单列登录；五项底部导航；账号头部入口；接入卡片单列与全屏表单'}
(root/'ui.schema.json').write_text(json.dumps(u,ensure_ascii=False,indent=2),encoding='utf-8')
i=json.loads(Path('prototype/interaction.json').read_text(encoding='utf-8'));i['version']='1.7.0'
i['interactions'].append({'id':'EVT-ACCOUNT','component_id':'account-control','trigger':'click/input/change/submit','from_state':'signed_out','to_state':'ready','action':'登录/注册；账号切换只加载对应工作台；设置、令牌生成/复制下载/撤销、登录授权确认与拒绝','requirement_ids':['REQ-018','REQ-019','REQ-020','REQ-021'],'api_paths':['/auth/login','/auth/register','/auth/logout','/account','/account/password','/account/mcp-access','/account/mcp-access/{access_id}/revoke','/oauth/authorize']})
(root/'interaction.json').write_text(json.dumps(i,ensure_ascii=False,indent=2),encoding='utf-8')
m=json.loads(Path('prototype/manifest.json').read_text(encoding='utf-8'));m['version']='1.7.0';m['intent']='账号密码登录、各账号独立工作台及MCP接入与授权管理';m['input']['intent']=m['intent'];m['input']['constraints']=['原型离线运行，不连接生产API','账号之间无成员共享、无工作台切换或授权他人工作台','现有记录归test账号，按用户指定初始凭据体验'];m['input']['assumptions']=['原型模拟账号及OAuth，真实认证与租户隔离在系统阶段实现','现有原型localStorage只读复制给test，原键保留','演示令牌不能连接真实服务，HTTPS地址是后续部署设计']
reqs=[('REQ-018','账号密码登录、注册、退出与资料密码设置',['错误登录保留输入且显示提示','test使用指定初始凭据进入','新账号初始无数据']),('REQ-019','账号拥有独立工作台，数据不互通',['test保留现有记录与来源快照','新账号看不到test问题、行动、身份及接入','切换登录不继承筛选或打开的详情']),('REQ-020','通过网页发放独立MCP访问令牌',['命名、选择只读/读写、复制/下载配置','接入强绑定当前账号','令牌一次性显示，可撤销且保留其他接入']),('REQ-021','个人客户端登录授权交互',['显示客户端、当前账号和作用范围','允许、拒绝和切换登录可操作','授权不涉及其他账号数据'])]
for id,statement,criteria in reqs:m['input']['requirements'].append({'id':id,'statement':statement,'acceptance_criteria':criteria})
m['runtime']='offline account isolation and authorization interaction preview';m['limitations']=['本地账号/密码模拟，不具备真实安全认证','OAuth与令牌为交互预览，不能访问真实MCP','生产数据和API尚未迁移到账号模型','未真机验证iOS或软键盘'];
(root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
print('Account preview HTML and machine contracts generated')
