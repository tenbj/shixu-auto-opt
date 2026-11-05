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

def expect_boot_notice(page,url,fail,text):
 calls=[]
 def handle(route):
  calls.append(route.request.url)
  if len(calls)==1:fail(route)
  else:route.continue_()
 page.route('**/api/auth/me',handle)
 page.goto(url)
 notice=page.locator('#account-auth-error')
 expect(notice).to_contain_text(text)
 expect(notice.locator('button[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]')).to_have_text('重试')
 notice.locator('button[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]').click()
 expect(page.locator('#account-auth')).to_be_visible();expect(page.locator('#account-auth-form')).to_be_visible()
 expect(page.locator('[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]')).to_have_count(0)
 assert len(calls)==2,calls
 page.unroute('**/api/auth/me')

def expect_boot_faults(url,errors):
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  for fail,text in [(lambda route:route.fulfill(status=502,content_type='text/html',body='<html>bad gateway</html>'),'服务暂不可用，请稍后重试'),(lambda route:route.abort('timedout'),'连接超时，请检查网络后重试'),(lambda route:route.fulfill(status=403,content_type='application/json',body='{"detail":"账号已停用"}'),'账号已停用')]:
   page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
   expect_boot_notice(page,url,fail,text);page.close()
  browser.close()

def expect_boot_signed_out(url,errors):
 # 401 returns to the login screen and does not surface the failure or its detail.
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/auth/me',lambda route:route.fulfill(status=401,content_type='application/json',body='{"detail":"未登录"}'))
  page.goto(url)
  page.wait_for_function("() => document.documentElement.dataset.accountBoot==='complete'")
  expect(page.locator('#account-auth')).to_be_visible();expect(page.locator('#account-auth-form')).to_be_visible()
  expect(page.locator('#account-boot-status')).to_have_count(0)
  notice=page.locator('#account-auth-error')
  expect(notice).to_have_text('')
  expect(page.locator('[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]')).to_have_count(0)
  expect(notice).not_to_contain_text('未登录');expect(notice).not_to_contain_text('登录状态检查失败');expect(notice).not_to_contain_text('连接超时')
  page.unroute('**/api/auth/me');page.close();browser.close()

def expect_boot_page_fault(url,errors):
 # A page exception after a successful JSON parse is not a network timeout.
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(url)
  page.wait_for_function("() => document.documentElement.dataset.accountBoot==='complete'")
  page.route('**/api/auth/me',lambda route:route.fulfill(status=200,content_type='application/json',body='{"user":{"id":"page-fault","displayName":"页面错误"},"csrf":"t"}'))
  with page.expect_console_message(lambda msg:msg.type=='error' and 'render failed' in msg.text):
   page.evaluate("""() => { loginAccount = async () => { throw new TypeError('render failed') }; return bootAccount() }""")
  notice=page.locator('#account-auth-error')
  expect(notice).to_contain_text('页面出错，请刷新重试')
  expect(notice).not_to_contain_text('连接超时')
  expect(notice.locator('button[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]')).to_have_text('重试')
  page.unroute('**/api/auth/me');page.close();browser.close()

def expect_boot_slow_login(url,errors):
 # Hold /api/auth/me for about 10s, then let the real session succeed. Client timeout stays 15s.
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
  username='slow_'+uuid4().hex[:12];secret=uuid4().hex
  page.goto(url)
  page.locator('[data-account-action=register-mode]').click()
  page.locator('[name=username]').fill(username);page.locator('[name=displayName]').fill('慢登录')
  page.locator('[name=password]').fill(secret);page.locator('[name=confirm]').fill(secret)
  page.locator('#account-auth-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_contain_text('慢登录')
  held=[]
  page.route('**/api/auth/me',lambda route:held.append(route))
  page.reload(wait_until='domcontentloaded')
  expect(page.locator('#sync-state')).to_have_text('同步中')
  expect(page.locator('.account-pill:visible')).to_contain_text('慢登录')
  expect(page.locator('#account-auth-form')).to_be_hidden()
  page.wait_for_timeout(10000)
  assert len(held)==1,held
  held[0].continue_()
  expect(page.locator('.account-pill:visible')).to_contain_text('慢登录')
  expect(page.locator('#account-auth')).to_be_hidden()
  expect(page.locator('[data-event-id="EVT-ACCOUNT-BOOT-RETRY"]')).to_have_count(0)
  expect(page.get_by_role('heading',name='把困扰理清，把今天过好。')).to_be_visible()
  page.unroute('**/api/auth/me');page.close();browser.close()

def run(url):
 expect.set_options(timeout=20000)
 checks=[];errors=[]
 expect_boot_faults(url,errors)
 expect_boot_signed_out(url,errors)
 expect_boot_page_fault(url,errors)
 expect_boot_slow_login(url,errors)
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
