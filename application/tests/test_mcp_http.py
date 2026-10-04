from fastapi.testclient import TestClient
from app.main import create_app

def initialize(client, token=None, **headers):
    headers.update({'Accept':'application/json, text/event-stream'})
    if token:headers['Authorization']='Bearer '+token
    return client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'isolated-test','version':'1'}}})

def provision(client):
    r=client.post('/api/auth/register',json={'username':'mcp_fixture','password':'fixture-password'})
    if r.status_code==409:r=client.post('/api/auth/login',json={'username':'mcp_fixture','password':'fixture-password'})
    assert r.status_code==200,r.text
    client.headers['x-csrf-token']=r.json()['csrf']
    return client.post('/api/account/mcp-access',json={'name':'SDK','scope':'write'}).json()

def test_lifecycle_and_auth(tmp_path):
    app=create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        assert client.get('/api/health').json()['mcp']['running']
        assert initialize(client).status_code==401
        assert initialize(client,'wrong').status_code==401
        key=provision(client)
        r=initialize(client,key['token']);assert r.status_code==200,r.text
        assert r.json()['result']['serverInfo']['name']=='shixu'
        assert not (tmp_path/'mcp-client-default.json').exists()
    assert not app.state.mcp_running

def test_revoke_restart_and_no_legacy_fallback(tmp_path):
    app=create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        key=provision(client)
        client.post('/api/account/mcp-access/'+key['item']['id']+'/revoke',json={}).raise_for_status()
        assert initialize(client,key['token']).status_code==401
        from app.mcp_access import issue
        _,legacy=issue(tmp_path/'mcp-access.json','old-global-key')
        assert initialize(client,legacy).status_code==401
    with TestClient(create_app(tmp_path/'test.sqlite3')) as client:
        assert initialize(client,key['token']).status_code==401
        assert initialize(client,legacy).status_code==401

def test_bad_origin_and_host(tmp_path):
    with TestClient(create_app(tmp_path/'test.sqlite3')) as client:
        token=provision(client)['token']
        assert initialize(client,token,Origin='https://evil.invalid').status_code==403
        assert initialize(client,token,Host='evil.invalid').status_code==400
