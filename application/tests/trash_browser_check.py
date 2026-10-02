"""桌面与三种手机尺寸，真实HTTP软删除/刷新/同批恢复。仅专属验证库。"""
import argparse, json
from pathlib import Path
from uuid import uuid4
import httpx
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
def run(url):
    health=httpx.get(url+'/api/health',trust_env=False).raise_for_status().json()
    assert health['backend']=='sqlite-test' or health['database'].endswith('_test')
    checks=[]; errors=[]
    def write(path,**body):
        rev=httpx.get(url+'/api/workspace',trust_env=False).json()['revision']
        return httpx.post(url+path,json=dict(body,expected_version=rev,request_id=str(uuid4())),trust_env=False).raise_for_status().json()['resource']
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        for width in [1440,360,390,430]:
            issue=write('/api/issues',title=f'回收站浏览器{width}-'+str(uuid4())[:8])
            write('/api/issues/'+issue['id']+'/transitions',action='triage',nextStep='真实下一步',successCriteria='恢复原编号')
            task=write('/api/tasks',title='同批恢复行动',issueId=issue['id'])
            context=browser.new_context(viewport=dict(width=width,height=900))
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);expect(page.locator('#sync-state' if width>700 else '#mobile-sync-state')).to_contain_text('已同步')
            nav='#nav' if width>700 else '.mobile-bottom'
            page.locator(nav+' [data-id=issues]').click()
            page.locator('#search').fill(issue['title'])
            expect(page.locator('.issue-card')).to_have_count(1)
            expect(page.locator('.issue-next')).to_be_hidden()
            page.locator('[data-next-toggle]').click();expect(page.locator('.issue-next')).to_be_visible()
            page.locator('[data-next-toggle]').click();expect(page.locator('.issue-next')).to_be_hidden()
            page.locator('[data-action=issue-menu]').click()
            expect(page.locator('.compact-menu')).to_be_visible()
            if width<=700:
                box=page.locator('.compact-menu').bounding_box()
                assert abs(box['x'])<1 and abs(box['width']-width)<1 and abs(box['y']+box['height']-900)<2
            page.locator('.compact-menu [data-action=delete-issue]').click()
            expect(page.locator('#trash-form')).to_contain_text('服务端')
            page.locator('#trash-form [type=submit]').click();expect(page.locator('#modal')).not_to_be_visible()
            trash=httpx.get(url+'/api/trash',trust_env=False).json()
            deleted=next(x for x in trash['issues'] if x['id']==issue['id'])
            child=next(x for x in trash['tasks'] if x['id']==task['id'])
            assert deleted['deletionBatch']==child['deletionBatch']
            assert deleted['number']==issue['number'] and child['sequence']==task['sequence']
            page.reload();expect(page.locator('#sync-state' if width>700 else '#mobile-sync-state')).to_contain_text('已同步')
            if width>700: page.locator('#nav [data-id=trash]').click()
            else:
                page.locator('[data-action=mobile-more]').click()
                page.locator('#modal [data-action=open-trash]').click()
            expect(page.locator('[data-action=restore-issue][data-id="'+issue['id']+'"]')).to_be_visible()
            assert page.locator('[data-action=restore-task][data-id="'+task['id']+'"]').count()==0
            page.locator('[data-action=restore-issue][data-id="'+issue['id']+'"]').click()
            page.locator('#trash-form [type=submit]').click();expect(page.locator('#modal')).not_to_be_visible()
            restored=httpx.get(url+'/api/issues/'+issue['id'],trust_env=False).raise_for_status().json()
            assert restored['item']['number']==issue['number']
            assert next(x for x in restored['tasks'] if x['id']==task['id'])['sequence']==task['sequence']
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'verification'/f'trash-{width}.png'),full_page=True)
            checks.append(dict(width=width,passed=True,scope='默认隐藏/全局切换、紧凑菜单、同批删除、刷新回收站、整批恢复、原编号保留'))
            context.close()
        browser.close()
    assert not errors,errors
    report=dict(passed=True,backend=health['backend'],checks=checks,errors=errors,mock=False)
    (ROOT/'verification/trash-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True)
    run(parser.parse_args().url)
