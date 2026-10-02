"""MySQL实体存储：元数据行锁保护单人工作台的全局并发版本。"""
from contextlib import contextmanager
import hashlib
import json
import os
import re
import ssl
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
ISSUE_FIELDS = {'id': 'id', 'number': 'number', 'title': 'title', 'description': 'description', 'priority': 'priority',
                'tag': 'tag', 'status': 'status', 'resolution': 'resolution', 'nextStep': 'next_step',
                'successCriteria': 'success_criteria', 'treatment': 'treatment', 'verificationMethod': 'verification_method',
                'pauseReason': 'pause_reason', 'reviewDate': 'review_date', 'pausedFrom': 'paused_from',
                'closeReason': 'close_reason', 'closeType': 'close_type', 'duplicateOf': 'duplicate_of', 'deletedAt': 'deleted_at', 'deletionBatch': 'deletion_batch', 'deletedWithIssue': 'deleted_with_issue'}
TASK_FIELDS = {'id': 'id', 'title': 'title', 'issueId': 'issue_id', 'due': 'due', 'status': 'status', 'required': 'required_action',
               'cancelReason': 'cancel_reason', 'order': 'order_index', 'numberGroup': 'number_group', 'sequence': 'sequence_number', 'deletedAt': 'deleted_at', 'deletionBatch': 'deletion_batch', 'deletedWithIssue': 'deleted_with_issue'}


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
        # 只验证已有标记；运行服务不执行建库、建表或迁移DDL。
        with self.connect() as connection:
            with connection.cursor() as cur:
                cur.execute('SELECT application_id FROM workspace_meta WHERE id=1')
                row = cur.fetchone()
                if not row or row['application_id'] != APP_ID:
                    raise RuntimeError('数据库不是已初始化的拾序专属库，拒绝操作')

    @contextmanager
    def connect(self):
        connection = pymysql.connect(**self.options)
        try:
            with connection.cursor() as cur:
                cur.execute("SET time_zone = '+00:00'")
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _read(self, cur, lock=False):
        cur.execute('SELECT * FROM workspace_meta WHERE id=1' + (' FOR UPDATE' if lock else ''))
        meta = cur.fetchone()
        domain.require(meta and meta['application_id'] == APP_ID, '数据库身份校验失败', 503)
        state = domain.empty_state()
        state['nextIssueNumber'] = meta['next_issue_number']
        state['nextTaskNumbers'] = json.loads(meta['next_task_numbers'])
        cur.execute('SELECT * FROM issues ORDER BY number DESC')
        state['issues'] = [{key: row[column] for key, column in ISSUE_FIELDS.items()} for row in cur.fetchall()]
        index = {p['id']: p for p in state['issues']}
        for issue in state['issues']:
            issue.update(logs=[], history=[], followups=[])
        cur.execute('SELECT * FROM issue_logs ORDER BY issue_id,position_number')
        for row in cur.fetchall():
            index[row['issue_id']]['logs'].append(row['content'])
        cur.execute('SELECT * FROM issue_history ORDER BY issue_id,position_number')
        for row in cur.fetchall():
            index[row['issue_id']]['history'].append(dict(id=row['id'], **{'from': row['from_status']}, to=row['to_status'],
                                                         reason=row['reason'], at=row['event_at'], actor=row['actor']))
        cur.execute('SELECT * FROM issue_followups ORDER BY issue_id,event_at DESC,id')
        for row in cur.fetchall():
            index[row['issue_id']]['followups'].append({key: row[column] for key, column in dict(id='id',content='content',at='event_at',actor='actor').items()})
        cur.execute('SELECT * FROM tasks ORDER BY row_order DESC')
        state['tasks'] = [{key: row[column] for key, column in TASK_FIELDS.items()} for row in cur.fetchall()]
        tasks = {t['id']: t for t in state['tasks']}
        for task in state['tasks']:
            task['required'] = bool(task['required'])
            task['dependsOn'] = []
        cur.execute('SELECT * FROM task_dependencies WHERE deleted_at IS NULL ORDER BY task_id,position_number')
        for row in cur.fetchall():
            tasks[row['task_id']]['dependsOn'].append(row['dependency_id'])
        return dict(revision=meta['revision'], data=state)

    def read(self):
        with self.connect() as connection, connection.cursor() as cur:
            return self._read(cur)

    def activity(self, after=0, limit=100):
        with self.connect() as connection, connection.cursor() as cur:
            cur.execute('SELECT revision,event_at AS at,actor,operation,resource_id FROM activity WHERE revision>%s ORDER BY revision LIMIT %s', (after, limit))
            return list(cur.fetchall())

    @staticmethod
    def _upsert(cur, table, fields, item):
        columns = ','.join('`'+column+'`' for column in fields.values())
        placeholders = ','.join(['%s'] * len(fields))
        updates = ','.join('`'+column+'`=VALUES(`'+column+'`)' for key, column in fields.items() if key != 'id')
        cur.execute(f'INSERT INTO `{table}` ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}', tuple(item.get(key) for key in fields))

    def _persist(self, cur, state, previous):
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
        cur.execute('UPDATE workspace_meta SET next_issue_number=%s,next_task_numbers=%s WHERE id=1',
                    (state['nextIssueNumber'], dumps(state['nextTaskNumbers'])))

    def mutate(self, operation, identifier, body):
        import copy
        body = dict(body)
        request_id, expected, actor = body.pop('request_id'), body.pop('expected_version'), body.pop('actor')
        fingerprint = hashlib.sha256(dumps([operation, identifier, expected, actor, body]).encode()).hexdigest()
        with self.connect() as connection, connection.cursor() as cur:
            snapshot = self._read(cur, lock=True)
            cur.execute('SELECT fingerprint,response FROM idempotency_requests WHERE request_id=%s', (request_id,))
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
            cur.execute('UPDATE workspace_meta SET revision=%s WHERE id=1', (revision,))
            cur.execute('INSERT INTO activity VALUES (%s,%s,%s,%s,%s,%s)', (revision, domain.now(), actor, operation, resource['id'], dumps(body)))
            cur.execute('INSERT INTO idempotency_requests VALUES (%s,%s,%s)', (request_id, fingerprint, dumps(response)))
            return response
