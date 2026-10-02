"""增量迁移2.2.1：专属库追加软删除字段、索引与禁止DELETE触发器，不改变业务记录。"""
import argparse, json, sys
from pathlib import Path
import pymysql
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mysql_store import settings, APP_ID

def migrate(database=None):
    options = settings(database)
    report = dict(database=options['database'], added=[], existing=[], rows={})
    connection = pymysql.connect(**options)
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
            row = cur.fetchone()
            if not row or row['application_id'] != APP_ID:
                raise RuntimeError('数据库身份不匹配，拒绝迁移')
            for table in ['issues','tasks']:
                cur.execute(f'SELECT COUNT(*) AS n FROM {table}')
                report['rows'][table] = cur.fetchone()['n']
                cur.execute('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (options['database'], table))
                columns = {r['COLUMN_NAME'] for r in cur.fetchall()}
                for name, dtype in [('deleted_at','VARCHAR(40)'),('deletion_batch','VARCHAR(36)'),('deleted_with_issue','VARCHAR(36)')]:
                    if name in columns:
                        report['existing'].append(table+'.'+name)
                    else:
                        cur.execute(f'ALTER TABLE {table} ADD COLUMN {name} {dtype} NULL')
                        report['added'].append(table+'.'+name)
                cur.execute(f'SHOW INDEX FROM {table}')
                indexes = {r['Key_name'] for r in cur.fetchall()}
                index = 'idx_' + ('issue' if table == 'issues' else 'task') + '_deleted'
                if index not in indexes:
                    cur.execute(f'ALTER TABLE {table} ADD INDEX {index}(deleted_at)')
                    report['added'].append(index)
                cur.execute(f'SELECT COUNT(*) AS n FROM {table}')
                assert report['rows'][table] == cur.fetchone()['n']
            cur.execute('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (options['database'], 'task_dependencies'))
            if 'deleted_at' not in {r['COLUMN_NAME'] for r in cur.fetchall()}:
                cur.execute('ALTER TABLE task_dependencies ADD COLUMN deleted_at VARCHAR(40) NULL')
                report['added'].append('task_dependencies.deleted_at')
            cur.execute('SHOW INDEX FROM task_dependencies')
            if 'idx_dependency_deleted' not in {r['Key_name'] for r in cur.fetchall()}:
                cur.execute('ALTER TABLE task_dependencies ADD INDEX idx_dependency_deleted(deleted_at)')
                report['added'].append('idx_dependency_deleted')
            tables = ['workspace_meta','issues','tasks','task_dependencies','issue_followups','issue_history','issue_logs','activity','idempotency_requests']
            cur.execute('SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s', (options['database'],))
            existing = {r['TRIGGER_NAME'] for r in cur.fetchall()}
            for table in tables:
                name = 'shixu_no_delete_' + table
                if name not in existing:
                    cur.execute(f"CREATE TRIGGER {name} BEFORE DELETE ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled'")
                    report['added'].append(name)
            report['delete_guards'] = len(tables)
        connection.commit()
        report['passed'] = True
        return report
    finally:
        connection.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = migrate(args.database)
    if args.report: args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
