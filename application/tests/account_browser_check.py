"""账号原型v7真实浏览器验收，仅合成账号。"""
import argparse,json
from pathlib import Path
from uuid import uuid4
import httpx
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
def expect_mobile_account_position(page):
 # Login can replace the account button while its identity profile is saved.
 # Resolve the current element and measure it in the same browser task.
 page.wait_for_function("""() => {
  const button = document.querySelector('.mobile-header .account-pill');
  const box = button?.getBoundingClientRect();
  if (!box || box.width <= 0 || box.height <= 0) return false;
  const rightGap = window.innerWidth - box.right;
  return rightGap >= 0 && rightGap < 35;
 }""", timeout=20000).dispose()

def run(url):
 expect.set_options(timeout=20000)
 checks=[];errors=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  for width in [1440,537,390,360]:
   page=browser.new_page(viewport=dict(width=width,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
   username='ui_'+uuid4().hex[:12];password=uuid4().hex
   page.goto(url);page.locator('[data-account-action=register-mode]').click()
   page.locator('[name=username]').fill(username);page.locator('[name=displayName]').fill('验收账号')
   page.locator('[name=password]').fill(password);page.locator('[name=confirm]').fill(password)
   page.locator('#account-auth-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_contain_text('验收账号')
   expect(page.locator('#account-auth')).to_be_hidden()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   if width<700:
    expect_mobile_account_position(page)
    expect(page.locator('.mobile-header [data-action=mobile-more]')).to_be_hidden()
   page.locator('nav:visible [data-id=issues]').click();page.locator('#search').fill('保留筛选')
   page.locator('.account-pill:visible').click()
   page.evaluate('window.__accountTrigger=[...document.querySelectorAll(".account-pill")].find(x=>x.getClientRects().length); render()')
   assert page.evaluate('window.__accountTrigger.isConnected')
   expect(page.locator('#account-dropdown')).to_be_visible()
   page.locator('[data-account-action=menu-tools]').click()
   expect(page.locator('#account-dropdown')).to_contain_text('工作台工具')
   page.locator('[data-account-action=menu-back]').click();page.locator('#account-dropdown [data-account-action=settings]').click()
   expect(page.locator('#account-modal')).to_be_visible();expect(page.locator('#account-modal [role=tab]')).to_have_count(3)
   page.locator('#account-profile-form [name=displayName]').fill('更新账号');page.locator('#account-profile-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_contain_text('更新账号')
   page.locator('#account-profile-form [name=displayName]').fill('未保存名称');page.once('dialog',lambda d:d.dismiss());page.locator('[data-account-action=close-account-panel]').click();expect(page.locator('#account-modal')).to_be_visible();page.once('dialog',lambda d:d.accept());page.locator('[data-account-action=account-tab][data-id=password]').click();expect(page.locator('#account-password-form')).to_be_visible()
   page.locator('[data-account-action=close-account-panel]').click();expect(page.locator('#search')).to_have_value('保留筛选')
   page.locator('.account-pill:visible').click();page.locator('#account-dropdown [data-account-action=connections]').click()
   expect(page.locator('#account-modal [role=tab]')).to_have_count(3)
   page.locator('[role=tab][data-id=server]').click();page.locator('[data-account-action=new-access]').click()
   page.locator('#account-access-form [name=name]').fill('浏览器验收只读端');page.locator('#account-access-form [name=scope]').select_option('read')
   page.locator('#account-access-form [type=submit]').click();expect(page.locator('#issued-config')).to_be_visible()
   config=json.loads(page.locator('#issued-config').input_value())['mcpServers']['shixu']
   with httpx.Client(base_url=url,headers=config['headers'],trust_env=False) as client:
    assert client.get('/api/issues').raise_for_status().json()['items']==[]
    assert client.post('/api/issues',json=dict(title='禁止',expected_version=1,request_id=str(uuid4()))).status_code==403
    page.locator('#modal .modal-head [data-action=close]').click();page.locator('[data-account-action=revoke-access]').click();page.locator('[data-account-action=confirm-revoke]').click()
    expect(page.locator('#account-modal')).to_contain_text('已撤销');assert client.get('/api/workspace').status_code==401
   page.locator('[data-account-action=close-account-panel]').click()
   page.screenshot(path=str(ROOT/f'verification/account-{width}.png'),full_page=True)
   page.locator('.account-pill:visible').click();page.locator('#account-dropdown [data-account-action=logout]').click();expect(page.locator('#account-auth')).to_be_visible();expect(page.locator('.account-pill:visible')).to_have_count(0)
   page.locator('[name=username]').fill(username);page.locator('[name=password]').fill(password);page.locator('#account-auth-form [type=submit]').click();expect(page.locator('#account-auth')).to_be_hidden()
   assert not page.evaluate('Object.values(localStorage).some(x=>x.includes('+json.dumps(password)+'))')
   checks.append(dict(width=width,passed=True,scope='注册/退出/登录、右上角账号卡片、二级菜单返回、弹窗Tab与筛选保留、PAT发放回读/只读/撤销'))
   page.close()
  browser.close()
 assert not errors,errors
 report=dict(passed=True,checks=checks,browser_errors=errors,production_writes=0)
 (ROOT/'verification/account-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);run(p.parse_args().url)
