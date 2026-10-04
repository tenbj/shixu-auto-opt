"""真实浏览器与API回读：通用身份、AI代录、模型快照、组合筛选、跨会话持久化。仅隔离服务。"""
import argparse,json
from pathlib import Path
from uuid import uuid4
from http_auth import Session
import httpx
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]


def run(url):
    api=Session(url)
    expect.set_options(timeout=20000)
    api=api
    health=api.get('/api/health').raise_for_status().json()
    assert health['backend']=='sqlite-test' or health['database'].endswith('_test')
    checks=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        for width in [1440,360,390,430]:
            page=browser.new_page(viewport=dict(width=width,height=1000 if width==1440 else 844))
            page.set_default_timeout(20000)
            page.on('pageerror',lambda e:errors.append(str(e)))
            api.cookies(page.context);page.goto(url);expect(page.locator('#sync-state')).to_contain_text('已同步')
            expect(page.locator('.account-pill:visible')).to_be_visible()
            suffix=str(uuid4())[:6]
            def new_profile(name,agent=False):
                page.evaluate("openAccountPanel('settings')");page.locator('[data-account-action=account-tab][data-id=identity]').click();page.locator('#account-modal [data-action=identity-settings]').click()
                page.locator('dialog[open] [data-action="add-profile"]').click()
                page.locator('[name="profileName"]').fill(name)
                if agent:
                    page.locator('[name="profileKind"]').select_option('agent')
                    page.locator('[name="profileVia"]').select_option('__custom__')
                    page.locator('[name="profileCustomTool"]').fill('Browser tool '+suffix)
                    page.locator('[name="profileModel"]').fill('GPT-6.1 Sol')
                    page.locator('[name="profileProvider"]').fill('OpenAI')
                page.locator('#profile-form [type=submit]').click()
                expect(page.locator('#profile-form')).to_be_hidden();page.locator('[data-account-action=close-account-panel]').click()
            human='Elias-'+suffix;new_profile(human)
            new_profile('Codex-'+suffix,True)
            identities=api.get('/api/identities').json()['items']
            h=next(x for x in identities if x['name']==human)
            a=next(x for x in identities if x['name']=='Codex-'+suffix)
            page.locator('#app [data-action="new"]').first.click()
            page.locator('[name="title"]').fill('委托创建-'+suffix)
            page.locator('.creation-config summary').click()
            page.locator('[name="creationPerson"]').select_option(h['id'])
            page.locator('#record-form [type=submit]').click()
            expect(page.locator('#record-form')).to_be_hidden()
            record=next(x for x in api.get('/api/issues').json()['items'] if x['title']=='委托创建-'+suffix)
            assert record['createdByActorId']==a['id'] and record['initiatedByPersonId']==h['id']
            assert record['modelInfo']==dict(name='GPT-6.1 Sol',provider='OpenAI')
            page.locator('nav:visible [data-action="nav"][data-id="issues"]').click()
            card=page.locator('.issue-card').filter(has_text='委托创建-'+suffix)
            expect(card.locator('.creator-line')).to_contain_text(human)
            expect(card.locator('.creator-line')).to_contain_text('GPT-6.1 Sol')
            page.locator('[aria-label="按创建人筛选"]').select_option(h['id'])
            page.locator('[aria-label="按创建来源筛选"]').select_option(a['via'])
            expect(page.locator('.issue-card')).to_have_count(1)
            card.locator('[data-action="detail"]').first.click()
            expect(page.locator('dialog[open] .creation-detail')).to_contain_text('OpenAI')
            page.locator('dialog[open] [aria-label="关闭弹窗"]').click()
            # Rename/default changes affect new records only; cannot change identity kind.
            page.evaluate("openAccountPanel('settings')");page.locator('[data-account-action=account-tab][data-id=identity]').click();page.locator('#account-modal [data-action=identity-settings]').click()
            page.locator(f'[data-action="edit-profile"][data-id="{a["id"]}"]').click()
            expect(page.locator('[name="profileKind"]')).to_be_disabled()
            page.locator('[name="profileModel"]').fill('后续模型')
            page.locator('[name="profileVia"]').select_option('codex')
            page.locator('#profile-form [type=submit]').click()
            expect(page.locator('#profile-form')).to_be_hidden();page.locator('[data-account-action=close-account-panel]').click()
            assert api.get('/api/issues/'+record['id']).json()['item']['modelInfo']['name']=='GPT-6.1 Sol'
            assert api.get('/api/workspace').json()['data']['customTools'][a['via']]=='Browser tool '+suffix
            expect(page.locator('.creator-line:visible').filter(has_text='Browser tool '+suffix).first).to_be_visible()
            page.locator('nav:visible [data-action="nav"][data-id="tasks"]').click()
            page.locator('#app [data-action="new-task"]').first.click()
            page.locator('[name="title"]').fill('自主行动-'+suffix)
            page.locator('#record-form [type=submit]').click()
            expect(page.locator('#record-form')).to_be_hidden()
            task=next(x for x in api.get('/api/tasks').json()['items'] if x['title']=='自主行动-'+suffix)
            assert task['modelInfo']['name']=='后续模型' and task['initiatedByPersonId'] is None
            page.locator('[aria-label="按创建人筛选"]').select_option(a['id'])
            page.locator('[aria-label="按创建来源筛选"]').select_option('codex')
            expect(page.locator('#app')).to_contain_text('自主行动-'+suffix)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/f'verification/creator-{width}.png'),full_page=True)
            page.reload();expect(page.locator('#sync-state')).to_contain_text('已同步')
            other=browser.new_page();api.cookies(other.context);other.goto(url)
            expect(other.locator('#sync-state')).to_contain_text('已同步')
            other.evaluate("openAccountPanel('settings')");other.locator('[data-account-action=account-tab][data-id=identity]').click();other.locator('#account-modal [data-action=identity-settings]').click()
            expect(other.locator('.identity-list')).to_contain_text(human)
            other.close();page.close()
            checks.append(dict(viewport=width,passed=True,scope='服务端通用身份；人类发起+AI工具+模型；普通修改保留快照；新建默认模型；问题与行动筛选；刷新和新浏览器持久化'))
        browser.close()
    assert not errors,errors
    report=dict(passed=True,backend=health['backend'],checks=checks,browser_errors=errors,business_production_writes=0)
    (ROOT/'verification/creator-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);run(p.parse_args().url)
