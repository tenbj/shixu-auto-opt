"""专属_test库验证：依赖移除保留原行、重新激活与数据库DELETE保护。"""
import argparse,json,sys
from pathlib import Path
from uuid import uuid4
import httpx,pymysql
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.mysql_store import settings,MySQLStore
def run(url):
    client=httpx.Client(base_url=url,trust_env=False,timeout=30)
    health=client.get('/api/health').raise_for_status().json()
    assert health['backend']=='mysql' and health['database'].endswith('_test')
    def write(path,**body):
        rev=client.get('/api/workspace').json()['revision']
        return client.post(path,json=dict(body,expected_version=rev,request_id=str(uuid4()),actor='保留记录验证')).raise_for_status().json()['resource']
    issue=write('/api/issues',title='仅测试库软删除保留 '+str(uuid4())[:8])
    first=write('/api/tasks',title='保留前置',issueId=issue['id'])
    second=write('/api/tasks',title='保留后置',issueId=issue['id'])
    write('/api/tasks/'+second['id']+'/dependencies',dependsOn=[first['id']])
    options=settings(health['database'])
    # Bypass application cursor ONLY to verify database triggers themselves.
    options['cursorclass']=pymysql.cursors.DictCursor
    def edge():
        with pymysql.connect(**options) as conn,conn.cursor() as cur:
            cur.execute('SELECT * FROM task_dependencies WHERE task_id=%s AND dependency_id=%s',(second['id'],first['id']))
            return cur.fetchone()
    assert edge()['deleted_at'] is None
    write('/api/tasks/'+second['id']+'/dependencies',dependsOn=[])
    retained=edge();assert retained and retained['deleted_at']
    assert client.get('/api/tasks/'+second['id']).json()['item']['dependsOn']==[]
    write('/api/tasks/'+second['id']+'/dependencies',dependsOn=[first['id']])
    assert edge()['deleted_at'] is None
    with pymysql.connect(**options) as conn,conn.cursor() as cur:
        cur.execute("SELECT EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME LIKE 'shixu_no_delete_%%'",(health['database'],))
        triggers=cur.fetchall()
        assert len(triggers)==10
        assert all(t['EVENT_MANIPULATION']=='DELETE' and t['ACTION_TIMING']=='BEFORE' and 'SIGNAL' in t['ACTION_STATEMENT'].upper() for t in triggers)
        try:cur.execute('DELETE FROM tasks WHERE id=%s',(second['id'],))
        except pymysql.MySQLError as e:assert e.args[0]==1644 and 'Physical deletion' in str(e)
        else:raise AssertionError('Database allowed physical DELETE')
        finally:conn.rollback()
    deleted=write('/api/issues/'+issue['id']+'/trash')
    snapshot=MySQLStore(health['database']).read()
    assert next(i for i in snapshot['data']['issues'] if i['id']==issue['id'])['deletedAt']
    assert all(next(t for t in snapshot['data']['tasks'] if t['id']==i)['deletedAt'] for i in [first['id'],second['id']])
    write('/api/issues/'+issue['id']+'/restore')
    assert edge()['deleted_at'] is None
    assert client.get('/api/tasks/'+second['id']).json()['item']['dependsOn']==[first['id']]
    report=dict(passed=True,backend='mysql',guards=10,checks=['移除前置保留同一行并标记删除时间','有效依赖过滤已删除关联','重新添加激活原行','数据库自身触发器拒绝DELETE','软删除问题保留行动和依赖，恢复有效原关系'],business_production_writes=0)
    (ROOT/'verification/retention-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);run(p.parse_args().url)
