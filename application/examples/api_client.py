"""默认只读；--write-demo 仅创建新的合成演示对象。"""
import argparse
import json
from uuid import uuid4
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--write-demo', action='store_true')
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=15, trust_env=False) as client:
        for path in ['/api/health', '/api/issues', '/openapi.json']:
            result = client.get(path).raise_for_status().json()
            print(path, 'OK', len(result))
        if args.write_demo:
            revision = client.get('/api/workspace').raise_for_status().json()['revision']
            body = dict(title='合成演示：验证 API 接入', description='由 --write-demo 显式创建，不修改已有记录',
                        expected_version=revision, request_id=str(uuid4()), actor='Python示例')
            result = client.post('/api/issues', json=body).raise_for_status().json()
            print(json.dumps({'id': result['resource']['id'], 'revision': result['revision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
