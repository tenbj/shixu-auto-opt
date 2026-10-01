"""Isolated local prototype checks; no production API or user storage access."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8767/prototype.html'

def run():
    report = {'version':'1.6.0','environment':'isolated Chromium; local prototype only','checks':[],'measurements':[],'limitations':['未验证iOS Safari、真实软键盘和系统安全区']}
    errors = []
    def passed(name):
        report['checks'].append({'name':name,'passed':True})
        print('PASS '+name,flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in [360,390,430]:
            context = browser.new_context(viewport={'width':width,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
            page = context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(URL)
            expect(page.locator('#app .mobile-task-card').first).to_be_visible()
            metrics = page.evaluate('''() => {const card=document.querySelector('.mobile-task-card'),r=card.getBoundingClientRect();return {width:innerWidth,firstCardTop:r.top,firstCardBottom:r.bottom,documentWidth:document.documentElement.scrollWidth}}''')
            assert metrics['firstCardBottom'] < 844-80, metrics
            assert metrics['documentWidth'] <= width, metrics
            report['measurements'].append(metrics)
            passed(f'{width}px：首页首项行动及操作完整可见')
            if width == 390:
                page.screenshot(path=str(ROOT/'evaluation/mobile-today.png'))
            for view in ['issues','tasks','analysis','review','today']:
                page.locator(f'.mobile-bottom [data-id={view}]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),view
                assert page.locator('.mobile-bottom [aria-current=page]').get_attribute('data-id') == view
                bad = page.locator('#app button,.mobile-bottom button,.mobile-header button').evaluate_all('''els=>els.filter(e=>e.getBoundingClientRect().width&&e.getBoundingClientRect().height<43.5).map(e=>({text:e.textContent,height:e.getBoundingClientRect().height}))''')
                assert not bad,bad
            passed(f'{width}px：五个页面不横向溢出，可见按钮高度至少44px')
            page.locator('.mobile-bottom [data-id=tasks]').click()
            expect(page.locator('.action-table')).to_have_count(0)
            page.locator('#mobile-problem-select').select_option('p1')
            expect(page.locator('#app .mobile-task-card')).to_have_count(1)
            page.locator('[data-action=board-action-status][data-id="待办"]').click()
            expect(page.locator('#app .mobile-task-card')).to_have_count(0)
            expect(page.locator('.empty')).to_be_visible()
            page.locator('[data-action=board-action-status][data-id="全部"]').click()
            page.locator('#mobile-problem-select').select_option('all')
            if width == 390:
                page.screenshot(path=str(ROOT/'evaluation/mobile-tasks.png'))
            passed(f'{width}px：问题选择、状态筛选与空态正确')
            page.locator('[data-action=task-grouping][data-id=calendar]').click()
            expect(page.locator('.calendar-grid')).to_have_count(0)
            expect(page.locator('.mobile-agenda-toolbar')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            before=page.locator('.mobile-agenda-toolbar strong').inner_text()
            page.get_by_role('button',name='下个月',exact=True).click()
            assert page.locator('.mobile-agenda-toolbar strong').inner_text()!=before
            page.get_by_role('button',name='本月',exact=True).click()
            if width == 390:
                page.screenshot(path=str(ROOT/'evaluation/mobile-agenda.png'))
            passed(f'{width}px：日程无横滚且月份切换有效')
            page.locator('.mobile-bottom [data-id=issues]').click()
            page.locator('[data-action=detail][data-id=p1]').first.click()
            dims=page.locator('#modal').evaluate('e=>({width:e.clientWidth,height:e.clientHeight,top:e.getBoundingClientRect().top})')
            assert abs(dims['width']-width)<=1 and dims['top']==0,dims
            page.locator('#modal [data-action=followup]').click()
            expect(page.locator('#child-modal')).to_be_visible()
            page.locator('#child-modal [name=content]').fill('移动端跟进验证：已确认下一步。')
            page.locator('#child-modal [type=submit]').click()
            expect(page.locator('#child-modal')).to_have_count(0)
            expect(page.locator('#modal')).to_contain_text('移动端跟进验证：已确认下一步。')
            if width == 390:
                page.screenshot(path=str(ROOT/'evaluation/mobile-detail.png'))
            page.locator('#modal .modal-head [data-action=close]').click()
            passed(f'{width}px：全屏详情、嵌套跟进保存及返回正确')
            page.locator('.mobile-bottom [data-id=tasks]').click()
            page.locator('[data-action=task-grouping][data-id=issues]').click()
            page.locator('#mobile-problem-select').select_option('p2')
            page.locator('#app .mobile-task-card [data-action=advance]').click()
            expect(page.locator('#app .mobile-task-state')).to_have_text('进行中')
            page.locator('#app .mobile-task-card [data-action=toggle]').click()
            expect(page.locator('#app .mobile-task-state')).to_have_text('已完成')
            page.reload()
            page.locator('.mobile-bottom [data-id=tasks]').click()
            page.locator('#mobile-problem-select').select_option('p2')
            expect(page.locator('#app .mobile-task-state')).to_have_text('已完成')
            passed(f'{width}px：行动开始、完成与刷新持久保存')
            page.locator('.mobile-bottom [data-id=today]').click()
            page.get_by_role('button',name='＋ 随手记',exact=True).click()
            page.locator('#record-form [name=title]').fill('长标题手机阅读验证：'+('需要清楚看到的问题标题，'*8))
            page.locator('#record-form [type=submit]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            page.locator('.mobile-bottom [data-id=issues]').click()
            page.locator('#search').fill('长标题手机阅读验证')
            expect(page.locator('.issue-card')).to_have_count(1)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            passed(f'{width}px：新建与长标题搜索，不横向溢出')
            context.close()
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(URL)
        page.locator('#nav [data-id=tasks]').click()
        expect(page.locator('.desk-layout')).to_be_visible()
        expect(page.locator('.action-row').first).to_be_visible()
        expect(page.locator('.mobile-bottom')).not_to_be_visible()
        page.locator('[data-action=task-grouping][data-id=calendar]').click()
        expect(page.locator('.calendar-grid')).to_be_visible()
        page.screenshot(path=str(ROOT/'evaluation/mobile-desktop-retained.png'))
        passed('1440px：桌面分栏表格与月历保留')
        assert not errors,errors
        passed('全程无JavaScript运行错误')
        report['passed']=True
        (ROOT/'evaluation/mobile-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'passed':True,'checks':len(report['checks']),'measurements':report['measurements']},ensure_ascii=False),flush=True)
        context.close()
        browser.close()

if __name__=='__main__':
    run()
