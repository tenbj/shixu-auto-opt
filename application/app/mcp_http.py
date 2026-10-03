"""嵌入API进程的HTTP MCP；每次请求先认证，生命周期随服务启停。"""
import httpx
from starlette.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from mcp_server import create_server
from .mcp_access import authenticate


class AccessGate:
    def __init__(self, app, keys):
        self.app, self.keys = app, keys

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        if scope['path'] not in ('/mcp', '/mcp/'):
            return await JSONResponse({'detail': 'Not Found'}, status_code=404)(scope, receive, send)
        headers = dict(scope['headers'])
        value = headers.get(b'authorization', b'').decode('latin-1')
        scheme, _, token = value.partition(' ')
        identifier = authenticate(self.keys, token) if scheme.lower() == 'bearer' else None
        if not identifier:
            return await JSONResponse({'detail': '需要有效的MCP访问密钥'}, status_code=401,
                                      headers={'WWW-Authenticate': 'Bearer realm="shixu-mcp"'})(scope, receive, send)
        scope.setdefault('state', {})['mcp_access_id'] = identifier
        return await self.app(scope, receive, send)


def create_http(app, keys, allowed_hosts):
    # 复用同一ASGI HTTP路由；没有第二个数据库连接层，也不依赖固定API端口。
    server = create_server(api_transport=httpx.ASGITransport(app=app))
    hosts = [item for host in allowed_hosts for item in (host, host + ':*')]
    origins = [scheme + host for host in hosts for scheme in ('http://', 'https://')]
    http_app = server.streamable_http_app(stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins))
    return http_app, AccessGate(http_app, keys)
