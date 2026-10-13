"""Loopback-only TLS termination for the real isolated Docker acceptance."""
import os
from urllib.parse import urlparse
import httpx

UPSTREAM=os.environ['SHIXU_TEST_UPSTREAM'].rstrip('/')
assert urlparse(UPSTREAM).scheme=='http' and urlparse(UPSTREAM).hostname=='127.0.0.1'
PROOF=os.environ['SHIXU_TEST_PROXY_PROOF'].encode()
HOP={b'connection',b'transfer-encoding',b'keep-alive',b'proxy-authenticate',b'proxy-authorization',b'te',b'trailer',b'upgrade'}

async def app(scope,receive,send):
    if scope['type']!='http':return
    body=b''
    while True:
        message=await receive()
        if message['type']=='http.disconnect':return
        body+=message.get('body',b'')
        if not message.get('more_body'):break
    headers=[(k,v) for k,v in scope['headers'] if k not in HOP|{b'x-shixu-https-proof',b'x-forwarded-proto'}]
    headers.extend([(b'x-shixu-https-proof',PROOF),(b'x-forwarded-proto',b'https')])
    url=UPSTREAM+scope['raw_path'].decode('ascii')
    if scope.get('query_string'):url+='?'+scope['query_string'].decode('ascii')
    async with httpx.AsyncClient(trust_env=False,timeout=45) as client:
        async with client.stream(scope['method'],url,headers=headers,content=body) as response:
            await send({'type':'http.response.start','status':response.status_code,'headers':[(k,v) for k,v in response.headers.raw if k.lower() not in HOP]})
            async for chunk in response.aiter_raw():await send({'type':'http.response.body','body':chunk,'more_body':True})
            await send({'type':'http.response.body','body':b'','more_body':False})
