"""3.2.0增量迁移：先备份全部表，新增工具目录并扩展来源ID；幂等、保留原值。停写期间执行。"""
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import pymysql
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.mysql_store import settings, APP_ID
from migrate_creators import digest

def migrate(database=None):
    options=settings(database)
    report=dict(passed=False,version='3.2.0',added=[],preserved_tables={},backup_created=False)
    with pymysql.connect(**options) as conn,conn.cursor() as cur:
        cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
        if (cur.fetchone() or {}).get('application_id')!=APP_ID:raise RuntimeError('拒绝迁移非拾序库')
        cur.execute('SHOW TABLES');tables=[next(iter(x.values())) for x in cur.fetchall()]
        if not all(re.fullmatch('[a-z_]+',t) for t in tables):raise RuntimeError('非应用表名')
        snapshot={}
        for table in tables:
            cur.execute(f'SHOW CREATE TABLE `{table}`');ddl=cur.fetchone()['Create Table']
            cur.execute(f'SELECT * FROM `{table}`');rows=list(cur.fetchall())
            snapshot[table]=dict(ddl=ddl,rows=rows)
        cur.execute('SHOW TRIGGERS');triggers=list(cur.fetchall())
        backup=ROOT/'runtime/backups'/('before-custom-tools-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(json.dumps(dict(database=options['database'],tables=snapshot,triggers=triggers),ensure_ascii=False,default=str),encoding='utf-8')
        assert json.loads(backup.read_text(encoding='utf-8'))['tables'].keys()==snapshot.keys()
        report['backup_created']=True;conn.commit()
        schema=(ROOT/'data/mysql-schema.sql').read_text(encoding='utf-8')
        if 'ai_tools' not in tables:
            cur.execute(re.search(r'CREATE TABLE ai_tools \(.*?\) ENGINE=InnoDB;',schema,re.S).group(0));report['added'].append('ai_tools')
        for table,field,definition in [('identity_profiles','via','NOT NULL'),('issues','created_via',"NOT NULL DEFAULT 'unknown'"),('tasks','created_via',"NOT NULL DEFAULT 'unknown'"),('activity','resource_id','NULL')]:
            cur.execute(f'SHOW COLUMNS FROM `{table}` LIKE %s',(field,))
            if cur.fetchone()['Type'].lower()!='varchar(80)':
                cur.execute(f'ALTER TABLE `{table}` MODIFY COLUMN `{field}` VARCHAR(80) '+definition);report['added'].append(table+'.'+field)
        if not any(t['Trigger']=='shixu_no_delete_ai_tools' for t in triggers):
            cur.execute(re.search(r'CREATE TRIGGER shixu_no_delete_ai_tools[^;]+',schema).group(0));report['added'].append('tool_delete_guard')
        for table,data in snapshot.items():
            cur.execute(f'SELECT * FROM `{table}`');after=list(cur.fetchall())
            if digest(data['rows'])!=digest(after):raise RuntimeError('数据校验不一致：'+table)
            report['preserved_tables'][table]=dict(rows=len(after),sha256=digest(after))
        conn.commit()
    report['passed']=True
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database');p.add_argument('--report',type=Path)
    a=p.parse_args();r=migrate(a.database)
    if a.report:a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False))
