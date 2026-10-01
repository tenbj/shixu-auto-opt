"""从保留的原型复用布局，替换本地写入为 API。只有显式运行才重新生成页面。"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = ROOT.parent / 'prototype' / 'prototype.html'
if not source.exists():
    raise SystemExit('本脚本仅用于原型仓库开发；分发包直接使用 static/index.html。')
html = source.read_text(encoding='utf-8-sig')


def section(start, end, replacement):
    global html
    a, b = html.index(start), html.index(end, html.index(start))
    html = html[:a] + replacement + '\n' + html[b:]


section('const seed=', 'const ISSUE_STATES=', '')
section('try{const saved=localStorage.getItem(KEY)', 'const btn=', "db={version:1,schemaVersion:2,issues:[],tasks:[],nextIssueNumber:1,nextTaskNumbers:{}};\nlet revision=0,loaded=false,busy=false,pendingWrite=null;")
section('function save(){', 'const issue=id=>', "function changed(message){render();toast(message)}")
section('function setTaskDependencies(', 'function dependenciesForm(', '')
section('function reorderTask(', 'let pointerSort=', '''async function reorderTask(id,targetId,after=false){
 if(id===targetId)return false;
 try{await mutate(`/api/tasks/${id}/reorder`,'POST',{target_id:targetId,after});return true}catch(e){toast(e.message);return false}
}''')
section('function addFollowup(', 'function followupTimeline(', '')
section('function transitionIssue(', 'function taskHTML(', '''async function transitionIssue(p,action,values){
 try{await mutate(`/api/issues/${p.id}/transitions`,'POST',{action,...values});return ''}catch(e){return e.message}
}''')
section('function changeTask(', 'function cancelTaskForm(', '''async function changeTask(t,action){
 const status=action==='toggle'?(['已完成','已取消'].includes(t.status)?'待办':'已完成'):(t.status==='待办'?'进行中':'待办');
 try{await mutate(`/api/tasks/${t.id}/transitions`,'POST',{status});changed('行动状态已保存');if(document.querySelector('#modal').open&&t.issueId)detail(t.issueId)}catch(e){toast(e.message)}
}''')
section('function submitRecord(', "document.addEventListener('click'", '')
section("document.addEventListener('submit'", '</script>', '''document.addEventListener('submit',async e=>{
 if(e.target.dataset.eventId!=='EVT-SUBMIT')return;e.preventDefault();
 const f=e.target,v=Object.fromEntries(new FormData(f)),id=f.dataset.id;
 let route='',method='POST',values={},returnId=null;
 if(f.id==='attributes-form'){route=`/api/issues/${id}`;method='PATCH';values={priority:v.priority,tag:v.tag};if(f.dataset.return==='detail')returnId=id}
 else if(f.id==='background-form'){route=`/api/issues/${id}`;method='PATCH';values={description:v.description};returnId=id}
 else if(f.id==='followup-form'){route=`/api/issues/${id}/followups`;values={content:v.content};returnId=id}
 else if(f.id==='workflow-form'){route=`/api/issues/${id}/transitions`;values={action:f.dataset.transition,...v};returnId=id}
 else if(f.id==='dependencies-form'){route=`/api/tasks/${id}/dependencies`;values={dependsOn:new FormData(f).getAll('prerequisite')}}
 else if(f.id==='cancel-form'){route=`/api/tasks/${id}/transitions`;values={status:'已取消',reason:v.reason};returnId=db.tasks.find(t=>t.id===id)?.issueId}
 else if(f.id==='record-form'){
   const kind=f.dataset.kind==='issue'?'issues':'tasks';route=`/api/${kind}${id?'/'+id:''}`;method=id?'PATCH':'POST';
   values=kind==='issues'?{title:v.title,description:v.description,priority:v.priority,tag:v.tag}:{title:v.title,issueId:v.issueId||null,due:v.due||'',required:v.required!=='later'};
 }else return;
 const button=f.querySelector('[type=submit]');if(button)button.disabled=true;
 try{await mutate(route,method,values);const nested=!!document.querySelector('#child-modal[open]');changed('已保存到服务端');closeDialog(true);if(returnId&&!nested)detail(returnId)}
 catch(e){const error=f.querySelector('#form-error');if(error)error.textContent=e.message;else toast(e.message)}
 finally{if(button)button.disabled=false}
});

function showConnection(message){const el=document.querySelector('#storage-warning');el.replaceChildren(document.createTextNode(message+' '));el.classList.remove('hidden');const b=document.createElement('button');b.textContent='重新连接';b.onclick=()=>loadWorkspace();el.append(b)}
async function request(route,options={}){
 const response=await fetch(route,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:AbortSignal.timeout(15000)});
 const result=await response.json();if(!response.ok){const e=new Error(typeof result.detail==='string'?result.detail:'输入不符合要求，请检查必填内容和长度');e.status=response.status;throw e}return result;
}
async function loadWorkspace(){
 try{const result=await request('/api/workspace');db=result.data;revision=result.revision;loaded=true;document.querySelector('#storage-warning').classList.add('hidden');render();document.querySelector('#sync-state').textContent='已同步 · '+revision}
 catch(e){loaded=false;showConnection('连接服务失败，尚未加载记录。');document.querySelector('#app').textContent='服务暂时不可用，请恢复连接后重试。'}
}
async function mutate(route,method,values){
 if(!loaded)throw Error('请先连接服务');if(busy)throw Error('正在保存，请稍候');
 const signature=JSON.stringify([route,method,values]);
 if(pendingWrite&&pendingWrite.signature!==signature)throw Error('上一笔请求结果未确认，请先重试原操作，避免重复或丢失记录。');
 if(!pendingWrite)pendingWrite={signature,body:{...values,request_id:uid(),expected_version:revision,actor:'我'}};
 busy=true;document.querySelector('#sync-state').textContent='保存中…';
 try{
   const result=await request(route,{method,body:JSON.stringify(pendingWrite.body)});
   pendingWrite=null;db=result.data;revision=result.revision;render();document.querySelector('#storage-warning').classList.add('hidden');
   document.querySelector('#sync-state').textContent='已同步 · '+revision;return result;
 }catch(e){
   if(e.status&&e.status<500)pendingWrite=null;
   if(e.status===409){await loadWorkspace();e.message+='；已刷新工作台，请检查当前内容再提交。'}
   else if(!e.status||e.status>=500){showConnection('本次保存结果尚未确认，请恢复连接后重试相同操作。');e.message='保存结果未确认；请重试相同操作（保留幂等编号）。'}
   document.querySelector('#sync-state').textContent='保存未完成';throw e;
 }finally{busy=false}
}
document.querySelector('#sync-button').onclick=()=>loadWorkspace();
loadWorkspace();
''')
html = html.replace("function workflowForm(", "async function workflowForm(")
html = html.replace("const error=transitionIssue(p,action,{})", "const error=await transitionIssue(p,action,{})")
html = html.replace("document.addEventListener('click',e=>", "document.addEventListener('click',async e=>")
html = html.replace("document.addEventListener('pointerup',e=>", "document.addEventListener('pointerup',async e=>")
html = html.replace("document.addEventListener('drop',e=>", "document.addEventListener('drop',async e=>")
html = html.replace('if(reorderTask(', 'if(await reorderTask(').replace('target&&reorderTask(', 'target&&await reorderTask(')
html = html.replace('个人工作台 · 本地体验版<br>数据仅保存在当前浏览器', '个人工作台 · 系统版<br>数据由服务端持久保存')
html = html.replace('交互原型 · 初始内容为演示数据，可自由编辑。', '拾序 · 记录已接入服务端，页面与 AI 共用同一工作台。')
html = html.replace('<div class="topbar-right">', '<div class="topbar-right"><span id="sync-state" role="status" style="font-size:11px">连接中…</span><button id="sync-button" class="subtle">刷新数据</button>')
html = html.replace('const KEY=\'shixu-personal-v1\'', 'const KEY=\'shixu-system-v2\'')
html = html.replace("new Date().toLocaleString('zh-CN')", "new Date().toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})")
html = html.replace('const date=d=>{const x=new Date();x.setDate(x.getDate()+d);return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,\'0\')}-${String(x.getDate()).padStart(2,\'0\')}`}', "const date=d=>{const x=new Date(Date.now()+d*86400000);return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(x)}")
html = html.replace('</style>', '@media(max-width:700px){.topbar-right{flex-wrap:wrap;gap:6px}.topbar{align-items:flex-start}.topbar-right #sync-state{width:100%;text-align:right}}\n</style>')
(ROOT / 'static' / 'index.html').write_text(html, encoding='utf-8')
print('Generated static/index.html; prototype unchanged')
