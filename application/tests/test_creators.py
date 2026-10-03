"""创建元数据是历史事实：覆盖归属、模型、兼容性、事务与幂等。"""
from uuid import uuid4
import pytest
from test_api import client, write


def profile(c,kind='person',**kwargs):
    return write(c,'/api/identities',dict(name='Elias' if kind=='person' else 'Codex',kind=kind,
                 via='manual' if kind=='person' else 'codex',**kwargs))['resource']


@pytest.mark.parametrize('route',['issues','tasks'])
def test_delegated_snapshot_immutable_and_queryable(client,route):
    human=profile(client);agent=profile(client,'agent',modelName='GPT-6.1 Sol',modelProvider='OpenAI')
    row=write(client,'/api/'+route,dict(title='模型来源快照',creation=dict(identityId=agent['id'],initiatedByPersonId=human['id'])))['resource']
    assert row['creatorName']=='Elias' and row['createdVia']=='codex'
    assert row['createdByActorId']==agent['id'] and row['modelInfo']==dict(name='GPT-6.1 Sol',provider='OpenAI')
    assert row['createdAt'].endswith('+00:00') or row['createdAt'].endswith('Z')
    write(client,'/api/identities/'+human['id'],dict(name='别名'),method='patch')
    write(client,'/api/identities/'+agent['id'],dict(modelName='新默认模型'),method='patch')
    write(client,f'/api/{route}/{row["id"]}',dict(title='改标题'),method='patch')
    write(client,f'/api/{route}/{row["id"]}/trash',{})
    write(client,f'/api/{route}/{row["id"]}/restore',{})
    current=client.get(f'/api/{route}/{row["id"]}').json()['item']
    for k in ['creatorName','createdByActorId','initiatedByPersonId','createdVia','createdAt','modelInfo']:assert row[k]==current[k]
    assert [x['id'] for x in client.get('/api/'+route,params=dict(creator=human['id'],created_via='codex',model='6.1')).json()['items']]==[row['id']]
    assert not client.get('/api/'+route,params=dict(created_via='manual')).json()['items']
    assert client.get('/api/export').json()['data']['identityProfiles']


def test_manual_unknown_and_explicit_empty_model(client):
    human=profile(client);agent=profile(client,'agent',modelName='Default')
    row=write(client,'/api/issues',dict(title='手动',creation=dict(identityId=human['id'])))['resource']
    assert row['createdVia']=='manual' and row['modelInfo'] is None and row['initiatedByPersonId'] is None
    row=write(client,'/api/tasks',dict(title='自主',creation=dict(identityId=agent['id'],modelInfo={})))['resource']
    assert row['creatorName']=='Codex' and row['modelInfo']==dict(name='',provider='')
    unknown=write(client,'/api/issues',dict(title='兼容旧客户端'))['resource']
    assert unknown['createdVia']=='unknown' and unknown['creatorName'] is None


def test_invalid_context_rolls_back_everything(client):
    human=profile(client);agent=profile(client,'agent')
    for context in [dict(identityId=str(uuid4())),dict(identityId=human['id'],modelInfo=dict(name='GPT')),
                    dict(identityId=agent['id'],initiatedByPersonId=agent['id'])]:
        before=client.get('/api/workspace').json();audit=client.get('/api/activity').json()
        write(client,'/api/issues',dict(title='失败不落库',creation=context),expected=404 if context['identityId'] not in [human['id'],agent['id']] else 422)
        assert client.get('/api/workspace').json()==before and client.get('/api/activity').json()==audit
    write(client,'/api/identities/'+human['id'],dict(kind='agent'),method='patch',expected=422)
    write(client,'/api/identities',dict(name='错误人',kind='person',via='codex'),expected=422)


def test_metadata_cannot_be_forged_by_patch(client):
    row=write(client,'/api/issues',dict(title='不可改来源'))['resource']
    write(client,'/api/issues/'+row['id'],dict(createdAt='fake',creatorName='fake'),method='patch',expected=422)
    human=profile(client)
    before=client.get('/api/workspace').json()
    body=dict(request_id=str(uuid4()),expected_version=before['revision'],title='幂等快照',creation=dict(identityId=human['id']))
    first=client.post('/api/issues',json=body);assert first.status_code==200
    assert client.post('/api/issues',json=body).json()==first.json()
    changed=dict(body,creation=dict(identityId=human['id'],modelInfo={}))
    assert client.post('/api/issues',json=changed).status_code==409
