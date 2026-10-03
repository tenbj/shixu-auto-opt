"""隔离检查：不触碰日常数据库，不使用用户浏览器。"""
import json
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'verification'


def run(*arguments, env=None):
    subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env, check=True)


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('验证服务提前退出')
        try:
            return httpx.get(url + '/api/health', timeout=1, trust_env=False).raise_for_status().json()
        except httpx.HTTPError:
            time.sleep(.1)
    raise RuntimeError('验证服务未就绪')


def stop(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.terminate()
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql', action='store_true', help='集成验证使用当前新建库对应的_test库；不会写日常库')
    args = parser.parse_args()
    REPORT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shixu-check-') as temporary:
        env = dict(os.environ, SHIXU_BACKEND='sqlite', SHIXU_DB=str(Path(temporary) / 'tests.sqlite3'), PYTHONIOENCODING='utf-8')
        run('-m', 'pytest', 'tests', '-q', '--junitxml=verification/pytest.xml', env=env)
        suite = ET.parse(REPORT / 'pytest.xml').getroot().find('testsuite')
        api_report = {'passed': True, 'tests': int(suite.attrib['tests']), 'failures': int(suite.attrib['failures']), 'scope': 'FastAPI TestClient + 真实临时SQLite；包括事务回滚、幂等、并发与状态机'}
        (REPORT / 'api-report.json').write_text(json.dumps(api_report, ensure_ascii=False, indent=2), encoding='utf-8')
        port = available_port()
        url = f'http://127.0.0.1:{port}'
        env['SHIXU_API_URL'] = url
        env['SHIXU_MCP_KEYS_PATH'] = str(Path(temporary) / 'mcp-access.json')
        env['SHIXU_DB'] = str(Path(temporary) / 'integration.sqlite3')
        backend = 'sqlite-test'
        if args.mysql:
            from dotenv import dotenv_values
            pointer = dotenv_values(ROOT / '.env')
            private = dotenv_values(os.getenv('SHIXU_ENV_FILE') or pointer['SHIXU_ENV_FILE'])
            target = private['DB_NAME'] + '_test'
            if not target.startswith('shixu_') or not target.endswith('_test'):
                raise RuntimeError('只允许专属_test验证库')
            env.update(SHIXU_BACKEND='mysql', DB_NAME=target)
            backend = 'mysql'
        def start():
            kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            return subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                                    cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        process = start()
        try:
            first_health = wait(url, process)
            assert first_health['backend'] == backend
            run('examples/api_client.py', '--url', url, env=env)
            run('examples/mcp_client.py', '--url', url, '--write-demo', '--report', str(REPORT / 'mcp-report.json'), env=env)
            run('examples/http_mcp_client.py', '--config', str(Path(temporary) / 'mcp-client-default.json'),
                '--write-demo', '--report', str(REPORT / 'http-mcp-report.json'), env=env)
            run('tests/browser_check.py', '--url', url, env=env)
            run('tests/trash_browser_check.py', '--url', url, env=env)
            run('tests/creator_browser_check.py', '--url', url, env=env)
            if args.mysql:
                run('tests/mysql_check.py', '--url', url, env=env)
                run('tests/retention_mysql_check.py', '--url', url, env=env)
            before = httpx.get(url + '/api/workspace', trust_env=False).raise_for_status().json()
            stop(process)
            try:
                httpx.get(url + '/api/health', timeout=1, trust_env=False)
            except httpx.HTTPError:
                pass
            else:
                raise AssertionError('Old service still responds after stop')
            process = start()
            second_health = wait(url, process)
            assert first_health['pid'] != second_health['pid']
            after = httpx.get(url + '/api/workspace', trust_env=False).raise_for_status().json()
            assert before == after
            persistence = {'passed': True, 'backend': backend, 'scope': '旧进程树退出且端口不再响应，重新启动得到不同PID，数据库完整工作台回读相等', 'revision': after['revision'], 'issues': len(after['data']['issues']), 'tasks': len(after['data']['tasks'])}
            (REPORT / 'persistence-report.json').write_text(json.dumps(persistence, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            stop(process)
    summary = {'passed': True, 'business_api_tests': api_report['tests'], 'browser_checks': len(json.loads((REPORT / 'browser-report.json').read_text(encoding='utf-8'))['checks']), 'mcp_tools': 25, 'integration_backend': backend, 'mysql_checks': 5 if args.mysql else 0, 'persistence': 'passed', 'ai_autonomous': 'not_run', 'environment': {'os': sys.platform, 'python': sys.version.split()[0]}, 'scope': '单机服务；MySQL模式在新建_test库真实联调；浏览器响应丢失使用网络拦截模拟；未做AI自主任务验收'}
    (REPORT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
