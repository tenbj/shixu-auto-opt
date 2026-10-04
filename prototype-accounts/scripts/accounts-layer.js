/* Account flows are a local interaction preview, never a production auth implementation. */
let accountPanelView='settings';
let accountTabs={settings:'profile',connections:'quick'};
function accountNow(){return accountModel.users.find(x=>x.id===signedInId)||null}
function storeAccounts(){try{localStorage.setItem(ACCOUNT_KEY,JSON.stringify(accountModel));return true}catch{toast('账号设置未保存，请检查浏览器存储');return false}}
function accountButton(label,action,id='',cls='secondary'){return `<button type="button" class="${cls}" data-event-id="EVT-ACCOUNT" data-account-action="${action}" data-id="${esc(id)}">${label}</button>`}
function accountField(label,control){return `<label class="account-field"><span>${label}</span>${control}</label>`}
function accountInput(name,type='text',value='',placeholder='',attrs=''){return `<input data-event-id="EVT-ACCOUNT" name="${name}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs}>`}
function showLogin(mode='login',notice=''){
 closeAccountMenu();
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());document.body.classList.add('account-logged-out');
 let box=document.querySelector('#account-auth');if(!box){box=document.createElement('section');box.id='account-auth';document.body.prepend(box)}box.hidden=false;
 box.innerHTML=`<div class="auth-story"><div class="auth-wordmark"><span>⌁</span> 拾序</div><div><div class="auth-eyebrow">A LITTLE MORE CLARITY</div><h1>每个人，<br>都有自己的空间。</h1><p>记下困扰，整理行动。<br>把生活里重要的事，慢慢理出头绪。</p></div><small>你的问题、行动和接入授权，只属于你的工作台。</small></div><div class="auth-panel"><div class="auth-panel-inner"><span class="auth-preview">账号体验原型</span><h2>${mode==='register'?'开始你的工作台':'欢迎回来'}</h2><p>${mode==='register'?'新账号从空工作台开始，记录不会与他人互通。':'登录，继续整理属于你的问题和行动。'}</p><form id="account-auth-form" data-event-id="EVT-ACCOUNT" data-mode="${mode}">${accountField('账号',accountInput('username','text',mode==='login'?'test':'', '输入账号','required maxlength="40" autocomplete="username"'))}${mode==='register'?accountField('显示名称',accountInput('displayName','text','','你希望如何被称呼','maxlength="60"')):''}${accountField('密码',accountInput('password','password','','输入密码','required minlength="4" autocomplete="'+(mode==='login'?'current-password':'new-password')+'"'))}${mode==='register'?accountField('确认密码',accountInput('confirm','password','','再次输入密码','required minlength="4" autocomplete="new-password"')):''}<div id="account-auth-error" class="account-error" role="alert">${esc(notice)}</div><button type="submit" data-event-id="EVT-ACCOUNT" class="primary auth-submit">${mode==='register'?'创建账号并进入':'登录工作台'} <span>→</span></button></form><div class="auth-switch">${mode==='register'?'已经有账号？':'第一次使用？'}${accountButton(mode==='register'?'返回登录':'创建独立工作台',mode==='register'?'login-mode':'register-mode','','account-link')}</div><div class="auth-demo"><b>体验账号：test</b><span>初始密码：1234</span><small>现有原型记录已归入 test 工作台。</small></div></div></div>`;
}
function loadAccountWorkspace(user){
 KEY=WORKSPACE_KEY+user.id;accountTabs={settings:'profile',connections:'quick'};view='today';query='';priority='全部';scope='全部';category='';taskFilter=null;taskGrouping='issues';selectedTaskIssue='all';taskIssueStatus='全部';taskActionStatus='全部';parentIssueId=null;
 creatorFilters.issues={person:'',via:''};creatorFilters.tasks={person:'',via:''};
 const saved=localStorage.getItem(KEY);db=normalizeData(saved?JSON.parse(saved):user.id==='test'?structuredClone(seed):{version:1,issues:[],tasks:[]});
 const pref=JSON.parse(localStorage.getItem(KEY+'-profiles')||'null');profiles=pref?.items?.length?pref.items:[{...defaultProfile}];
 let human=profiles.find(x=>x.id==='account:'+user.id);if(!human){human={id:'account:'+user.id,name:user.displayName,kind:'person',via:'manual',modelName:'',modelProvider:''};profiles.unshift(human)}
 activeProfileId=human.id;storageBlocked=false;document.querySelector('#storage-warning').classList.add('hidden');persistProfiles();if(!save())throw Error('工作台保存失败');
}
function loginAccount(user){
 loadAccountWorkspace(user);signedInId=user.id;sessionStorage.setItem(SESSION_KEY,user.id);render();
 const pending=sessionStorage.getItem('shixu-preview-pending-auth');if(pending){sessionStorage.removeItem('shixu-preview-pending-auth');showAuthorization(pending)}
}
function logoutAccount(){save();persistProfiles();signedInId=null;sessionStorage.removeItem(SESSION_KEY);document.querySelectorAll('dialog[open]').forEach(x=>x.close());document.querySelector('#child-modal')?.remove();lastPreviewConfig=null;showLogin();window.scrollTo(0,0)}
function renderAccountChrome(){
 document.querySelectorAll('aside [data-action="nav"][data-id="settings"],aside [data-action="nav"][data-id="connections"]').forEach(x=>x.remove());
 const user=accountNow();document.querySelector('#account-auth')?.setAttribute('hidden','');document.body.classList.remove('account-logged-out');
 let top=document.querySelector('#account-menu');if(!top){top=document.createElement('div');top.id='account-menu';document.querySelector('.topbar-right').append(top)}
 const control=accountButton(`<span class="account-avatar">${esc(user.displayName.slice(0,1).toUpperCase())}</span><span>${esc(user.displayName)}<small>独立工作台</small></span><span>⌄</span>`,'toggle-menu','','account-pill');top.innerHTML=control;top.querySelector('button').setAttribute('aria-haspopup','menu');top.querySelector('button').setAttribute('aria-expanded','false');
 document.querySelector('#mobile-identity').innerHTML=control;document.querySelector('#mobile-identity button').setAttribute('aria-label','账号菜单：'+user.displayName);document.querySelector('#mobile-identity button').setAttribute('aria-haspopup','menu');document.querySelector('#mobile-identity button').setAttribute('aria-expanded','false');closeAccountMenu();document.querySelector('.nav-label').textContent=user.displayName+' 的工作台';
 document.querySelector('.topbar>span').innerHTML=esc(user.displayName)+' 的工作台 <span class="breadcrumb-separator">/</span><span id="breadcrumb">'+({settings:'账号设置',connections:'AI接入',today:'今日概览',issues:'问题池',tasks:'行动看板',analysis:'统计分析',review:'复盘记录'}[view])+'</span>';
 
}
function accountHead(title,desc,extra=''){return `<div class="pagehead"><div><div class="eyebrow">拾序 / ${esc(accountNow().displayName)} 的工作台</div><h1>${title}</h1><p>${desc}</p></div>${extra}</div>`}
function renderLegacyAccountPage(){
 const view=accountPanelView;
 const user=accountNow();if(view==='settings'){
 document.querySelector('#account-app').innerHTML=accountHead('属于你的工作台。','账号决定数据归属，记录身份说明谁创建了这条记录。')+`<div class="account-settings-grid"><section class="panel account-card"><h2>账号资料</h2><form id="account-profile-form" data-event-id="EVT-ACCOUNT">${accountField('账号',accountInput('username','text',user.username,'','readonly'))}${accountField('显示名称',accountInput('displayName','text',user.displayName,'','required maxlength="60"'))}<p class="account-muted">${db.issues.length} 个问题 · ${db.tasks.length} 项行动<br>其他账号不能查看或使用这个工作台。</p><div class="account-error" role="alert"></div><button type="submit" data-event-id="EVT-ACCOUNT" class="primary">保存资料</button></form></section><section class="panel account-card"><h2>密码与会话</h2><form id="account-password-form" data-event-id="EVT-ACCOUNT">${accountField('当前密码',accountInput('oldPassword','password','','','required autocomplete="current-password"'))}${accountField('新密码',accountInput('newPassword','password','','','required minlength="4" autocomplete="new-password"'))}${accountField('确认新密码',accountInput('confirmPassword','password','','','required minlength="4" autocomplete="new-password"'))}<div class="account-error" role="alert"></div><button type="submit" data-event-id="EVT-ACCOUNT" class="secondary">修改密码</button></form></section></div><section class="panel account-card account-settings-links"><div><h3>AI接入</h3><p>让AI客户端或服务器读写你的工作台。</p></div>${accountButton('管理接入 →','connections','','primary')}<div><h3>记录身份</h3><p>配置人工与AI名称、工具和模型；已有创建快照保持不变。</p></div>${btn('设置记录身份','identity-settings','','secondary')}</section><div class="account-logout">${accountButton('退出登录','logout','','secondary')}</div>`;
 }else{
 document.querySelector('#account-app').innerHTML=accountHead('让 AI 接入你的工作台。','授权与你的账号绑定，访问范围始终是这个独立工作台。')+`<div class="mcp-methods"><section class="panel account-card"><span class="access-type">个人电脑 / AI客户端</span><h2>登录后授权</h2><p>客户端请求连接时，登录拾序并确认访问范围。</p><div class="access-flow">填写MCP地址 <span>→</span> 登录 <span>→</span> 确认授权</div>${accountButton('预览客户端授权','oauth-preview','','primary')}<small class="account-muted">适用于支持登录授权的MCP客户端。</small></section><section class="panel account-card"><span class="access-type">服务器 / 自动化脚本</span><h2>生成访问令牌</h2><p>在这里生成专属配置，复制到远端后即可长期运行。</p><div class="access-flow">命名接入端 <span>→</span> 复制配置 <span>→</span> 连接</div>${accountButton('＋ 新增令牌接入','new-access','','primary')}<small class="account-muted">无需远端访问项目或运行发放脚本。</small></section></div><section class="panel account-card"><div class="access-list-head"><h2>已授权接入 <span class="pill">${user.connections.filter(x=>x.enabled).length}</span></h2><span>仅 ${esc(user.displayName)} 的工作台</span></div><div class="access-list">${user.connections.length?user.connections.map(x=>`<article class="access-row" data-access-id="${esc(x.id)}"><div class="access-icon">${x.method==='oauth'?'↗':'⌘'}</div><div class="access-info"><h3>${esc(x.name)} <span class="pill ${x.enabled?'':'muted'}">${x.enabled?'有效':'已撤销'}</span></h3><p>${x.method==='oauth'?'登录授权':'访问令牌'} · ${x.scope==='read'?'只读':'读写'} · ${esc(user.username)} 的工作台</p><small>创建于 ${esc(new Date(x.createdAt).toLocaleString('zh-CN'))}</small></div>${x.enabled?accountButton('撤销','revoke-access',x.id,'secondary'):''}</article>`).join(''):'<div class="empty"><strong>还没有外部接入</strong>可以授权AI客户端，或为服务器生成一份配置。</div>'}</div></section><p class="access-preview-note">交互预览：此页模拟授权与配置管理，不会连接或改变真实MCP服务。</p>`;
 }
}
function showNewAccess(){show('新增令牌接入',`<p>给这个接入端起个名字，方便以后识别和撤销。</p><form id="account-access-form" data-event-id="EVT-ACCOUNT">${accountField('接入名称',accountInput('name','text','','例如：笔记本 Codex、定时任务服务器','required maxlength="60"'))}${accountField('访问范围',`<select name="scope" data-event-id="EVT-ACCOUNT"><option value="write">读写问题与行动</option><option value="read">只读问题与行动</option></select>`)}<div class="scope-card"><span>工作台</span><strong>${esc(accountNow().displayName)}</strong><p>此配置只能访问这个账号的数据。</p></div><div class="account-error" role="alert"></div><div class="modal-actions">${btn('取消','close')}<button type="submit" data-event-id="EVT-ACCOUNT" class="primary">生成配置</button></div></form>`)}
function showIssuedConfig(connection,token){
 const user=accountNow();lastPreviewConfig={owner:user.id,connectionId:connection.id,config:{mcpServers:{shixu:{type:'http',url:'https://eliasliu.cc:11865/mcp',headers:{Authorization:'Bearer '+token}}}}};
 show('配置已生成',`<div class="access-success">✓ ${esc(connection.name)} 已绑定 ${esc(user.displayName)} 的工作台</div><p>复制到目标客户端的MCP配置中。令牌仅在本次生成时显示，关闭后可重新发放。</p><label class="account-field"><span>MCP配置</span><textarea id="issued-config" data-event-id="EVT-ACCOUNT" readonly rows="9">${esc(JSON.stringify(lastPreviewConfig.config,null,2))}</textarea></label><p class="access-preview-note">这是原型演示配置，DEMO令牌不能访问真实服务；HTTPS地址为待落地配置。</p><div class="modal-actions">${accountButton('复制配置','copy-config','','primary')}${accountButton('下载JSON','download-config')}${btn('完成','close')}</div>`)
}
function showAuthorization(client='Codex'){
 const user=accountNow();show('确认 MCP 授权',`<div class="oauth-brand"><div class="oauth-app-icon">${esc(client.slice(0,1))}</div><h2>${esc(client)} 请求访问拾序</h2><p>只授权当前账号的工作台。</p></div><div class="scope-card"><span>当前账号</span><strong>${esc(user.displayName)} <small>(${esc(user.username)})</small></strong>${accountButton('切换登录账号','switch-auth-account',client,'account-link')}</div><form id="account-oauth-form" data-event-id="EVT-ACCOUNT" data-client="${esc(client)}">${accountField('授权范围',`<select name="scope" data-event-id="EVT-ACCOUNT"><option value="write">读取、新增和修改问题与行动</option><option value="read">仅查询问题与行动</option></select>`)}<ul class="oauth-permissions"><li>访问 ${esc(user.displayName)} 的问题和行动</li><li>保留人类发起者、AI工具及模型创建信息</li><li>不访问其他账号，不提供账号密码给客户端</li></ul><p class="account-muted">可随时在“AI接入”撤销授权。此处为授权流程预览。</p><div class="modal-actions">${accountButton('拒绝','reject-auth')}<button type="submit" data-event-id="EVT-ACCOUNT" class="primary">允许访问</button></div></form>`)
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-account-action]');if(!b)return;const a=b.dataset.accountAction;
 if(a==='register-mode')showLogin('register');if(a==='login-mode')showLogin();if(a==='logout')logoutAccount();
 if(a==='toggle-menu'){toggleAccountMenu(b);return;}
 if(a==='menu-tools'){showAccountTools();return;}
 if(a==='menu-back'){const trigger=[...document.querySelectorAll('[data-account-action="toggle-menu"]')].find(x=>x.getBoundingClientRect().width>0);closeAccountMenu();toggleAccountMenu(trigger);return;}
 if(a==='account-tab'){accountTabs[accountPanelView]=b.dataset.id;renderAccountPage();document.querySelector('[role=tab][aria-selected=true]')?.focus();return;}
 if(a==='settings'||a==='connections'){closeAccountMenu();openAccountPanel(a)}
 if(a==='close-account-panel')document.querySelector('#account-modal')?.close();
 if(a==='new-access')showNewAccess();if(a==='oauth-preview')showAuthorization();
 if(a==='switch-auth-account'){sessionStorage.setItem('shixu-preview-pending-auth',b.dataset.id);logoutAccount()}
 if(a==='reject-auth'){closeDialog();toast('已拒绝，此客户端没有获得访问权限')}
 if(a==='revoke-access'){const c=accountNow().connections.find(x=>x.id===b.dataset.id);if(c)show('撤销接入',`<p>撤销后，${esc(c.name)} 的后续访问会被拒绝。工作台记录保留，其他接入不受影响。</p><div class="modal-actions">${btn('取消','close')}${accountButton('确认撤销','confirm-revoke',c.id,'primary')}</div>`)}
 if(a==='confirm-revoke'){const user=accountNow(),c=user.connections.find(x=>x.id===b.dataset.id);if(c)c.enabled=false;if(storeAccounts()){closeDialog();renderAccountPage();toast('接入已撤销')}}
 if(a==='copy-config'||a==='download-config'){
  if(lastPreviewConfig?.owner!==accountNow()?.id)return;const text=JSON.stringify(lastPreviewConfig.config,null,2);
  if(a==='copy-config'){try{await navigator.clipboard.writeText(text);toast('配置已复制')}catch{const t=document.querySelector('#issued-config');t.focus();t.select();toast('请复制已选中的配置')}}
  else{const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([text],{type:'application/json'}));link.download='shixu-demo-'+lastPreviewConfig.connectionId+'.json';link.click();URL.revokeObjectURL(link.href);toast('演示配置已下载')}
 }
});
document.addEventListener('submit',e=>{
 const form=e.target;if(form.dataset.eventId!=='EVT-ACCOUNT')return;e.preventDefault();const v=Object.fromEntries(new FormData(form)),user=accountNow(),error=form.querySelector('.account-error')||document.querySelector('#account-auth-error');
 const fail=t=>{if(error)error.textContent=t};
 if(form.id==='account-auth-form'){
  const name=String(v.username||'').trim();if(form.dataset.mode==='login'){const found=accountModel.users.find(x=>x.username===name&&x.password===v.password);if(!found)return fail('账号或密码不正确，请重新输入。');try{loginAccount(found)}catch{return fail('无法保存工作台，请检查浏览器存储。')}}
  else{if(!/^[A-Za-z0-9_-]{2,40}$/.test(name))return fail('账号使用2–40位字母、数字、下划线或短横线。');if(accountModel.users.some(x=>x.username.toLowerCase()===name.toLowerCase()))return fail('这个账号已被使用。');if(v.password!==v.confirm)return fail('两次密码不一致。');const fresh={id:uid(),username:name,displayName:String(v.displayName||name).trim()||name,password:v.password,connections:[]};accountModel.users.push(fresh);if(storeAccounts())loginAccount(fresh)}
 }
 if(form.id==='account-profile-form'){const name=String(v.displayName||'').trim();if(!name)return fail('请输入显示名称。');user.displayName=name;if(storeAccounts()){const human=profiles.find(x=>x.id==='account:'+user.id);if(human)human.name=name;persistProfiles();render();renderAccountPage();toast('账号资料已保存')}}
 if(form.id==='account-password-form'){if(v.oldPassword!==user.password)return fail('当前密码不正确。');if(v.newPassword!==v.confirmPassword)return fail('两次新密码不一致。');user.password=v.newPassword;if(storeAccounts()){renderAccountPage();toast('密码已修改')}}
 if(form.id==='account-access-form'||form.id==='account-oauth-form'){
  const oauth=form.id==='account-oauth-form',name=oauth?form.dataset.client:String(v.name||'').trim();if(!name)return fail('请输入接入名称。');if(!oauth&&user.connections.some(x=>x.enabled&&x.name===name))return fail('已有同名接入，请换一个名称。');
  const connection={id:uid(),name,scope:v.scope,method:oauth?'oauth':'token',enabled:true,createdAt:new Date().toISOString(),owner:user.id};user.connections.push(connection);if(!storeAccounts())return;
  closeDialog();accountTabs.connections='list';openAccountPanel('connections');if(oauth)toast('授权成功，'+name+' 只能访问 '+user.displayName+' 的工作台');else showIssuedConfig(connection,'DEMO_'+uid());
 }
});

