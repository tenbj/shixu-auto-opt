// All mobile actions delegate to the existing prototype business rules.
const mobileViewport=matchMedia('(max-width:700px)');
const mobileIcons={today:'<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',issues:'<rect x="5" y="4" width="14" height="16" rx="3"/><path d="M9 9h6M9 13h6M9 17h3"/>',tasks:'<path d="m4 7 2 2 4-4M12 7h8M4 15l2 2 4-4M12 15h8"/>',analysis:'<path d="M5 20V10M12 20V4M19 20v-7"/>',review:'<path d="M4 10a8 8 0 1 1 2 8M4 4v6h6"/><path d="M12 8v5l3 2"/>'};
const mobileAttrs=(html,attrs)=>html.replace(' class=',attrs+' class=');
const mobileSvg=(id)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${mobileIcons[id]}</svg>`;
function mobileTaskCard(t){
 const p=issue(t.issueId),finished=['已完成','已取消'].includes(t.status),waiting=blockedBy(t);
 return `<article class="mobile-task-card ${finished?'finished':''}" data-mobile-task="${esc(t.id)}"><div class="mobile-task-top"><span class="mobile-task-number">${esc(taskCode(t))}</span><span class="mobile-task-state ${t.status==='进行中'?'doing':finished?'done':''}">${esc(t.status)}</span></div>${btn(esc(t.title),'edit-task',t.id,'mobile-task-title')}<div class="mobile-task-meta"><span class="${t.due&&t.due<today&&!finished?'late':''}">${esc(dueLabel(t))}</span>${waiting.length?`<span class="mobile-dependency">等待 ${waiting.length} 项前置</span>`:''}${t.required===false?'<span>后续改进</span>':''}</div>${p?btn('↗ '+esc(issueCode(p))+' · '+esc(p.title),'detail',p.id,'mobile-task-source'):'<span class="mobile-task-source">独立行动</span>'}<div class="mobile-task-footer">${finished?btn('重新打开','toggle',t.id,'secondary'):t.status==='待办'?btn(waiting.length?'查看前置':'开始行动',waiting.length?'task-dependencies':'advance',t.id,'primary'):btn('✓ 完成行动','toggle',t.id,'primary')}${!finished&&t.status==='待办'?btn('完成','toggle',t.id,'complete'):''}${mobileAttrs(btn('···','mobile-task-menu',t.id,'more'),' aria-label="行动更多操作：'+esc(t.title)+'"')}</div></article>`;
}
function mobileTaskMenu(id){
 const t=db.tasks.find(x=>x.id===id);if(!t)return;
 const finished=['已完成','已取消'].includes(t.status),p=issue(t.issueId);
 show('行动操作',`<h3 class="mobile-task-context">${esc(t.title)}</h3><div class="mobile-menu-actions">${btn('编辑标题、日期与属性','edit-task',id)}${btn('设置前置行动','task-dependencies',id)}${!finished&&t.status==='进行中'?btn('退回待办','advance',id):''}${p?btn('查看关联问题','detail',p.id):''}${t.issueId?btn('向上调整顺序','task-up',id)+btn('向下调整顺序','task-down',id):''}${!finished?btn('取消行动','cancel-task',id,'danger'):''}</div>`);
}
function mobileToday(){
 const ts=pending().filter(t=>t.due&&t.due<=today&&!['已暂缓','已关闭'].includes(issue(t.issueId)?.status)).sort((a,b)=>a.due.localeCompare(b.due));
 const focus=active().slice().sort((a,b)=>['高','中','低'].indexOf(a.priority)-['高','中','低'].indexOf(b.priority))[0];
 return `<div class="pagehead mobile-today-head"><div><div class="eyebrow">${new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</div><h1>今天，往前走一步。</h1><p>从一件具体的小事开始。</p></div>${btn('＋ 随手记','new','','primary')}</div><div class="mobile-summary">${[[active().filter(p=>p.status==='待梳理').length,'待梳理','issues'],[pending().filter(t=>t.status==='进行中').length,'进行中','tasks'],[db.issues.filter(p=>p.status==='已解决').length,'已解决','review']].map(([n,label,id])=>btn(`<strong>${n}</strong><span>${label}</span>`,'nav',id,'')).join('')}</div>${db.issues.some(dueReview)?`<div class="review-reminder">${btn(db.issues.filter(dueReview).length+' 个问题到了回看时间 →','status-filter','已暂缓','subtle')}</div>`:''}<section aria-label="今日行动"><div class="mobile-section-title"><h2>今天要推进 <span class="mobile-count">${ts.length}</span></h2>${btn('＋ 添加','new-task','','subtle')}</div><p class="mobile-section-sub">含逾期事项，完成后再看问题是否改善。</p><div class="mobile-task-list">${ts.map(mobileTaskCard).join('')||empty('今天的清单很轻盈','添加一项行动，或给自己留点空白。')}</div>${btn('查看全部行动 →','nav','tasks','subtle')}</section>${focus?`<section class="mobile-focus"><div class="mobile-section-title"><h2>值得关注</h2>${btn('全部问题 →','nav','issues','subtle')}</div><div class="mobile-focus-card"><div class="meta">${numberBadge(focus)}${stateBadge(focus)}</div>${btn(esc(focus.title),'detail',focus.id,'issue-title')}<p>${linked(focus.id).filter(t=>t.status==='已完成').length}/${linked(focus.id).length} 项行动完成 · ${esc(focus.tag)}</p></div></section>`:''}<p class="mobile-footer-hint">行动可以很小，每一次改善都算数。</p>`;
}
function mobileAgenda(ts){
 const dated=ts.filter(t=>t.due&&t.due.startsWith(calendarMonth));
 const days=[...new Set(dated.map(t=>t.due))].sort();
 return `<div class="mobile-agenda-toolbar">${mobileAttrs(btn('‹','calendar-month','-1','secondary'),' aria-label="上个月"')}<strong>${calendarMonth.replace('-','年 ')}月</strong>${mobileAttrs(btn('›','calendar-month','1','secondary'),' aria-label="下个月"')}${btn('本月','calendar-month','today','subtle')}</div><p class="mobile-month-note">按计划日期查看行动</p>${days.map(day=>`<div class="mobile-group-head">${day===today?'今天 · ':day<today?'已过期日期 · ':''}${day.slice(5).replace('-','月 ')}日</div><div class="mobile-task-list">${dated.filter(t=>t.due===day).map(mobileTaskCard).join('')}</div>`).join('')||empty('本月没有已安排的行动','可在行动编辑中设置计划日期，或切换月份。')}<div class="mobile-group-head">未设日期 · ${ts.filter(t=>!t.due).length}</div><div class="mobile-task-list">${ts.filter(t=>!t.due).map(mobileTaskCard).join('')||'<p class="mobile-month-note">没有未设日期的行动</p>'}</div>`;
}
function mobileTaskBoard(){
 const rows=boardTasks(),groups=[{id:'all',title:'全部问题 / 全部行动',ts:rows},...db.issues.map(p=>({id:p.id,p,title:issueCode(p)+' · '+p.title,ts:rows.filter(t=>t.issueId===p.id)})),{id:'independent',title:'独立行动',ts:rows.filter(t=>!t.issueId)}];
 if(!groups.some(g=>g.id===selectedTaskIssue))selectedTaskIssue='all';
 const selected=groups.find(g=>g.id===selectedTaskIssue),ts=selected.ts;
 const tabs=`<div class="analysis-tabs" role="group" aria-label="行动组织方式">${[['issues','列表'],['status','按状态'],['calendar','日程']].map(([id,title])=>btn(title,'task-grouping',id,'analysis-tab '+(taskGrouping===id?'selected':''))).join('')}</div>`;
 const controls=`<div class="mobile-board-tools"><label class="mobile-problem-select">关联问题<select id="mobile-problem-select" data-event-id="EVT-MOBILE-PROBLEM" aria-label="选择关联问题">${groups.map(g=>`<option value="${esc(g.id)}" ${g.id===selectedTaskIssue?'selected':''}>${esc(g.title)}</option>`).join('')}</select></label><div class="mobile-board-status" role="group" aria-label="行动状态">${['全部',...TASK_STATES].map(st=>btn(st+' · '+boardStatusCount('board-action-status',st),'board-action-status',st,'status-chip '+(taskActionStatus===st?'selected':''))).join('')}</div><div class="mobile-board-top"><span class="mobile-month-note">${ts.length} 项行动${selected.p?' · '+esc(selected.p.status):''}</span>${selected.p?btn('查看问题 →','detail',selected.p.id,'subtle'):''}</div></div>`;
 const filter=taskFilter?`<div class="task-filter-bar"><span>${esc(taskFilter.value)}</span>${btn('清除筛选','clear-task-filter','','subtle')}</div>`:'';
 const body=taskGrouping==='calendar'?mobileAgenda(ts):taskGrouping==='status'?TASK_STATES.filter(st=>taskActionStatus==='全部'||taskActionStatus===st).map(st=>`<div class="mobile-group-head">${st} · ${ts.filter(t=>t.status===st).length}</div><div class="mobile-task-list">${ts.filter(t=>t.status===st).map(mobileTaskCard).join('')||'<p class="mobile-month-note">暂无行动</p>'}</div>`).join(''):`<div class="mobile-task-list">${ts.map(mobileTaskCard).join('')||empty('这里还没有匹配的行动','试试其他状态，或添加一项行动。')}</div>`;
 return tabs+filter+controls+body;
}
function render(){
 renderDesktop();
 document.body.dataset.view=view;
 if(!document.querySelector('.mobile-header')){
  document.body.insertAdjacentHTML('afterbegin',`<header class="mobile-header"><div class="mobile-brand"><svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="10" fill="#42684e"/><path d="m8 16 5-3 6 6 5-3" fill="none" stroke="#f6f8f0" stroke-width="2" stroke-linecap="round"/></svg>拾序</div>${mobileAttrs(btn('···','mobile-more','','mobile-more'),' aria-label="更多功能"')}</header><nav class="mobile-bottom" aria-label="移动主导航"></nav>`);
 }
 const names={today:'今日',issues:'问题',tasks:'行动',analysis:'统计',review:'复盘'};
 document.querySelector('.mobile-bottom').innerHTML=Object.keys(names).map(id=>mobileAttrs(btn(mobileSvg(id)+`<span>${names[id]}</span>`,'nav',id,view===id?'active':''),` aria-label="${names[id]}" ${view===id?'aria-current="page"':''}`)).join('');
 if(mobileViewport.matches){
  if(view==='today')document.querySelector('#app').innerHTML=mobileToday();
  if(view==='tasks'){
   document.querySelector('.pagehead h1').textContent='每一步，都算数。';
   document.querySelector('.pagehead p').textContent='选好下一步，然后开始行动。';
   const add=document.querySelector('.pagehead>.primary');add.textContent='＋ 行动';add.dataset.action=selectedTaskIssue!=='all'&&selectedTaskIssue!=='independent'?'new-linked':'new-task';add.dataset.id=add.dataset.action==='new-linked'?selectedTaskIssue:'';
  }
 }
}
document.addEventListener('change',e=>{if(e.target.id==='mobile-problem-select'){selectedTaskIssue=e.target.value;render()}});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-event-id="EVT-ACTION"]');if(!b)return;
 if(b.dataset.action==='mobile-more')show('更多功能',`<div class="mobile-menu-actions">${btn('查看状态流转说明','workflow-guide')}${btn('导出原型记录','export')}${btn('查看统计分析','mobile-go-analysis')}<p>当前为原型体验，记录只保存在此浏览器。</p></div>`);
 if(b.dataset.action==='mobile-task-menu')mobileTaskMenu(b.dataset.id);
 if(b.dataset.action==='mobile-go-analysis'){closeDialog();view='analysis';render();window.scrollTo(0,0)}
 if(b.dataset.action==='nav'){window.scrollTo(0,0)}
});
mobileViewport.addEventListener('change',()=>render());
