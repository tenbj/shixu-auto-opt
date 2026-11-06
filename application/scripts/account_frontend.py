"""冻结原型账号界面接入真实API。"""
import re

# Shared by the inline bootstrap and the main script; no requests or workspace data.
EARLY_SHELL = '''<script id="early-shell">
function readLocalUser(){
 try{const u=JSON.parse(localStorage.getItem('shixu-local-user'));if(u&&typeof u.id==='string'&&u.id.trim()&&typeof u.displayName==='string'&&u.displayName.trim()&&Object.keys(u).every(k=>k==='id'||k==='displayName'))return u}catch{}
 try{localStorage.removeItem('shixu-local-user')}catch{}return null;
}
function resetShell(){
 const wb=document.querySelector('#workbench');delete wb.dataset.shellOwner;wb.dataset.fill='pending';wb.dataset.sync='confirming';
 document.querySelector('#app').innerHTML=document.querySelector('#shell-skeleton').innerHTML;
 document.querySelectorAll('#account-menu,#mobile-identity,#desktop-identity,.nav-label,.topbar>span,#modal-content,#modal-title').forEach(e=>e.replaceChildren());
 document.querySelectorAll('#account-dropdown,#account-modal,#child-modal').forEach(e=>e.remove());
 document.querySelectorAll('#nav span').forEach(e=>e.textContent='');document.querySelector('#storage-warning').classList.add('hidden');
}
function paintShell(user){
 const wb=document.querySelector('#workbench');if(wb.dataset.shellOwner===user.id&&!wb.hidden)return;
 resetShell();
 document.querySelectorAll('#account-menu,#mobile-identity').forEach(el=>{
  el.innerHTML='<button type="button" class="account-pill" data-event-id="EVT-ACCOUNT" data-account-action="toggle-menu" aria-haspopup="menu" aria-expanded="false"><span class="account-avatar"></span><span><b></b><small>独立工作台</small></span><span>⌄</span></button>';
  el.querySelector('.account-avatar').textContent=Array.from(user.displayName)[0];el.querySelector('b').textContent=user.displayName;el.querySelector('button').setAttribute('aria-label','账号菜单：'+user.displayName);
 });
 document.querySelector('.nav-label').textContent=user.displayName+' 的工作台';
 document.querySelector('.topbar>span').textContent=user.displayName+' 的工作台 / 今日概览';
 document.querySelectorAll('#sync-state,#mobile-sync-state').forEach(el=>el.textContent='同步中');
 document.querySelector('#account-auth')?.setAttribute('hidden','');document.body.classList.remove('account-logged-out');wb.hidden=false;wb.dataset.shellOwner=user.id;
}
{const user=readLocalUser();if(user)paintShell(user)}
</script>'''

