"""默认只读列出身份；--write-demo 创建合成Elias/Codex身份及问题，回读模型快照。"""
import argparse,json
from uuid import uuid4
import httpx


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--write-demo',action='store_true');args=p.parse_args()
    with httpx.Client(base_url=args.url,trust_env=False,timeout=30) as client:
        identities=client.get('/api/identities').raise_for_status().json()
        if not args.write_demo:print(json.dumps(identities,ensure_ascii=False));return
        revision=identities['revision']
        def write(path,values):
            nonlocal revision
            body=dict(values,request_id=str(uuid4()),expected_version=revision,actor='Python合成示例')
            # 网络结果不确定时，请保留此完整body并以同一request_id重试；409先重读。
            result=client.post(path,json=body).raise_for_status().json()
            revision=result['revision'];return result['resource']
        person=write('/api/identities',dict(name='Elias（示例）',kind='person',via='manual'))
        agent=write('/api/identities',dict(name='Codex（示例）',kind='agent',via='codex',modelName='GPT-6.1 Sol',modelProvider='OpenAI'))
        issue=write('/api/issues',dict(title='Elias 委托 Codex 记录（合成示例）',creation=dict(identityId=agent['id'],initiatedByPersonId=person['id'],modelInfo=dict(name='GPT-6.1 Sol',provider='OpenAI'))))
        saved=client.get('/api/issues/'+issue['id']).raise_for_status().json()['item']
        assert saved['modelInfo']==dict(name='GPT-6.1 Sol',provider='OpenAI')
        print(json.dumps(saved,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
