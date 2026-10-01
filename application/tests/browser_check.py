"""真实 Chromium + HTTP + SQLite；只连接专用验证端口并创建合成对象。"""
import argparse
import json
from pathlib import Path
from uuid import uuid4
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def run(url):
    backend = httpx.get(url + '/api/health', trust_env=False).raise_for_status().json()['backend']
    report = {'kind': 'real-browser-api-' + backend, 'mock': False, 'simulated_fault': '仅响应丢失场景使用网络拦截模拟', 'checks': []}
    errors = []
    def passed(name):
        report['checks'].append({'name': name, 'passed': True})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator('#sync-state')).to_contain_text('已同步')
        passed('首屏从真实 API 加载')
        page.locator('[data-action=new]').click()
        title = '浏览器合成问题 ' + str(uuid4())[:8]
        page.locator('#record-form [name=title]').fill(title)
        page.locator('#record-form [type=submit]').click()
        expect(page.locator('#modal')).not_to_be_visible()
        data = httpx.get(url + '/api/workspace').json()['data']
        issue = next(p for p in data['issues'] if p['title'] == title)
        identifier = issue['id']
        passed('页面创建问题并通过 API 回读')
        page.reload()
        expect(page.locator('#sync-state')).to_contain_text('已同步')
        page.locator('#nav [data-id=issues]').click()
        page.locator('#search').fill(title)
        expect(page.locator('.list-issue')).to_have_count(1)
        passed('刷新持久化与搜索过滤')
        page.locator(f'[data-action=detail][data-id="{identifier}"]').first.click()
        page.locator('#modal [data-action=triage]').click()
        page.locator('[name=nextStep]').fill('浏览器创建并执行行动')
        page.locator('[name=successCriteria]').fill('页面/API/MCP同一数据')
        page.locator('#workflow-form [type=submit]').click()
        expect(page.locator('#modal')).to_contain_text('待处理')
        passed('页面梳理流转')
        page.locator('#modal [data-action=new-linked]').first.click()
        form = page.locator('#record-form')
        form.locator('[name=title]').fill('浏览器验证行动')
        form.locator('[type=submit]').click()
        expect(page.locator('#child-modal')).not_to_be_visible()
        task = next(t for t in httpx.get(url + '/api/tasks').json()['items'] if t['issueId'] == identifier)
        passed('子弹窗创建关联行动')
        page.locator(f'#modal [data-action=toggle][data-id="{task["id"]}"]').click()
        expect(page.locator('#modal')).to_contain_text('已完成')
        page.locator('#modal [data-action=verify]').click()
        page.locator('[name=treatment]').fill('通过页面完成行动并回读')
        page.locator('[name=verificationMethod]').fill('刷新和 API 独立读取')
        page.locator('#workflow-form [type=submit]').click()
        expect(page.locator('#modal')).to_contain_text('待验证')
        page.locator('#modal [data-action=resolve]').click()
        page.locator('[name=resolution]').fill('真实 Chromium 检查通过，记录已保存')
        page.locator('#workflow-form [type=submit]').click()
        expect(page.locator('#modal')).to_contain_text('已解决')
        passed('页面完成行动、提交验证、确认解决')
        page.locator('#modal [data-action=followup]').first.click()
        page.locator('[name=content]').fill('<img src=x onerror=alert(1)> 纯文本跟进')
        page.locator('#followup-form [type=submit]').click()
        expect(page.locator('#modal')).to_contain_text('<img src=x onerror=alert(1)>')
        assert page.locator('#modal img').count() == 0
        passed('跟进保存与 HTML 安全显示')
        page.locator('#modal .modal-head [data-action=close]').click()
        for view in ['today', 'issues', 'tasks', 'analysis', 'review']:
            page.locator(f'#nav [data-id={view}]').click()
            expect(page.locator('h1')).to_be_visible()
        passed('五个工作视图可用')
        page.locator('#nav [data-id=tasks]').click()
        page.locator('[data-action=task-grouping][data-id=calendar]').click()
        expect(page.locator('.calendar-grid')).to_be_visible()
        passed('行动日历')
        with page.expect_download() as download:
            page.locator('[data-action=export]').click()
        exported = json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        assert any(p['id'] == identifier for p in exported['issues'])
        passed('JSON 导出完整记录')
        page.locator('#nav [data-id=today]').click()
        page.screenshot(path=str(ROOT / 'verification' / 'desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.locator('#nav [data-id=issues]').click()
        page.screenshot(path=str(ROOT / 'verification' / 'mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        passed('390px 布局不横向溢出')
        page.set_viewport_size({'width': 3840, 'height': 2160})
        page.locator('#nav [data-id=tasks]').click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        passed('4K 自适应')
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.locator('[data-action=new]').click()
        page.locator('#record-form [name=title]').fill('冲突草稿')
        revision = httpx.get(url + '/api/workspace').json()['revision']
        httpx.post(url + '/api/issues', json=dict(title='其他客户端的合成写入', expected_version=revision, request_id=str(uuid4()))).raise_for_status()
        page.locator('#record-form [type=submit]').click()
        expect(page.locator('#form-error')).to_contain_text('工作台已更新')
        expect(page.locator('#record-form [name=title]')).to_have_value('冲突草稿')
        passed('并发冲突提示且保留表单草稿')
        page.locator('#record-form [type=submit]').click()
        expect(page.locator('#modal')).not_to_be_visible()
        passed('冲突后明确重试成功')
        # 模拟响应丢失：真实请求已到后端，浏览器未收到响应；同号重试不可重复创建。
        page.locator('[data-action=new]').click()
        lost_title = '响应丢失幂等演示 ' + str(uuid4())[:8]
        page.locator('#record-form [name=title]').fill(lost_title)
        def lose_response(route):
            route.fetch()
            route.abort('failed')
        page.route('**/api/issues', lose_response, times=1)
        page.locator('#record-form [type=submit]').click()
        expect(page.locator('#form-error')).to_contain_text('结果未确认')
        page.locator('#record-form [type=submit]').click()
        expect(page.locator('#modal')).not_to_be_visible()
        assert len(httpx.get(url + '/api/issues', params={'q': lost_title}).json()['items']) == 1
        passed('响应丢失使用同号重试，不重复创建（此项模拟网络故障）')
        assert not errors, errors
        passed('无 JavaScript 运行错误')
        browser.close()
    report['passed'] = True
    (ROOT / 'verification' / 'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8766')
    run(parser.parse_args().url)
