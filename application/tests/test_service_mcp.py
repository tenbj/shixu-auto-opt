"""验证管理脚本默认启动/停止HTTP MCP，随机端口与临时数据库。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import httpx

ROOT = Path(__file__).resolve().parents[1]


def test_service_start_stop_restart(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, SHIXU_BACKEND='sqlite', SHIXU_MCP_KEYS_PATH=str(tmp_path/'mcp-access.json'),
               PYTHONIOENCODING='utf-8')
    def service(action):
        result = subprocess.run([sys.executable, 'scripts/service.py', action, '--port', str(port),
                                 '--host', '127.0.0.1', '--db', str(tmp_path/'test.sqlite3')],
                                cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stderr + result.stdout
        return result.stdout
    started = False
    try:
        for _ in range(2):
            service('start')
            started = True
            state = json.loads(service('status'))
            assert state['mcp']['running'] is True
            assert httpx.post(url+'/mcp', trust_env=False).status_code == 401
            checked = subprocess.run([sys.executable, 'examples/http_mcp_client.py', '--config',
                                      str(tmp_path/'mcp-client-default.json')], cwd=ROOT, env=env,
                                     capture_output=True, text=True, encoding='utf-8', timeout=30)
            assert checked.returncode == 0, checked.stderr
            service('stop')
            started = False
            try:
                httpx.post(url+'/mcp', trust_env=False, timeout=2)
            except httpx.RequestError:
                pass
            else:
                raise AssertionError('MCP未随服务停止')
    finally:
        if started:
            service('stop')
