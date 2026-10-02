"""单人工作台：一致性快照、审计和幂等结果在同一事务内提交。"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from . import domain


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activity (revision INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, operation TEXT NOT NULL, resource_id TEXT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS no_delete_workspace BEFORE DELETE ON workspace BEGIN SELECT RAISE(ABORT, 'Physical deletion is disabled'); END;
                CREATE TRIGGER IF NOT EXISTS no_delete_activity BEFORE DELETE ON activity BEGIN SELECT RAISE(ABORT, 'Physical deletion is disabled'); END;
                CREATE TRIGGER IF NOT EXISTS no_delete_requests BEFORE DELETE ON requests BEGIN SELECT RAISE(ABORT, 'Physical deletion is disabled'); END;
                PRAGMA user_version=1;
            ''')
            connection.execute('INSERT OR IGNORE INTO workspace VALUES (1,0,?)', (dumps(domain.empty_state()),))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.execute('PRAGMA busy_timeout=10000')
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self):
        with self.connect() as connection:
            revision, payload = connection.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
            return dict(revision=revision, data=json.loads(payload))

    def activity(self, after=0, limit=100):
        with self.connect() as connection:
            rows = connection.execute('SELECT revision,at,actor,operation,resource_id FROM activity WHERE revision>? ORDER BY revision LIMIT ?', (after, limit)).fetchall()
        return [dict(zip(['revision', 'at', 'actor', 'operation', 'resource_id'], row)) for row in rows]

    def mutate(self, operation, identifier, body):
        body = dict(body)
        request_id, expected, actor = body.pop('request_id'), body.pop('expected_version'), body.pop('actor')
        fingerprint = hashlib.sha256(dumps([operation, identifier, expected, actor, body]).encode()).hexdigest()
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            previous = connection.execute('SELECT fingerprint,response FROM requests WHERE request_id=?', (request_id,)).fetchone()
            if previous:
                domain.require(previous[0] == fingerprint, 'request_id 已用于不同请求，请使用新编号', 409)
                return json.loads(previous[1])
            revision, payload = connection.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
            domain.require(revision == expected, '工作台已更新，请重新读取版本后再提交', 409)
            state = json.loads(payload)
            resource = domain.apply(state, operation, identifier, body, actor)
            revision += 1
            response = dict(revision=revision, resource=resource, data=state)
            connection.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1', (revision, dumps(state)))
            connection.execute('INSERT INTO activity VALUES (?,?,?,?,?,?)', (revision, domain.now(), actor, operation, resource['id'], dumps(body)))
            connection.execute('INSERT INTO requests VALUES (?,?,?)', (request_id, fingerprint, dumps(response)))
            return response
