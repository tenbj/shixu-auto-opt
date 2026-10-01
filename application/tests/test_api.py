import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'workspace.sqlite3')) as value:
        yield value


def write(client, route, values, method='POST', expected=200, version=None, request_id=None):
    version = client.get('/api/workspace').json()['revision'] if version is None else version
    body = dict(values, request_id=request_id or str(uuid4()), expected_version=version, actor='隔离测试')
    result = client.request(method, route, json=body)
    assert result.status_code == expected, result.text
    return result.json()


def issue(client):
    return write(client, '/api/issues', {'title': '合成测试问题'})['resource']['id']


def task(client, issue_id=None):
    return write(client, '/api/tasks', {'title': '合成测试行动', 'issueId': issue_id})['resource']['id']


def stage(client, identifier, action, **values):
    return write(client, f'/api/issues/{identifier}/transitions', dict(action=action, **values))


def triage(client, identifier):
    stage(client, identifier, 'triage', nextStep='运行试验', successCriteria='检查通过')


def verify(client, identifier):
    return stage(client, identifier, 'verify', successCriteria='检查通过', treatment='已执行观察', verificationMethod='隔离测试回读')


def test_full_lifecycle_and_audit(client):
    p = issue(client)
    t = task(client, p)
    write(client, f'/api/tasks/{t}/transitions', {'status': '进行中'}, expected=422)
    triage(client, p)
    write(client, f'/api/tasks/{t}/transitions', {'status': '进行中'})
    assert client.get(f'/api/issues/{p}').json()['item']['status'] == '处理中'
    write(client, f'/api/issues/{p}/transitions', {'action': 'verify'}, expected=422)
    write(client, f'/api/tasks/{t}/transitions', {'status': '已完成'})
    verify(client, p)
    write(client, f'/api/issues/{p}/transitions', {'action': 'resolve'}, expected=422)
    stage(client, p, 'resolve', resolution='隔离测试报告显示所有预期成立')
    write(client, f'/api/tasks/{t}/transitions', {'status': '待办'})
    result = client.get(f'/api/issues/{p}').json()['item']
    assert result['status'] == '处理中'
    assert result['resolution'] and result['history'][-1]['actor'] == '隔离测试'
    assert len(client.get('/api/activity').json()['items']) == client.get('/api/workspace').json()['revision']


def test_zero_task_observation_and_reopen(client):
    p = issue(client)
    verify(client, p)
    stage(client, p, 'reject', reason='观察不足')
    verify(client, p)
    stage(client, p, 'resolve', resolution='重复观察后成立')
    stage(client, p, 'reopen', reason='问题复发')
    assert client.get(f'/api/issues/{p}').json()['item']['status'] == '处理中'


@pytest.mark.parametrize('action', ['resolve', 'start', 'resume', 'reopen', 'reject'])
def test_illegal_issue_transitions(client, action):
    p = issue(client)
    before = client.get('/api/workspace').json()
    write(client, f'/api/issues/{p}/transitions', {'action': action}, expected=409)
    assert client.get('/api/workspace').json() == before


def test_pause_resume_close_detach(client):
    p = issue(client)
    t = task(client, p)
    triage(client, p)
    stage(client, p, 'pause', reason='等待资料', reviewDate='2099-01-01')
    write(client, f'/api/tasks/{t}/transitions', {'status': '进行中'}, expected=422)
    stage(client, p, 'resume')
    assert client.get(f'/api/issues/{p}').json()['item']['status'] == '待处理'
    write(client, f'/api/issues/{p}/transitions', {'action': 'close-issue', 'reason': '范围变化', 'closeType': '不再处理'}, expected=422)
    stage(client, p, 'close-issue', reason='范围变化', closeType='不再处理', taskPolicy='detach')
    item = client.get(f'/api/tasks/{t}').json()['item']
    assert item['issueId'] is None and item['numberGroup'] == '独立'
    stage(client, p, 'reopen', reason='重新考虑')
    assert client.get(f'/api/issues/{p}').json()['item']['status'] == '待梳理'


def test_duplicate_close_and_cancel(client):
    p, q = issue(client), issue(client)
    t = task(client, p)
    write(client, f'/api/issues/{p}/transitions', dict(action='close-issue', reason='重复', closeType='重复问题', duplicateOf=p, taskPolicy='cancel'), expected=422)
    stage(client, p, 'close-issue', reason='重复', closeType='重复问题', duplicateOf=q, taskPolicy='cancel')
    assert client.get(f'/api/tasks/{t}').json()['item']['cancelReason']


def test_dependencies_cycle_scope_and_reopen(client):
    p = issue(client)
    a, b = task(client, p), task(client, p)
    independent = task(client)
    write(client, f'/api/tasks/{b}/dependencies', {'dependsOn': [a]})
    write(client, f'/api/tasks/{a}/dependencies', {'dependsOn': [b]}, expected=422)
    write(client, f'/api/tasks/{a}/dependencies', {'dependsOn': [a]}, expected=422)
    write(client, f'/api/tasks/{a}/dependencies', {'dependsOn': [independent]}, expected=422)
    triage(client, p)
    write(client, f'/api/tasks/{b}/transitions', {'status': '进行中'}, expected=422)
    write(client, f'/api/tasks/{a}/transitions', {'status': '已完成'})
    write(client, f'/api/tasks/{b}/transitions', {'status': '进行中'})
    write(client, f'/api/tasks/{a}/transitions', {'status': '待办'}, expected=422)
    write(client, f'/api/tasks/{b}', {'issueId': None}, method='PATCH', expected=422)


