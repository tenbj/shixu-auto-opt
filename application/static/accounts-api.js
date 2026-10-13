async function loginAccount(result){
 currentUser={...result.user,connections:[]};csrfToken=result.csrf;
 view='today';query='';priority='全部';scope='全部';category='';parentIssueId=null;pendingWrite=null;taskFilter=null;taskGrouping='issues';selectedTaskIssue='all';taskIssueStatus='全部';taskActionStatus='全部';accountTabs={settings:'profile',connections:'quick'};
 creatorFilters.issues={person:'',via:''};creatorFilters.tasks={person:'',via:''};
 activeProfileId=localStorage.getItem('shixu-system-active-identity:'+currentUser.id)||'';
 await loadWorkspace();
 if(loaded&&!profiles.some(x=>x.kind==='person'&&x.name===currentUser.displayName)){
  try{const made=await mutate('/api/identities','POST',{name:currentUser.displayName,kind:'person',via:'manual',modelName:'',modelProvider:''});activeProfileId=made.resource.id;persistProfiles();render()}catch(e){toast(e.message)}
 }
 if(!activeProfileId){activeProfileId=profiles.find(x=>x.kind==='person'&&x.name===currentUser.displayName)?.id||'';persistProfiles();render()}
 if(new URLSearchParams(location.search).has('authorize'))await showAuthorization();
}
async function logoutAccount(){
 try{await request('/api/auth/logout',{method:'POST',body:'{}'})}catch(e){if(e.status!==401){toast(e.message);return}}
 currentUser=null;csrfToken='';loaded=false;profiles=[];restoreCustomTools([],{});activeProfileId='';db={issues:[],tasks:[],identityProfiles:[]};pendingWrite=null;lastPreviewConfig=null;
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());showLogin();window.scrollTo(0,0);
}
async function bootAccount(){
 try{
  const response=await fetch('/api/auth/me',{signal:AbortSignal.timeout(15000)}),result=await response.json();
  if(!response.ok){const error=new Error(typeof result.detail==='string'?result.detail:'登录状态检查失败');error.status=response.status;throw error}
  if(!currentUser)await loginAccount(result);
 }catch(e){
  if(currentUser)return;
  const form=document.querySelector('#account-auth-form');
  if(!form)showLogin('login',e.status===401?'':e.message);
  else if(e.status!==401){const notice=document.querySelector('#account-auth-error');if(notice)notice.textContent=e.message}
 }finally{document.documentElement.dataset.accountBoot='complete'}
}
async function showAuthorization(){
 const key=new URLSearchParams(location.search).get('authorize');
 if(!key&&currentUser.connection?.oauthAvailable===false){show('HTTP 连接方法',`<p>当前HTTP地址使用访问令牌连接。请在“AI接入 → 手动配置”生成并下载配置，再导入客户端。</p><p>“访问令牌”也适用于个人电脑上的AI客户端。标准OAuth登录授权需要HTTPS。</p>`);return}
 if(!key){show('客户端连接方法',`<p>在支持OAuth的客户端中添加下方MCP地址，连接时会打开拾序登录和授权页面。</p><label class="account-field">MCP地址<input readonly value="${esc(currentUser.connection?.url||location.origin+'/mcp')}"></label><p>不支持登录授权的客户端，请使用“访问令牌”中的配置。</p>`);return}
 try{const info=await request('/api/oauth/requests/'+encodeURIComponent(key));show('确认 MCP 授权',`<h2>${esc(info.client)} 请求访问拾序</h2><div class="scope-card"><span>当前账号</span><strong>${esc(currentUser.displayName)}</strong>${accountButton('切换登录账号','switch-auth-account','','account-link')}</div><form id="account-oauth-form" data-event-id="EVT-ACCOUNT">${accountField('授权范围',`<select name="scope"><option value="read">只读问题与行动</option>${info.scope==='write'?'<option value="write">读取与修改问题及行动</option>':''}</select>`)}<p>只访问当前工作台，账号密码不会提供给客户端。</p><div class="account-error"></div><div class="modal-actions">${accountButton('拒绝','reject-auth')}<button type="submit" data-event-id="EVT-ACCOUNT" class="primary">允许访问</button></div></form>`)}catch(e){toast(e.message)}
}
async function completeConsent(allow,scope){const key=new URLSearchParams(location.search).get('authorize');if(!key)return;const result=await request('/api/oauth/requests/'+encodeURIComponent(key),{method:'POST',body:JSON.stringify({allow,scope})});location.assign(result.redirect)}
document.addEventListener('submit',async e=>{
 const form=e.target;if(form.dataset.eventId!=='EVT-ACCOUNT')return;e.preventDefault();const v=Object.fromEntries(new FormData(form));const error=form.querySelector('.account-error')||document.querySelector('#account-auth-error');const button=form.querySelector('[type=submit]');if(button)button.disabled=true;
 try{
  if(form.id==='account-auth-form'){
   if(form.dataset.mode==='register'&&v.password!==v.confirm)throw Error('两次密码不一致');
   const result=await request('/api/auth/'+(form.dataset.mode==='register'?'register':'login'),{method:'POST',body:JSON.stringify({username:v.username,password:v.password,displayName:v.displayName||''})});await loginAccount(result);
  }
  if(form.id==='account-profile-form'){const updated=await request('/api/account',{method:'PATCH',body:JSON.stringify({displayName:v.displayName})});Object.assign(currentUser,updated);render();renderAccountPage();toast('账号资料已保存')}
  if(form.id==='account-password-form'){if(v.newPassword!==v.confirmPassword)throw Error('两次新密码不一致');await request('/api/account/password',{method:'POST',body:JSON.stringify({oldPassword:v.oldPassword,newPassword:v.newPassword})});await logoutAccount();toast('密码已修改，请重新登录')}
  if(form.id==='account-access-form'){
   const result=await request('/api/account/mcp-access',{method:'POST',body:JSON.stringify({name:v.name,scope:v.scope})});closeDialog();accountTabs.connections='list';await openAccountPanel('connections');showIssuedConfig({...result.item,url:result.url},result.token);
  }
  if(form.id==='account-oauth-form')await completeConsent(true,v.scope);
 }catch(e){if(error)error.textContent=e.message;else toast(e.message)}finally{if(button)button.disabled=false}
});

