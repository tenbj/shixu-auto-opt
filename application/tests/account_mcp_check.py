"""真实HTTP MCP并行账号隔离，仅专用测试服务。"""
import argparse,asyncio,json
from pathlib import Path
from uuid import uuid4
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from http_auth import Session

async def run(url):
    tokens=[]
    for i in range(2):
        api=Session(url)
        health=api.get('/api/health').json()
        assert health['backend']=='sqlite-test' or health['database'].endswith('_test')
        # 每个会话使用不同账号，不复用套件共享账号。
        name='isolation_'+uuid4().hex[:10]
        api.client.cookies.clear();api.client.headers.pop('X-CSRF-Token',None)
        auth=api.post('/api/auth/register',json=dict(username=name,password=uuid4().hex)).raise_for_status().json()
        api.client.headers['X-CSRF-Token']=auth['csrf']
        tokens.append(api.post('/api/account/mcp-access',json=dict(name='并行SDK',scope='write')).raise_for_status().json()['token'])
    async def one(token,label):
        async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token},trust_env=False,timeout=30) as http:
            async with Client(streamable_http_client(url+'/mcp',http_client=http)) as client:
                async def call(name,args=None):
                    r=await client.call_tool(name,args or {});assert not r.is_error
                    return r.structured_content or json.loads(r.content[0].text)
                s=await call('get_workspace');assert s['data']['issues']==[]
                made=await call('create_issue',{'body':dict(title=label,expected_version=s['revision'],request_id=str(uuid4()))})
                state=await call('get_workspace');assert [x['title'] for x in state['data']['issues']]==[label]
                return made['resource']['id']
    ids=await asyncio.gather(one(tokens[0],'A workspace synthetic'),one(tokens[1],'B workspace synthetic'))
    assert ids[0]!=ids[1]
    root=Path(__file__).resolve().parents[1]
    report=dict(passed=True,delivery_id=json.loads((root/'project-contract.json').read_text(encoding='utf-8'))['delivery_id'],checks=['两个真实HTTP MCP并行会话各自创建与回读，账号上下文不串用'],backend=health['backend'])
    (root/'verification/account-mcp-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);asyncio.run(run(p.parse_args().url))
