"""Default read-only. --add-tool NAME explicitly adds/reuses one tool, then reads it back."""
import argparse,json,os
from uuid import uuid4
import httpx

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8765')
    p.add_argument('--add-tool');p.add_argument('--skill-version',default='')
    a=p.parse_args()
    with httpx.Client(base_url=a.url,trust_env=False,headers={'Authorization':'Bearer '+os.environ['SHIXU_MCP_TOKEN']}) as c:
        listing=c.get('/api/ai-tools').raise_for_status().json()
        if a.add_tool:
            # Keep the exact body/request_id for any retry after an uncertain result.
            body=dict(name=a.add_tool,request_id=str(uuid4()),expected_version=listing['revision'])
            result=c.post('/api/ai-tools',json=body).raise_for_status().json()
            listing=c.get('/api/ai-tools').raise_for_status().json()
            assert any(x['id']==result['resource']['id'] for x in listing['items'])
        updates=c.get('/api/connection-updates',params=dict(skill_version=a.skill_version,mcp_url=a.url.rstrip('/')+'/mcp')).raise_for_status().json()
        print(json.dumps(dict(tools=listing,updates=updates),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
