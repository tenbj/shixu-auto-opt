"""在现有系统页面中合入冻结身份原型；保留回收站、紧凑菜单等系统能力。"""
from pathlib import Path


def integrate(html, root):
    prototype = (root/'reference/creator-source.html').read_text(encoding='utf-8')
    helpers = prototype[prototype.index('const TOOLS='):prototype.index('const seed=')]
    a,b = helpers.index('const defaultProfile='),helpers.index('const creatorFilters=')
    helpers = helpers[:a]+'''let profiles=[],activeProfileId='';
try{activeProfileId=localStorage.getItem('shixu-system-active-identity')||''}catch{}
const currentProfile=()=>profiles.find(p=>p.id===activeProfileId)||{id:'',name:'未设置',kind:'person',via:'manual'};
function syncProfiles(){profiles=db.identityProfiles||[];if(!profiles.some(x=>x.id===activeProfileId))activeProfileId=''}
''' + helpers[b:]
    def fn(name, value):
        nonlocal helpers
        lines=helpers.splitlines();i=next(i for i,s in enumerate(lines) if s.startswith('function '+name+'('))
        lines[i]=value;helpers='\n'.join(lines)+'\n'
    fn('persistProfiles',"function persistProfiles(){try{localStorage.setItem('shixu-system-active-identity',activeProfileId);return true}catch{toast('当前身份偏好未保存');return false}}")
    fn('creationFields', '''function creationFields(obj){if(obj)return creationDetail(obj);const c=currentProfile();return `<details class="creation-config"><summary>创建信息 · ${esc(c.name)}${c.kind==='agent'?' · '+esc(c.modelName||'模型未提供'):''}</summary>${field('实际记录身份',`<select name="creationIdentity" data-event-id="EVT-CREATION"><option value="">未指定（来源未知）</option>${profiles.map(x=>`<option value="${esc(x.id)}" ${x.id===c.id?'selected':''}>${esc(x.name)} · ${x.kind==='agent'?esc(TOOLS[x.via]):'手动'}</option>`).join('')}</select>`)}${field('人类发起者 · AI代录时选填',`<select name="creationPerson" data-event-id="EVT-CREATION" ${c.kind!=='agent'?'disabled':''}><option value="ai">未指定人类发起者</option>${profiles.filter(x=>x.kind==='person').map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}</select>`)}<div class="grid2 model-fields ${c.kind!=='agent'?'hidden':''}">${field('模型名称 / ID · 选填',`<input name="modelName" maxlength="160" value="${esc(c.modelName||'')}" placeholder="实际模型名称或标识">`)}${field('模型提供方 · 选填',`<input name="modelProvider" maxlength="80" value="${esc(c.modelProvider||'')}">`)}</div><p>记录身份在右上角设置。工具随身份带入；未提供模型时留空。</p></details>`}
'''.strip())
    fn('creationValues', "function creationValues(v){if(!v.creationIdentity)return null;const p=profiles.find(x=>x.id===v.creationIdentity);if(!p)throw Error('请重新选择记录身份');return {identityId:p.id,initiatedByPersonId:p.kind==='agent'&&v.creationPerson!=='ai'?v.creationPerson||null:null,modelInfo:p.kind==='agent'?{name:v.modelName||'',provider:v.modelProvider||''}:null}}")
    # Source/profile names are escaped by the frozen presentation helpers.
    helpers=helpers.replace('name="profileKind" data-event-id="EVT-IDENTITY"','name="profileKind" ${x?\'disabled\':\'\'} data-event-id="EVT-IDENTITY"')
    a=helpers.index("document.addEventListener('change'");b=helpers.index("document.addEventListener('click'",a)
    helpers=helpers[:a]+'''document.addEventListener('change',e=>{
const el=e.target;if(el.name==='profileKind')el.closest('form').querySelector('.profile-ai-fields').classList.toggle('hidden',el.value!=='agent');
if(el.dataset.eventId==='EVT-CREATOR-FILTER'){creatorFilters[el.dataset.kind][el.dataset.filter]=el.value;render()}
if(el.name==='creationIdentity'){const f=el.closest('form'),p=profiles.find(x=>x.id===el.value);f.elements.creationPerson.disabled=p?.kind!=='agent';f.elements.creationPerson.value='ai';f.querySelector('.model-fields').classList.toggle('hidden',p?.kind!=='agent');f.elements.modelName.value=p?.modelName||'';f.elements.modelProvider.value=p?.modelProvider||'';f.querySelector('summary').textContent='创建信息 · '+(p?.name||'未指定')}
});
''' + helpers[b:]
    a=helpers.index("document.addEventListener('submit'")
    helpers=helpers[:a]+'''document.addEventListener('submit',async e=>{if(e.target.id!=='profile-form')return;e.preventDefault();const f=e.target,v=Object.fromEntries(new FormData(f)),old=profiles.find(p=>p.id===f.dataset.id),kind=old?.kind||v.profileKind;
const values={name:v.profileName,via:kind==='person'?'manual':v.profileVia,modelName:kind==='person'?'':v.profileModel,modelProvider:kind==='person'?'':v.profileProvider};if(!old)values.kind=kind;
const b=f.querySelector('[type=submit]');b.disabled=true;
try{const result=await mutate('/api/identities'+(old?'/'+old.id:''),old?'PATCH':'POST',values);activeProfileId=result.resource.id;persistProfiles();closeDialog();render();toast('记录身份已保存')}
catch(e){f.querySelector('#form-error').textContent=e.message}finally{b.disabled=false}
});
'''
    def rep(a,b):
        nonlocal html
        assert a in html,a[:90]
        html=html.replace(a,b)
    css=prototype[prototype.index('.identity-switch{'):prototype.index('</style>')]
    rep('</style>',css+'\n.action-row:not(.table-head){height:auto;min-height:58px;padding-top:7px;padding-bottom:7px}.topbar-right{flex-wrap:wrap}.creation-detail{overflow-wrap:anywhere}\n</style>')
    rep('const ISSUE_STATES=',helpers+'\nconst ISSUE_STATES=')
    rep('<span class="avatar">我</span>','<div id="desktop-identity"></div>')
    rep("${field(kind==='issue'?'什么事情让你困扰？'", "${creationFields(obj)}${field(kind==='issue'?'什么事情让你困扰？'")
    rep('${backgroundSection(p)}','${creationDetail(p)}${backgroundSection(p)}')
    rep('<div class="issue-foot">','${creatorLine(p)}<div class="issue-foot">')
    rep('<p class="issue-description">','${creatorLine(p)}<p class="issue-description">')
    rep('<div class="meta task-status">','${creatorLine(t)}<div class="meta task-status">')
    # Keep menu markup in the newer trash baseline, only insert a second title line.
    rep('${title}</button></div>${btn(t.status','${title}</button>${creatorLine(t)}</div>${btn(t.status')
    rep('${stateBadge(focus)}</div>', '${stateBadge(focus)}</div>${creatorLine(focus)}')
    rep("liveIssues().filter(p=>(scope===", "liveIssues().filter(p=>matchesCreator(p,'issues')&&(scope===")
    rep('</select></div><div class="status-summary">',"</select></div>${creatorFilterBar('issues')}<div class=\"status-summary\">")
    rep('function filteredTasks(){return liveTasks().filter(',"function filteredTasks(){return liveTasks().filter(t=>matchesCreator(t,'tasks')).filter(")
    rep('return bar+filter+`<div class="desk-layout',"return bar+creatorFilterBar('tasks')+filter+`<div class=\"desk-layout")
    rep('renderDesktop();\n document.body.dataset.view=view;',"renderDesktop();\n document.querySelector('#desktop-identity').innerHTML=identitySwitch('desktop-identity');\n document.body.dataset.view=view;")
    rep('</span></div>${mobileAttrs','</span></div><div id="mobile-identity"></div>${mobileAttrs')
    rep('const names={today:',"document.querySelector('#mobile-identity').innerHTML=identitySwitch('mobile-identity');\n const names={today:")
    rep("${btn(esc(t.title),'edit-task',t.id,'mobile-task-title')}<div", "${btn(esc(t.title),'edit-task',t.id,'mobile-task-title')}${creatorLine(t)}<div")
    rep('return tabs+filter+controls+body;',"return tabs+creatorFilterBar('tasks')+filter+controls+body;")
    rep('db=result.data;revision=result.revision;', 'db=result.data;syncProfiles();revision=result.revision;')
    rep("actor:'我'", "actor:currentProfile().id?currentProfile().name:'未指定'")
    rep(" }else return;", "   if(!id)values.creation=creationValues(v);\n }else return;")
    return html
