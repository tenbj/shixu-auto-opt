from uuid import uuid4
from test_api import client,write
from app.main import create_app
from auth_client import TestClient

def test_tool_atomic_reuse_history_and_export(client):
    p=write(client,'/api/identities',dict(name='助手',kind='agent',via='__custom__',toolName='  Cursor  '))['resource']
    tool=p['via'];assert tool.startswith('custom:')
    for route in ['issues','tasks']:
        write(client,'/api/'+route,dict(title='自定义来源',creation=dict(identityId=p['id'])))
    assert write(client,'/api/ai-tools',dict(name='cUrSoR'))['resource']['id']==tool
    assert write(client,'/api/ai-tools',dict(name=' Codex '))['resource']['id']=='codex'
    write(client,'/api/identities/'+p['id'],dict(via='codex'),method='PATCH')
    export=client.get('/api/export').json()['data']
    assert export['customTools']=={tool:'Cursor'}
    for route in ['issues','tasks']:
        assert client.get('/api/'+route,params={'created_via':tool}).json()['items'][0]['createdVia']==tool
    second=write(client,'/api/identities',dict(name='另一身份',kind='agent',via=tool))['resource']
    assert second['via']==tool

def test_tool_validation_and_rollback(client):
    for name in ['', ' '*3,'x'*81]:
        before=client.get('/api/workspace').json()
        write(client,'/api/identities',dict(name='失败',kind='agent',via='__custom__',toolName=name),expected=422)
        assert client.get('/api/workspace').json()==before
    profile=write(client,'/api/identities',dict(name='原子更新',kind='agent',via='codex'))['resource']
    before=client.get('/api/workspace').json()
    # Null passes the PATCH schema but fails domain validation after tool allocation.
    write(client,'/api/identities/'+profile['id'],dict(via='__custom__',toolName='Must roll back',modelName=None),method='PATCH',expected=422)
    assert client.get('/api/workspace').json()==before
    for values in [dict(kind='person',via='__custom__',toolName='fail'),dict(kind='agent',via='custom:'+str(uuid4())),dict(kind='agent',via='codex',toolName='fail')]:
        before=client.get('/api/workspace').json()
        write(client,'/api/identities',dict(name='失败',**values),expected=422)
        assert client.get('/api/workspace').json()==before

def test_tools_idempotency_and_account_scope(client,tmp_path):
    v=client.get('/api/workspace').json()['revision'];rid=str(uuid4())
    result=write(client,'/api/ai-tools',dict(name='<b>Tool</b>'),version=v,request_id=rid)
    assert write(client,'/api/ai-tools',dict(name='<b>Tool</b>'),version=v,request_id=rid)==result
    app=client.app
    from fastapi.testclient import TestClient as RawClient
    from contextlib import closing
    with closing(RawClient(app)) as other:
        login=other.post('/api/auth/register',json=dict(username='other_tools',password=uuid4().hex)).json()
        other.headers['X-CSRF-Token']=login['csrf']
        assert not other.get('/api/workspace').json()['data']['customTools']
        write(other,'/api/identities',dict(name='跨账号',kind='agent',via=result['resource']['id']),expected=422)
        other_tool=write(other,'/api/ai-tools',dict(name='<b>Tool</b>'))['resource']
        assert other_tool['id']!=result['resource']['id']

def test_updates_are_read_only_and_current(client):
    before=client.get('/api/workspace').json()
    catalog=client.get('/connect/manifest.json').json()
    result=client.get('/api/connection-updates',params=dict(skill_version='1.4.0',mcp_url='https://old.invalid/mcp')).json()
    assert result['comparison']==dict(skill='different',mcp='different')
    assert result['clientChangesApplied'] is False
    result=client.get('/api/connection-updates',params=dict(skill_version=catalog['skill']['version'],mcp_url=catalog['mcp'])).json()
    assert set(result['comparison'].values())=={'current'}
    assert client.get('/api/workspace').json()==before
    assert client.get('/connect/updates.md').status_code==200
