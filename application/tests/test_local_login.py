"""真实生成页 + 拦截响应；不启动后端、不访问数据库。"""
import json
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

KEY = 'shixu-local-user'
OLD = {'id': 'a', 'displayName': '旧账号'}
NEW = {'id': 'b', 'displayName': '新账号', 'password': 'excluded', 'token': 'excluded', 'workspace': {}}
INDEX = (Path(__file__).resolve().parents[1] / 'static/index.html').read_text(encoding='utf-8')
WORKSPACE = {'revision': 1, 'data': {'issues': [], 'tasks': [], 'identityProfiles': [
    {'id': NEW['id'], 'name': NEW['displayName'], 'kind': 'person', 'via': 'manual'}]}}


@pytest.fixture
def screen():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chromium')
        page = browser.new_page(storage_state={'cookies': [], 'origins': [{'origin': 'http://shixu.test', 'localStorage': [{'name': KEY, 'value': json.dumps(OLD)}]}]})
        held, errors = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('http://shixu.test/', lambda r: r.fulfill(content_type='text/html', body=INDEX))
        page.route('**/api/workspace', lambda r: r.fulfill(json=WORKSPACE))
        page.route('**/api/auth/login', lambda r: r.fulfill(json={'user': NEW, 'csrf': 'memory-only'}))
        page.route('**/api/auth/me', lambda r: held.append(r))
        page.goto('http://shixu.test/', wait_until='domcontentloaded')
        expect(page.locator('.account-pill:visible')).to_contain_text(OLD['displayName'])
        expect(page.locator('#sync-state')).to_have_text('同步中')
        assert page.evaluate('loaded') is False
        yield page, held
        browser.close()
        assert not errors


@pytest.mark.parametrize('content_type,width', [('application/json', 1440), ('text/html', 390)])
def test_401_clears_cache(screen, content_type, width):
    page, held = screen
    page.set_viewport_size({'width': width, 'height': 900})
    if width == 390:
        expect(page.locator('#mobile-sync-state')).to_have_text('同步中')
    held.pop().fulfill(status=401, content_type=content_type, body='{}')
    expect(page.locator('#account-auth')).to_be_visible()
    expect(page.locator('#account-auth-error')).to_have_text('登录已过期，请重新登录')
    assert page.evaluate(f"localStorage.getItem('{KEY}')") is None
    assert page.evaluate('currentUser') is None
    expect(page.locator('#account-menu')).to_be_empty()
    assert page.locator('a.auth-connect').evaluate("e => [getComputedStyle(e).color, getComputedStyle(e).textDecorationLine]") == ['rgb(66, 104, 78)', 'none']


@pytest.mark.parametrize('failure', ['502', '403', 'html', 'bad-json', 'null', 'network', 'timeout'])
def test_non_401_keeps_workbench_and_retries(screen, failure):
    page, held = screen
    route = held.pop()
    if failure == 'timeout':
        expect(page.locator('#storage-warning')).to_contain_text('连接超时，请检查网络后重试', timeout=20000)
        route.abort('timedout')
    elif failure == 'network':
        route.abort('failed')
    else:
        route.fulfill(status=int(failure) if failure.isdigit() else 200,
                      content_type='text/html' if failure in ('502', 'html') else 'application/json',
                      body='{"detail":"账号已停用"}' if failure == '403' else 'null' if failure == 'null' else '<html>unavailable</html>')
    tip = '连接超时，请检查网络后重试' if failure in ('network', 'timeout') else '账号已停用' if failure == '403' else '服务暂不可用，请稍后重试'
    expect(page.locator('#storage-warning')).to_contain_text(tip)
    expect(page.locator('#sync-state')).to_have_text('同步未完成')
    expect(page.locator('.account-pill:visible')).to_contain_text(OLD['displayName'])
    assert page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))") == OLD
    assert page.evaluate('loaded') is False
    page.get_by_role('button', name='重试', exact=True).click()
    expect(page.locator('#sync-state')).to_have_text('同步中')
    held.pop().fulfill(json={'user': NEW, 'csrf': 'memory-only'})
    expect(page.locator('#sync-state')).to_have_text('已同步')
    expect(page.locator('#storage-warning')).to_be_hidden()
    expect(page.locator('.account-pill:visible')).to_contain_text(NEW['displayName'])
    assert page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))") == {'id': 'b', 'displayName': '新账号'}
    assert page.evaluate('csrfToken') == 'memory-only'


