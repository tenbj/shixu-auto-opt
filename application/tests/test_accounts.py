from contextlib import closing
import base64,hashlib
from urllib.parse import urlparse,parse_qs
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def system(tmp_path):
    app=create_app(tmp_path/'accounts.sqlite3')
    with TestClient(app) as a,closing(TestClient(app)) as b:
        for client,name in [(a,'alice'),(b,'bob')]:
            r=client.post('/api/auth/register',json=dict(username=name,password='fixture-password',displayName=name))
            assert r.status_code==200,r.text
            client.headers['x-csrf-token']=r.json()['csrf']
        yield app,a,b

def write(client,title,req=None):
    return client.post('/api/issues',json=dict(title=title,request_id=req or str(uuid4()),expected_version=client.get('/api/workspace').json()['revision'],actor='fixture'))

def test_workspace_isolation_and_idempotency(system):
    app,a,b=system
    req=str(uuid4());first=write(a,'Alice only',req);assert first.status_code==200
    key=first.json()['resource']['id']
    assert b.get('/api/issues').json()['items']==[]
    assert b.get('/api/issues/'+key).status_code==404
    assert b.post('/api/issues/'+key+'/trash',json=dict(request_id=str(uuid4()),expected_version=0,actor='fixture')).status_code==404
    assert write(b,'Bob only',req).status_code==200
    assert len(a.get('/api/issues').json()['items'])==1
    assert a.get('/api/workspace').json()['data']['issues'][0]['number']==1
    assert b.get('/api/workspace').json()['data']['issues'][0]['number']==1
    assert a.get('/api/activity').json()!=b.get('/api/activity').json()

def test_token_scope_revoke_and_management_boundary(system):
    app,a,b=system
    key=a.post('/api/account/mcp-access',json={'name':'readonly','scope':'read'}).json()
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+key['token']
        assert remote.get('/api/workspace').status_code==200
        assert write(remote,'denied').status_code==403
        assert remote.get('/api/account/mcp-access').status_code==403
        assert b.post('/api/account/mcp-access/'+key['item']['id']+'/revoke',json={}).status_code==404
        assert a.post('/api/account/mcp-access/'+key['item']['id']+'/revoke',json={}).status_code==200
        assert remote.get('/api/workspace').status_code==401
    assert key['token'] not in a.get('/api/account/mcp-access').text

def test_csrf_logout_and_anonymous(system):
    app,a,b=system
    csrf=a.headers.pop('x-csrf-token')
    assert write(a,'blocked').status_code==403
    a.headers['x-csrf-token']=csrf
    assert a.post('/api/auth/logout',json={}).status_code==200
    assert a.get('/api/workspace').status_code==401
    assert b.get('/api/workspace').status_code==200

def test_oauth_pkce_binding_and_replay(system):
    app,a,b=system
    callback='http://127.0.0.1:9999/callback'
    c=a.post('/oauth/register',json={'client_name':'test SDK','redirect_uris':[callback]}).json()
    verifier='a'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params=dict(client_id=c['client_id'],redirect_uri=callback,code_challenge=challenge,code_challenge_method='S256',resource='http://testserver/mcp',response_type='code',scope='write',state='state123')
    r=a.get('/oauth/authorize',params=params,follow_redirects=False);assert r.status_code==303
    pending=parse_qs(urlparse(r.headers['location']).query)['authorize'][0]
    assert a.get('/api/oauth/requests/'+pending).json()['client']=='test SDK'
    r=a.post('/api/oauth/requests/'+pending,json={'allow':True,'scope':'read'});assert r.status_code==200,r.text
    query=parse_qs(urlparse(r.json()['redirect']).query);assert query['state']==['state123']
    data=dict(grant_type='authorization_code',client_id=c['client_id'],redirect_uri=callback,code=query['code'][0],code_verifier='b'*64,resource='http://testserver/mcp')
    assert a.post('/oauth/token',data=data).status_code==400
    data['code_verifier']=verifier
    r=a.post('/oauth/token',data=data);assert r.status_code==200,r.text
    assert r.json()['scope']=='read'
    assert a.post('/oauth/token',data=data).status_code==400
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+r.json()['access_token']
        assert remote.get('/api/workspace').status_code==200
        assert write(remote,'denied').status_code==403
    params['redirect_uri']='https://attacker.invalid/'
    assert a.get('/oauth/authorize',params=params).status_code==400

def test_password_rotation_and_expired_access(system):
    app,a,b=system
    assert a.post('/api/account/password',json=dict(oldPassword='wrong',newPassword='changed-password')).status_code==422
    assert a.get('/api/auth/me').status_code==200
    key=a.post('/api/account/mcp-access',json=dict(name='expire',scope='read')).json()
    with app.state.accounts.connection() as c:
        app.state.accounts.query(c,'UPDATE account_access SET expires_at=0 WHERE id=?',(key['item']['id'],))
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+key['token']
        assert remote.get('/api/workspace').status_code==401
    assert a.post('/api/account/password',json=dict(oldPassword='fixture-password',newPassword='changed-password')).status_code==200
    assert a.get('/api/workspace').status_code==401
    assert b.get('/api/workspace').status_code==200
    a.cookies.clear();a.headers.pop('x-csrf-token')
    assert a.post('/api/auth/login',json=dict(username='alice',password='fixture-password')).status_code==401
    assert a.post('/api/auth/login',json=dict(username='alice',password='changed-password')).status_code==200


def test_auth_database_failure_is_retryable_without_leaking_details(system, monkeypatch):
    import pymysql
    app,session,_=system
    key=session.post('/api/account/mcp-access',json={'name':'outage','scope':'read'}).json()['token']
    original=app.state.accounts.authenticate
    def unavailable(*args):raise pymysql.OperationalError(2003,'private-host-and-secret')
    monkeypatch.setattr(app.state.accounts,'authenticate',unavailable)
    with closing(TestClient(app)) as remote:
        for headers in [{},{'Authorization':'Bearer '+key}]:
            response=remote.get('/api/health',headers=headers)
            assert response.status_code==503
            assert 'private-host-and-secret' not in response.text
        assert session.get('/api/workspace').status_code==503
        monkeypatch.setattr(app.state.accounts,'authenticate',original)
        assert session.get('/api/workspace').status_code==200
        assert remote.get('/api/workspace',headers={'Authorization':'Bearer '+key}).status_code==200