def test_followup_edit_filter_export(client):
    p = issue(client)
    write(client, f'/api/issues/{p}/followups', {'content': '<script>literal text</script>'})
    write(client, f'/api/issues/{p}', {'title': '更新标题', 'description': '背景', 'priority': '高', 'tag': '测试'}, method='PATCH')
    result = client.get('/api/issues', params=dict(q='背景', tag='测试', priority='高', status='待梳理')).json()
    assert len(result['items']) == 1
    assert result['items'][0]['followups'][0]['content'].startswith('<script>')
    assert client.get('/api/export').json()['data']['issues'][0]['title'] == '更新标题'


def test_numbering_and_reorder(client):
    p = issue(client)
    a, b = task(client, p), task(client, p)
    before = client.get(f'/api/tasks/{a}').json()['item']
    write(client, f'/api/tasks/{a}/reorder', dict(target_id=b, after=True))
    after = client.get(f'/api/tasks/{a}').json()['item']
    assert before['sequence'] == after['sequence'] and before['numberGroup'] == after['numberGroup']
    assert client.get('/api/tasks').json()['items'][-1]['id'] == a
    write(client, f'/api/tasks/{a}', {'issueId': None}, method='PATCH')
    write(client, f'/api/tasks/{a}', {'issueId': p}, method='PATCH')
    assert client.get(f'/api/tasks/{a}').json()['item']['sequence'] == 3


def test_idempotency_conflict_and_persistence(client):
    key = str(uuid4())
    first = write(client, '/api/issues', {'title': '幂等写入'}, request_id=key, version=0)
    second = write(client, '/api/issues', {'title': '幂等写入'}, request_id=key, version=0)
    assert first == second
    write(client, '/api/issues', {'title': '不同内容'}, request_id=key, version=0, expected=409)
    write(client, '/api/issues', {'title': '旧版本'}, version=0, expected=409)
    with TestClient(create_app(client.app.state.store.path)) as restarted:
        assert restarted.get('/api/workspace').json()['revision'] == 1
        assert write(restarted, '/api/issues', {'title': '幂等写入'}, request_id=key, version=0) == first


def test_concurrent_writers(client):
    def send(index):
        return client.post('/api/issues', json={'title': str(index), 'expected_version': 0, 'request_id': str(uuid4())}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(send, range(4)))
    assert sorted(statuses) == [200, 409, 409, 409]
    assert len(client.get('/api/issues').json()['items']) == 1


@pytest.mark.parametrize('values', [{'title': ''}, {'title': '  '}, {'title': 'x' * 161}, {'title': 'x', 'status': '已解决'}, {'title': 'x', 'priority': '非法'}])
def test_input_validation(client, values):
    write(client, '/api/issues', values, expected=422)
    assert client.get('/api/workspace').json()['revision'] == 0


@pytest.mark.parametrize('due', ['2026-02-30', 'tomorrow', None])
def test_invalid_dates(client, due):
    t = task(client)
    write(client, f'/api/tasks/{t}', {'due': due}, method='PATCH', expected=422)


def test_required_tasks_and_cancel_reason(client):
    p = issue(client)
    t = task(client, p)
    triage(client, p)
    stage(client, p, 'start')
    write(client, f'/api/tasks/{t}/transitions', {'status': '已取消'}, expected=422)
    write(client, f'/api/tasks/{t}', {'required': False}, method='PATCH')
    verify(client, p)
    write(client, f'/api/tasks/{t}', {'required': True}, method='PATCH')
    assert client.get(f'/api/issues/{p}').json()['item']['status'] == '处理中'


def test_unknown_ids_and_origin_protection(client):
    assert client.get('/api/issues/missing').status_code == 404
    assert client.post('/api/issues', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/health', headers={'Host': 'evil.example'}).status_code == 400
    assert client.get('/api/activity?limit=501').status_code == 422


def test_lan_access_keeps_host_and_origin_checks(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIXU_ALLOWED_HOSTS', '192.168.1.138,0.0.0.0')
    with TestClient(create_app(tmp_path / 'lan.sqlite3'), base_url='http://192.168.1.138:8765') as lan:
        assert lan.get('/').status_code == 200
        assert lan.get('/api/health').status_code == 200
        body = {'title': '内网同源合成测试', 'expected_version': 0, 'request_id': str(uuid4())}
        assert lan.post('/api/issues', json=body, headers={'Origin': 'http://192.168.1.138:8765'}).status_code == 200
        assert lan.get('/api/workspace').json()['revision'] == 1
        assert lan.post('/api/issues', json=body, headers={'Origin': 'http://192.168.1.138:9999'}).status_code == 403
        assert lan.get('/api/health', headers={'Host': 'evil.example'}).status_code == 400
        assert lan.get('/api/health', headers={'Host': '0.0.0.0:8765'}).status_code == 200
