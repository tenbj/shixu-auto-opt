"""Dual-scheme authentication, cookie separation and OAuth transport boundary."""
from contextlib import closing
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Keep the test's transport settings independent of the deployed .env.
    monkeypatch.setattr('app.main.load_environment', lambda: None)
    monkeypatch.setenv('SHIXU_ALLOW_HTTP_AUTH', 'true')
    monkeypatch.setenv('SHIXU_PUBLIC_URL', '')
    monkeypatch.setenv('SHIXU_HTTPS_PROXY_SECRET', '')
    return create_app(tmp_path/'dual.sqlite3')


@pytest.mark.parametrize('scheme,cookie', [('http','shixu_session'),('https','__Host-shixu_session')])
def test_dual_scheme_account_pat_and_csrf(app, scheme, cookie, monkeypatch):
    base=scheme+'://eliasliu.cc:11865'
    with TestClient(app,base_url=base) as web, closing(TestClient(app,base_url=base)) as remote:
        r=web.post('/api/auth/register',json=dict(username='alice',password='fixture-password'))
        assert r.status_code==200,r.text
        header=r.headers['set-cookie']
        assert header.startswith(cookie+'=') and 'HttpOnly' in header and 'SameSite=lax' in header
        assert ('; Secure' in header)==(scheme=='https')
        assert web.get('/api/auth/me').status_code==200
        assert web.post('/api/account/mcp-access',json=dict(name='denied')).status_code==403
        web.headers['x-csrf-token']=r.json()['csrf']
        options=web.get('/api/account/mcp-access').json()['connection']
        assert options['oauthAvailable']==(scheme=='https')
        # Configured HTTPS is preferred from either workspace entry.
        monkeypatch.setenv('SHIXU_PUBLIC_URL','https://canonical.example')
        key=web.post('/api/account/mcp-access',json=dict(name='test',scope='write')).json()
        assert key['url']=='https://canonical.example/mcp'
        assert web.get('/api/account/mcp-access').json()['connection']==dict(url=key['url'],oauthAvailable=True,encrypted=True)
        remote.headers['Authorization']='Bearer '+key['token']
        snapshot=remote.get('/api/workspace').json()
        result=remote.post('/api/issues',json=dict(title='Transport test',expected_version=snapshot['revision'],request_id=str(uuid4())))
        assert result.status_code==200,result.text
        assert remote.get('/api/issues/'+result.json()['resource']['id']).status_code==200
        assert remote.get('/api/account/mcp-access').status_code==403
        assert web.post('/api/issues',headers={'Origin':'https://attacker.invalid'},json={}).status_code==403
        assert web.post('/api/account/mcp-access/'+key['item']['id']+'/revoke',json={}).status_code==200
        assert remote.get('/api/workspace').status_code==401
        assert web.post('/api/auth/logout',json={}).status_code==200
        assert web.get('/api/auth/me').status_code==401


def test_http_switch_does_not_weaken_oauth_or_https(app,monkeypatch):
    with TestClient(app,base_url='http://eliasliu.cc:11865') as http:
        for path in ['/oauth/register','/oauth/token']:
            response=http.post(path,json={})
            assert response.status_code==400 and 'HTTPS' in response.json()['detail']
        assert http.get('/.well-known/oauth-authorization-server').status_code==400
        assert http.get('/.well-known/oauth-protected-resource').status_code==400
        assert 'resource_metadata' not in http.get('/mcp').headers['www-authenticate']
        monkeypatch.setenv('SHIXU_ALLOW_HTTP_AUTH','false')
        assert http.post('/api/auth/register',json=dict(username='alice',password='fixture-password')).status_code==400
        assert http.post('/api/auth/login',json=dict(username='alice',password='fixture-password'),headers={'X-Forwarded-Proto':'https'}).status_code==400
    with closing(TestClient(app,base_url='https://eliasliu.cc:11865')) as https:
        assert https.post('/api/auth/register',json=dict(username='alice',password='fixture-password')).status_code==200
        assert https.get('/.well-known/oauth-authorization-server').json()['issuer']=='https://eliasliu.cc:11865'
        assert https.post('/oauth/register',json={'redirect_uris':['http://127.0.0.1:9911/callback']}).status_code==201
        assert https.post('/oauth/register',json={'redirect_uris':['http://remote.invalid/callback']}).status_code==400


def test_http_session_is_not_accepted_by_https(app):
    with TestClient(app,base_url='http://eliasliu.cc:11865') as http, closing(TestClient(app,base_url='https://eliasliu.cc:11865')) as https:
        r=http.post('/api/auth/register',json=dict(username='alice',password='fixture-password'))
        assert r.status_code==200
        https.cookies.update(http.cookies)
        assert https.get('/api/auth/me').status_code==401
        assert https.post('/api/auth/login',json=dict(username='alice',password='fixture-password')).status_code==200
        assert https.get('/api/auth/me').status_code==200
        assert http.get('/api/auth/me').status_code==200


def test_http_configuration_cannot_downgrade_https(app,monkeypatch):
    monkeypatch.setenv('SHIXU_PUBLIC_URL','http://legacy.example')
    with TestClient(app,base_url='https://eliasliu.cc:11865') as web:
        r=web.post('/api/auth/register',json=dict(username='alice',password='fixture-password'))
        assert r.status_code==200
        assert web.get('/api/account/mcp-access').json()['connection']['url']=='https://eliasliu.cc:11865/mcp'
