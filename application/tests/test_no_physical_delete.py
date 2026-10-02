"""验证软删除保留关系与数据库删除阻拦；不复制业务实现。"""
import sqlite3
from pathlib import Path
import pytest
from app.mysql_store import RetainingCursor, MySQLStore
from app.store import Store
from app.domain import DomainError

@pytest.mark.parametrize('query',['DELETE FROM issues','/* comment */ delete from task_dependencies','TRUNCATE TABLE tasks','DROP TABLE activity','REPLACE INTO issues VALUES (1)'])
def test_runtime_cursor_rejects_destructive_sql(query):
    with pytest.raises(RuntimeError,match='禁止物理删除'):
        RetainingCursor(None).execute(query)

def test_sqlite_database_blocks_direct_delete(tmp_path):
    store=Store(tmp_path/'workspace.sqlite3')
    before=store.read()
    with store.connect() as c:
        with pytest.raises(sqlite3.IntegrityError,match='Physical deletion'):
            c.execute('DELETE FROM workspace')
    assert store.read()==before

def test_persist_rejects_lost_entities():
    class Cursor:
        def execute(self,*args): raise AssertionError('must reject before SQL')
    with pytest.raises(DomainError,match='只能软删除'):
        MySQLStore.__new__(MySQLStore)._persist(Cursor(),dict(issues=[],tasks=[],nextIssueNumber=2,nextTaskNumbers={}),dict(issues=[dict(id='old')],tasks=[]))
