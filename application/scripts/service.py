"""跨平台本地服务管理，只停止由此脚本创建且健康端点身份匹配的进程。"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import load_environment


def health(url):
    return httpx.get(url + '/api/health', timeout=2, trust_env=False).raise_for_status().json()


def main():
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default=os.getenv('SHIXU_HOST', '127.0.0.1'),
                        help='监听地址；0.0.0.0开放全部IPv4网卡，须配置SHIXU_ALLOWED_HOSTS')
    parser.add_argument('--db', type=Path, default=ROOT / 'runtime' / 'shixu.sqlite3')
    args = parser.parse_args()
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    state_file = runtime / f'service-{args.port}.json'
    url = f'http://127.0.0.1:{args.port}'
    try:
        current = health(url)
    except (httpx.HTTPError, ValueError):
        current = None
    if args.action == 'status':
        print(json.dumps(current or {'status': 'offline'}, ensure_ascii=False))
        return 0 if current else 1
    if args.action == 'stop':
        if not current:
            print('Service is offline')
            return 0
        if not state_file.exists():
            raise SystemExit('No owned service record; refusing to stop another process')
        record = json.loads(state_file.read_text(encoding='utf-8'))
        if current.get('instance') != record['instance'] or current.get('pid') != record['pid']:
            raise SystemExit('Service identity mismatch; refusing to stop another process')
        os.kill(record['pid'], signal.SIGTERM)
        for _ in range(30):
            try:
                health(url)
            except httpx.HTTPError:
                state_file.unlink(missing_ok=True)
                print('Stopped')
                return 0
            time.sleep(.1)
        raise SystemExit('Stop requested but service still responds')
    if current:
        raise SystemExit('Port already serves an application; use status or another port')
    instance = str(uuid4())
    env = dict(os.environ, SHIXU_DB=str(args.db.resolve()), SHIXU_INSTANCE=instance,
               SHIXU_API_URL=url, PYTHONIOENCODING='utf-8')
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    with (runtime / f'service-{args.port}.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', args.host, '--port', str(args.port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kwargs)
    for _ in range(80):
        if process.poll() is not None:
            raise SystemExit('Service failed; inspect runtime log')
        try:
            result = health(url)
            if result.get('instance') == instance:
                state_file.write_text(json.dumps({'pid': result['pid'], 'instance': instance, 'url': url, 'bind_host': args.host}), encoding='utf-8')
                print(f'Started {url}; listening on {args.host}:{args.port}; authenticated MCP: {url}/mcp')
                return 0
            process.terminate()
            raise SystemExit('Port belongs to another process')
        except httpx.HTTPError:
            time.sleep(.2)
    process.terminate()
    raise SystemExit('Service startup timed out')


if __name__ == '__main__':
    raise SystemExit(main())
