import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from app.https_proxy import HTTPSProxyProof

SECRET = 'test-only-proxy-proof-' + 'a' * 32

def client():
    async def echo(request):
        return JSONResponse({'scheme': request.url.scheme,
                             'proof_present': 'x-shixu-https-proof' in request.headers})
    return TestClient(HTTPSProxyProof(Starlette(routes=[Route('/', echo)]),
                                     SECRET, 'https://proxy.example'),
                      base_url='http://proxy.example')

@pytest.mark.parametrize('headers,scheme', [
    ({}, 'http'),
    ({'x-forwarded-proto': 'https'}, 'http'),
    ({'x-shixu-https-proof': 'wrong', 'x-forwarded-proto': 'https'}, 'http'),
    ({'x-shixu-https-proof': SECRET, 'x-forwarded-proto': 'https'}, 'https'),
    ({'x-shixu-https-proof': SECRET, 'x-forwarded-proto': 'http'}, 'http'),
    ({'x-shixu-https-proof': SECRET, 'x-forwarded-proto': 'https', 'host': 'other.example'}, 'http'),
    ({'x-shixu-https-proof': SECRET, 'x-forwarded-proto': 'https', 'host': 'proxy.example:443'}, 'https'),
])
def test_proof_and_host_are_required(headers, scheme):
    with client() as c:
        assert c.get('/', headers=headers).json() == {'scheme': scheme, 'proof_present': False}

def test_duplicate_proof_rejected():
    with client() as c:
        response = c.get('/', headers=[('x-shixu-https-proof', SECRET),
                                       ('x-shixu-https-proof', SECRET),
                                       ('x-forwarded-proto', 'https')])
        assert response.json()['scheme'] == 'http'

def test_weak_configuration_rejected():
    with pytest.raises(ValueError):
        HTTPSProxyProof(None, 'short', 'https://proxy.example')

def test_accounts_preserve_http_and_authenticated_https(tmp_path, monkeypatch):
    from app.main import create_app
    monkeypatch.setenv('SHIXU_HTTPS_PROXY_SECRET', SECRET)
    monkeypatch.setenv('SHIXU_PUBLIC_URL', 'https://proxy.example')
    monkeypatch.setenv('SHIXU_ALLOWED_HOSTS', 'proxy.example')
    monkeypatch.setenv('SHIXU_ALLOW_HTTP_AUTH', 'true')
    monkeypatch.setenv('SHIXU_ALLOW_REGISTRATION', 'true')
    with TestClient(create_app(tmp_path / 'proxy.sqlite3'), base_url='http://proxy.example') as c:
        credentials = {'username': 'proxy-fixture', 'password': 'fixture-password'}
        registered = c.post('/api/auth/register', json=credentials)
        assert registered.status_code == 200
        assert registered.headers['set-cookie'].startswith('shixu_session=')
        assert 'Secure' not in registered.headers['set-cookie']
        forged = c.get('/.well-known/oauth-protected-resource', headers={'x-forwarded-proto': 'https'})
        assert forged.status_code == 400
        headers = {'x-shixu-https-proof': SECRET, 'x-forwarded-proto': 'https', 'origin': 'https://proxy.example'}
        logged_in = c.post('/api/auth/login', json=credentials, headers=headers)
        assert logged_in.status_code == 200
        assert logged_in.headers['set-cookie'].startswith('__Host-shixu_session=')
        assert 'Secure' in logged_in.headers['set-cookie']
        assert c.get('/.well-known/oauth-protected-resource', headers=headers).status_code == 200
        headers['cookie'] = '__Host-shixu_session=' + logged_in.cookies['__Host-shixu_session']
        connected = c.get('/api/account/mcp-access', headers=headers)
        assert connected.status_code == 200
        assert connected.json()['connection'] == {'url': 'https://proxy.example/mcp', 'oauthAvailable': True, 'encrypted': True}
