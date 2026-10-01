"""显式导入合成演示数据，只允许空工作台；通过 API 写入。"""
import argparse
import json
from pathlib import Path
from uuid import uuid4
import httpx
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.domain import today


def seed(url):
    with httpx.Client(base_url=url, timeout=15, trust_env=False) as client:
        state = client.get('/api/workspace').raise_for_status().json()
        if state['revision'] or state['data']['issues'] or state['data']['tasks']:
            raise SystemExit('只允许向空工作台导入演示数据；未修改现有记录。')
        revision = state['revision']
        def write(path, values):
            nonlocal revision
            result = client.post(path, json=dict(values, expected_version=revision, request_id=str(uuid4()), actor='合成演示')).raise_for_status().json()
            revision = result['revision']
            return result['resource']
        source = json.loads((ROOT / 'data/demo.json').read_text(encoding='utf-8'))
        for index, item in enumerate(source['issues']):
            issue = write('/api/issues', {key: item[key] for key in ['title', 'description', 'priority', 'tag']})
            if item['tasks']:
                write(f'/api/issues/{issue["id"]}/transitions', dict(action='triage', nextStep=item['nextStep'], successCriteria=item['successCriteria']))
                tasks = [write('/api/tasks', dict(title=title, issueId=issue['id'], due=today())) for title in item['tasks']]
                if index == 0:
                    write(f'/api/tasks/{tasks[1]["id"]}/dependencies', dict(dependsOn=[tasks[0]['id']]))
                    write(f'/api/tasks/{tasks[0]["id"]}/transitions', dict(status='进行中'))
        print('Synthetic demo imported through API')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    seed(parser.parse_args().url)
