"""回收站事务、依赖、批次和验证门槛回归。"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from test_api import client, write, issue, task, triage, stage, verify

def trash(c,kind,id): return write(c,f'/api/{kind}/{id}/trash',{})
def restore(c,kind,id): return write(c,f'/api/{kind}/{id}/restore',{})

def test_batch_preserves_old_single_deletion_and_numbers(client):
    p=issue(client); old=task(client,p); current=task(client,p)
    original=client.get(f'/api/tasks/{current}').json()['item']
    trash(client,'tasks',old); trash(client,'issues',p)
    snap=client.get('/api/trash').json()
    assert len(snap['tasks'])==2 and len(snap['issues'])==1
    assert client.get('/api/issues').json()['items']==[]
    assert client.get('/api/tasks').json()['items']==[]
    before=client.get('/api/workspace').json()
    write(client,f'/api/tasks/{current}/restore',{},expected=409)
    assert client.get('/api/workspace').json()==before
    restore(client,'issues',p)
    assert [t['id'] for t in client.get('/api/tasks').json()['items']]==[current]
    restored=client.get(f'/api/tasks/{current}').json()['item']
    for key in ['sequence','numberGroup','title','status','dependsOn','required','issueId']:
        assert restored[key]==original[key]
    assert len(client.get('/api/export').json()['data']['tasks'])==2
    restore(client,'tasks',old)
    assert len(client.get('/api/tasks').json()['items'])==2
    assert client.get(f'/api/tasks/{task(client,p)}').json()['item']['sequence']==3

def test_dependency_delete_block_and_restore_order(client):
    p=issue(client); a=task(client,p); b=task(client,p)
    write(client,f'/api/tasks/{b}/dependencies',{'dependsOn':[a]})
    before=client.get('/api/workspace').json()
    write(client,f'/api/tasks/{a}/trash',{},expected=409)
    assert client.get('/api/workspace').json()==before
    trash(client,'tasks',b); trash(client,'tasks',a)
    write(client,f'/api/tasks/{b}/restore',{},expected=409)
    restore(client,'tasks',a); restore(client,'tasks',b)
    trash(client,'issues',p); restore(client,'issues',p)
    assert client.get(f'/api/tasks/{b}').json()['item']['dependsOn']==[a]

def test_restoration_reopens_verification_preserves_evidence(client):
    p=issue(client); t=task(client,p); triage(client,p); stage(client,p,'start')
    trash(client,'tasks',t); verify(client,p); stage(client,p,'resolve',resolution='原结论')
    assert client.get(f'/api/issues/{p}').json()['item']['status']=='已解决'
    restore(client,'tasks',t)
    restored=client.get(f'/api/issues/{p}').json()['item']
    assert restored['status']=='处理中' and restored['resolution']=='原结论'
    assert restored['history'][-1]['reason'].startswith('恢复')

@pytest.mark.parametrize('operation,values,method',[
    ('',{'title':'不能编辑'},'PATCH'),('/transitions',{'status':'进行中'},'POST'),
    ('/dependencies',{'dependsOn':[]},'POST'),('/reorder',{'target_id':'other'},'POST')])
def test_deleted_tasks_reject_mutations(client,operation,values,method):
    t=task(client);trash(client,'tasks',t);before=client.get('/api/workspace').json()
    write(client,f'/api/tasks/{t}'+operation,values,method=method,expected=409)
    assert client.get('/api/workspace').json()==before

@pytest.mark.parametrize('operation,values,method',[
    ('',{'title':'不能编辑'},'PATCH'),('/followups',{'content':'禁止'},'POST'),
    ('/transitions',{'action':'triage','nextStep':'步骤','successCriteria':'标准'},'POST')])
def test_deleted_issues_reject_mutations(client,operation,values,method):
    p=issue(client);trash(client,'issues',p);before=client.get('/api/workspace').json()
    write(client,f'/api/issues/{p}'+operation,values,method=method,expected=409)
    write(client,'/api/tasks',{'title':'不能关联','issueId':p},expected=409)
    assert client.get('/api/workspace').json()==before

def test_soft_delete_idempotency_restart_and_conflict(client):
    t=task(client);version=client.get('/api/workspace').json()['revision'];key=str(uuid4())
    result=write(client,f'/api/tasks/{t}/trash',{},request_id=key,version=version)
    replay=write(client,f'/api/tasks/{t}/trash',{},request_id=key,version=version)
    assert result==replay
    write(client,f'/api/tasks/{t}/trash',{},expected=409)
    with TestClient(create_app(client.app.state.store.path)) as restarted:
        assert restarted.get('/api/trash').json()['tasks'][0]['id']==t
        assert write(restarted,f'/api/tasks/{t}/trash',{},request_id=key,version=version)==result
    write(client,f'/api/tasks/{t}/restore',{},version=version,expected=409)
    restore(client,'tasks',t)
    write(client,f'/api/tasks/{t}/restore',{},expected=409)

def test_deleted_parent_blocks_single_restore_and_pause(client):
    p=issue(client); t=task(client,p); trash(client,'tasks',t);trash(client,'issues',p)
    write(client,f'/api/tasks/{t}/restore',{},expected=409);restore(client,'issues',p)
    triage(client,p);stage(client,p,'pause',reason='等待',reviewDate='2099-01-01')
    write(client,f'/api/tasks/{t}/restore',{},expected=409)
    stage(client,p,'resume');restore(client,'tasks',t)

def test_duplicate_original_restore_first(client):
    p=issue(client);q=issue(client)
    stage(client,p,'close-issue',reason='重复',closeType='重复问题',duplicateOf=q)
    trash(client,'issues',p);trash(client,'issues',q)
    write(client,f'/api/issues/{p}/restore',{},expected=409)
    restore(client,'issues',q);restore(client,'issues',p)

def test_nonrequired_and_completed_restore_leave_resolved(client):
    p=issue(client);t=task(client,p);triage(client,p)
    write(client,f'/api/tasks/{t}',{'required':False},method='PATCH');trash(client,'tasks',t)
    stage(client,p,'start');verify(client,p);stage(client,p,'resolve',resolution='成立')
    restore(client,'tasks',t)
    assert client.get(f'/api/issues/{p}').json()['item']['status']=='已解决'
