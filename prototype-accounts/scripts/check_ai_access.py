"""Check onboarding state invariants, recovery, clipboard and navigation."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
checks=[]
def ok(name):checks.append(name)
with sync_playwright() as p:
 browser=p.chromium.launch()
 for width in (360,390,430,537,1440):
  context=browser.new_context(viewport={'width':width,'height':900 if width==1440 else 844},permissions=['clipboard-read','clipboard-write'])
  page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto('http://127.0.0.1:8770/prototype.html?v=8')
  page.locator('#account-auth [name=password]').fill('1234');page.locator('#account-auth button[type=submit]').click()
  before=page.evaluate('JSON.stringify(db)')
  page.locator('[data-account-action=toggle-menu]:visible').click()
  page.locator('[data-account-action=menu-tools]').click()
  expect(page.locator('#account-dropdown')).to_contain_text('导出工作台记录')
  page.locator('[data-account-action=menu-back]').click()
  page.locator('[data-account-action=connections]').click()
  page.locator('#ai-runtime').select_option('workbuddy')
  page.locator('[data-ai-action=copy-prompt]').click()
  copied=page.evaluate('navigator.clipboard.readText()')
  assert 'WorkBuddy' in copied and '待上线' in copied and 'DEMO_' not in copied
  ok(f'{width}: clipboard contains selected runtime and no token')
  page.locator('[data-ai-action=start-demo]').click();page.locator('[data-ai-action=authorize]').click()
  count=page.evaluate('accountNow().connections.length')
  page.locator('[data-ai-action=deny]').click()
  assert page.evaluate('accountNow().connections.length')==count
  page.locator('[data-ai-action=authorize]').click();page.locator('#ai-consent-form button[type=submit]').click()
  assert page.evaluate('accountNow().connections.length')==count+1
  page.locator('[data-ai-action=fail]').click();page.locator('[data-ai-action=verify]').click()
  assert page.evaluate('accountNow().connections.length')==count+1
  expect(page.locator('#account-tabpanel')).to_contain_text('已准备好')
  page.screenshot(path=str(root/f'evaluation/ai-success-{width}.png'))
  ok(f'{width}: denial creates none; retry reuses authorized device')
  page.locator('[data-ai-action=devices]').click()
  page.locator('[data-account-action=revoke-access]').click();page.locator('[data-account-action=confirm-revoke]').click()
  assert page.evaluate('accountNow().connections[0].enabled') is False
  assert page.evaluate('JSON.stringify(db)')==before
  ok(f'{width}: revocation affects device only; business records unchanged')
  page.locator('#account-modal .account-panel-close').click()
  expect(page.locator('[data-account-action=toggle-menu]:visible')).to_be_focused()
  page.locator('[data-account-action=toggle-menu]:visible').click();page.locator('[data-account-action=settings]').click()
  page.locator('#account-profile-form [name=displayName]').fill('未保存草稿')
  page.once('dialog',lambda dialog:dialog.dismiss())
  page.locator('#account-modal .account-panel-close').click()
  expect(page.locator('#account-modal')).to_be_visible()
  expect(page.locator('#account-profile-form [name=displayName]')).to_have_value('未保存草稿')
  page.once('dialog',lambda dialog:dialog.accept());page.locator('#account-modal .account-panel-close').click()
  page.locator('[data-account-action=toggle-menu]:visible').click();page.locator('[data-account-action=connections]').click()
  page.locator('#account-tab-quick').focus();page.keyboard.press('ArrowRight')
  expect(page.locator('#account-tab-list')).to_have_attribute('aria-selected','true')
  ok(f'{width}: focus restoration, draft cancel and keyboard tabs')
  page.locator('#account-tab-server').click();page.locator('#ai-config-runtime').select_option('codex')
  page.locator('[data-account-action=new-access]').click();page.locator('#account-access-form [name=name]').fill('专属电脑')
  page.locator('#account-access-form button[type=submit]').click()
  with page.expect_download() as pending:page.locator('[data-ai-action=download-issued]').click()
  download=pending.value
  assert download.suggested_filename=='shixu-demo.toml'
  assert '[mcp_servers.shixu]' in Path(download.path()).read_text(encoding='utf-8')
  ok(f'{width}: runtime-specific config download')
  assert not errors,errors
  context.close()
 browser.close()
report={'passed':True,'checks':checks,'scope':'Offline prototype in Chromium; no real installation, authorization, MCP or business writes; no physical mobile keyboard test'}
(root/'evaluation/ai-access-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':True,'checks':len(checks)}))
