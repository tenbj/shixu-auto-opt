"""账号隔离迁移：停服后执行；先保存本地私有全量快照，保留所有原列。"""
import argparse, json, os, re, sys
from pathlib import Path
from datetime import datetime, timezone
import pymysql
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.mysql_store import settings, APP_ID, MySQLStore
from app.accounts import Accounts, TABLES
from migrate_creators import digest

def migrate(database=None):
    options=settings(database)
    with pymysql.connect(**options) as conn, conn.cursor() as cur:
        cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
        if (cur.fetchone() or {}).get('application_id')!=APP_ID:raise RuntimeError('数据库身份不符')
        cur.execute('SHOW TABLES');tables=[next(iter(x.values())) for x in cur.fetchall()]
        snapshot={}
        for table in tables:
            if not re.fullmatch('[a-z_]+',table):raise RuntimeError('不支持的表名')
            cur.execute(f'SHOW CREATE TABLE `{table}`');ddl=cur.fetchone()['Create Table']
            cur.execute(f'SHOW COLUMNS FROM `{table}`');columns=[r['Field'] for r in cur.fetchall()]
            cur.execute(f'SELECT * FROM `{table}`');snapshot[table]=dict(ddl=ddl,columns=columns,rows=list(cur.fetchall()))
        cur.execute('SHOW TRIGGERS');triggers=list(cur.fetchall())
        backup=ROOT/'runtime/backups'/('before-accounts-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(json.dumps(dict(database=options['database'],tables=snapshot,triggers=triggers),ensure_ascii=False,default=str),encoding='utf-8')
        if json.loads(backup.read_text(encoding='utf-8'))['tables'].keys()!=snapshot.keys():raise RuntimeError('备份校验失败')
        conn.commit()
        if 'app_users' not in tables and not os.getenv('SHIXU_BOOTSTRAP_PASSWORD'):raise RuntimeError('请通过私有环境提供SHIXU_BOOTSTRAP_PASSWORD')
        for name,fields in TABLES.items():cur.execute(f'CREATE TABLE IF NOT EXISTS {name} ({fields}) ENGINE=InnoDB')
        for table in ['workspace_meta','issues','tasks','identity_profiles','activity','idempotency_requests']:
            cur.execute(f'SHOW COLUMNS FROM {table}')
            if 'owner_id' not in [r['Field'] for r in cur.fetchall()]:cur.execute(f'ALTER TABLE {table} ADD COLUMN owner_id VARCHAR(36) NULL')
        cur.execute('ALTER TABLE workspace_meta MODIFY id BIGINT NOT NULL AUTO_INCREMENT')
        indexes={}
        for table in ['workspace_meta','issues','tasks','activity','idempotency_requests']:
            cur.execute(f'SHOW INDEX FROM {table}');indexes[table]={r['Key_name'] for r in cur.fetchall()}
        if 'number' in indexes['issues']:cur.execute('ALTER TABLE issues DROP INDEX number')
        if 'unique_task_number' in indexes['tasks']:cur.execute('ALTER TABLE tasks DROP INDEX unique_task_number')
        for table,columns in [('activity','owner_id,revision'),('idempotency_requests','owner_id,request_id')]:
            cur.execute(f'SHOW INDEX FROM {table} WHERE Key_name=\'PRIMARY\'')
            if 'owner_id' not in [r['Column_name'] for r in cur.fetchall()]:
                cur.execute(f"UPDATE {table} SET owner_id='test' WHERE owner_id IS NULL")
                cur.execute(f'ALTER TABLE {table} DROP PRIMARY KEY, ADD PRIMARY KEY ({columns})')
        for table,name,columns in [('workspace_meta','uq_workspace_owner','owner_id'),('issues','uq_owner_issue_number','owner_id,number'),('tasks','uq_owner_task_number','owner_id,number_group,sequence_number')]:
            if name not in indexes[table]:cur.execute(f'ALTER TABLE {table} ADD UNIQUE KEY {name} ({columns})')
        conn.commit()
    accounts=Accounts(MySQLStore(database));accounts.bootstrap(os.getenv('SHIXU_BOOTSTRAP_PASSWORD'))
    with pymysql.connect(**options) as conn, conn.cursor() as cur:
        for table in ['workspace_meta','issues','tasks','identity_profiles','activity','idempotency_requests']:
            cur.execute(f"UPDATE {table} SET owner_id='test' WHERE owner_id IS NULL")
            cur.execute(f'ALTER TABLE {table} MODIFY owner_id VARCHAR(36) NOT NULL')
        # 原始业务列、审计及幂等响应均逐表比对，排除本次归属列。
        preserved={}
        for table in snapshot:
            if table in TABLES:continue
            columns=[c for c in snapshot[table]['columns'] if c!='owner_id']
            cur.execute('SELECT '+','.join('`'+c+'`' for c in columns)+' FROM `'+table+'`')
            actual=list(cur.fetchall());before=[{c:r[c] for c in columns} for r in snapshot[table]['rows']]
            preserved[table]=digest(actual)==digest(before)
        if not all(preserved.values()):raise RuntimeError('原列校验不一致，请保留停服状态并检查私有备份')
        for table in TABLES:
            cur.execute('SHOW TRIGGERS WHERE `Table`=%s',(table,))
            if not any(r['Event']=='DELETE' for r in cur.fetchall()):cur.execute(f"CREATE TRIGGER no_delete_{table} BEFORE DELETE ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled'")
        conn.commit()
    return dict(passed=True,backup_created=True,preserved_tables=preserved,version='3.0.0',legacy_owner='test')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database');args=parser.parse_args()
    print(json.dumps(migrate(args.database),ensure_ascii=False))