let accountDraft='';
function accountFormSnapshot(){return JSON.stringify([...document.querySelectorAll('#account-modal form')].map(f=>[f.id,[...new FormData(f)]]))}
function accountHasDraft(){return document.querySelector('#account-modal')?.open&&accountDraft!==accountFormSnapshot()}
function allowAccountDiscard(){return !accountHasDraft()||confirm('有未保存的修改。确定放弃吗？取消可继续编辑。')}
function closeAccountPanel(){
 const modal=document.querySelector('#account-modal');modal?.close();
 const restore=()=>[...document.querySelectorAll('.account-pill')].find(x=>x.getClientRects().length&&getComputedStyle(x).visibility!=='hidden')?.focus({preventScroll:true});
 restore();requestAnimationFrame(()=>{if(!modal?.open&&!document.querySelector('dialog[open]'))restore()});
};
// Handle Escape deterministically after tab DOM replacement and nested-dialog closure.
document.addEventListener('keydown',e=>{const modal=document.querySelector('#account-modal');if(e.key!=='Escape'||!modal?.open||document.querySelector('#modal')?.open)return;e.preventDefault();e.stopPropagation();if(allowAccountDiscard())closeAccountPanel()},true);
const accountRenderPage=renderAccountPage;
renderAccountPage=function(){
 accountRenderPage();
 const connection=currentUser.connection;
 if(accountPanelView==='connections'&&connection?.oauthAvailable===false){
  const panel=document.querySelector('#account-tabpanel');
  if(accountTabs.connections==='client')panel.innerHTML=`<section class="panel account-card"><h2>使用访问令牌连接</h2><p>当前为HTTP地址，请生成专属配置后导入AI客户端。个人电脑和服务器都可以使用。</p><div class="access-flow">生成令牌 <span>→</span> 下载配置 <span>→</span> 客户端连接</div>${accountButton('前往生成令牌','account-tab','server','primary')}<p class="account-muted">标准OAuth登录授权需要HTTPS。</p></section>`;
  const note=document.querySelector('#account-app .access-preview-note');
  if(note)note.textContent='当前为HTTP连接，令牌和数据未经加密；接入仍受账号权限与撤销控制。';
 }
 accountDraft=accountFormSnapshot();const modal=document.querySelector('#account-modal');if(modal&&!modal.dataset.cancelGuard){modal.dataset.cancelGuard='true';modal.addEventListener('cancel',e=>{e.preventDefault();if(allowAccountDiscard())closeAccountPanel()})}
};
document.addEventListener('click',e=>{const button=e.target.closest('[data-account-action]');if(button&&['close-account-panel','account-tab'].includes(button.dataset.accountAction)&&accountHasDraft()&&!allowAccountDiscard()){e.preventDefault();e.stopImmediatePropagation()}},true);
document.addEventListener('keydown',e=>{if(!e.target.matches('#account-modal [role=tab]')||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const tabs=[...document.querySelectorAll('#account-modal [role=tab]')],i=tabs.indexOf(e.target),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;e.preventDefault();tabs[next].click();document.querySelector('#account-modal [role=tab][aria-selected=true]')?.focus()});
