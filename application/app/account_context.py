"""每次请求的认证上下文；不能从业务提交字段设置归属。"""
from contextvars import ContextVar
from .domain import DomainError

mcp_call = ContextVar('shixu_mcp_call', default=False)
principal = ContextVar('shixu_principal', default=None)
bearer = ContextVar('shixu_bearer', default='')

def owner():
    user = principal.get()
    if not user:
        raise DomainError('请先登录', 401)
    return user['id']

class AccountStore:
    def __init__(self, store):
        self.base = store
        self.path = getattr(store, 'path', None)
        self.backend = getattr(store, 'backend', 'sqlite-test')
        self.database = getattr(store, 'database', None)

    def read(self):
        return self.base.for_owner(owner()).read()

    def mutate(self, operation, identifier, body):
        user = principal.get()
        if user and user.get('scope') == 'read':
            raise DomainError('此接入只允许查询', 403)
        return self.base.for_owner(owner()).mutate(operation, identifier, body)

    def activity(self, after=0, limit=100):
        return self.base.for_owner(owner()).activity(after, limit)
