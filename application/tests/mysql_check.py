"""仅新建_test库：真实MySQL并发、回滚、实体表和幂等持久化验收。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from uuid import uuid4
from http_auth import Session
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mysql_store import MySQLStore


def main(url):
    api=Session(url)
    health = api.get(url + '/api/health', trust_env=False).raise_for_status().json()
    assert health['backend'] == 'mysql' and health['database'].endswith('_test')
    store = MySQLStore(health['database']).for_owner(api.user['id'])
    revision = api.get(url + '/api/workspace', trust_env=False).json()['revision']
    def send(index):
        return api.post(url + '/api/issues', json=dict(title='MySQL并发合成记录 '+str(index), expected_version=revision, request_id=str(uuid4())), timeout=30, trust_env=False).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(send, range(4)))
    assert sorted(statuses) == [200,409,409,409], statuses
    current = store.read()
    issue = current['data']['issues'][0]
    rejected = api.post(url + '/api/issues/' + issue['id'] + '/transitions', json=dict(action='triage',nextStep='事务失败前可能改变的字段',successCriteria='',expected_version=current['revision'],request_id=str(uuid4())), trust_env=False)
    assert rejected.status_code == 422
    assert store.read() == current
    key = str(uuid4())
    body = dict(title='MySQL幂等合成记录', expected_version=current['revision'], request_id=key)
    first = api.post(url + '/api/issues', json=body, trust_env=False).raise_for_status().json()
    second = api.post(url + '/api/issues', json=body, trust_env=False).raise_for_status().json()
    assert first == second
    # Create this check's own related rows; it must also work without earlier demos.
    def write(path, **values):
        version=api.get('/api/workspace').raise_for_status().json()['revision']
        return api.post(path,json=dict(values,expected_version=version,request_id=str(uuid4()))).raise_for_status().json()['resource']
    identifier=first['resource']['id']
    write('/api/issues/'+identifier+'/transitions',action='triage',nextStep='验证关联实体',successCriteria='实体表中可回读')
    write('/api/issues/'+identifier+'/followups',content='独立MySQL验收合成跟进')
    parent=write('/api/tasks',title='前置合成行动',issueId=identifier)
    child=write('/api/tasks',title='后续合成行动',issueId=identifier)
    write('/api/tasks/'+child['id']+'/dependencies',dependsOn=[parent['id']])
    with store.connect() as connection, connection.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS n FROM issues WHERE owner_id=%s',(api.user['id'],))
        issues = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) AS n FROM tasks WHERE owner_id=%s',(api.user['id'],))
        tasks = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) AS n FROM issue_followups WHERE issue_id IN (SELECT id FROM issues WHERE owner_id=%s)',(api.user['id'],))
        followups = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) AS n FROM issue_history WHERE issue_id IN (SELECT id FROM issues WHERE owner_id=%s)',(api.user['id'],))
        histories = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) AS n FROM task_dependencies WHERE task_id IN (SELECT id FROM tasks WHERE owner_id=%s)',(api.user['id'],))
        dependencies = cur.fetchone()['n']
        cur.execute('SELECT COUNT(*) AS n FROM idempotency_requests WHERE owner_id=%s AND request_id=%s', (api.user['id'],key))
        assert cur.fetchone()['n'] == 1
    assert issues and tasks and followups and histories and dependencies
    fresh = MySQLStore(health['database']).for_owner(api.user['id'])
    assert fresh.read() == store.read()
    result = {'passed':True,'backend':'mysql','database_kind':'new-dedicated-test-database','checks':[
        '4个并发同版本请求仅1成功，其余409','非法梳理触发完整事务回滚','重复request_id只提交1次且保存相同响应',
        '直接SQL确认问题/行动/跟进/状态历史/依赖均在实体表','新建独立连接回读完整状态一致'],
        'entity_counts':dict(issues=issues,tasks=tasks,followups=followups,histories=histories,dependencies=dependencies),
        'old_databases_accessed':False}
    (ROOT / 'verification/mysql-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    main(parser.parse_args().url)
