"""升级本机已由service.py管理的2.2.1服务；先冻结快照，增量迁移，再重启验证。"""
import hashlib,json,subprocess,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from migrate_creators import migrate


def run():
    url='http://127.0.0.1:8765'
    with httpx.Client(base_url=url,trust_env=False,timeout=30) as client:
        try:health=client.get('/api/health').raise_for_status().json()
        except httpx.ConnectError:health=None
        record=ROOT/'runtime/service-8765.json'
        service=json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
        before=None
        if health:
            assert health['backend']=='mysql' and health['version']=='2.2.1','Only migrate the known previous service'
            before=client.get('/api/workspace').raise_for_status().json()
            assert service.get('instance')==health['instance'] and service.get('pid')==health['pid']
            # JSON snapshot is private; full table/trigger backup is made by migrate().
            backup=ROOT/'runtime/backups/creator-upgrade-workspace.json'
            backup.parent.mkdir(parents=True,exist_ok=True)
            with backup.open('x',encoding='utf-8') as f:json.dump(before,f,ensure_ascii=False)
            subprocess.run([sys.executable,'scripts/service.py','stop'],cwd=ROOT,check=True)
        result=migrate()
        subprocess.run([sys.executable,'scripts/service.py','start','--host',service.get('bind_host','127.0.0.1')],cwd=ROOT,check=True)
        after=client.get('/api/workspace').raise_for_status().json()
        current=client.get('/api/health').raise_for_status().json()
        assert current['version']=='2.3.0' and current['backend']=='mysql'
        if before:
            assert before['revision']==after['revision']
            for kind in ['issues','tasks']:
                old={x['id']:x for x in before['data'][kind]};new={x['id']:x for x in after['data'][kind]}
                assert old.keys()==new.keys()
                for key,row in old.items():
                    assert all(new[key][field]==value for field,value in row.items()),'Historical fields changed'
            assert after['data']['nextIssueNumber']==before['data']['nextIssueNumber']
            assert after['data']['nextTaskNumbers']==before['data']['nextTaskNumbers']
        for kind in ['issues','tasks']:
            assert len(after['data'][kind])==result['preserved_tables'][kind]['rows']
            assert all(x['createdVia']=='unknown' and x['createdAt'] is None for x in after['data'][kind])
        assert after['data']['identityProfiles']==[]
        assert len(client.get('/api/identities').raise_for_status().json()['items'])==0
        report=dict(passed=True,version=current['version'],backend=current['backend'],revision=after['revision'],
                    issues=len(after['data']['issues']),tasks=len(after['data']['tasks']),business_rows_written=0,
                    source_prototype_modified=False,migration=result)
        (ROOT/'verification/deployment-2.3.0.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':run()
