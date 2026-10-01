"""仅打印 MCP 配置片段，不自动修改任何客户端配置。"""
import argparse
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--format', choices=['json', 'toml'], default='json')
parser.add_argument('--url', default='http://127.0.0.1:8765')
args = parser.parse_args()
config = dict(command=sys.executable, args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')], env={'SHIXU_API_URL': args.url})
if args.format == 'json':
    print(json.dumps({'mcpServers': {'shixu': config}}, ensure_ascii=False, indent=2))
else:
    print('[mcp_servers.shixu]\ncommand = ' + json.dumps(config['command'], ensure_ascii=False))
    print('args = ' + json.dumps(config['args'], ensure_ascii=False))
    print('[mcp_servers.shixu.env]\nSHIXU_API_URL = ' + json.dumps(args.url))
