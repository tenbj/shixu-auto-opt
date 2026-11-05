"""MySQL实体存储：元数据行锁保护账号工作台的独立并发版本。"""
from contextlib import contextmanager
import hashlib
import json
import os
import re
import ssl
import threading
import pymysql
from . import domain
from .store import dumps
from .config import load_environment

class RetainingCursor(pymysql.cursors.DictCursor):
    """运行时拒绝物理删除、清空或替换记录的SQL。"""
    def execute(self, query, args=None):
        statement = query.decode() if isinstance(query, bytes) else query
        statement = re.sub(r'/\*.*?\*/|--[^\n]*', '', statement, flags=re.S).lstrip()
        if re.match(r'(DELETE|TRUNCATE|DROP|REPLACE)\b', statement, re.I):
            raise RuntimeError('禁止物理删除数据库记录；请使用软删除标识')
        return super().execute(query, args)

APP_ID = 'shixu-system-entities-v2'
# 与原先每次建连后执行的语句保持一致。隔离级不加 SESSION，只作用于下一个事务。
TIME_ZONE_SQL = "SET time_zone = '+00:00'"
ISOLATION_SQL = 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'
ISSUE_FIELDS = {'id': 'id', 'number': 'number', 'title': 'title', 'description': 'description', 'priority': 'priority',
                'tag': 'tag', 'status': 'status', 'resolution': 'resolution', 'nextStep': 'next_step',
                'successCriteria': 'success_criteria', 'treatment': 'treatment', 'verificationMethod': 'verification_method',
                'pauseReason': 'pause_reason', 'reviewDate': 'review_date', 'pausedFrom': 'paused_from',
                'closeReason': 'close_reason', 'closeType': 'close_type', 'duplicateOf': 'duplicate_of', 'deletedAt': 'deleted_at', 'deletionBatch': 'deletion_batch', 'deletedWithIssue': 'deleted_with_issue'}
TASK_FIELDS = {'id': 'id', 'title': 'title', 'issueId': 'issue_id', 'due': 'due', 'status': 'status', 'required': 'required_action',
               'cancelReason': 'cancel_reason', 'order': 'order_index', 'numberGroup': 'number_group', 'sequence': 'sequence_number', 'deletedAt': 'deleted_at', 'deletionBatch': 'deletion_batch', 'deletedWithIssue': 'deleted_with_issue'}


CREATION_FIELDS = {'createdByActorId':'created_by_actor_id','initiatedByPersonId':'initiated_by_person_id',
                   'creatorName':'creator_name','createdVia':'created_via','createdAt':'created_at','modelInfo':'model_info'}
ISSUE_FIELDS.update(CREATION_FIELDS)
TASK_FIELDS.update(CREATION_FIELDS)
IDENTITY_FIELDS = dict(id='id',name='name',kind='kind',via='via',modelName='model_name',
                       modelProvider='model_provider',createdAt='created_at',updatedAt='updated_at')


def settings(database=None):
    load_environment()
    name = database or os.getenv('DB_NAME', '')
    if not re.fullmatch(r'shixu_[a-z0-9_]{1,54}', name):
        raise RuntimeError('DB_NAME必须是专门新建的shixu_前缀数据库；拒绝连接其他库')
    required = ['DB_HOST', 'DB_USER', 'DB_PASSWORD']
    if any(not os.getenv(key) for key in required):
        raise RuntimeError('请配置MySQL本机私有环境文件SHIXU_ENV_FILE')
    options = dict(host=os.environ['DB_HOST'], port=int(os.getenv('DB_PORT', '3306')), user=os.environ['DB_USER'],
                   password=os.environ['DB_PASSWORD'], database=name, charset=os.getenv('DB_CHARSET', 'utf8mb4'),
                   connect_timeout=10, read_timeout=20, write_timeout=20, autocommit=False,
                   cursorclass=RetainingCursor, local_infile=False)
    if os.getenv('DB_SSL', 'true').lower() in ['true', '1', 'yes']:
        options['ssl'] = ssl.create_default_context(cafile=os.getenv('DB_SSL_CA') or None)
    else:
        options['ssl_disabled'] = True
    return options


