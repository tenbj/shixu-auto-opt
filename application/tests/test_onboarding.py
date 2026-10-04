import base64
import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def setup(tmp_path):
    app=create_app(tmp_path/'onboard.sqlite3')
    with TestClient(app) as client:
        r=client.post('/api/auth/register',json={'username':'onboard','password':uuid4().hex})
        client.headers['X-CSRF-Token']=r.json()['csrf']
        yield app,client

def oauth(client,scope='read write',allow=True,consent_scope=None):
    callback='http://127.0.0.1:8899/callback'
    registration=client.post('/oauth/register',json={'client_name':'Test runtime','redirect_uris':[callback]}).json()
    verifier='a'*64
    params=dict(client_id=registration['client_id'],redirect_uri=callback,resource='http://testserver/mcp',scope=scope,state='fixture-state',code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
    start=client.get('/oauth/authorize',params=params,follow_redirects=False)
    assert start.status_code==303,start.text
    key=parse_qs(urlparse(start.headers['location']).query)['authorize'][0]
    decision={'allow':allow}
    if consent_scope:decision['scope']=consent_scope
    reply=client.post('/api/oauth/requests/'+key,json=decision)
    if not allow:return reply.json()
    assert reply.status_code==200,reply.text
    code=parse_qs(urlparse(reply.json()['redirect']).query)['code'][0]
    form=dict(grant_type='authorization_code',client_id=params['client_id'],resource=params['resource'],redirect_uri=callback,code=code,code_verifier=verifier)
    response=client.post('/oauth/token',data=form)
    assert response.status_code==200,response.text
    return response.json(),form

def renewal(tokens,form,**overrides):
    return dict(grant_type='refresh_token',refresh_token=tokens['refresh_token'],client_id=form['client_id'],resource=form['resource'],**overrides)

def test_refresh_rotation_replay_revokes_family(setup):
    app,c=setup;tokens,form=oauth(c)
    assert tokens['scope']=='read write'
    refreshed=c.post('/oauth/token',data=renewal(tokens,form));assert refreshed.status_code==200
    assert refreshed.headers['cache-control']=='no-store'
    new=refreshed.json()
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+tokens['access_token']
        assert remote.get('/api/connection-context').status_code==401
        remote.headers['Authorization']='Bearer '+new['access_token']
        assert remote.get('/api/connection-context').json()['scopes']==['read','write']
        assert c.post('/oauth/token',data=renewal(tokens,form)).status_code==400
        assert remote.get('/api/workspace').status_code==401
        assert c.post('/oauth/token',data=renewal(new,form)).status_code==400

def test_refresh_binding_scope_expiry_revoke(setup):
    app,c=setup;tokens,form=oauth(c,'read write',consent_scope='read')
    values=renewal(tokens,form)
    for field,value in [('client_id','other'),('resource','https://other.invalid/mcp'),('scope','write')]:
        assert c.post('/oauth/token',data={**values,field:value}).status_code==400
    assert c.post('/oauth/token',data=values).status_code==200
    tokens,form=oauth(c)
    with app.state.accounts.connection() as connection:
        from app.accounts import digest
        app.state.accounts.query(connection,'UPDATE oauth_refresh_tokens SET expires_at=0 WHERE digest=?',(digest(tokens['refresh_token']),))
    assert c.post('/oauth/token',data=renewal(tokens,form)).status_code==400
    tokens,form=oauth(c)
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+tokens['access_token']
        key=remote.get('/api/connection-context').json()['accessId']
        assert c.post('/api/account/mcp-access/'+key+'/revoke',json={}).status_code==200
        assert c.post('/oauth/token',data=renewal(tokens,form)).status_code==400
        assert remote.get('/api/connection-context').status_code==401

def test_public_resources_and_private_context(setup):
    app,c=setup
    with closing(TestClient(app)) as anon:
        manifest=anon.get('/connect/manifest.json').json()
        bundle=anon.get('/downloads/'+manifest['skill']['filename'])
        assert hashlib.sha256(bundle.content).hexdigest()==manifest['skill']['sha256']
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
            assert 'shixu-issues/SKILL.md' in archive.namelist()
            text=archive.read('shixu-issues/SKILL.md').decode()
            assert 'E:/' not in text and 'B08' not in text
        assert anon.get('/connect').status_code==200
        guide=anon.get('/connect.md').text
        assert '{{' not in guide and manifest['skill']['sha256'] in guide
        assert anon.get('/api/connection-context').status_code==401
        assert anon.get('/downloads/secret.env').status_code==404
    result=c.get('/api/connection-context').json()
    assert result['account']['username']=='onboard' and result['verifiedAt'] is None
    assert 'csrf' not in result and 'password' not in json.dumps(result)

def test_device_metadata_owner_boundary_and_no_forged_verification(setup):
    app,c=setup
    issued=c.post('/api/account/mcp-access',json={'name':'device','scope':'read'}).json();key=issued['item']['id']
    with closing(TestClient(app)) as remote:
        remote.headers['Authorization']='Bearer '+issued['token']
        r=remote.get('/api/connection-context',params={'runtime_name':'Pretend'},headers={'X-MCP-Verified':'true'})
        assert r.status_code==200 and r.json()['verifiedAt'] is None
        assert remote.patch('/api/account/mcp-access/'+key,json={'displayName':'attacker'}).status_code==403
    rows=c.get('/api/account/mcp-access').json()['items'];assert rows[0]['lastSeenAt'] and rows[0]['verifiedAt'] is None
    assert c.patch('/api/account/mcp-access/'+key,json={'displayName':'renamed'}).status_code==200
    with closing(TestClient(app)) as other:
        auth=other.post('/api/auth/register',json={'username':'other','password':uuid4().hex}).json();other.headers['X-CSRF-Token']=auth['csrf']
        assert other.patch('/api/account/mcp-access/'+key,json={'displayName':'stolen'}).status_code==404
        assert other.get('/api/account/mcp-access').json()['items']==[]

def test_denial_and_invalid_scopes_leave_no_access(setup):
    app,c=setup
    assert 'access_denied' in oauth(c,allow=False)['redirect']
    assert c.get('/api/account/mcp-access').json()['items']==[]
    from app.onboarding_auth import normalize_scope
    from app.domain import DomainError
    for value in ('','read admin','READ',None):
        with pytest.raises(DomainError):normalize_scope(value)

def test_concurrent_refresh_one_winner_and_revocation(setup):
    app,c=setup;tokens,form=oauth(c)
    def exchange(_):
        with closing(TestClient(app)) as remote:return remote.post('/oauth/token',data=renewal(tokens,form))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(exchange,range(2)))
    assert sorted(x.status_code for x in results)==[200,400]
    winner=next(x.json() for x in results if x.status_code==200)
    with closing(TestClient(app)) as remote:
        assert remote.get('/api/workspace',headers={'Authorization':'Bearer '+winner['access_token']}).status_code==401
