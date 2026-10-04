"""隔离集成测试的账号会话；不连接日常账号。"""
import os, httpx
from uuid import uuid4
class Session:
    def __init__(self,url):
        self.url=url
        self.client=httpx.Client(base_url=url,trust_env=False,timeout=30)
        user=os.getenv('SHIXU_TEST_USER') or 'check_'+uuid4().hex[:12]
        password=os.getenv('SHIXU_TEST_PASSWORD') or uuid4().hex
        r=self.client.post('/api/auth/register',json=dict(username=user,password=password,displayName='合成验证'))
        if r.status_code==409:r=self.client.post('/api/auth/login',json=dict(username=user,password=password))
        result=r.raise_for_status().json();self.user=result['user']
        self.client.headers['X-CSRF-Token']=result['csrf']
    def get(self,*a,**kw):
        kw.pop('trust_env',None);return self.client.get(*a,**kw)
    def post(self,*a,**kw):
        kw.pop('trust_env',None);return self.client.post(*a,**kw)
    def close(self):self.client.close()
    def cookies(self,context):
        context.add_cookies([dict(name=k,value=v,url=self.url) for k,v in self.client.cookies.items()])
