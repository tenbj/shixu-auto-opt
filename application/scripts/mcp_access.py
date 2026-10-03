"""在服务电脑串行管理MCP密钥；不向终端打印密钥或完整客户端配置。"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import load_environment
from app.mcp_access import issue, revoke, read_keys, client_config, atomic_json


def main():
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'list', 'revoke'])
    parser.add_argument('--label')
    parser.add_argument('--id')
    parser.add_argument('--url', default='http://127.0.0.1:8765/mcp')
    parser.add_argument('--output', type=Path, help='私有JSON配置输出路径；create必填且不能覆盖已有文件')
    parser.add_argument('--keys', type=Path, default=Path(os.getenv('SHIXU_MCP_KEYS_PATH', ROOT/'runtime/mcp-access.json')))
    args = parser.parse_args()
    if args.action == 'create':
        if not args.label or not args.output or args.output.exists():
            parser.error('create须提供label和不存在的私有output文件')
        output = args.output.resolve()
        if output.is_relative_to(ROOT.parent) and not output.is_relative_to(ROOT/'runtime'):
            parser.error('仓库内的密钥配置只能保存到application/runtime；也可使用仓库外私有目录')
        identifier, token = issue(args.keys, args.label)
        try:
            atomic_json(args.output, client_config(args.url, token))
        except Exception:
            revoke(args.keys, identifier)
            raise
        print(json.dumps({'id': identifier, 'config_file': str(args.output), 'token_printed': False}, ensure_ascii=False))
    elif args.action == 'revoke':
        if not args.id:
            parser.error('revoke须提供id')
        revoke(args.keys, args.id)
        print('Revoked; next request is rejected without restart')
    else:
        print(json.dumps([{k: row[k] for k in ('id', 'label', 'enabled', 'createdAt')}
                          for row in read_keys(args.keys)['keys']], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
