"""MySQL 连接复用。只使用假连接，不访问真实数据库。"""
import threading
import pymysql
import pytest
from app.mysql_store import APP_ID, ISOLATION_SQL, TIME_ZONE_SQL, MySQLStore

class World:
    def __init__(self, application_id=APP_ID):
        self.committed, self.application_id, self.fail_isolation = 'clean', application_id, 0

class FakeCursor:
    def __init__(self, connection):
        self.connection, self.row = connection, None
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, args=None):
        self.connection.execute(sql, args)
        self.row = self.connection.row
    def fetchone(self):
        return self.row

class FakeConn:
    def __init__(self, world, kwargs):
        self.world, self.kwargs, self.executed, self.pending, self.row = world, kwargs, [], None, None
        self.commits = self.rollbacks = self.fail_execute = self.pings = 0
        self.closed = self.fail_ping = self.fail_rollback = False
        self.time_zone = '+00:00' if kwargs.get('init_command') == TIME_ZONE_SQL else None
        self.isolation, self.isolation_session = None, False
    @property
    def open(self):
        return not self.closed
    def cursor(self):
        return FakeCursor(self)
    def ping(self, reconnect=False):
        self.pings += 1
        if self.closed or self.fail_ping:
            raise pymysql.err.InterfaceError(0, 'closed')
    def execute(self, sql, args=None):
        if self.fail_execute:
            self.fail_execute -= 1
            raise pymysql.err.OperationalError(2006, 'MySQL server has gone away')
        if self.world.fail_isolation and 'ISOLATION LEVEL' in sql.upper():
            self.world.fail_isolation -= 1
            raise pymysql.err.OperationalError(2006, 'MySQL server has gone away')
        self.executed.append((sql, args))
        if 'ISOLATION LEVEL' in sql.upper():
            self.isolation, self.isolation_session = 'REPEATABLE-READ', 'SESSION' in sql.upper()
        if 'workspace_meta' in sql:
            self.row = {'application_id': self.world.application_id}
        elif sql.startswith('SELECT marker'):
            self.row = {'marker': self.pending if self.pending is not None else self.world.committed}
        elif sql.startswith('UPDATE marker'):
            self.pending, self.row = args[0], None
        else:
            self.row = None
    def commit(self):
        self.commits += 1
        if self.pending is not None:
            self.world.committed, self.pending = self.pending, None
        if not self.isolation_session:
            self.isolation = None
    def rollback(self):
        if self.fail_rollback:
            raise pymysql.err.OperationalError(2006, 'gone')
        self.rollbacks, self.pending = self.rollbacks + 1, None
    def close(self):
        if self.closed:
            raise pymysql.err.Error('Already closed')
        self.closed = True

def install(monkeypatch, world=None):
    world, created = world or World(), []
    def connect(**kwargs):
        created.append(conn := FakeConn(world, kwargs))
        return conn
    monkeypatch.setattr('app.mysql_store.pymysql.connect', connect)
    monkeypatch.setattr('app.mysql_store.settings', lambda database=None: {'database': 'shixu_unit', 'autocommit': False})
    return world, created

def make_store(monkeypatch, world=None):
    world, created = install(monkeypatch, world)
    return MySQLStore(), world, created

def session_sql(connection):
    return [sql for sql, _args in connection.executed]

def read_marker(connection):
    with connection.cursor() as cur:
        cur.execute('SELECT marker')
        return cur.fetchone()['marker']

def test_init_still_checks_workspace_meta(monkeypatch):
    store, _world, created = make_store(monkeypatch)
    assert session_sql(created[0])[0] == ISOLATION_SQL
    assert any('workspace_meta' in sql for sql in session_sql(created[0]))
    assert created[0].kwargs['init_command'] == TIME_ZONE_SQL
    assert created[0].time_zone == '+00:00' and created[0].isolation == 'REPEATABLE-READ'
    install(monkeypatch, World('other-app'))
    with pytest.raises(RuntimeError, match='拒绝操作'):
        MySQLStore()
    assert store.database == 'shixu_unit'

def test_reconnects_for_the_current_request(monkeypatch):
    store, _world, created = make_store(monkeypatch)
    created[0].fail_execute = 1
    with store.connect() as conn:
        assert read_marker(conn) == 'clean'
    assert created[0].closed and created[1].open and conn is created[0]
    assert session_sql(created[1]).count(ISOLATION_SQL) == 1
    assert TIME_ZONE_SQL not in session_sql(created[1]) and created[1].pings == 0
    assert created[1].time_zone == '+00:00' and created[1].isolation == 'REPEATABLE-READ'
    created[1].fail_execute = 1
    with store.connect() as again:
        assert read_marker(again) == 'clean'
    assert created[1].closed and created[2].open and again is created[1]
    assert created[2].pings == 0 and session_sql(created[2]).count(ISOLATION_SQL) == 1