def test_login_and_refresh_store_only_identity(screen):
    page, held = screen
    held.pop().fulfill(json={'user': NEW, 'csrf': 'memory-only'})
    expect(page.locator('#sync-state')).to_have_text('已同步')
    assert page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))") == {'id': 'b', 'displayName': '新账号'}
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('.account-pill:visible')).to_contain_text(NEW['displayName'])
    expect(page.locator('#sync-state')).to_have_text('同步中')
    assert page.evaluate('[loaded, csrfToken]') == [False, '']
    held.pop().fulfill(json={'user': NEW, 'csrf': 'fresh-csrf'})
    expect(page.locator('#sync-state')).to_have_text('已同步')
    assert page.evaluate('csrfToken') == 'fresh-csrf'


def test_without_cache_preserves_login_error_and_retry(screen):
    page, held = screen
    page.evaluate('clearLocalAccount()')
    held.pop().fulfill(status=401, json={})
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#account-boot-status')).to_have_text('正在确认登录状态…')
    held.pop().fulfill(status=502, content_type='text/html', body='unavailable')
    expect(page.locator('#account-auth-error')).to_contain_text('服务暂不可用，请稍后重试')
    page.get_by_role('button', name='重试', exact=True).click()
    held.pop().fulfill(status=401, json={})
    expect(page.locator('#account-auth-form')).to_be_visible()
    expect(page.locator('#account-auth-error')).to_be_empty()


@pytest.mark.parametrize('status', [401, 502])
def test_workspace_failure_never_reports_success(screen, status):
    page, held = screen
    page.route('**/api/workspace', lambda r: r.fulfill(status=status, json={'detail': 'failed'}))
    held.pop().fulfill(json={'user': NEW, 'csrf': 'memory-only'})
    page.wait_for_function('!accountBootRunning')
    assert page.evaluate('loaded') is False
    if status == 401:
        expect(page.locator('#account-auth-error')).to_be_visible()
        expect(page.locator('#account-auth-error')).to_have_text('登录已过期，请重新登录')
        assert page.evaluate(f"localStorage.getItem('{KEY}')") is None
    else:
        expect(page.locator('#sync-state')).to_have_text('连接失败')
        expect(page.locator('#storage-warning')).to_contain_text('连接服务失败，尚未加载记录。')
        expect(page.get_by_role('button', name='重新连接', exact=True)).to_be_visible()


@pytest.mark.parametrize('pending', ['me', 'workspace'])
def test_logout_and_switch_ignore_old_responses(screen, pending):
    page, held = screen
    if pending == 'workspace':
        page.route('**/api/workspace', lambda r: held.append(r))
        held.pop().fulfill(json={'user': OLD, 'csrf': 'old-csrf'})
        page.wait_for_function('csrfToken === "old-csrf"')
        page.unroute('**/api/workspace')
        page.route('**/api/workspace', lambda r: r.fulfill(json=WORKSPACE))
    logout = []
    page.route('**/api/auth/logout', lambda r: logout.append(r))
    page.evaluate('void logoutAccount()')
    expect(page.locator('#account-auth')).to_be_visible()
    assert page.evaluate(f"localStorage.getItem('{KEY}')") is None
    page.locator('[name=username]').fill('new-user')
    page.locator('[name=password]').fill('new-password')
    page.locator('#account-auth-form [type=submit]').click()
    expect(page.locator('#sync-state')).to_have_text('已同步')
    held.pop().fulfill(json={'user': OLD, 'csrf': 'old-csrf'} if pending == 'me' else {'revision': 99, 'data': {}})
    logout.pop().fulfill(status=401, json={'detail': 'expired'})
    page.wait_for_function('!accountBootRunning')
    expect(page.locator('.account-pill:visible')).to_contain_text(NEW['displayName'])
    expect(page.locator('body')).not_to_contain_text(OLD['displayName'])
    assert page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))") == {'id': 'b', 'displayName': '新账号'}
    assert page.evaluate('revision') == 1