def integrate(html,root):
    layer=(root/'reference/accounts-layer.js').read_text(encoding='utf-8')
    css=(root/'reference/accounts-style.css').read_text(encoding='utf-8')
    def cut(start,end,replacement=''):
        nonlocal layer
        a=layer.index(start);b=layer.index(end,a);layer=layer[:a]+replacement+'\n'+layer[b:]
    layer=layer.replace("function accountNow(){return accountModel.users.find(x=>x.id===signedInId)||null}","function accountNow(){return currentUser}")
    cut('function storeAccounts()', 'function accountButton(')
    cut('function loadAccountWorkspace(', 'function renderAccountChrome(){')
    layer=layer.replace("mode==='login'?'test':''","''")
    layer=re.sub(r'<div class="auth-demo">.*?</div></div></div>`;', '</div></div>`;',layer,count=1)
    layer=layer.replace('账号体验原型','拾序 · 独立工作台')
    layer=layer.replace('required minlength="4" autocomplete="new-password"','required minlength="8" autocomplete="new-password"')
    layer=layer.replace("if(a==='settings'||a==='connections'){closeAccountMenu();openAccountPanel(a)}", "if(a==='settings'||a==='connections'){closeAccountMenu();try{await openAccountPanel(a)}catch(e){toast(e.message)}}")
    layer=layer.replace("if(a==='switch-auth-account'){sessionStorage.setItem('shixu-preview-pending-auth',b.dataset.id);logoutAccount()}","if(a==='switch-auth-account')await logoutAccount();")
    layer=layer.replace("if(a==='reject-auth'){closeDialog();toast('已拒绝，此客户端没有获得访问权限')}","if(a==='reject-auth')await completeConsent(false);")
    cut(" if(a==='confirm-revoke')"," if(a==='copy-config'", " if(a==='confirm-revoke'){try{await request('/api/account/mcp-access/'+encodeURIComponent(b.dataset.id)+'/revoke',{method:'POST',body:'{}'});closeDialog();await openAccountPanel('connections');toast('接入已撤销')}catch(e){toast(e.message)}}")
    cut("document.addEventListener('submit',e=>{",'function closeAccountMenu()')
    cut('function showAuthorization(',"document.addEventListener('click',async")
    layer=layer.replace("url:'https://eliasliu.cc:11865/mcp'", "url:connection.url")
    layer=layer.replace('这是原型演示配置，DEMO令牌不能访问真实服务；HTTPS地址为待落地配置。','请妥善保管配置。令牌只显示一次，可随时撤销。')
    layer=layer.replace("'shixu-demo-'","'shixu-client-'").replace('演示配置已下载','配置已下载')
    layer=layer.replace('交互预览：授权与令牌仅为演示，未连接真实MCP服务。','接入仅能访问当前账号，权限由服务器校验。')
    layer=layer.replace('预览客户端授权','查看连接方法').replace('此处为授权流程预览。','')
    layer=layer.replace('new Date(x.createdAt)','new Date(x.createdAt*1000)')
    layer=layer.replace('function openAccountPanel(kind){',"async function openAccountPanel(kind){\n if(kind==='connections'){const result=await request('/api/account/mcp-access');currentUser.connections=result.items;currentUser.connection=result.connection;}")
    layer=layer.replace("${btn('状态流转说明','workflow-guide','','menu-item')}","${btn('刷新工作台','system-refresh','','menu-item')}${btn('状态流转说明','workflow-guide','','menu-item')}")
    layer=layer.replace("menu.querySelector('button').focus()","menu.querySelector('button').focus({preventScroll:true})")
    layer=layer.replace("${btn('查看统计分析','mobile-go-analysis','','menu-item')}","${btn('查看统计分析','mobile-go-analysis','','menu-item')}${btn('回收站','open-trash','','menu-item')}")
    layer=layer.replace("if(a==='close-account-panel')document.querySelector('#account-modal')?.close();", "if(a==='close-account-panel')closeAccountPanel();")
    layer=layer.replace("menu.querySelector('button').focus({preventScroll:true})", "menu.querySelector('button').focus({preventScroll:true})")
    layer=layer.replace("window.addEventListener('scroll',closeAccountMenu)","window.addEventListener('scroll',()=>{const menu=document.querySelector('#account-dropdown'),trigger=[...document.querySelectorAll('.account-pill')].find(x=>x.getBoundingClientRect().width>0);if(menu&&trigger){const r=trigger.getBoundingClientRect();if(r.bottom<0)closeAccountMenu();else menu.style.top=(r.bottom+8)+'px'}})")
    layer=layer.replace("function showLogin(mode='login',notice=''){\n closeAccountMenu();", "function showLogin(mode='login',notice=''){\n closeAccountMenu();\n"+" document.querySelectorAll('#account-menu,#mobile-identity').forEach(x=>{x.replaceChildren();delete x.dataset.accountControl});\n")
    # Keep account controls stable while background workspace responses render.
    layer=layer.replace("top.innerHTML=control;", "if(top.dataset.accountControl!==control){top.innerHTML=control;top.dataset.accountControl=control;closeAccountMenu()};")
    layer=layer.replace("document.querySelector('#mobile-identity').innerHTML=control;", "const mobileControl=document.querySelector('#mobile-identity');if(mobileControl.dataset.accountControl!==control){mobileControl.innerHTML=control;mobileControl.dataset.accountControl=control;closeAccountMenu()};")
    layer=layer.replace(";closeAccountMenu();document.querySelector('.nav-label')", ";document.querySelector('.nav-label')")
    chrome_start=layer.index('function renderAccountChrome(){');chrome_end=layer.index('function accountHead(',chrome_start)
    layer=layer[:chrome_start]+layer[chrome_start:chrome_end].replace("setAttribute('aria-expanded','false')","setAttribute('aria-expanded',String(!!document.querySelector('#account-dropdown')))")+layer[chrome_end:]
    layer=layer.replace('MCP 接入','AI 接入').replace('MCP接入','AI接入').replace('服务器令牌','访问令牌').replace("connections:'list'","connections:'quick'")
    layer=layer.replace('<div class="auth-switch">','<p><a class="auth-connect" href="/connect">连接 AI · 查看接入指引</a></p><div class="auth-switch">')
    css+='\na.auth-connect{color:#42684e;text-decoration:none}\na.auth-connect:hover{text-decoration:underline;text-underline-offset:4px}\n'
    css+='\n'+(root/'static/ai-access.css').read_text(encoding='utf-8')
    # 类名与冻结原型 v0.4.0 的 style 块一致；只追加 CSS，不改写 build 已生成的标记。
    css += '''
/* R4: 9 处内联样式 → 类（含视觉微调） */
.sidebar-meta{font-size:11px;line-height:1.7;margin-top:10px;color:#8a957f}
.crumb-sep{margin:0 10px;color:#bcc6b2;font-weight:300}
.sync-state{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);white-space:nowrap}
.sync-state::before{content:"";width:6px;height:6px;border-radius:50%;background:#91a985}
.issue-progress-text{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.note-motto{margin-top:20px;padding-top:14px;border-top:1px dashed #d3dcc6}
.list-issue-title{margin-top:10px;line-height:1.45}
.detail-title{margin-top:14px;line-height:1.4;overflow-wrap:anywhere}
.panelhead.panelhead-inline{padding:12px 0 8px;margin-top:6px;border-top:1px solid #e6ebdf}
.form-context{margin-bottom:18px;padding:10px 12px;border-radius:8px;background:#f3f6ee;color:#5c7053;font-size:13px;overflow-wrap:anywhere}
@media(max-width:700px){.sync-state{display:none}.form-context{font-size:14px}}
'''
    layer="let currentUser=null,csrfToken='',lastPreviewConfig=null;\n"+layer+'\n'+(root/'static/accounts-api.js').read_text(encoding='utf-8')+'\n'+(root/'static/ai-access-api.js').read_text(encoding='utf-8')
    # Keep the existing session checks/data loader, but hand off the already painted shell.
    layer=layer.replace('let currentUser=null,', 'let currentUser=readLocalUser(),')
    layer=layer.replace("if(!currentUser)try{const user=JSON.parse(localStorage.getItem(LOCAL_USER_KEY));if(typeof user?.id==='string'&&user.id&&typeof user.displayName==='string'){currentUser={id:user.id,displayName:user.displayName};cacheLocalUser(currentUser);render()}}catch{}", "if(!currentUser)currentUser=readLocalUser();if(!currentUser){accountBootRunning=false;showLogin();document.documentElement.dataset.accountBoot='complete';return}paintShell(currentUser);")
    layer=layer.replace("accountVersion++;loaded=false;", "accountVersion++;if(currentUser?.id!==result.user.id)resetShell();loaded=false;")
    layer=layer.replace("render();syncStatus('同步中');", "paintShell(user);renderAccountChrome();syncStatus('同步中');")
    layer=layer.replace("function clearLocalAccount(notice=''){", "function clearLocalAccount(notice='',forget=true){")
    layer=layer.replace("clearLocalAccount();", "clearLocalAccount('登录已过期，请重新登录');")
    layer=layer.replace("accountVersion++;cacheLocalUser(null);", "accountVersion++;accountBootRunning=false;if(forget)cacheLocalUser(null);resetShell();document.querySelector('#workbench').hidden=true;")
    layer=layer.replace("syncStatus('同步未完成')", "syncStatus('暂未同步');document.querySelector('#workbench').dataset.sync='warn'")
    layer=layer.replace("let accountBootRunning=false;", "let accountBootRunning=false,accountBootGeneration=0;\nwindow.addEventListener('storage',e=>{if(e.storageArea===localStorage&&(e.key===LOCAL_USER_KEY||e.key===null)){clearLocalAccount('登录已过期，请重新登录',false);if(readLocalUser())bootAccount()}});")
    layer=layer.replace("accountBootRunning=true;", "accountBootRunning=true;const generation=++accountBootGeneration;")
    layer=layer.replace("finally{accountBootRunning=false;document.documentElement.dataset.accountBoot='complete'}", "finally{if(generation===accountBootGeneration){accountBootRunning=false;document.documentElement.dataset.accountBoot='complete'}}")
    layer=layer.replace("typeof result.user.displayName!=='string'", "typeof result.user.id!=='string'||typeof result.user.displayName!=='string'")
    html=html.replace('\nloadWorkspace();\n','\nqueueMicrotask(bootAccount);\n',1)
    html=html.replace("document.querySelector('#mobile-identity').innerHTML=identitySwitch('mobile-identity');", "// Account chrome owns the mobile identity control and preserves its focus across renders.")
    html=html.replace('function render(){',"function render(){\n if(!currentUser){showLogin();return;}\n if(!loaded){paintShell(currentUser);return;}\n document.querySelector('#workbench').dataset.fill='ready';\n",1)
    marker="\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')"
    assert marker in html
    html=html.replace(marker,"\n renderAccountChrome();\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')",1)
    html=html.replace('// MOBILE-DESIGN-END',layer+'\n// MOBILE-DESIGN-END',1)
    html=html.replace("headers:{'Content-Type':'application/json',...options.headers}","headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken,...options.headers}")
    html=html.replace("const response=await fetch(route,", "const user=currentUser;\n const response=await fetch(route,")
    html=html.replace("const result=await response.json();if(!response.ok)", "if(response.status===401&&currentUser&&currentUser===user)clearLocalAccount('登录已过期，请重新登录');\n const result=await response.json();if(!response.ok)")
    html=html.replace("try{const result=await request('/api/workspace');db=", "const user=currentUser;\n try{const result=await request('/api/workspace');if(currentUser!==user)return;db=")
    html=html.replace("catch(e){loaded=false;showConnection(", "catch(e){if(currentUser!==user)return;loaded=false;showConnection(")
    html=html.replace("localStorage.setItem('shixu-system-active-identity',activeProfileId)","localStorage.setItem('shixu-system-active-identity:'+currentUser.id,activeProfileId)")
    html=html.replace("try{activeProfileId=localStorage.getItem('shixu-system-active-identity')||''}catch{}",'')
    html=html.replace("async function loadWorkspace(){", "async function loadWorkspace(){\n if(!csrfToken){bootAccount();return;}")
    html=html.replace("function syncStatus(message){", "function syncStatus(message){if(message==='同步中'||message.startsWith('已同步'))document.querySelector('#workbench').dataset.sync=message==='同步中'?'confirming':'ok';")
    # Static markup must exist before the small bootstrap, including both mobile account controls.
    skeleton='<div class="pagehead"><h1>把困扰理清，把今天过好。</h1></div><div class="stats">'+''.join('<div class="stat"><div class="shell-block"></div><p>'+s+'</p></div>' for s in ['待梳理的问题','今天要推进','正在行动','已解决的问题'])+'</div><section class="panel shell-panel"><h2>今天，先做这些</h2><div class="shell-line"></div><div class="shell-line"></div></section>'
    header=re.search(r'<header class="mobile-header">.*?</header>',html).group(0).split('${mobileAttrs')[0]+'</header>'
    nav=''.join('<button class="nav'+(' active' if k=='today' else '')+'" data-event-id="EVT-ACTION" data-action="nav" data-id="'+k+'">'+v+'</button>' for k,v in [('today','今日'),('issues','问题'),('tasks','行动'),('analysis','统计'),('review','复盘')])
    html=html.replace('<body><aside>','<body class="account-logged-out"><div id="workbench" hidden>'+header+'<nav class="mobile-bottom" aria-label="移动主导航">'+nav+'</nav><aside>',1)
    html=html.replace('<nav id="nav"></nav>','<nav id="nav">'+nav+'</nav>',1).replace('<div id="desktop-identity"></div>','<div id="desktop-identity"></div><div id="account-menu"></div>',1)
    html=html.replace('</main><dialog','</main></div><template id="shell-skeleton">'+skeleton+'</template><dialog',1)
    html=html.replace('<script>',EARLY_SHELL+'\n<script>',1)
    css+='\n.account-logged-out>#workbench{display:none!important}.shell-panel{padding:20px}.shell-block,.shell-line{background:#eef0e8;border-radius:6px;height:34px;width:56px;margin:8px 0}.shell-line{height:12px;width:70%;margin:14px 0}.shell-line:last-child{width:55%}\n'
    return html.replace('</style>',css+'\n</style>',1)
