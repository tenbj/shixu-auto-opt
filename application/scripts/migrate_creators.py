"""2.3.0 增量迁移：先备份专属库全部表，再增加身份表与创建快照字段。可重复执行。"""
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import pymysql
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.mysql_store import settings, APP_ID


def digest(rows):
    return hashlib.sha256(json.dumps(sorted(rows,key=lambda x:json.dumps(x,sort_keys=True,default=str)),sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def migrate(database=None):
    options=settings(database)
    report=dict(passed=False,version='2.3.0',added=[],preserved_tables={},backup_created=False)
    with pymysql.connect(**options) as conn, conn.cursor() as cur:
        cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
        if (cur.fetchone() or {}).get('application_id')!=APP_ID: raise RuntimeError('拒绝迁移非拾序专属库')
        cur.execute('SHOW TABLES')
        tables=[next(iter(x.values())) for x in cur.fetchall()]
        if not all(re.fullmatch('[a-z_]+',t) for t in tables): raise RuntimeError('表名不符合应用范围')
        snapshot={}
        for table in tables:
            cur.execute(f'SHOW CREATE TABLE `{table}`');ddl=cur.fetchone()['Create Table']
            cur.execute(f'SELECT * FROM `{table}`');rows=list(cur.fetchall())
            cur.execute(f'SHOW COLUMNS FROM `{table}`');columns=[x['Field'] for x in cur.fetchall()]
            snapshot[table]=dict(ddl=ddl,columns=columns,rows=rows)
        cur.execute('SHOW TRIGGERS');triggers=list(cur.fetchall())
        backup=ROOT/'runtime'/'backups'/('before-creators-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(json.dumps(dict(database=options['database'],tables=snapshot,triggers=triggers),ensure_ascii=False,default=str),encoding='utf-8')
        assert json.loads(backup.read_text(encoding='utf-8'))['tables'].keys()==snapshot.keys()
        report['backup_created']=True
        conn.commit()
        ddl=(ROOT/'data/mysql-schema.sql').read_text(encoding='utf-8')
        if 'identity_profiles' not in tables:
            cur.execute(re.search(r'CREATE TABLE identity_profiles \(.*?\) ENGINE=InnoDB;',ddl,re.S).group(0))
            report['added'].append('identity_profiles')
        fields=[('created_by_actor_id','VARCHAR(36) NULL'),('initiated_by_person_id','VARCHAR(36) NULL'),
                ('creator_name','VARCHAR(60) NULL'),('created_via',"VARCHAR(32) NOT NULL DEFAULT 'unknown'"),
                ('created_at','VARCHAR(40) NULL'),('model_info','JSON NULL')]
        for table in ['issues','tasks']:
            cur.execute(f'SHOW COLUMNS FROM `{table}`');existing={x['Field'] for x in cur.fetchall()}
            for field,dtype in fields:
                if field not in existing:
                    cur.execute(f'ALTER TABLE `{table}` ADD COLUMN `{field}` {dtype}')
                    report['added'].append(table+'.'+field)
        if not any(x['Trigger']=='shixu_no_delete_identity_profiles' for x in triggers):
            cur.execute("CREATE TRIGGER shixu_no_delete_identity_profiles BEFORE DELETE ON identity_profiles FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled'")
            report['added'].append('identity_delete_guard')
        for table,data in snapshot.items():
            columns=','.join('`'+c+'`' for c in data['columns'])
            cur.execute(f'SELECT {columns} FROM `{table}`')
            after=list(cur.fetchall())
            if digest(data['rows'])!=digest(after): raise RuntimeError('迁移前后原有数据不一致：'+table)
            report['preserved_tables'][table]=dict(rows=len(after),sha256=digest(after))
        conn.commit()
    report['passed']=True
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database');p.add_argument('--report',type=Path)
    a=p.parse_args();result=migrate(a.database)
    if a.report:a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
