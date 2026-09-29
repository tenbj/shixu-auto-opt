async () => {
const results=[],ok=(name,condition)=>{results.push({name,passed:!!condition});if(!condition)throw Error(name)};
const click=(action,id)=>{const s='[data-action="'+action+'"]'+(id?'[data-id="'+id+'"]':'');const el=document.querySelector('#modal[open] '+s)||document.querySelector(s);if(!el)throw Error('missing '+s);el.click()};
const fill=(name,value)=>document.querySelector('[name="'+name+'"]').value=value;
const submit=()=>document.querySelector('#modal form').requestSubmit();
window.testInitialStorage=localStorage.getItem(KEY);
const initial=structuredClone(db);window.restorePrototype=()=>{db=structuredClone(initial);if(window.testInitialStorage===null)localStorage.removeItem(KEY);else localStorage.setItem(KEY,window.testInitialStorage);view='today';query='';priority='全部';scope='未解决';document.querySelector('#modal').close();render()};
try{
ok('desktop no horizontal overflow',document.documentElement.scrollWidth<=innerWidth);
click('new');fill('title','   ');submit();ok('blank title rejected',document.querySelector('#form-error').textContent.includes('空格')&&db.issues.length===initial.issues.length);
fill('title','测试问题 <img src=x onerror=alert(1)>');fill('description','真实测试背景');submit();const p=db.issues[0];ok('issue creation',p.status==='待梳理');
click('nav','issues');click('detail',p.id);ok('user content escaped',!document.querySelector('#modal-content img'));
click('new-linked',p.id);fill('title','测试行动一');submit();const t1=db.tasks[0];ok('issue task association',t1.issueId===p.id&&p.status==='处理中');
click('detail',p.id);click('new-linked',p.id);fill('title','测试行动二');submit();const t2=db.tasks[0];ok('multiple actions',linked(p.id).length===2);
click('detail',p.id);click('resolve',p.id);ok('incomplete action blocks resolution',document.querySelector('#modal-title').textContent==='问题详情'&&p.status!=='已解决');
click('advance',t1.id);ok('start task',t1.status==='进行中');click('toggle',t1.id);click('toggle',t2.id);ok('all tasks done is not auto resolution',p.status==='处理中');
click('resolve',p.id);fill('resolution','   ');submit();ok('blank resolution rejected',document.querySelector('#form-error').textContent==='请填写验证结论。');
fill('resolution','连续观察一周，重复步骤已经减少。');submit();ok('explicit verification closes issue',p.status==='已解决');
click('nav','review');ok('review visible',document.querySelector('#app').textContent.includes('连续观察一周'));
click('detail',p.id);click('toggle',t1.id);ok('reopening task reopens issue',p.status==='处理中'&&t1.status==='待办'&&p.resolution.length>0);
click('edit-task',t1.id);fill('title','重新整理');fill('issueId','');fill('due','');submit();ok('edit task to standalone',t1.issueId===null&&t1.due===''&&t1.title==='重新整理');
click('nav','issues');document.querySelector('#search').value='___no_match___';document.querySelector('#search').dispatchEvent(new Event('input',{bubbles:true}));ok('search empty state',document.querySelector('#app').textContent.includes('这里还没有匹配的问题'));
document.querySelector('#search').value='';document.querySelector('#search').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#priority').value='高';document.querySelector('#priority').dispatchEvent(new Event('change',{bubbles:true}));ok('priority filter',document.querySelectorAll('.list-issue').length===1);
click('new');fill('title','类型切换保留标题');document.querySelector('#kind').value='task';document.querySelector('#kind').dispatchEvent(new Event('change',{bubbles:true}));ok('record type preserves title',document.querySelector('[name=title]').value==='类型切换保留标题');click('close');
click('nav','today');ok('undated task excluded today',!document.querySelector('#app').textContent.includes('重新整理'));
const setter=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('simulated quota')};click('new');fill('title','仅内存问题');submit();ok('storage failure visible',!document.querySelector('#storage-warning').classList.contains('hidden')&&document.querySelector('#storage-warning').textContent.includes('尚未保存'));Storage.prototype.setItem=setter;document.querySelector('#storage-warning').classList.add('hidden');
let exported,filename;const make=URL.createObjectURL,aclick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{exported=b;return make(b)};HTMLAnchorElement.prototype.click=function(){filename=this.download};click('export');URL.createObjectURL=make;HTMLAnchorElement.prototype.click=aclick;const data=JSON.parse(await exported.text());ok('export contains all records',data.issues.length===db.issues.length&&data.tasks.length===db.tasks.length&&filename.endsWith('.json'));
ok('all buttons mapped',Array.from(document.querySelectorAll('button')).every(b=>b.dataset.eventId));
window.restorePrototype();db.issues.push({id:'reload-proof',title:'刷新验证标记',description:'',priority:'低',tag:'测试',status:'待梳理',resolution:'',logs:[]});save();window.browserTestResults=results;
return {passed:results.every(r=>r.passed),cases:results,reloadMarkerSaved:true};
}catch(e){window.restorePrototype();return {passed:false,cases:results,error:String(e)}}}
