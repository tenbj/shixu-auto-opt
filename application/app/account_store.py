"""SQLite隔离测试底座。生产继续使用MySQL实体表。"""
import copy
import hashlib
import json
from .store import Store, dumps
from . import domain

class ScopedSQLite(Store):
    def __init__(self, base, user_id):
        self.path, self.user_id = base.path, user_id

    def read(self):
        with self.connect() as c:
            row = c.execute('SELECT revision,payload FROM account_workspace WHERE owner_id=?', (self.user_id,)).fetchone()
            domain.require(row, '工作台不存在', 404)
            return dict(revision=row[0], data=domain.normalize_state(json.loads(row[1])))

    def activity(self, after=0, limit=100):
        with self.connect() as c:
            rows = c.execute('SELECT revision,at,actor,operation,resource_id FROM account_activity WHERE owner_id=? AND revision>? ORDER BY revision LIMIT ?', (self.user_id, after, limit)).fetchall()
            return [dict(zip(['revision','at','actor','operation','resource_id'], r)) for r in rows]

    def mutate(self, operation, identifier, body):
        values = dict(body)
        req, expected, actor = values.pop('request_id'), values.pop('expected_version'), values.pop('actor')
        fingerprint = hashlib.sha256(dumps([operation,identifier,expected,actor,values]).encode()).hexdigest()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = c.execute('SELECT fingerprint,response FROM account_requests WHERE owner_id=? AND request_id=?', (self.user_id, req)).fetchone()
            if previous:
                domain.require(previous[0] == fingerprint, 'request_id已用于其他内容', 409)
                return json.loads(previous[1])
            row = c.execute('SELECT revision,payload FROM account_workspace WHERE owner_id=?', (self.user_id,)).fetchone()
            domain.require(row and row[0] == expected, '工作台已更新，请重新读取版本', 409)
            state = json.loads(row[1])
            resource = domain.apply(state,operation,identifier,values,actor)
            revision = expected+1
            result = dict(revision=revision,resource=resource,data=state)
            c.execute('UPDATE account_workspace SET revision=?,payload=? WHERE owner_id=?', (revision,dumps(state),self.user_id))
            c.execute('INSERT INTO account_activity VALUES (?,?,?,?,?,?,?)', (self.user_id,revision,domain.now(),actor,operation,resource['id'],dumps(values)))
            c.execute('INSERT INTO account_requests VALUES (?,?,?,?)', (self.user_id,req,fingerprint,dumps(result)))
            return result

def initialize_sqlite(base):
    with base.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS account_workspace(owner_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS account_activity(owner_id TEXT NOT NULL,revision INTEGER NOT NULL,at TEXT NOT NULL,actor TEXT NOT NULL,operation TEXT NOT NULL,resource_id TEXT,payload TEXT NOT NULL,PRIMARY KEY(owner_id,revision));
        CREATE TABLE IF NOT EXISTS account_requests(owner_id TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(owner_id,request_id));
        ''')
        for table in ('account_workspace','account_activity','account_requests'):
            c.execute(f"CREATE TRIGGER IF NOT EXISTS no_delete_{table} BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'Physical deletion is disabled'); END")
    base.for_owner = lambda identifier: ScopedSQLite(base, identifier)

def create_sqlite_workspace(base, identifier, legacy=False):
    with base.connect() as c:
        if legacy:
            c.execute('INSERT OR IGNORE INTO account_workspace SELECT ?,revision,payload FROM workspace WHERE id=1', (identifier,))
            c.execute('INSERT OR IGNORE INTO account_activity SELECT ?,revision,at,actor,operation,resource_id,payload FROM activity', (identifier,))
            c.execute('INSERT OR IGNORE INTO account_requests SELECT ?,request_id,fingerprint,response FROM requests', (identifier,))
        else:
            c.execute('INSERT OR IGNORE INTO account_workspace VALUES (?,0,?)',(identifier,dumps(domain.empty_state())))
