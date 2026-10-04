"""Add renewal/evidence tables after stopping the service; preserve existing rows."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import pymysql

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.mysql_store import settings, APP_ID
from app.onboarding_auth import EXTRA_TABLES

def fingerprint(rows):
    return hashlib.sha256(json.dumps(sorted(json.dumps(r,sort_keys=True,default=str) for r in rows)).encode()).hexdigest()

def migrate(database=None):
    with pymysql.connect(**settings(database)) as conn, conn.cursor() as cur:
        cur.execute('SELECT application_id FROM workspace_meta LIMIT 1')
        if (cur.fetchone() or {}).get('application_id')!=APP_ID:raise RuntimeError('数据库身份不匹配')
        cur.execute('SHOW TABLES');names=[next(iter(x.values())) for x in cur.fetchall()]
        snapshot={}
        for name in names:
            if not re.fullmatch('[a-z_]+',name):raise RuntimeError('不支持的表名')
            cur.execute(f'SHOW CREATE TABLE `{name}`');ddl=cur.fetchone()['Create Table']
            cur.execute(f'SELECT * FROM `{name}`');rows=list(cur.fetchall())
            snapshot[name]=dict(ddl=ddl,rows=rows,sha256=fingerprint(rows))
        target=ROOT/'runtime/backups'/('before-onboarding-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(snapshot,ensure_ascii=False,default=str),encoding='utf-8')
        if set(json.loads(target.read_text(encoding='utf-8')))!=set(snapshot):raise RuntimeError('快照校验失败')
        conn.commit()
        for name,columns in EXTRA_TABLES.items():
            cur.execute(f'CREATE TABLE IF NOT EXISTS {name} ({columns}) ENGINE=InnoDB')
            cur.execute('SHOW TRIGGERS WHERE `Table`=%s',(name,))
            if not any(x['Event']=='DELETE' for x in cur.fetchall()):
                cur.execute(f"CREATE TRIGGER no_delete_{name} BEFORE DELETE ON {name} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled'")
        cur.execute('INSERT INTO access_metadata (access_id) SELECT id FROM account_access WHERE id NOT IN (SELECT access_id FROM access_metadata)')
        conn.commit()
        preserved={}
        for name,data in snapshot.items():
            if name in EXTRA_TABLES:continue
            cur.execute(f'SELECT * FROM `{name}`');preserved[name]=fingerprint(list(cur.fetchall()))==data['sha256']
        if not all(preserved.values()):raise RuntimeError('原数据不一致，请保持停服并检查私有快照')
        return dict(passed=True,version='3.1.0',backup_created=True,preserved=preserved,added_tables=list(EXTRA_TABLES))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database');args=parser.parse_args()
    print(json.dumps(migrate(args.database),ensure_ascii=False))
