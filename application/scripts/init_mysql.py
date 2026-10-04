"""初始化已创建的空专属库。无IF NOT EXISTS、无DROP、无覆盖已有表。"""
import argparse
import os
from pathlib import Path
import sys
import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mysql_store import settings, APP_ID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if not os.getenv('SHIXU_BOOTSTRAP_PASSWORD'):raise SystemExit('Set SHIXU_BOOTSTRAP_PASSWORD before initialization')
    options = settings(args.database)
    connection = pymysql.connect(**options)
    try:
        with connection.cursor() as cur:
            cur.execute('SHOW TABLES')
            if cur.fetchall():
                raise SystemExit('目标库非空；拒绝初始化或覆盖')
            source = '\n'.join(line for line in (ROOT / 'data/mysql-schema.sql').read_text(encoding='utf-8').splitlines() if not line.startswith('--'))
            for statement in source.split(';'):
                if statement.strip():
                    cur.execute(statement)
            cur.execute("INSERT INTO workspace_meta (id,application_id,revision,next_issue_number,next_task_numbers,owner_id) VALUES (1,%s,0,1,%s,'test')", (APP_ID, '{}'))
        connection.commit()
        from app.accounts import Accounts
        from app.mysql_store import MySQLStore
        Accounts(MySQLStore(args.database)).bootstrap(os.getenv('SHIXU_BOOTSTRAP_PASSWORD'))
        print('Initialized account-isolated schema in ' + args.database)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