class MySQLStore:
    backend = 'mysql'

    def __init__(self, database=None):
        self.options = settings(database)
        self.database = self.options['database']
        # 每个线程单独持有连接；for_owner 的浅拷贝共用这一槽位，仍按线程隔离。
        self._local = threading.local()
        # 只验证已有标记；运行服务不执行建库、建表或迁移DDL。
        with self.connect() as connection:
            with connection.cursor() as cur:
                cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
                row = cur.fetchone()
                if not row or row['application_id'] != APP_ID:
                    raise RuntimeError('数据库不是已初始化的拾序专属库，拒绝操作')

    def _open(self):
        options = dict(self.options)
        # 物理建连时先设定时区。隔离级必须在每个事务开始前再执行一次。
        options.setdefault('init_command', TIME_ZONE_SQL)
        return pymysql.connect(**options)

    def _close_quietly(self, connection):
        try:
            connection.close()
        except Exception:
            pass

    def _alive(self, connection):
        if not getattr(connection, 'open', False):
            return False
        try:
            connection.ping(reconnect=False)
        except Exception:
            return False
        return True

    def _drop(self, connection, pooled):
        if pooled:
            local = self._local
            if getattr(local, 'conn', None) is connection:
                local.conn = None
            local.busy = False
        self._close_quietly(connection)

    def _take(self):
        """取出本线程的空闲连接。没有、已失效，或外层事务仍占用时，另建一条。"""
        local = self._local
        busy = getattr(local, 'busy', False)
        current = getattr(local, 'conn', None)
        if not busy and current is not None and self._alive(current):
            local.busy = True
            return current, True
        if not busy and current is not None:
            local.conn = None
            self._close_quietly(current)
        connection = self._open()
        if busy:
            return connection, False
        local.conn = connection
        local.busy = True
        return connection, True

    def _apply_session(self, connection):
        with connection.cursor() as cur:
            cur.execute(TIME_ZONE_SQL)
            cur.execute(ISOLATION_SQL)

    def _acquire(self):
        connection, pooled = self._take()
        try:
            self._apply_session(connection)
            return connection, pooled
        except Exception:
            self._drop(connection, pooled)
        connection, pooled = self._take()
        try:
            self._apply_session(connection)
            return connection, pooled
        except Exception:
            self._drop(connection, pooled)
            raise

    def _release(self, connection, pooled, discard):
        if not pooled:
            self._close_quietly(connection)
            return
        local = self._local
        if discard or getattr(local, 'conn', None) is not connection:
            if getattr(local, 'conn', None) is connection:
                local.conn = None
            local.busy = False
            self._close_quietly(connection)
            return
        local.busy = False

    @contextmanager
    def connect(self):
        """复用当前线程的连接。正常结束提交，异常回滚，未提交状态不留给下一次。"""
        connection, pooled = self._acquire()
        discard = False
        try:
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                discard = True
            raise
        finally:
            self._release(connection, pooled, discard)

    def for_owner(self, identifier):
        import copy
        scoped = copy.copy(self)
        scoped.owner_id = identifier
        return scoped

    def _scope(self):
        return getattr(self, 'owner_id', 'test')

    def _read(self, cur, lock=False):
        cur.execute('SELECT * FROM workspace_meta WHERE owner_id=%s' + (' FOR UPDATE' if lock else ''), (self._scope(),))
        meta = cur.fetchone()
        domain.require(meta and meta['application_id'] == APP_ID, '数据库身份校验失败', 503)
        state = domain.empty_state()
        state['nextIssueNumber'] = meta['next_issue_number']
        state['nextTaskNumbers'] = json.loads(meta['next_task_numbers'])
        cur.execute('SELECT * FROM issues WHERE owner_id=%s ORDER BY number DESC', (self._scope(),))
        state['issues'] = [{key: row[column] for key, column in ISSUE_FIELDS.items()} for row in cur.fetchall()]
        for item in state['issues']:
            item['modelInfo'] = json.loads(item['modelInfo']) if item['modelInfo'] is not None else None
        index = {p['id']: p for p in state['issues']}
        for issue in state['issues']:
            issue.update(logs=[], history=[], followups=[])
        cur.execute('SELECT * FROM issue_logs WHERE issue_id IN (SELECT id FROM issues WHERE owner_id=%s) ORDER BY issue_id,position_number', (self._scope(),))
        for row in cur.fetchall():
            index[row['issue_id']]['logs'].append(row['content'])
        cur.execute('SELECT * FROM issue_history WHERE issue_id IN (SELECT id FROM issues WHERE owner_id=%s) ORDER BY issue_id,position_number', (self._scope(),))
        for row in cur.fetchall():
            index[row['issue_id']]['history'].append(dict(id=row['id'], **{'from': row['from_status']}, to=row['to_status'],
                                                         reason=row['reason'], at=row['event_at'], actor=row['actor']))
        cur.execute('SELECT * FROM issue_followups WHERE issue_id IN (SELECT id FROM issues WHERE owner_id=%s) ORDER BY issue_id,event_at DESC,id', (self._scope(),))
        for row in cur.fetchall():
            index[row['issue_id']]['followups'].append({key: row[column] for key, column in dict(id='id',content='content',at='event_at',actor='actor').items()})
        cur.execute('SELECT * FROM tasks WHERE owner_id=%s ORDER BY row_order DESC', (self._scope(),))
        state['tasks'] = [{key: row[column] for key, column in TASK_FIELDS.items()} for row in cur.fetchall()]
        tasks = {t['id']: t for t in state['tasks']}
        for task in state['tasks']:
            task['modelInfo'] = json.loads(task['modelInfo']) if task['modelInfo'] is not None else None
            task['required'] = bool(task['required'])
            task['dependsOn'] = []
        cur.execute('SELECT * FROM task_dependencies WHERE deleted_at IS NULL AND task_id IN (SELECT id FROM tasks WHERE owner_id=%s) ORDER BY task_id,position_number', (self._scope(),))
        for row in cur.fetchall():
            tasks[row['task_id']]['dependsOn'].append(row['dependency_id'])
        cur.execute('SELECT * FROM identity_profiles WHERE owner_id=%s ORDER BY created_at,id', (self._scope(),))
        state['identityProfiles'] = [{key: row[column] for key,column in IDENTITY_FIELDS.items()} for row in cur.fetchall()]
        cur.execute('SELECT id,name FROM ai_tools WHERE owner_id=%s ORDER BY id', (self._scope(),))
        state['customTools'] = {row['id']:row['name'] for row in cur.fetchall()}
        return dict(revision=meta['revision'], data=state)

    def read(self):
        with self.connect() as connection, connection.cursor() as cur:
            return self._read(cur)

    def activity(self, after=0, limit=100):
        with self.connect() as connection, connection.cursor() as cur:
            cur.execute('SELECT revision,event_at AS at,actor,operation,resource_id FROM activity WHERE owner_id=%s AND revision>%s ORDER BY revision LIMIT %s', (self._scope(), after, limit))
            return list(cur.fetchall())

    def _upsert(self, cur, table, fields, item):
        cur.execute(f'SELECT owner_id FROM `{table}` WHERE id=%s', (item['id'],))
        existing = cur.fetchone()
        domain.require(not existing or existing['owner_id'] == self._scope(), '资源不存在', 404)
        fields = dict(fields, owner_id='owner_id')
        item = dict(item, owner_id=self._scope())
        columns = ','.join('`'+column+'`' for column in fields.values())
        placeholders = ','.join(['%s'] * len(fields))
        updates = ','.join('`'+column+'`=VALUES(`'+column+'`)' for key, column in fields.items() if key != 'id')
        cur.execute(f'INSERT INTO `{table}` ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}', tuple(dumps(item[key]) if key=='modelInfo' and item.get(key) is not None else item.get(key) for key in fields))

    def _persist(self, cur, state, previous):
        for identifier,name in state.get('customTools',{}).items():
            if identifier not in previous.get('customTools',{}):
                self._upsert(cur,'ai_tools',dict(id='id',name='name',nameKey='name_key'),dict(id=identifier,name=name,nameKey=hashlib.sha256(name.casefold().encode()).hexdigest()))
        old_profiles = {p['id']:p for p in previous.get('identityProfiles',[])}
        for profile in state.get('identityProfiles',[]):
            if profile != old_profiles.get(profile['id']):
                self._upsert(cur,'identity_profiles',IDENTITY_FIELDS,profile)
        old_issues = {p['id']: p for p in previous['issues']}
        old_tasks = {t['id']: t for t in previous['tasks']}
        domain.require(set(old_issues) <= {p['id'] for p in state['issues']} and set(old_tasks) <= {t['id'] for t in state['tasks']}, '业务记录只能软删除，不得移除实体', 409)
        for issue in reversed(state['issues']):
            old = old_issues.get(issue['id'], {})
            if any(old.get(key) != issue.get(key) for key in ISSUE_FIELDS):
                self._upsert(cur, 'issues', ISSUE_FIELDS, issue)
            for position, content in enumerate(issue['logs']):
                if position >= len(old.get('logs', [])):
                    cur.execute('INSERT INTO issue_logs VALUES (%s,%s,%s)', (issue['id'], position, content))
            for position, entry in enumerate(issue['history']):
                if position >= len(old.get('history', [])):
                    cur.execute('INSERT INTO issue_history VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                                (entry['id'], issue['id'], position, entry['from'], entry['to'], entry['reason'], entry['at'], entry['actor']))
            old_followups = {entry['id'] for entry in old.get('followups', [])}
            for entry in issue['followups']:
                if entry['id'] not in old_followups:
                    cur.execute('INSERT INTO issue_followups VALUES (%s,%s,%s,%s,%s)',
                                (entry['id'], issue['id'], entry['content'], entry['at'], entry['actor']))
        for task in reversed(state['tasks']):
            old = old_tasks.get(task['id'], {})
            if any(old.get(key) != task.get(key) for key in TASK_FIELDS):
                self._upsert(cur, 'tasks', TASK_FIELDS, task)
        for task in state['tasks']:
            if task['dependsOn'] != old_tasks.get(task['id'], {}).get('dependsOn', []):
                cur.execute('UPDATE task_dependencies SET deleted_at=%s WHERE task_id=%s AND deleted_at IS NULL', (domain.now(), task['id']))
                if task['dependsOn']:
                    cur.executemany('INSERT INTO task_dependencies (task_id,dependency_id,position_number,deleted_at) VALUES (%s,%s,%s,NULL) ON DUPLICATE KEY UPDATE position_number=VALUES(position_number),deleted_at=NULL',
                                    [(task['id'], key, index) for index, key in enumerate(task['dependsOn'])])
        cur.execute('UPDATE workspace_meta SET next_issue_number=%s,next_task_numbers=%s WHERE owner_id=%s',
                    (state['nextIssueNumber'], dumps(state['nextTaskNumbers']), self._scope()))

    def mutate(self, operation, identifier, body):
        import copy
        body = dict(body)
        request_id, expected, actor = body.pop('request_id'), body.pop('expected_version'), body.pop('actor')
        fingerprint = hashlib.sha256(dumps([operation, identifier, expected, actor, body]).encode()).hexdigest()
        with self.connect() as connection, connection.cursor() as cur:
            snapshot = self._read(cur, lock=True)
            cur.execute('SELECT fingerprint,response FROM idempotency_requests WHERE owner_id=%s AND request_id=%s', (self._scope(), request_id))
            previous = cur.fetchone()
            if previous:
                domain.require(previous['fingerprint'] == fingerprint, 'request_id 已用于不同请求，请使用新编号', 409)
                return json.loads(previous['response'])
            domain.require(snapshot['revision'] == expected, '工作台已更新，请重新读取版本后再提交', 409)
            state = snapshot['data']
            original = copy.deepcopy(state)
            resource = domain.apply(state, operation, identifier, body, actor)
            revision = snapshot['revision'] + 1
            self._persist(cur, state, original)
            response = dict(revision=revision, resource=resource, data=state)
            cur.execute('UPDATE workspace_meta SET revision=%s WHERE owner_id=%s', (revision, self._scope()))
            cur.execute('INSERT INTO activity (revision,event_at,actor,operation,resource_id,payload,owner_id) VALUES (%s,%s,%s,%s,%s,%s,%s)', (revision, domain.now(), actor, operation, resource['id'], dumps(body), self._scope()))
            cur.execute('INSERT INTO idempotency_requests (request_id,fingerprint,response,owner_id) VALUES (%s,%s,%s,%s)', (request_id, fingerprint, dumps(response), self._scope()))
            return response
