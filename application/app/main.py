"""HTTP 系统入口：python -m uvicorn app.main:app --host 127.0.0.1 --port 8765"""
import os
import sqlite3
import pymysql
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from .domain import DomainError, get, live_issues, live_tasks, matches_creation
from .store import Store
from .config import load_environment
from .mysql_store import MySQLStore

ROOT = Path(__file__).resolve().parents[1]


from .models import (Write, IssueCreate, IssueUpdate, IssueTransition, Followup, TaskCreate, TaskUpdate, TaskTransition, Dependencies, Reorder, IdentityCreate, IdentityUpdate)


def create_app(db_path=None):
    app = FastAPI(title='拾序系统 API', version='2.3.0', description='共享记录工作台；写入使用全局版本与持久化幂等请求。')
    load_environment()
    if db_path is not None or os.getenv('SHIXU_BACKEND') == 'sqlite':
        app.state.store = Store(db_path or os.getenv('SHIXU_DB', str(ROOT / 'runtime' / 'test.sqlite3')))
    else:
        app.state.store = MySQLStore()
    allowed_hosts = ['localhost', '127.0.0.1', '[::1]', 'testserver', 'eliasliu.cc']
    extra_hosts = [host.strip() for host in os.getenv('SHIXU_ALLOWED_HOSTS', '').split(',') if host.strip()]
    if any('*' in host or '/' in host for host in extra_hosts):
        raise ValueError('SHIXU_ALLOWED_HOSTS须为明确的IP或主机名，不支持通配符或URL')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts + extra_hosts)

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ['GET', 'HEAD', 'OPTIONS']:
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': '拒绝跨站写入'}, status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': '拒绝跨站写入'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({'detail': error.message}, status_code=error.status)

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(pymysql.MySQLError)
    async def database_error(request, error):
        return JSONResponse({'detail': '数据库暂时不可用；未确认保存，请使用同一 request_id 重试'}, status_code=503)

    def write(operation, identifier, body):
        values = body.model_dump(exclude_unset=isinstance(body, (IssueUpdate, TaskUpdate, IdentityUpdate)))
        values.setdefault('actor', body.actor)
        return app.state.store.mutate(operation, identifier, values)

    @app.get('/api/health', summary='检查服务与数据库状态')
    def health():
        state = app.state.store.read()
        return {'status': 'ok', 'version': '2.3.0', 'revision': state['revision'], 'mode': 'local-single-user',
                'backend': getattr(app.state.store, 'backend', 'sqlite-test'),
                'database': getattr(app.state.store, 'database', None),
                'pid': os.getpid(), 'instance': os.getenv('SHIXU_INSTANCE', '')}

    @app.get('/api/workspace', summary='读取完整工作台与并发版本')
    def workspace():
        return app.state.store.read()

    @app.get('/api/identities', summary='查询通用人类与AI记录身份')
    def identities():
        result = app.state.store.read()
        return {'revision': result['revision'], 'items': result['data']['identityProfiles']}

    @app.post('/api/identities', summary='创建记录身份与默认工具模型')
    def identity_create(body: IdentityCreate):
        return write('create_identity', None, body)

    @app.patch('/api/identities/{identity_id}', summary='修改身份名称与新建默认值，保留历史快照')
    def identity_update(identity_id: str, body: IdentityUpdate):
        return write('update_identity', identity_id, body)

    @app.get('/api/issues', summary='查询问题列表')
    def issues(q: str = '', status: str = '', priority: str = '', tag: str = '', creator: str = '', created_via: str = '', model: str = ''):
        snapshot = app.state.store.read()
        rows = [p for p in live_issues(snapshot['data']) if (not q or q.casefold() in (p['title'] + p['description']).casefold())
                and (not status or p['status'] == status) and (not priority or p['priority'] == priority) and (not tag or p['tag'] == tag) and matches_creation(p, creator, created_via, model)]
        return {'revision': snapshot['revision'], 'items': rows}

    @app.get('/api/issues/{issue_id}', summary='读取问题详情及关联行动')
    def issue(issue_id: str):
        snapshot = app.state.store.read()
        return {'revision': snapshot['revision'], 'item': get(snapshot['data'], 'issues', issue_id),
                'tasks': [t for t in live_tasks(snapshot['data']) if t['issueId'] == issue_id]}

    @app.post('/api/issues', summary='创建待梳理问题')
    def issue_create(body: IssueCreate):
        return write('create_issue', None, body)

    @app.patch('/api/issues/{issue_id}', summary='编辑问题内容与属性')
    def issue_update(issue_id: str, body: IssueUpdate):
        return write('update_issue', issue_id, body)

    @app.post('/api/issues/{issue_id}/transitions', summary='按七状态规则流转问题')
    def issue_transition(issue_id: str, body: IssueTransition):
        return write('transition_issue', issue_id, body)

    @app.post('/api/issues/{issue_id}/followups', summary='追加问题跟进记录')
    def issue_followup(issue_id: str, body: Followup):
        return write('followup', issue_id, body)

    @app.get('/api/tasks', summary='查询行动列表')
    def tasks(issue_id: str | None = None, status: str = '', creator: str = '', created_via: str = '', model: str = ''):
        snapshot = app.state.store.read()
        rows = [t for t in live_tasks(snapshot['data']) if (issue_id is None or t['issueId'] == (issue_id or None)) and (not status or t['status'] == status) and matches_creation(t, creator, created_via, model)]
        return {'revision': snapshot['revision'], 'items': sorted(rows, key=lambda t: t['order'])}

    @app.get('/api/tasks/{task_id}', summary='读取行动详情')
    def task(task_id: str):
        snapshot = app.state.store.read()
        return {'revision': snapshot['revision'], 'item': get(snapshot['data'], 'tasks', task_id)}

    @app.post('/api/tasks', summary='创建关联或独立行动')
    def task_create(body: TaskCreate):
        return write('create_task', None, body)

    @app.patch('/api/tasks/{task_id}', summary='编辑行动内容与关联')
    def task_update(task_id: str, body: TaskUpdate):
        return write('update_task', task_id, body)

    @app.post('/api/tasks/{task_id}/transitions', summary='推进取消或重新打开行动')
    def task_transition(task_id: str, body: TaskTransition):
        return write('transition_task', task_id, body)

    @app.post('/api/tasks/{task_id}/dependencies', summary='设置行动依赖并检查循环')
    def task_dependencies(task_id: str, body: Dependencies):
        return write('dependencies', task_id, body)

    @app.post('/api/tasks/{task_id}/reorder', summary='调整同组行动显示顺序')
    def task_reorder(task_id: str, body: Reorder):
        return write('reorder', task_id, body)

    @app.get('/api/trash', summary='读取回收站问题与行动')
    def trash():
        snapshot = app.state.store.read()
        return {'revision': snapshot['revision'], 'issues': [p for p in snapshot['data']['issues'] if p.get('deletedAt')],
                'tasks': [t for t in snapshot['data']['tasks'] if t.get('deletedAt')]}

    @app.post('/api/issues/{issue_id}/trash', summary='软删除问题及关联行动')
    def issue_delete(issue_id: str, body: Write):
        return write('delete_issue', issue_id, body)

    @app.post('/api/issues/{issue_id}/restore', summary='恢复问题及同批行动')
    def issue_restore(issue_id: str, body: Write):
        return write('restore_issue', issue_id, body)

    @app.post('/api/tasks/{task_id}/trash', summary='软删除行动并检查依赖')
    def task_delete(task_id: str, body: Write):
        return write('delete_task', task_id, body)

    @app.post('/api/tasks/{task_id}/restore', summary='恢复独立删除的行动')
    def task_restore(task_id: str, body: Write):
        return write('restore_task', task_id, body)

    @app.get('/api/activity', summary='读取操作审计事件')
    def activity(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        return {'items': app.state.store.activity(after, limit)}

    @app.get('/api/export', summary='导出全部问题行动与版本')
    def export():
        return app.state.store.read()

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(ROOT / 'static' / 'index.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
    app.mount('/examples', StaticFiles(directory=ROOT / 'examples', html=True), name='examples')
    return app


app = create_app()
