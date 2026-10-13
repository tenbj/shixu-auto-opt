"""冻结原型账号界面接入真实API。"""
import re

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
    layer=layer.replace('<div class="auth-switch">','<p><a href="/connect">连接 AI · 查看接入指引</a></p><div class="auth-switch">')
    css+='\n'+(root/'static/ai-access.css').read_text(encoding='utf-8')
    layer="let currentUser=null,csrfToken='',lastPreviewConfig=null;\n"+layer+'\n'+(root/'static/accounts-api.js').read_text(encoding='utf-8')+'\n'+(root/'static/ai-access-api.js').read_text(encoding='utf-8')
    html=html.replace('\nloadWorkspace();\n','\nqueueMicrotask(bootAccount);\n',1)
    html=html.replace("document.querySelector('#mobile-identity').innerHTML=identitySwitch('mobile-identity');", "// Account chrome owns the mobile identity control and preserves its focus across renders.")
    html=html.replace('function render(){',"function render(){\n if(!currentUser){showLogin();return;}\n",1)
    marker="\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')"
    assert marker in html
    html=html.replace(marker,"\n renderAccountChrome();\n}\ndocument.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select')",1)
    html=html.replace('// MOBILE-DESIGN-END',layer+'\n// MOBILE-DESIGN-END',1)
    html=html.replace("headers:{'Content-Type':'application/json',...options.headers}","headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken,...options.headers}")
    html=html.replace("const e=new Error(typeof result.detail", "if(response.status===401&&currentUser){currentUser=null;loaded=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());showLogin('login','登录已过期，请重新登录')}const e=new Error(typeof result.detail")
    html=html.replace("localStorage.setItem('shixu-system-active-identity',activeProfileId)","localStorage.setItem('shixu-system-active-identity:'+currentUser.id,activeProfileId)")
    html=html.replace("try{activeProfileId=localStorage.getItem('shixu-system-active-identity')||''}catch{}",'')
    return html.replace('</style>',css+'\n</style>',1)
