const fs=require('fs'),vm=require('vm'),assert=require('assert');
const s=fs.readFileSync(require('path').join(__dirname,'../prototype.html'),'utf8');
const ctx={db:{issues:[{id:'p',status:'已解决'},{id:'q',status:'处理中'}],tasks:[{id:'a',issueId:'p',status:'已完成',order:2},{id:'b',issueId:'q',status:'待办',order:1},{id:'c',issueId:null,status:'待办',order:0}]},taskActionStatus:'全部',taskIssueStatus:'全部'};ctx.filteredTasks=()=>ctx.db.tasks;vm.createContext(ctx);
vm.runInContext(s.slice(s.indexOf('function boardTasks'),s.indexOf('function calendarBoard')),ctx);
assert.equal(ctx.boardTasks().length,3);ctx.taskIssueStatus='已解决';assert.equal(ctx.boardTasks().length,2);ctx.taskActionStatus='已完成';assert.equal(ctx.boardTasks()[0].id,'a');ctx.taskActionStatus='待办';assert.equal(ctx.boardTasks()[0].id,'c');
const feb=ctx.calendarDays('2024-02');assert.equal(feb.length,42);assert.equal(feb[0],'2024-01-29');assert(feb.includes('2024-02-29'));assert.equal(ctx.calendarDays('2026-01')[0],'2025-12-29');assert.equal(ctx.calendarDays('2026-10')[0],'2026-09-28');assert.equal(ctx.db.tasks[0].order,2);
console.log('日历与筛选10项断言通过');
