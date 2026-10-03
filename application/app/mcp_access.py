"""MCP专用访问密钥；只保存摘要，客户端配置保存在忽略的本机runtime目录。"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4
from datetime import datetime, timezone


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.mcp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_keys(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('version') != 1 or not isinstance(value.get('keys'), list):
        raise ValueError('MCP访问密钥文件格式无效')
    return value


def issue(path, label):
    path = Path(path)
    value = read_keys(path) if path.exists() else {'version': 1, 'keys': []}
    if not label.strip() or any(row['label'] == label.strip() and row['enabled'] for row in value['keys']):
        raise ValueError('名称为空或已有同名有效密钥')
    token = 'sx_' + secrets.token_urlsafe(32)
    row = dict(id=str(uuid4()), label=label.strip(), enabled=True,
               createdAt=datetime.now(timezone.utc).isoformat(),
               digest=hashlib.sha256(token.encode()).hexdigest())
    value['keys'].append(row)
    atomic_json(path, value)
    return row['id'], token


def revoke(path, identifier):
    value = read_keys(path)
    row = next((row for row in value['keys'] if row['id'] == identifier), None)
    if row is None:
        raise ValueError('密钥ID不存在')
    row['enabled'] = False
    atomic_json(path, value)


def client_config(url, token):
    return {'mcpServers': {'shixu': {'type': 'http', 'url': url,
                                   'headers': {'Authorization': 'Bearer ' + token}}}}


def ensure_keys(path, url):
    """单进程服务首次启动准备一份私有配置，已有文件（含全撤销状态）不覆盖。"""
    path = Path(path)
    if not path.exists():
        _, token = issue(path, '默认接入')
        atomic_json(path.parent / 'mcp-client-default.json', client_config(url, token))
    read_keys(path)  # 格式错误须阻止启动，不能降级成免认证。


def authenticate(path, token):
    if not token or len(token) > 256:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    try:
        for row in read_keys(path)['keys']:
            if row['enabled'] and hmac.compare_digest(row['digest'], digest):
                return row['id']
    except (OSError, ValueError, KeyError, TypeError):
        return None  # 读取异常拒绝访问，不放行。
    return None