function closeAccountMenu(){document.querySelector('#account-dropdown')?.remove();document.querySelectorAll('[data-account-action="toggle-menu"]').forEach(x=>x.setAttribute('aria-expanded','false'))}
function toggleAccountMenu(trigger){
 if(document.querySelector('#account-dropdown')){closeAccountMenu();return;}
 const u=accountNow(),menu=document.createElement('div');menu.id='account-dropdown';menu.setAttribute('role','menu');menu.innerHTML=`<div class="account-dropdown-info"><strong>${esc(u.displayName)}</strong><small>${esc(u.username)} · 独立工作台</small></div>${accountButton('账号设置','settings','','menu-item')}${accountButton('AI接入','connections','','menu-item')}${accountButton('工作台工具 <span aria-hidden="true">›</span>','menu-tools','','menu-item menu-tools')}<div class="menu-divider"></div>${accountButton('退出登录','logout','','menu-item menu-logout')}`;
 document.body.append(menu);menu.querySelectorAll('button').forEach(x=>x.setAttribute('role','menuitem'));const r=trigger.getBoundingClientRect();menu.style.top=(r.bottom+8)+'px';menu.style.right=Math.max(12,innerWidth-r.right)+'px';trigger.setAttribute('aria-expanded','true');menu.querySelector('button').focus();
}
document.addEventListener('click',e=>{if(e.target.closest('#account-dropdown [data-event-id="EVT-ACTION"]')||(!e.composedPath().some(x=>x.id==='account-dropdown')&&!e.target.closest('[data-account-action="toggle-menu"]')))closeAccountMenu()});
document.addEventListener('keydown',e=>{const menu=document.querySelector('#account-dropdown');if(!menu)return;if(e.key==='Escape'){closeAccountMenu();document.querySelector('[data-account-action="toggle-menu"]:not([hidden])')?.focus();e.preventDefault()}if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){const buttons=[...menu.querySelectorAll('button')],i=buttons.indexOf(document.activeElement),next=e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[next].focus();e.preventDefault()}});
window.addEventListener('resize',closeAccountMenu);window.addEventListener('scroll',closeAccountMenu);
function renderAccountPage(){
 const view=accountPanelView;
 renderLegacyAccountPage();const app=document.querySelector('#account-app'),head=app.querySelector('.pagehead').outerHTML,user=accountNow(),settings=view==='settings';
 const items=settings?[['profile','账号资料'],['password','修改密码'],['identity','记录身份']]:[['list','已授权接入'],['client','客户端授权'],['server','服务器令牌']];
 const key=accountTabs[view],index=items.findIndex(x=>x[0]===key);let content;
 if(settings){const cards=app.querySelectorAll('.account-card');content=index<2?cards[index].outerHTML:`<section class="panel account-card"><h2>记录身份</h2><p>配置创建人、AI工具和模型，便于追溯每条问题与行动的来源。</p><p class="account-muted">已有记录保留创建时的来源信息。身份设置仅作用于当前工作台。</p>${btn('管理记录身份','identity-settings','','primary')}</section>`;}
 else{const methods=app.querySelectorAll('.mcp-methods>.account-card');content=index===0?app.querySelector('.access-list-head').closest('section').outerHTML:methods[index-1].outerHTML;}
 app.innerHTML=head+`<div class="account-tabs" role="tablist" aria-label="${settings?'账号设置':'AI接入'}">${items.map(([id,label])=>`<button role="tab" id="account-tab-${id}" aria-controls="account-tabpanel" aria-selected="${id===key}" data-event-id="EVT-ACCOUNT" data-account-action="account-tab" data-id="${id}" class="${id===key?'active':''}">${label}</button>`).join('')}</div><div id="account-tabpanel" role="tabpanel" aria-labelledby="account-tab-${key}" class="account-tabpanel ${key==='list'?'wide':''}">${content}</div>`+(settings?'':`<p class="access-preview-note">交互预览：授权与令牌仅为演示，未连接真实MCP服务。</p>`);
 if(!settings&&key==='list'){const h=app.querySelector('.access-list-head');h.insertAdjacentHTML('afterend',`<div class="access-list-toolbar"><span>管理可以访问你工作台的客户端和服务器。</span>${accountButton('＋ 新增接入','account-tab','server','primary')}</div>`)}
}

function showAccountTools(){
 const menu=document.querySelector('#account-dropdown');if(!menu)return;
 menu.innerHTML=`${accountButton('‹ 返回账号菜单','menu-back','','menu-item menu-back')}<div class="menu-divider"></div><div class="account-tools-caption">工作台工具</div>${btn('状态流转说明','workflow-guide','','menu-item')}${btn('导出工作台记录','export','','menu-item')}${btn('查看统计分析','mobile-go-analysis','','menu-item')}`;
 menu.querySelectorAll('button').forEach(x=>x.setAttribute('role','menuitem'));menu.querySelector('button').focus();
}
function openAccountPanel(kind){
 accountPanelView=kind;let d=document.querySelector('#account-modal');if(!d){d=document.createElement('dialog');d.id='account-modal';d.setAttribute('aria-labelledby','account-modal-title');document.body.append(d)}
 d.innerHTML=`<div class="modal-head"><h2 id="account-modal-title">${kind==='settings'?'账号设置':'AI接入'}</h2>${accountButton('✕','close-account-panel','','account-panel-close')}</div><div class="modal-body" id="account-app"></div>`;d.querySelector('.account-panel-close').setAttribute('aria-label','关闭账号管理');renderAccountPage();if(!d.open)d.showModal();
}
