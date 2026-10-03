import json
from fastapi.testclient import TestClient
from app.main import create_app
from app.mcp_access import issue, revoke, read_keys


def initialize(client, token=None, **headers):
    headers.update({'Accept': 'application/json, text/event-stream'})
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1,
        'method': 'initialize', 'params': {'protocolVersion': '2025-11-25', 'capabilities': {},
                                         'clientInfo': {'name': 'isolated-test', 'version': '1'}}})


def test_lifecycle_and_auth(tmp_path):
    app = create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        assert client.get('/api/health').json()['mcp']['running'] is True
        assert initialize(client).status_code == 401
        assert initialize(client, 'wrong').status_code == 401
        token = json.loads((tmp_path/'mcp-client-default.json').read_text(encoding='utf-8'))['mcpServers']['shixu']['headers']['Authorization'].split()[1]
        response = initialize(client, token)
        assert response.status_code == 200, response.text
        assert response.json()['result']['serverInfo']['name'] == 'shixu'
        assert token not in (tmp_path/'mcp-access.json').read_text(encoding='utf-8')
    assert app.state.mcp_running is False


def test_independent_revoke_and_restart(tmp_path):
    app = create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        key_a, token_a = issue(app.state.mcp_keys, '电脑A')
        _, token_b = issue(app.state.mcp_keys, '电脑B')
        assert initialize(client, token_a).status_code == 200
        revoke(app.state.mcp_keys, key_a)
        assert initialize(client, token_a).status_code == 401
        assert initialize(client, token_b).status_code == 200
    with TestClient(create_app(tmp_path/'test.sqlite3')) as restarted:
        assert initialize(restarted, token_a).status_code == 401
        assert initialize(restarted, token_b).status_code == 200


def test_no_recreation_after_all_revoked(tmp_path):
    app = create_app(tmp_path/'test.sqlite3')
    with TestClient(app):
        for row in read_keys(app.state.mcp_keys)['keys']:
            revoke(app.state.mcp_keys, row['id'])
    before = app.state.mcp_keys.read_bytes()
    with TestClient(create_app(tmp_path/'test.sqlite3')):
        assert app.state.mcp_keys.read_bytes() == before


def test_reject_bad_origin_and_host(tmp_path):
    app = create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        _, token = issue(app.state.mcp_keys, '测试')
        assert initialize(client, token, Origin='https://evil.invalid').status_code == 403
        assert initialize(client, token, Host='evil.invalid').status_code == 400


def test_corrupt_store_fails_closed(tmp_path):
    app = create_app(tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        _, token = issue(app.state.mcp_keys, '测试')
        app.state.mcp_keys.write_text('invalid', encoding='utf-8')
        assert initialize(client, token).status_code == 401
