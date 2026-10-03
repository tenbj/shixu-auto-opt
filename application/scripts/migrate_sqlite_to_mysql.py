"""把本地旧工作台迁入空MySQL专属库；源SQLite只读，不删除任何来源数据。"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mysql_store import MySQLStore
from app.domain import empty_state, require, normalize_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    source = sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        revision, payload = source.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
        state = normalize_state(json.loads(payload))
        activity = source.execute('SELECT revision,at,actor,operation,resource_id,payload FROM activity').fetchall()
        requests = source.execute('SELECT request_id,fingerprint,response FROM requests').fetchall()
    finally:
        source.close()
    target = MySQLStore()
    with target.connect() as connection, connection.cursor() as cur:
        current = target._read(cur, lock=True)
        require(current['revision'] == 0 and not current['data']['issues'] and not current['data']['tasks'], 'MySQL目标库非空；拒绝覆盖')
        target._persist(cur, state, empty_state())
        if activity:
            cur.executemany('INSERT INTO activity VALUES (%s,%s,%s,%s,%s,%s)', activity)
        if requests:
            cur.executemany('INSERT INTO idempotency_requests VALUES (%s,%s,%s)', requests)
        cur.execute('UPDATE workspace_meta SET revision=%s WHERE id=1', (revision,))
    result = target.read()
    assert result == dict(revision=revision, data=state), '迁移后回读不一致，保留源库用于检查'
    print(json.dumps({'passed': True, 'database': target.database, 'revision': revision, 'issues': len(state['issues']), 'tasks': len(state['tasks']), 'source_modified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
