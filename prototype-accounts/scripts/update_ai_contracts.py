"""Apply the AI onboarding design delta to the existing account package."""
from pathlib import Path
import json
import yaml

root = Path(__file__).resolve().parents[1]
def read(name): return json.loads((root/name).read_text(encoding='utf-8-sig'))
def write(name, obj): (root/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
reqs = [
 ('REQ-022','AI接入弹窗与公开引导入口',['右上账号卡片和工作台工具二级菜单保持','快速接入、已连接设备、手动配置三个Tab','登录前可查看接入说明，个人访问仍需授权','关闭保留业务上下文并返回焦点']),
 ('REQ-023','一段提示词接入与安装引导',['选择runtime、复制及展开完整提示词','提示词不含秘密，原型明确待发布','缺少AI工具可进入安装引导','不支持自动配置时提供手动路径']),
 ('REQ-024','接入演示、授权与可恢复结果',['准备、授权、验证、成功可操作','拒绝不创建接入，只读提示无法记录','失败重试、重载恢复不重复创建接入','配置、授权与验证成功分开显示，不写测试问题']),
 ('REQ-025','设备与适配配置管理',['列表显示权限、认证方式和最近验证，不伪称在线','支持空态、重命名和撤销','配置优先HTTPS，Codex TOML与通用JSON分开','演示令牌不可访问真实服务'])
]
m=read('manifest.json'); m['version']='1.8.0'
m['intent']='独立账号工作台与AI接入：复制提示词、客户端授权、Skill安装引导及设备管理的离线交互原型'
m['input']['intent']=m['intent']
m['input']['requirements']=[x for x in m['input']['requirements'] if x['id'] not in [r[0] for r in reqs]]
m['input']['requirements'] += [dict(id=i,statement=s,acceptance_criteria=c) for i,s,c in reqs]
m['input']['assumptions']=['保留账号原型既有演示账号及独立工作台','HTTPS MCP为既有正式入口，但本原型不访问它','公开接入指南、适配安装和自动续期属于待实施设计','runtime名字用于演示选择，不代表当前机器已安装或兼容已验收']
m['limitations']=['离线原型，不执行真实授权、安装、MCP连接或业务写入','示例提示词有原型标记，connect.md尚未上线','客户端安装按钮只演示指引，不下载软件','未验证真机、iOS或软键盘']
m['runtime']='self-contained offline AI onboarding preview'
write('manifest.json',m)
u=read('ui.schema.json');u['version']='1.8.0'
states=['connection_quick','connection_prepare','connection_consent','connection_denied','connection_verify','connection_reload','connection_error','connection_unsupported','connection_ready','connection_manual','connection_devices','connection_public']
u['page']['states']=list(dict.fromkeys(u['page']['states']+states))
for v in u['page'].get('views',[]):
 if v['id']=='connections': v['title']='AI接入'
u['components']=[x for x in u['components'] if x['id']!='ai-connect-control']
u['components'].append(dict(id='ai-connect-control',type='ai-onboarding',selector='[data-event-id="EVT-AI-CONNECT"]',events=['EVT-AI-CONNECT'],states=states,requirement_ids=[r[0] for r in reqs]))
def s(action,selector,value=None):
 d=dict(action=action,selector=selector)
 if value is not None:d['value']=value
 return d
login=[s('fill','#account-auth [name="username"]','test'),s('fill','#account-auth [name="password"]','1234'),s('click','#account-auth button[type="submit"]')]
entry=login+[s('click','[data-account-action="toggle-menu"]:visible'),s('click','#account-dropdown [data-account-action="connections"]')]
def a(action):return s('click',f'[data-ai-action="{action}"]:visible')
start=entry+[a('start-demo'),a('authorize')]
allow=s('click','#ai-consent-form button[type="submit"]')
u['responsive']['scenarios']=[x for x in u['responsive']['scenarios'] if x['id'] in ['account-login-error-success','workspace-create','new-account-empty']]
u['responsive']['scenarios'] += [
 dict(id='ai-quick-copy',requirement_ids=['REQ-022','REQ-023'],steps=entry+[s('select','#ai-runtime','workbuddy'),a('copy-prompt'),s('expect_text','#ai-prompt','WorkBuddy'),s('expect_text','#ai-prompt','待上线'),s('expect_text','#ai-prompt','不要让我把密码')]),
 dict(id='ai-authorize-verify-manage',requirement_ids=['REQ-024','REQ-025'],steps=start+[allow,a('verify'),s('expect_text','#account-tabpanel','已准备好'),a('devices'),s('click','.ai-device:last-of-type [data-ai-action="rename"]'),s('fill','#ai-rename-form [name="name"]','办公电脑'),s('click','#ai-rename-form button[type="submit"]'),s('expect_text','#account-tabpanel','办公电脑'),s('click','.ai-device:last-of-type [data-account-action="revoke-access"]'),s('click','[data-account-action="confirm-revoke"]:visible'),s('expect_text','#account-tabpanel','已撤销')]),
 dict(id='ai-deny-readonly',requirement_ids=['REQ-024'],steps=start+[a('deny'),s('expect_text','#account-tabpanel','没有新增设备'),a('authorize'),s('select','#ai-consent-form [name="scope"]','read'),allow,a('verify'),s('expect_text','#account-tabpanel','记录新问题需要重新确认读写权限')]),
 dict(id='ai-fail-retry',requirement_ids=['REQ-024'],steps=start+[allow,a('fail'),s('expect_text','#account-tabpanel','连接还没有验证成功'),a('verify'),s('expect_text','#account-tabpanel','已准备好')]),
 dict(id='ai-reload',requirement_ids=['REQ-024'],steps=start+[allow,a('reload'),s('expect_text','#account-tabpanel','配置无需重新填写'),a('verify'),s('expect_text','#account-tabpanel','已准备好')]),
 dict(id='ai-manual-token',requirement_ids=['REQ-023','REQ-025'],steps=entry+[a('start-demo'),a('unsupported'),a('manual'),s('select','#ai-config-runtime','codex'),s('click','[data-account-action="new-access"]:visible'),s('fill','#account-access-form [name="name"]','服务器配置'),s('click','#account-access-form button[type="submit"]'),s('expect_text','#issued-config','[mcp_servers.shixu]'),s('expect_text','#issued-config','https://shixu.eliasliu.cc/mcp'),s('expect_text','#issued-config','DEMO_')]),
 dict(id='ai-public-guide',requirement_ids=['REQ-022','REQ-023'],steps=[a('public-help'),s('expect_visible','#ai-runtime'),a('install-help'),s('click','[data-ai-action="choose-install"][data-id="workbuddy"]'),s('expect_text','#ai-install-detail','WorkBuddy')]),
]
u['responsive']['viewports']=[{'width':w,'height':h} for w,h in [(360,844),(390,844),(430,844),(537,884),(1440,1000)]]
u['responsive']['layouts']={'desktop':'账号卡片下拉与工作台工具二级菜单；AI接入居中弹窗、三Tab，主操作复制给AI','mobile':'账号卡片保持最右上；全屏接入弹窗、内部滚动、44px触达；底部业务导航不重复辅助入口'}
write('ui.schema.json',u)
i=read('interaction.json');i['version']='1.8.0'
i['interactions']=[x for x in i['interactions'] if x['id']!='EVT-AI-CONNECT']
i['interactions'].append(dict(id='EVT-AI-CONNECT',component_id='ai-connect-control',trigger='click/change/submit',from_state='connection_quick',to_state='connection_ready',action='复制预览提示词、公开安装指引、准备/同意/拒绝/只读、失败重试及重载恢复、管理演示设备；不连接正式服务',requirement_ids=[r[0] for r in reqs],api_paths=['/connect','/connect.md','/connect/manifest.json','/account/mcp-access','/oauth/authorize','/oauth/token','/mcp']))
write('interaction.json',i)
api=yaml.safe_load((root/'api.yaml').read_text(encoding='utf-8-sig'));api['info']['version']='1.8.0'
api['info']['description']='AI接入后续工程设计合同；当前HTML仅离线模拟，下述新增接入路径未上线。'
for path,summary in [('/connect','公开接入帮助页面'),('/connect.md','AI可读取的公开接入指南'),('/connect/manifest.json','版本化runtime适配和Skill下载清单')]:
 api['paths'][path]={'get':{'summary':summary,'security':[],'responses':{'200':{'description':'不含凭据的公开引导资料'},'503':{'description':'发布资料暂不可用，保留重试入口'}}}}
api['paths']['/account/mcp-access/{access_id}']={'patch':{'summary':'重命名本账号接入设备','parameters':[{'name':'access_id','in':'path','required':True,'schema':{'type':'string'}}],'requestBody':{'required':True,'content':{'application/json':{'schema':{'type':'object','required':['name'],'properties':{'name':{'type':'string','minLength':1,'maxLength':60}},'additionalProperties':False}}}},'responses':{'200':{'description':'已更新名称'},'401':{'description':'未登录'},'404':{'description':'设备不存在或非本账号'}}}}
api['x-ai-onboarding']={'status':'design-only','scope':'Parse standard space-separated scope sets; never broaden user consent','refresh':'Rotating refresh token, revoke authorization family; no implementation in this prototype','runtime':'Verify native tools and Skill in target client; a generated file is not a successful connection','secrets':'Public prompts/manifest/skill contain no credentials','preferred_mcp':'https://shixu.eliasliu.cc/mcp'}
(root/'api.yaml').write_text(yaml.safe_dump(api,allow_unicode=True,sort_keys=False),encoding='utf-8')
sql=root/'database.sql';text=sql.read_text(encoding='utf-8');marker='-- AI-ONBOARDING-DESIGN'
text=text.split(marker)[0].rstrip()+'''\n\n-- AI-ONBOARDING-DESIGN: reference only, NOT a production migration.
-- Existing mcp_access.label supports renaming; display last_seen as a timestamp, never online status.
CREATE TABLE mcp_device_observation(access_id TEXT PRIMARY KEY REFERENCES mcp_access(id),runtime_name TEXT,runtime_version TEXT,skill_version TEXT,last_seen_at TEXT,verification_state TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE oauth_refresh_token(token_hash TEXT PRIMARY KEY,access_id TEXT NOT NULL REFERENCES mcp_access(id),family_id TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT,revoked_at TEXT,replaced_by_hash TEXT);
-- Runtime/Skill observations are client-reported, not verified model-execution provenance.
-- Refresh reuse detection and family revocation must be transactional and account scoped.
''';sql.write_text(text,encoding='utf-8')
def append_section(filename,text):
 p=root/filename;old=p.read_text(encoding='utf-8');old=old.split('\n## AI接入原型 1.8.0')[0]
 p.write_text(old+'\n## AI接入原型 1.8.0\n\n'+text+'\n',encoding='utf-8')
append_section('prd.md','2026-10-04：本节为当前接入设计，早期迁移时态以当时记录为准。现有正式系统已具备独立账号与HTTPS；本轮仅更新原型。\n\n'+'\n\n'.join('### '+r[0]+' '+r[1]+'\n\n'+'\n'.join('- '+c for c in r[2]) for r in reqs)+'\n\n新增公共引导、Skill分发与自动续期仍待系统实施。原型不下载、不安装、不授权正式账号，不创建测试问题。所有设备结果都为本地模拟。关闭弹窗保留业务筛选；手机账号卡片保持右上方，更多功能留在二级菜单。')
append_section('user-flow.md','START → 登录前“连接AI”或账号下拉“AI接入” → 快速接入 → 选择runtime → 复制提示词 → AI准备配置 → 本人登录授权 → 验证 → END。\n\n演示分支：准备 → 无法自动配置 → 手动配置；授权 → 拒绝 → 重新授权；授权 → 只读 → 查询可用/记录需读写；验证 → 失败 → 原配置重试；验证 → 需重载 → 新会话恢复；成功 → 复制记录示例（不写入）。\n\nSTART → 已连接设备 → 重命名/撤销 → 更新列表 → END。\n\nSTART → 手动配置 → 选择格式 → 访问令牌 → 复制或下载DEMO配置 → END。Codex采用TOML预览，其他工具为通用JSON，真实兼容待各客户端验证。')
(root/'README.md').write_text('''# 拾序账号与AI接入原型 · 1.8.0

打开prototype.html，登录演示账号后从右上账号下拉进入AI接入。快速接入 / 已连接设备 / 手动配置使用Tab弹窗。登录前也可查看公开接入指引。

体验“复制给AI”与“体验接入流程”：允许/拒绝/只读、验证失败重试、重载恢复、成功后的记录示例、设备改名撤销、TOML/JSON演示配置。

所有授权、安装、验证及设备状态都是离线模拟；不访问正式服务，不创建真实问题，DEMO令牌无效。提示词中connect.md为待上线设计。账号卡片、二级工作台工具和业务界面保持。

在仓库根运行 scripts/generate_accounts.py 的正确路径为：
`python prototype-accounts/scripts/generate_accounts.py --html-only`
增量合同：`python prototype-accounts/scripts/update_ai_contracts.py`。
本次不要运行早期write_contracts.py覆盖增量设计。H01响应式与合同报告在evaluation内。
''',encoding='utf-8')
print('AI onboarding contracts 1.8.0 updated')