def test_rollback_hides_uncommitted_state_from_next_connect(monkeypatch):
    store, world, created = make_store(monkeypatch)
    with pytest.raises(RuntimeError, match='boom'):
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE marker', ('dirty',))
            raise RuntimeError('boom')
    assert conn is created[0] and conn.rollbacks == 1 and conn.commits == 1 and conn.pending is None
    assert world.committed == 'clean' and not conn.closed
    with store.connect() as again:
        assert again is conn and read_marker(again) == 'clean'
    with store.connect() as saved:
        with saved.cursor() as cur:
            cur.execute('UPDATE marker', ('saved',))
    assert world.committed == 'saved' and saved.commits == 3
    with store.connect() as reread:
        assert reread is saved and read_marker(reread) == 'saved'
    saved.fail_rollback = True
    with pytest.raises(RuntimeError, match='boom'):
        with store.connect() as broken:
            with broken.cursor() as cur:
                cur.execute('UPDATE marker', ('leaked',))
            raise RuntimeError('boom')
    assert broken.closed and world.committed == 'saved'
    with store.connect() as fresh:
        assert fresh is not broken and read_marker(fresh) == 'saved'

def test_threads_do_not_share_a_connection(monkeypatch):
    store, _world, created = make_store(monkeypatch)
    barrier, found, errors, lock = threading.Barrier(2), [], [], threading.Lock()
    def worker():
        try:
            with store.connect() as conn:
                with lock:
                    found.append(conn)
                barrier.wait(timeout=5)
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert not errors and len(found) == 2 and found[0] is not found[1]
    assert found[0] in created and found[1] in created and found[0].open and found[1].open
    with store.connect() as again:
        assert again is created[0]
        assert session_sql(again).count(TIME_ZONE_SQL) == 0
        assert session_sql(again).count(ISOLATION_SQL) == 1
        assert again.pings == 0 and again.time_zone == '+00:00'
        assert again.isolation == 'REPEATABLE-READ' and again.isolation_session

def test_session_is_set_once_and_stays_effective(monkeypatch):
    _store, _world, created = make_store(monkeypatch)
    conn = created[0]
    assert ISOLATION_SQL == 'SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'
    assert session_sql(conn)[0] == ISOLATION_SQL and session_sql(conn).count(ISOLATION_SQL) == 1
    assert TIME_ZONE_SQL not in session_sql(conn) and conn.kwargs['init_command'] == TIME_ZONE_SQL
    before = len(conn.executed)
    for _ in range(3):
        with _store.connect() as again:
            assert again is conn and read_marker(again) == 'clean'
    extra = [sql for sql, _args in conn.executed[before:]]
    assert extra and all(not sql.upper().lstrip().startswith('SET ') for sql in extra)
    assert conn.pings == 0 and len(created) == 1
    assert conn.time_zone == '+00:00' and conn.isolation == 'REPEATABLE-READ' and conn.isolation_session

def test_closed_connection_is_replaced_without_ping(monkeypatch):
    _store, _world, created = make_store(monkeypatch)
    created[0].closed = True
    with _store.connect() as conn:
        assert read_marker(conn) == 'clean'
    assert conn is created[1] and created[1].open and created[1].pings == 0
    assert session_sql(created[1]).count(ISOLATION_SQL) == 1

def test_session_setup_failure_retries_open_once(monkeypatch):
    world, created = install(monkeypatch)
    world.fail_isolation = 1
    MySQLStore()
    assert created[0].closed and created[1].open
    assert session_sql(created[1]).count(ISOLATION_SQL) == 1 and created[1].isolation_session
    world.fail_isolation = 2
    with pytest.raises(pymysql.err.OperationalError):
        MySQLStore()
    assert len(created) == 4

def test_disconnect_does_not_replay_a_written_transaction(monkeypatch):
    store, world, created = make_store(monkeypatch)
    with pytest.raises(pymysql.err.OperationalError):
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE marker', ('dirty',))
                created[0].fail_execute = 1
                cur.execute('SELECT marker')
    assert len(created) == 1 and world.committed == 'clean' and created[0].pending is None and created[0].closed
    def open_then_fail():
        connection = MySQLStore._open(store)
        connection.fail_execute = 1
        return connection
    store._open = open_then_fail
    with pytest.raises(pymysql.err.OperationalError):
        with store.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE marker', ('dirty',))
    assert len(created) == 2 and world.committed == 'clean' and created[1].closed
