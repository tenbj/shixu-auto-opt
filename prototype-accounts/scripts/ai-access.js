/* Offline UX only. No network calls, installations or real credentials. */
let aiRuntime='auto', aiExpanded=false, aiCopied=false, aiFlow=null, aiIssued=null;
const AI_ENDPOINT='https://shixu.eliasliu.cc/mcp';
const AI_RUNTIME_NAMES={auto:'自动识别',codex:'Codex',workbuddy:'WorkBuddy',claude:'Claude Code',other:'其他 AI / 服务器'};
const aiClient=()=>AI_RUNTIME_NAMES[aiRuntime==='auto'?'codex':aiRuntime];
const aiBtn=(label,action,id='',cls='secondary')=>`<button type="button" class="${cls}" data-event-id="EVT-AI-CONNECT" data-ai-action="${action}" data-id="${esc(id)}">${label}</button>`;
function aiSelect(id){return `<select id="${id}" data-event-id="EVT-AI-CONNECT" aria-label="选择AI工具">${Object.entries(AI_RUNTIME_NAMES).map(([k,v])=>`<option value="${k}" ${aiRuntime===k?'selected':''}>${v}</option>`).join('')}</select>`}
function aiPrompt(){return `【交互原型文案预览，接入指南及自动配置功能尚未发布，请勿执行】\n\n请帮我把${aiRuntime==='auto'?'当前 AI 工具':aiClient()}接入拾序，用于查询和记录问题。\n\n1. 读取拾序官方接入指南：https://shixu.eliasliu.cc/connect.md（待上线），识别当前操作系统、AI 工具及版本，选择对应的接入方式。\n2. 安装配套的拾序问题记录 Skill，合并配置远程 MCP：${AI_ENDPOINT}。保留已有其他服务配置，不要求拾序项目源码。优先原生远程连接，只安装必要依赖。\n3. 需要登录时打开拾序授权页，由我登录并确认读写权限。不要让我把密码或长期令牌发到聊天里。\n4. 验证当前账号、权限、工具及 Skill 是否可用；如需重载或新开会话，保存进度并告诉我如何继续。只做读取验证，不创建测试问题。\n5. 以后我说“记录问题”时，按 Skill 完成分类、查重、真实发起人、AI 工具与本次模型记录，并在保存后回读确认编号。无法确认的信息不要编造。\n\n如果当前工具没有执行能力或版本不支持，请说明具体阻碍和最少的人工操作。`}
function aiSteps(active=0){return `<ol class="ai-steps">${['复制给 AI','登录并授权','开始记录'].map((x,i)=>`<li class="${i===active?'current':i<active?'done':''}"><span>${i<active?'✓':i+1}</span>${x}</li>`).join('')}</ol>`}
function aiQuick(publicMode=false){return `<section class="ai-quick"><div class="ai-intro"><span class="ai-mark" aria-hidden="true">↗</span><div><h3>让 AI 帮你接好拾序。</h3><p>复制一段话，交给你正在使用的 AI。<br>配置完成后，直接说“帮我记录一个问题”。</p></div></div><label class="account-field ai-runtime-field"><span>你使用的 AI 工具</span>${aiSelect('ai-runtime')}</label><p class="ai-runtime-hint">${['claude','other'].includes(aiRuntime)?'将先检查工具能力，不支持时提供手动接入方式。':'不确定就选自动识别，AI 会检查自己的运行环境。'}</p><div class="ai-primary-actions">${aiBtn(aiCopied?'✓ 已复制提示词':'复制给 AI','copy-prompt','','primary')}${aiBtn('体验接入流程','start-demo')}</div><div id="ai-copy-status" role="status" class="ai-copy-status">${aiCopied?'已复制原型预览文案。正式接入功能待发布。':'当前为交互原型，不会安装软件或连接真实服务。'}</div>${aiSteps()}<div class="ai-support"><span>${aiBtn(aiExpanded?'收起提示词 ↑':'查看完整提示词 ↓','toggle-prompt','','account-link')}</span>${aiBtn('还没有 AI 工具？','install-help','','account-link')}</div>${aiExpanded?`<label class="account-field"><span>给 AI 的接入说明 · 原型预览</span><textarea id="ai-prompt" data-event-id="EVT-AI-CONNECT" rows="10" readonly>${esc(aiPrompt())}</textarea></label>`:''}${publicMode?'<p class="ai-public-note">接入说明可以公开查看。访问个人工作台时，仍需本人登录授权。</p>':''}</section>`}
function aiFlowView(){
 const f=aiFlow,client=esc(f.client),scope=f.scope==='read'?'只读':'读写';
 const states={prepare:['先由 AI 准备连接','识别环境、配置远程连接，并安装问题记录 Skill。'],authorizing:['等待你确认授权','登录拾序，确认这个 AI 可以访问的工作台与权限。'],denied:['你已拒绝这次授权','没有新增设备，也没有向客户端开放工作台。'],verify:['授权已完成，继续验证','AI 会核对当前账号、工具和 Skill 是否可用。'],reload:['还差一步：重新加载 AI','配置已准备好。重载客户端或新开会话后，继续完成验证。'],error:['连接还没有验证成功','网络连接中断。已保留配置和授权，可以直接重试。'],unsupported:['当前工具需要手动接入','这个演示环境没有自动写入配置的能力，请导入适配后的配置。'],success:['已准备好，开始记录吧。','以后在 AI 对话里说出问题，拾序会接住你的记录。']};
 const [title,desc]=states[f.stage];
 let body='';
 if(f.stage==='prepare')body=`<div class="ai-checks"><p>✓ 已识别：${client} <span>演示环境</span></p><p>✓ 已准备：远程 MCP 与问题记录 Skill</p><p>○ 下一步：由你登录并允许访问</p></div>${aiBtn('继续授权','authorize','','primary')}`;
 if(f.stage==='authorizing')body=aiBtn('打开授权确认','authorize','','primary');
 if(f.stage==='denied')body=aiBtn('重新发起授权','authorize','','primary');
 if(f.stage==='verify')body=`<div class="ai-checks"><p>✓ 当前工作台：${esc(accountNow().displayName)}</p><p>✓ 已授权范围：${scope}</p><p>○ 待验证：工具可用、Skill 已加载</p></div>${aiBtn('验证连接','verify','','primary')}`;
 if(f.stage==='reload')body=`<div class="ai-note">在新会话中说：“继续完成拾序接入验证”。配置无需重新填写。</div>${aiBtn('我已重新加载，继续验证','verify','','primary')}`;
 if(f.stage==='error')body=`<div class="ai-note">配置与授权保留，不会重复创建接入。</div>${aiBtn('重试验证','verify','','primary')}`;
 if(f.stage==='unsupported')body=aiBtn('查看手动配置','manual','','primary');
 if(f.stage==='success')body=`<div class="ai-result"><span>工作台 <b>${esc(accountNow().displayName)}</b></span><span>AI 工具 <b>${client}</b></span><span>权限 <b>${scope}</b></span><span>记录 Skill <b>已加载 · 演示</b></span></div>${f.scope==='read'?`<div class="ai-note">当前可以查询。记录新问题需要重新确认读写权限。</div>${aiBtn('授权读写权限','authorize','','primary')}`:`<div class="ai-example">帮我在拾序记录一个问题：每次开会后都忘记整理行动项。</div>${aiBtn('复制记录示例','copy-example','','primary')}`} ${aiBtn('查看已连接设备','devices')}<p class="ai-runtime-hint">这是流程演示，没有创建任何问题，也没有真实配置你的电脑。</p>`;
 return `<section class="ai-flow"><div class="ai-flow-top">${aiBtn('‹ 返回快速接入','exit-demo','','account-link')}<span class="ai-demo-badge">流程演示</span></div>${aiSteps(f.stage==='success'?2:f.stage==='prepare'?0:1)}<div class="ai-flow-title"><span class="ai-state-icon ${f.stage==='error'?'warning':''}">${f.stage==='success'?'✓':f.stage==='error'?'!':'↗'}</span><h3>${title}</h3><p>${desc}</p></div><div class="ai-flow-body" aria-live="polite">${body}</div>${['prepare','verify'].includes(f.stage)?`<div class="ai-demo-controls"><span>原型异常分支</span>${f.stage==='prepare'?aiBtn('无法自动配置','unsupported','','account-link'):aiBtn('需要重新加载','reload','','account-link')}${f.stage==='verify'?aiBtn('模拟连接失败','fail','','account-link'):''}</div>`:''}</section>`;
}
function aiDevices(){
 const user=accountNow(),items=user.connections;
 return `<section class="ai-devices"><div class="ai-list-head"><div><h3>${items.filter(x=>x.enabled).length} 个有效接入</h3><p>每个接入只访问 ${esc(user.displayName)} 的工作台。</p></div>${aiBtn('连接新设备','quick','','primary')}</div>${items.length?`<div class="ai-device-list">${items.map(x=>`<article class="ai-device" data-access-id="${esc(x.id)}"><div class="ai-device-icon" aria-hidden="true">${x.method==='oauth'?'↗':'⌘'}</div><div class="ai-device-info"><div class="ai-device-title"><h4>${esc(x.name)}</h4><span class="ai-status ${x.enabled?'':'revoked'}">${x.enabled?'已授权':'已撤销'}</span></div><p>${esc(x.runtime||x.name)} · ${x.method==='oauth'?'登录授权':'访问令牌'} · ${x.scope==='read'?'只读':'读写'}</p><small>${x.verifiedAt?'最近验证：'+esc(new Date(x.verifiedAt).toLocaleString('zh-CN'))+' · 演示':'尚无访问记录'}${x.enabled&&x.method==='oauth'?' · 自动续期（设计预览）':''}</small></div><div class="ai-device-actions">${aiBtn('重命名','rename',x.id,'account-link')}${x.enabled?accountButton('撤销','revoke-access',x.id,'secondary'):''}</div></article>`).join('')}</div>`:`<div class="ai-empty"><span aria-hidden="true">⌁</span><h3>还没有连接 AI</h3><p>从快速接入复制提示词，<br>让 AI 帮你完成配置。</p>${aiBtn('去快速接入','quick','','primary')}</div>`}<p class="ai-footnote">授权有效不代表设备在线。这里展示的接入与访问记录均为原型演示。</p></section>`;
}
function aiManual(){return `<section class="ai-manual"><h3>已有配置习惯？从这里连接。</h3><p>适用于手动配置的 AI 客户端和自动化服务器。</p><label class="account-field"><span>MCP 地址 · HTTPS</span><div class="ai-copy-row"><input data-event-id="EVT-AI-CONNECT" readonly value="${AI_ENDPOINT}">${aiBtn('复制','copy-url')}</div></label><div class="ai-manual-method"><div><b>登录授权</b><p>支持网页登录的客户端，添加地址后按提示登录。</p></div>${aiBtn('预览授权','manual-auth')}</div><div class="ai-manual-method"><div><b>访问令牌</b><p>不支持网页登录时，为这台设备生成一份专属配置。</p></div>${accountButton('生成访问令牌','new-access','','primary')}</div><label class="account-field ai-runtime-field"><span>配置格式</span>${aiSelect('ai-config-runtime')}</label><p class="ai-runtime-hint">${aiRuntime==='codex'?'Codex 使用 TOML 配置。':'生成时会展示对应工具的配置预览。'} 演示令牌不可连接真实服务。</p></section>`}
const originalAccountPage=renderAccountPage;
renderAccountPage=function(){
 if(accountPanelView!=='connections'){originalAccountPage();accountSavedDraft=aiDraft();return}
 const app=document.querySelector('#account-app');
 if(!['quick','list','server'].includes(accountTabs.connections))accountTabs.connections='quick';
 const key=accountTabs.connections;
 app.innerHTML=`<div class="account-tabs ai-tabs" role="tablist" aria-label="AI接入">${[['quick','快速接入'],['list','已连接设备'],['server','手动配置']].map(([id,label])=>`<button role="tab" id="account-tab-${id}" aria-controls="account-tabpanel" aria-selected="${key===id}" tabindex="${key===id?0:-1}" data-event-id="EVT-ACCOUNT" data-account-action="account-tab" data-id="${id}" class="${key===id?'active':''}">${label}</button>`).join('')}</div><div id="account-tabpanel" role="tabpanel" aria-labelledby="account-tab-${key}">${key==='quick'?(aiFlow?aiFlowView():aiQuick()):key==='list'?aiDevices():aiManual()}</div>`;
};
const originalLogin=showLogin;
showLogin=function(...args){originalLogin(...args);document.querySelector('.auth-demo').insertAdjacentHTML('afterend',`<div class="ai-login-link">${aiBtn('连接 AI，让它帮你记录 →','public-help','','account-link')}</div>`)};
function aiConsent(){
 const user=accountNow();if(!user){closeDialog();showLogin('login','请先登录体验账号，再继续接入演示。');return}
 if(!aiFlow)aiFlow={stage:'prepare',client:aiClient()};aiFlow.stage='authorizing';renderAccountPage();
 show('确认 AI 接入',`<div class="oauth-brand"><div class="oauth-app-icon">↗</div><h2>${esc(aiFlow.client)} 请求访问拾序</h2><p>此处为授权交互演示</p></div><div class="scope-card"><span>当前工作台</span><strong>${esc(user.displayName)}</strong><p>仅访问此账号的数据，不会向 AI 提供账号密码。</p></div><form id="ai-consent-form" data-event-id="EVT-AI-CONNECT">${accountField('授权范围',`<select name="scope" data-event-id="EVT-AI-CONNECT"><option value="write">读取与记录问题、行动</option><option value="read">仅查询问题、行动</option></select>`)}<p class="ai-runtime-hint">记录时保留真实发起人、AI 工具与模型。你可以随时在“已连接设备”撤销接入。</p><div class="account-error" role="alert"></div><div class="modal-actions">${aiBtn('拒绝','deny')}<button type="submit" class="primary" data-event-id="EVT-AI-CONNECT">允许访问</button></div></form>`);
}
function aiPublic(){show('连接 AI',`<div id="ai-public">${aiQuick(true)}</div>`)}
function aiRefresh(){if(document.querySelector('#ai-public'))document.querySelector('#ai-public').innerHTML=aiQuick(true);else renderAccountPage()}
async function aiCopy(text,source){try{await navigator.clipboard.writeText(text);return true}catch{if(source){source.focus();source.select()}toast('浏览器未允许复制，请手动复制已选中的文本');return false}}
showIssuedConfig=function(connection,token){
 const codex=aiRuntime==='codex';
 const text=codex?`# 原型演示，请勿用于真实接入\n[mcp_servers.shixu]\nurl = "${AI_ENDPOINT}"\nbearer_token_env_var = "SHIXU_MCP_TOKEN"\n\n# 在私有环境变量中配置以下演示令牌：\n# SHIXU_MCP_TOKEN = "${token}"`:JSON.stringify({mcpServers:{shixu:{type:'http',url:AI_ENDPOINT,headers:{Authorization:'Bearer '+token}}}},null,2);
 aiIssued={owner:accountNow().id,text,extension:codex?'toml':'json'};
 show('访问令牌配置预览',`<div class="access-success">✓ ${esc(connection.name)} · ${esc(accountNow().displayName)} 的工作台</div><p>配置仅在本次生成时展示。正式使用时保存在设备私有配置中。</p><label class="account-field"><span>${codex?'Codex · TOML':'远程 MCP · JSON'} 配置</span><textarea id="issued-config" rows="9" readonly data-event-id="EVT-AI-CONNECT">${esc(text)}</textarea></label><p class="ai-footnote">DEMO 令牌仅用于原型演示。请勿粘贴到真实客户端。</p><div class="modal-actions">${aiBtn('复制配置','copy-issued','','primary')}${aiBtn('下载配置','download-issued')}${btn('完成','close')}</div>`);
};
document.addEventListener('change',e=>{if(['ai-runtime','ai-config-runtime'].includes(e.target.id)){aiRuntime=e.target.value;aiCopied=false;aiRefresh();document.getElementById(e.target.id)?.focus()}},true);
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-ai-action]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();const action=b.dataset.aiAction;
 if(action==='copy-prompt'){aiExpanded=true;aiRefresh();aiCopied=await aiCopy(aiPrompt(),document.querySelector('#ai-prompt'));aiRefresh();if(!aiCopied){const field=document.querySelector('#ai-prompt');field?.focus();field?.select();document.querySelector('#ai-copy-status').textContent='未获得剪贴板权限，请手动复制已选中的提示词。'}}
 if(action==='toggle-prompt'){aiExpanded=!aiExpanded;aiRefresh()}
 if(action==='copy-url'){if(await aiCopy(AI_ENDPOINT,document.querySelector('.ai-copy-row input')))toast('MCP 地址已复制')}
 if(action==='public-help')aiPublic();
 if(action==='start-demo'){
  if(!accountNow()){closeDialog();showLogin('login','请先登录体验账号。登录后从右上角“AI接入”体验完整流程。');return}
  if(document.querySelector('#ai-public'))closeDialog();aiFlow={stage:'prepare',client:aiClient()};accountTabs.connections='quick';openAccountPanel('connections');
 }
 if(action==='install-help')show('还没有 AI 工具？',`<div class="ai-install"><h3>先准备一个能执行操作的 AI。</h3><p>选择并安装一款 AI 客户端，完成客户端自己的登录。然后回到拾序，复制接入提示词。</p><div class="ai-install-options">${aiBtn('Codex','choose-install','codex')}${aiBtn('WorkBuddy','choose-install','workbuddy')}</div><div id="ai-install-detail" class="ai-note">原型仅演示安装引导，不下载或安装软件。</div><p class="ai-footnote">如果 AI 只能聊天，不能执行本地操作，可以使用“手动配置”导入连接。</p><div class="modal-actions">${btn('返回','close')}</div></div>`);
 if(action==='choose-install')document.querySelector('#ai-install-detail').textContent=`${AI_RUNTIME_NAMES[b.dataset.id]}：正式版将提供官方下载入口。安装并登录后，把“复制给 AI”的内容粘贴到新对话中继续。`;
 if(action==='exit-demo'||action==='quick'){aiFlow=null;accountTabs.connections='quick';renderAccountPage()}
 if(action==='manual'||action==='devices'){accountTabs.connections=action==='manual'?'server':'list';renderAccountPage()}
 if(action==='authorize'||action==='manual-auth')aiConsent();
 if(action==='deny'){closeDialog();aiFlow.stage='denied';accountTabs.connections='quick';renderAccountPage()}
 if(action==='unsupported'||action==='reload'||action==='fail'){aiFlow.stage={unsupported:'unsupported',reload:'reload',fail:'error'}[action];renderAccountPage()}
 if(action==='verify'){
  aiFlow.stage='success';const c=accountNow().connections.find(x=>x.id===aiFlow.connectionId);if(c){c.verifiedAt=new Date().toISOString();storeAccounts()}renderAccountPage();
 }
 if(action==='copy-example'){const ok=await aiCopy('帮我在拾序记录一个问题：每次开会后都忘记整理行动项。');if(ok){b.textContent='✓ 示例已复制';toast('记录示例已复制，本原型未创建问题')}}
 if(action==='rename'){const c=accountNow().connections.find(x=>x.id===b.dataset.id);if(c)show('重命名设备',`<form id="ai-rename-form" data-event-id="EVT-AI-CONNECT" data-id="${esc(c.id)}">${accountField('设备名称',accountInput('name','text',c.name,'','required maxlength="60"'))}<div class="account-error" role="alert"></div><div class="modal-actions">${btn('取消','close')}<button type="submit" class="primary" data-event-id="EVT-AI-CONNECT">保存名称</button></div></form>`)}
 if(['copy-issued','download-issued'].includes(action)&&aiIssued?.owner===accountNow()?.id){if(action==='copy-issued'){if(await aiCopy(aiIssued.text,document.querySelector('#issued-config')))toast('演示配置已复制')}else{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([aiIssued.text],{type:'text/plain'}));a.download='shixu-demo.'+aiIssued.extension;a.click();URL.revokeObjectURL(a.href);toast('演示配置已下载')}}
},true);
document.addEventListener('submit',e=>{
 const f=e.target;if(!['ai-consent-form','ai-rename-form'].includes(f.id))return;e.preventDefault();e.stopImmediatePropagation();const data=Object.fromEntries(new FormData(f)),u=accountNow();
 if(f.id==='ai-consent-form'){
  let c=u.connections.find(x=>x.id===aiFlow.connectionId);
  if(c){c.scope=data.scope;c.enabled=true;delete c.verifiedAt}else{c={id:uid(),name:aiFlow.client+' · 本机演示',runtime:aiFlow.client,method:'oauth',scope:data.scope,owner:u.id,enabled:true,createdAt:new Date().toISOString()};u.connections.push(c)}
  if(!storeAccounts()){f.querySelector('.account-error').textContent='保存失败，请重试。';return}aiFlow.connectionId=c.id;aiFlow.scope=data.scope;aiFlow.stage='verify';closeDialog();accountTabs.connections='quick';renderAccountPage();
 }else{const c=u.connections.find(x=>x.id===f.dataset.id),name=String(data.name||'').trim();if(!name){f.querySelector('.account-error').textContent='请输入设备名称。';return}if(c)c.name=name;if(storeAccounts()){closeDialog();renderAccountPage();toast('名称已更新')}}
},true);
let accountSavedDraft='';
const aiDraft=()=>JSON.stringify([...document.querySelectorAll('#account-app form')].map(f=>[f.id,[...new FormData(f)]]));
const originalOpenAccount=openAccountPanel;
openAccountPanel=function(kind){originalOpenAccount(kind);const d=document.querySelector('#account-modal');d.querySelector('h2').textContent=kind==='connections'?'AI接入':'账号设置';accountSavedDraft=aiDraft();if(!d.dataset.aiClose){d.dataset.aiClose='1';d.addEventListener('close',()=>{[...document.querySelectorAll('[data-account-action="toggle-menu"]')].find(x=>x.getBoundingClientRect().width>0)?.focus({preventScroll:true})});d.addEventListener('cancel',e=>{if(aiDraft()!==accountSavedDraft&&!confirm('有未保存的修改。确定放弃吗？'))e.preventDefault()})}};
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-account-action]');if(!b)return;
 if(['close-account-panel','account-tab'].includes(b.dataset.accountAction)&&aiDraft()!==accountSavedDraft&&!confirm('有未保存的修改。确定放弃吗？')){e.preventDefault();e.stopImmediatePropagation();return}
 if(b.dataset.accountAction==='connections'){accountTabs.connections='quick';aiFlow=null}
 if(b.dataset.accountAction==='logout'){aiFlow=null;aiIssued=null}
 if(b.dataset.accountAction==='account-tab')queueMicrotask(()=>{accountSavedDraft=aiDraft()});
},true);
document.addEventListener('keydown',e=>{if(!e.target.matches('#account-modal [role=tab]')||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const tabs=[...document.querySelectorAll('#account-modal [role=tab]')],i=tabs.indexOf(e.target),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;e.preventDefault();tabs[next].click();document.querySelector('#account-modal [role=tab][aria-selected=true]')?.focus()});
queueMicrotask(()=>{const params=new URLSearchParams(location.search);if(params.get('connect')==='1')aiPublic();else if(params.get('panel')==='ai'&&accountNow()){accountTabs.connections='quick';openAccountPanel('connections')}});
