"""Authenticate TLS termination independently of a public TCP tunnel."""
import hmac
from urllib.parse import urlparse


class HTTPSProxyProof:
    def __init__(self, app, secret='', public_url=''):
        self.app = app
        self.secret = secret.encode()
        parsed = urlparse(public_url)
        self.host = parsed.hostname if parsed.scheme == 'https' else None
        if secret and (len(secret) < 32 or not self.host or parsed.port not in (None, 443)):
            raise ValueError('HTTPS代理标记至少32字符，公网地址须为标准443 HTTPS域名')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = scope.get('headers', [])
        proofs = [v for k, v in headers if k.lower() == b'x-shixu-https-proof']
        hosts = [v.decode('latin-1').lower() for k, v in headers if k.lower() == b'host']
        protocols = [v for k, v in headers if k.lower() == b'x-forwarded-proto']
        trusted = (self.secret and len(proofs) == 1 and
                   hmac.compare_digest(proofs[0], self.secret) and
                   len(hosts) == 1 and hosts[0] in (self.host, self.host + ':443') and
                   protocols == [b'https'])
        scope = dict(scope)
        scope['headers'] = [(k, v) for k, v in headers if k.lower() != b'x-shixu-https-proof']
        if trusted:
            scope['scheme'] = 'https'
            scope['server'] = (self.host, 443)
        await self.app(scope, receive, send)
