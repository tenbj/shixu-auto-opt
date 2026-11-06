"""生成页的登录/注册提交状态：全部请求拦截，不启动后端、不访问数据库。"""
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

INDEX = (Path(__file__).resolve().parents[1] / 'static/index.html').read_text(encoding='utf-8')
USER = {'id': 'pending-user', 'displayName': '提交状态测试'}
WORKSPACE = {'revision': 1, 'data': {'issues': [], 'tasks': [], 'identityProfiles': [
    {'id': USER['id'], 'name': USER['displayName'], 'kind': 'person', 'via': 'manual'}]}}


@pytest.fixture
def screen():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chromium')
        page = browser.new_page()
        held, errors, unexpected = [], [], []

        def intercept(route):
            path = route.request.url.removeprefix('http://shixu.test')
            if path == '/':
                route.fulfill(content_type='text/html', body=INDEX)
            elif path == '/api/auth/me':
                route.fulfill(status=401, json={'detail': '未登录'})
            elif path in ('/api/auth/login', '/api/auth/register', '/api/workspace'):
                held.append(route)
            else:
                unexpected.append(path)
                route.abort()

        page.route('**/*', intercept)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://shixu.test/', wait_until='domcontentloaded')
        page.wait_for_function("document.documentElement.dataset.accountBoot === 'complete'")
        yield page, held
        browser.close()
        assert not errors
        assert not unexpected


def fill_form(page, mode):
    if mode == 'register':
        page.locator('[data-account-action=register-mode]').click()
        expect(page.get_by_label('确认密码', exact=True)).to_be_visible()
        page.locator('[name=confirm]').fill('test-password')
        page.locator('[name=displayName]').fill(USER['displayName'])
    page.locator('[name=username]').fill('pending-user')
    page.locator('[name=password]').fill('test-password')
    return page.locator('#account-auth-form [type=submit]')


def submit_snapshot(page):
    # Read synchronously in the submitting JS task, before any promise/frame can run.
    return page.locator('#account-auth-form').evaluate("""form => {
        form.requestSubmit();
        const button = form.querySelector('[type=submit]');
        return [button.textContent, button.disabled, button.getAttribute('aria-busy')];
    }""")


@pytest.mark.parametrize('mode', ['login', 'register'])
@pytest.mark.parametrize('status,message', [
    (401, '账号或密码不正确'), (503, '服务暂不可用，请稍后重试')])
def test_pending_failure_and_retry(screen, mode, status, message):
    page, held = screen
    button = fill_form(page, mode)
    idle = '创建账号并进入 →' if mode == 'register' else '登录工作台 →'
    pending = '创建中…' if mode == 'register' else '登录中…'
    expect(button).to_have_text(idle)
    original = button.inner_html()
    with page.expect_request(f'**/api/auth/{mode}'):
        assert submit_snapshot(page) == [pending, True, 'true']
    # Repeated clicks, Enter, and explicit submit events must not duplicate the request.
    button.evaluate('button => button.click()')
    page.locator('[name=password]').press('Enter')
    page.locator('#account-auth-form').evaluate("""async form => {
        form.requestSubmit();
        form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        await new Promise(requestAnimationFrame);
    }""")
    expect(button).to_have_text(pending)
    expect(button).to_be_disabled()
    expect(button).to_have_attribute('aria-busy', 'true')
    assert len(held) == 1
    assert held[0].request.method == 'POST'
    held[0].fulfill(status=status, json={'detail': message})
    expect(page.locator('#account-auth-error')).to_have_text(message)
    expect(button).to_have_text(idle)
    expect(button).to_be_enabled()
    assert button.inner_html() == original
    assert button.get_attribute('aria-busy') is None
    with page.expect_request(f'**/api/auth/{mode}'):
        button.click()
    expect(button).to_have_text(pending)
    assert len(held) == 2
    held[1].fulfill(status=status, json={'detail': message})
    expect(button).to_be_enabled()


def test_confirmation_mismatch_restores_without_request(screen):
    page, held = screen
    button = fill_form(page, 'register')
    page.locator('[name=confirm]').fill('different-password')
    original = button.inner_html()
    button.click()
    expect(page.locator('#account-auth-error')).to_have_text('两次密码不一致')
    expect(button).to_have_text('创建账号并进入 →')
    expect(button).to_be_enabled()
    assert button.inner_html() == original
    assert button.get_attribute('aria-busy') is None
    assert held == []


@pytest.mark.parametrize('mode', ['login', 'register'])
def test_success_keeps_existing_workspace_sync(screen, mode):
    page, held = screen
    fill_form(page, mode).click()
    with page.expect_request('**/api/workspace'):
        held[0].fulfill(json={'user': USER, 'csrf': 'test-csrf'})
    expect(page.locator('#account-auth')).to_be_hidden()
    expect(page.locator('#sync-state')).to_have_text('同步中')
    expect(page.locator('.account-pill:visible')).to_contain_text(USER['displayName'])
    assert page.evaluate('csrfToken') == 'test-csrf'
    held[1].fulfill(json=WORKSPACE)
    expect(page.locator('#sync-state')).to_have_text('已同步')
    assert page.evaluate('loaded') is True
    expect(page.locator('#account-auth')).to_be_hidden()


def test_pending_spinner_respects_reduced_motion(screen):
    page, held = screen
    page.emulate_media(reduced_motion='reduce')
    button = fill_form(page, 'login')
    button.click()
    expect(button).to_have_attribute('aria-busy', 'true')
    assert button.evaluate("b => getComputedStyle(b, '::after').animationName") == 'none'
    page.emulate_media(reduced_motion='no-preference')
    assert button.evaluate("b => getComputedStyle(b, '::after').animationName") == 'auth-spin'
    held[0].fulfill(status=401, json={'detail': '账号或密码不正确'})
    expect(button).to_be_enabled()
