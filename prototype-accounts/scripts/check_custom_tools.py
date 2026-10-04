from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[2]
report={'passed':False,'checks':[],'errors':[]}
with sync_playwright() as p:
 browser=p.chromium.launch()
 try:
  for folder in ['prototype','prototype-accounts']:
   for width in [360,390,430,1440]:
    ctx=browser.new_context(viewport={'width':width,'height':1000 if width>700 else 844})
    page=ctx.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto((ROOT/folder/'prototype.html').resolve().as_uri())
    if folder=='prototype-accounts':
     page.locator('#account-auth [name=password]').fill('1234');page.locator('#account-auth button[type=submit]').click()
    def form():
     page.evaluate('profileForm()')
     page.locator('[name=profileName]').fill('测试助手')
     page.locator('[name=profileKind]').select_option('agent')
     page.locator('[name=profileVia]').select_option('__custom__')
    form();field=page.locator('[name=profileCustomTool]');expect(field).to_be_visible()
    field.fill('   ');page.locator('#profile-form button[type=submit]').click()
    expect(page.locator('#form-error')).to_contain_text('请输入')
    field.fill(' Cursor ')
    page.screenshot(path=str(ROOT/folder/f'evaluation/custom-tool-form-{width}.png'))
    page.locator('#profile-form button[type=submit]').click()
    source=page.evaluate('currentProfile().via');assert source.startswith('custom:')
    page.evaluate('profileForm(activeProfileId)');expect(page.locator('[name=profileVia]')).to_have_value(source)
    page.locator('#profile-form button[type=submit]').click()
    page.reload();assert page.evaluate("TOOLS["+json.dumps(source)+"]")=='Cursor'
    page.evaluate('identitySettings()');expect(page.locator('.identity-list')).to_contain_text('Cursor')
    page.evaluate('closeDialog()');form();page.locator('[name=profileCustomTool]').fill('cursor')
    page.locator('#profile-form button[type=submit]').click();assert page.evaluate('currentProfile().via')==source
    page.locator('nav:visible [data-action=nav][data-id=issues]').click()
    page.locator('#app [data-action=new]').click()
    page.locator('dialog[open] [name=title]').fill('自定义工具问题')
    page.locator('#profile-form').count()
    page.locator('dialog[open] button[type=submit]').click()
    item=page.evaluate("db.issues.find(x=>x.title==='自定义工具问题')")
    assert item['createdVia']==source
    expect(page.locator('.issue-card:has-text("自定义工具问题") .creator-line')).to_contain_text('Cursor')
    page.locator('[aria-label="按创建来源筛选"]').select_option(source)
    expect(page.locator('.issue-card:has-text("自定义工具问题")')).to_be_visible()
    page.evaluate('profiles.forEach(x=>{if(x.via.startsWith("custom:")){x.via="codex";x.toolName="Codex"}});persistProfiles()')
    page.reload()
    assert page.evaluate("TOOLS["+json.dumps(source)+"]")=='Cursor'
    assert page.evaluate("db.issues.find(x=>x.title==='自定义工具问题').createdVia")==source
    page.screenshot(path=str(ROOT/folder/f'evaluation/custom-tool-{width}.png'))
    # Failure must leave the draft open and restore the in-memory registry.
    form();page.locator('[name=profileCustomTool]').fill('失败草稿')
    page.evaluate("window.originalPersistProfiles=persistProfiles;persistProfiles=()=>false")
    page.locator('#profile-form button[type=submit]').click()
    expect(page.locator('#form-error')).to_contain_text('保存失败')
    assert page.evaluate("!Object.values(TOOLS).includes('失败草稿')")
    expect(page.locator('[name=profileCustomTool]')).to_have_value('失败草稿')
    page.evaluate('persistProfiles=window.originalPersistProfiles;closeDialog()')
    assert page.evaluate('document.documentElement.scrollWidth')<=width
    if folder=='prototype-accounts':
     page.evaluate("loadAccountWorkspace({id:'custom-isolation-test',displayName:'隔离账号'})")
     assert page.evaluate("!Object.values(TOOLS).includes('Cursor')")
     page.evaluate("loadAccountWorkspace({id:'test',displayName:'test'})")
     assert page.evaluate("Object.values(TOOLS).includes('Cursor')")
     assert page.evaluate("db.issues.find(x=>x.title==='自定义工具问题').createdVia")==source
    report['checks'].append(f'{folder} {width}: custom, validation, edit, reload, dedup, record, filter, failure'+(', account isolation' if folder=='prototype-accounts' else ''))
    print(report['checks'][-1],flush=True)
    ctx.close()
  report['passed']=not report['errors']
 except Exception as e:report['errors'].append(str(e))
 finally:
  (ROOT/'prototype-accounts/evaluation/custom-tools-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  browser.close()
print(json.dumps(report,ensure_ascii=False),flush=True)
raise SystemExit(0 if report['passed'] else 1)
