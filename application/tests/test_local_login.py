"""真实生成页 + 拦截响应；不启动后端、不访问数据库。"""
import json
import re
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
def screen(request):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chromium')
        context = browser.new_context(viewport={'width': getattr(request, 'param', 1440), 'height': 900}, storage_state={'cookies': [], 'origins': [{'origin': 'http://shixu.test', 'localStorage': [{'name': KEY, 'value': json.dumps(OLD)}]}]})
        page = context.new_page()
        held, errors, scripts, workspaces = [], [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        main = re.search(r'<script>(.*?)</script>', INDEX, re.S).group(1)
        paused = INDEX.replace('<script>'+main+'</script>', '<script src="/main-for-test.js"></script>', 1)
        page.route('http://shixu.test/', lambda r: r.fulfill(content_type='text/html', body=paused))
        page.route('**/main-for-test.js', lambda r: scripts.append(r))
        page.route('**/api/workspace', lambda r: (workspaces.append(r.request.url), r.fulfill(json=WORKSPACE)))
        page.route('**/api/auth/login', lambda r: r.fulfill(json={'user': NEW, 'csrf': 'memory-only'}))
        page.route('**/api/auth/me', lambda r: held.append(r))
        page.goto('http://shixu.test/', wait_until='commit')
        expect(page.locator('#workbench')).to_be_visible()
        expect(page.locator('#workbench')).to_have_attribute('data-shell-owner', OLD['id'])
        expect(page.locator('#account-auth-form')).to_be_hidden()
        expect(page.locator('#sync-state')).to_have_text('同步中')
        assert page.evaluate('typeof bootAccount') == 'undefined'
        page.evaluate('window.shellNode = document.querySelector("#app").firstElementChild')
        assert not workspaces
        scripts.pop().fulfill(content_type='text/javascript', body=main)
        page.wait_for_load_state('domcontentloaded')
        assert page.evaluate('window.shellNode === document.querySelector("#app").firstElementChild')
        expect(page.locator('#account-auth-form')).to_be_hidden()
        page.unroute('**/main-for-test.js')
        page.route('**/main-for-test.js', lambda r: r.fulfill(content_type='text/javascript', body=main))
        expect(page.locator('#account-menu .account-pill')).to_contain_text(OLD['displayName'])
        expect(page.locator('#sync-state')).to_have_text('同步中')
        assert page.evaluate('loaded') is False
        assert not workspaces
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
    calls = []
    page.on('request', lambda r: calls.append(r.url) if r.url.endswith('/api/workspace') else None)
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
    expect(page.locator('#sync-state')).to_have_text('暂未同步')
    expect(page.locator('.account-pill:visible')).to_contain_text(OLD['displayName'])
    assert page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))") == OLD
    assert page.evaluate('loaded') is False
    assert not calls
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


def test_without_cache_goes_directly_to_login(screen):
    page, held = screen
    page.evaluate('clearLocalAccount()')
    held.pop().fulfill(status=401, json={})
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#account-boot-status')).to_have_count(0)
    expect(page.locator('#workbench')).to_be_hidden()
    assert not held
    expect(page.locator('#account-auth-form')).to_be_visible()
    expect(page.locator('#account-auth-error')).to_be_empty()


@pytest.mark.parametrize('screen', [360, 390, 430, 1440], indirect=True)
def test_early_shell_same_identity_then_data(screen):
    page, held = screen
    page.route('**/api/workspace', lambda r: held.append(r))
    held.pop().fulfill(json={'user': OLD, 'csrf': 'memory-only'})
    page.wait_for_function('csrfToken === "memory-only"')
    assert page.evaluate('window.shellNode === document.querySelector("#app").firstElementChild')
    expect(page.locator('#workbench')).to_have_attribute('data-fill', 'pending')
    held.pop().fulfill(json={'revision': 1, 'data': {'issues': [], 'tasks': [], 'identityProfiles': [
        {'id': 'a', 'name': OLD['displayName'], 'kind': 'person', 'via': 'manual'}]}})
    expect(page.locator('#sync-state')).to_have_text('已同步')
    expect(page.locator('#workbench')).to_have_attribute('data-fill', 'ready')
    assert page.evaluate('loaded') is True


def test_mismatch_clears_old_content_before_loading_new_data(screen):
    page, held = screen
    page.evaluate('document.querySelector("#app").textContent = "旧账号的私有数据"')
    page.route('**/api/workspace', lambda r: held.append(r))
    held.pop().fulfill(json={'user': NEW, 'csrf': 'memory-only'})
    expect(page.locator('#workbench')).to_have_attribute('data-shell-owner', 'b')
    expect(page.locator('body')).not_to_contain_text('旧账号')
    expect(page.locator('#account-menu')).to_contain_text(NEW['displayName'])
    expect(page.locator('#account-auth-form')).to_be_hidden()
    expect(page.locator('#sync-state')).to_have_text('同步中')
    assert page.evaluate('[currentUser.id, loaded, db.issues.length]') == ['b', False, 0]
    held.pop().fulfill(json=WORKSPACE)
    expect(page.locator('#sync-state')).to_have_text('已同步')


@pytest.mark.parametrize('raw', ['broken', 'null', '0', '[]', '{"id":"a","displayName":""}', '{"id":"a","displayName":"旧账号","token":"forbidden"}'])
def test_invalid_cache_is_removed(screen, raw):
    page, held = screen
    page.evaluate('(raw) => localStorage.setItem("shixu-local-user",raw)', raw)
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#account-auth-form')).to_be_visible()
    assert page.evaluate(f'localStorage.getItem("{KEY}")') is None


@pytest.mark.parametrize('pending', ['me', 'workspace'])
def test_storage_switch_discards_stale_responses(screen, pending):
    page, held = screen
    if pending == 'workspace':
        page.route('**/api/workspace', lambda r: held.append(r))
        held.pop().fulfill(json={'user': OLD, 'csrf': 'old-csrf'})
        page.wait_for_function('csrfToken === "old-csrf"')
    stale = held.pop()
    sibling = page.context.new_page()
    sibling.route('http://shixu.test/storage', lambda r: r.fulfill(body=''))
    sibling.goto('http://shixu.test/storage')
    sibling.evaluate('(u) => localStorage.setItem("shixu-local-user", JSON.stringify(u))', {'id': 'b', 'displayName': '新账号'})
    expect(page.locator('#workbench')).to_have_attribute('data-shell-owner', 'b')
    expect(page.locator('body')).not_to_contain_text(OLD['displayName'])
    expect(page.locator('#sync-state')).to_have_text('同步中')
    stale.fulfill(status=401, json={})
    assert page.evaluate('currentUser.id') == 'b'
    held.pop().fulfill(status=502, body='unavailable')
    expect(page.locator('#sync-state')).to_have_text('暂未同步')
    sibling.evaluate('localStorage.clear()')
    expect(page.locator('#account-auth-error')).to_have_text('登录已过期，请重新登录')
    expect(page.locator('#workbench')).to_be_hidden()
    sibling.close()


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
