from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
report={'passed':False,'checks':[],'errors':[],'scope':'isolated local HTML; desktop/mobile Chromium simulation'}
def check(name,value=True):
 assert value,name
 report['checks'].append({'name':name,'passed':True})
 print(name,flush=True)
try:
 with sync_playwright() as p:
  browser=p.chromium.launch()
  for width in [1440,390]:
   ctx=browser.new_context(viewport={'width':width,'height':1000 if width>700 else 844},accept_downloads=True)
   page=ctx.new_page();page.set_default_timeout(30000);page.on('pageerror',lambda e:report['errors'].append(str(e)))
   page.goto((ROOT/'prototype.html').as_uri())
   check(f'{width}: exactly one unknown demo record',page.evaluate("[...db.issues,...db.tasks].filter(x=>x.createdVia==='unknown').length===1"))
   check(f'{width}: known samples Codex/GPT-6/OpenAI',page.evaluate("[...db.issues,...db.tasks].filter(x=>x.createdVia!=='unknown').every(x=>x.creatorName==='Codex'&&x.createdVia==='codex'&&x.modelInfo.name==='GPT-6'&&x.modelInfo.provider==='OpenAI')"))
   page.locator('nav:visible [data-action="nav"][data-id="issues"]').click()
   page.screenshot(path=str(ROOT/f'evaluation/creator-{width}.png'),full_page=True)
   page.locator('.identity-button:visible').click();page.locator('dialog[open] [data-action="add-profile"]').click()
   page.locator('dialog[open] [name="profileName"]').fill('任意成员甲');page.locator('dialog[open] button[type="submit"]').click()
   expect(page.locator('.identity-button:visible')).to_contain_text('任意成员甲')
   humanId=page.evaluate('activeProfileId');check(f'{width}: arbitrary human profile',humanId.startswith('person:'))
   page.locator('#app [data-action="new"]').click();page.locator('dialog[open] [name="title"]').fill('人类默认记录');page.locator('dialog[open] button[type="submit"]').click()
   item=page.evaluate("db.issues.find(x=>x.title==='人类默认记录')")
   check(f'{width}: manual defaults',item['creatorName']=='任意成员甲' and item['createdByActorId']==humanId and item['modelInfo'] is None)
   page.locator('.identity-button:visible').click();page.locator('dialog[open] [data-action="use-profile"][data-id="agent:codex"]').click()
   page.locator('.issue-card:has-text("每天整理报表") .issue-title').click();page.locator('dialog[open] [data-action="new-linked"]').click()
   page.locator('dialog[open] .creation-config summary').click();page.locator('dialog[open] [name="creationPerson"]').select_option(humanId)
   page.locator('dialog[open] [name="modelName"]').fill('test-model-snapshot');page.locator('dialog[open] [name="title"]').fill('成员委托AI行动');page.locator('dialog[open] button[type="submit"]').click()
   task=page.evaluate("db.tasks.find(x=>x.title==='成员委托AI行动')")
   check(f'{width}: AI actor and human initiator and model',task['initiatedByPersonId']==humanId and task['createdByActorId']=='agent:codex' and task['modelInfo']['name']=='test-model-snapshot')
   page.locator('dialog[open] .modal-head [data-action="close"]').click();page.locator('nav:visible [data-action="nav"][data-id="tasks"]').click()
   page.locator('[aria-label="按创建人筛选"]').select_option(humanId);page.locator('[aria-label="按创建来源筛选"]').select_option('codex')
   check(f'{width}: combined filters',page.evaluate('boardTasks().length')==1)
   page.locator('#app [data-action="edit-task"][data-id="'+task['id']+'"]').first.click();expect(page.locator('dialog[open] .creation-detail')).to_contain_text('test-model-snapshot')
   page.locator('dialog[open] [name="title"]').fill('已编辑行动');page.locator('dialog[open] button[type="submit"]').click()
   after=page.evaluate('(id)=>db.tasks.find(t=>t.id===id)',task['id'])
   check(f'{width}: immutable creation',all(after[k]==task[k] for k in ['createdByActorId','creatorName','initiatedByPersonId','createdVia','createdAt','modelInfo']))
   page.locator('.identity-button:visible').click();page.locator('dialog[open] [data-action="edit-profile"][data-id="agent:codex"]').click()
   page.locator('dialog[open] [name="profileName"]').fill('我的AI助手');page.locator('dialog[open] [name="profileModel"]').fill('next-model');page.locator('dialog[open] button[type="submit"]').click()
   check(f'{width}: profile rename keeps old snapshots',page.evaluate("db.tasks.find(x=>x.title==='已编辑行动').modelInfo.name==='test-model-snapshot'&&db.tasks.find(x=>x.id==='t1').creatorName==='Codex'"))
   page.reload();check(f'{width}: profile persistence',page.evaluate("currentProfile().name==='我的AI助手'&&profiles.some(x=>x.name==='任意成员甲')"))
   with page.expect_download() as d:page.evaluate("document.querySelector('[data-action=export]').click()")
   data=json.loads(Path(d.value.path()).read_text(encoding='utf-8'))
   check(f'{width}: export includes profiles and model',any(x['name']=='我的AI助手' for x in data['identityProfiles']) and any(t.get('modelInfo',{}).get('name')=='test-model-snapshot' for t in data['tasks'] if t.get('modelInfo')))
   check(f'{width}: no horizontal overflow',page.evaluate('document.documentElement.scrollWidth')<=width)
   ctx.close()
  browser.close()
 report['passed']=not report['errors']
except Exception as e:report['errors'].append(str(e))
(ROOT/'evaluation/creator-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'errors':report['errors']},ensure_ascii=False),flush=True)
raise SystemExit(0 if report['passed'] else 1)