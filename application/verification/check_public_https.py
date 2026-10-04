"""Read-only business verification; temporary access tokens are revoked."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

URL = 'https://shixu.eliasliu.cc'


async def sdk(token):
    async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + token},
                                  trust_env=False, timeout=30) as http:
        async with Client(streamable_http_client(URL + '/mcp', http_client=http)) as client:
            listing = await client.list_tools()
            context = await client.call_tool('get_connection_context', {'runtime_name':'public SDK verification','skill_version':'1.4.0'})
            assert not context.is_error
            result = await client.call_tool('get_workspace', {})
            assert not result.is_error
            state = result.structured_content or json.loads(result.content[0].text)
            return len(getattr(listing, 'tools', listing)), state


def run():
    report = {}
    credentials = {'username': 'test', 'password': os.environ['SHIXU_VERIFY_PASSWORD']}
    web = httpx.Client(base_url=URL, timeout=30, trust_env=False)
    access_ids = []
    try:
        logged = web.post('/api/auth/login', json=credentials, headers={'Origin': URL})
        logged.raise_for_status()
        assert '__Host-shixu_session=' in logged.headers['set-cookie']
        assert '; Secure' in logged.headers['set-cookie']
        web.headers['X-CSRF-Token'] = logged.json()['csrf']
        web.headers['Origin'] = URL
        baseline = web.get('/api/workspace').raise_for_status().json()
        connection = web.get('/api/account/mcp-access').raise_for_status().json()['connection']
        assert connection == {'url': URL + '/mcp', 'oauthAvailable': True, 'encrypted': True}
        report['https_login_secure_cookie'] = True
        pat = web.post('/api/account/mcp-access', json={'name': 'HTTPS验证-' + uuid4().hex[:8], 'scope': 'read'}).raise_for_status().json()
        access_ids.append(pat['item']['id'])
        count, state = asyncio.run(sdk(pat['token']))
        assert state == baseline
        report['pat_sdk_tools'] = count
        report['pat_sdk_read_workspace'] = True

        callback = 'http://127.0.0.1:9999/callback'
        client = web.post('/oauth/register', json={'client_name': 'HTTPS授权验证-' + uuid4().hex[:8], 'redirect_uris': [callback]}).raise_for_status().json()
        verifier = uuid4().hex + uuid4().hex
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        redirect = web.get('/oauth/authorize', params={'client_id': client['client_id'], 'redirect_uri': callback, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'resource': URL + '/mcp', 'response_type': 'code', 'scope': 'read', 'state': uuid4().hex})
        assert redirect.status_code == 303
        pending = parse_qs(urlparse(redirect.headers['location']).query)['authorize'][0]
        consent = web.post('/api/oauth/requests/' + pending, json={'allow': True}).raise_for_status().json()
        code = parse_qs(urlparse(consent['redirect']).query)['code'][0]
        exchanged = web.post('/oauth/token', data={'grant_type': 'authorization_code', 'code': code, 'client_id': client['client_id'], 'redirect_uri': callback, 'code_verifier': verifier, 'resource': URL + '/mcp'}).raise_for_status().json()
        items = web.get('/api/account/mcp-access').raise_for_status().json()['items']
        access_ids.extend(item['id'] for item in items if item['name'] == client['client_name'])
        oauth_state = web.get('/api/workspace', headers={'Authorization': 'Bearer ' + exchanged['access_token']}).raise_for_status().json()
        assert oauth_state == baseline
        report['oauth_pkce_exchange_and_read'] = True
        refreshed = web.post('/oauth/token',data={'grant_type':'refresh_token','refresh_token':exchanged['refresh_token'],'client_id':client['client_id'],'resource':URL+'/mcp'}).raise_for_status().json()
        assert refreshed['refresh_token'] != exchanged['refresh_token']
        count, renewed_state=asyncio.run(sdk(refreshed['access_token']))
        assert count==26 and renewed_state==baseline
        replay=web.post('/oauth/token',data={'grant_type':'refresh_token','refresh_token':exchanged['refresh_token'],'client_id':client['client_id'],'resource':URL+'/mcp'})
        assert replay.status_code==400 and replay.json()['error']=='invalid_grant'
        assert httpx.get(URL+'/api/workspace',headers={'Authorization':'Bearer '+refreshed['access_token']},trust_env=False).status_code==401
        report['mysql_refresh_rotation_and_replay_revocation']=True
        manifest=httpx.get(URL+'/connect/manifest.json',trust_env=False).raise_for_status().json()
        assert manifest['mcp']==URL+'/mcp'
        package=httpx.get(manifest['skill']['url'],trust_env=False).raise_for_status()
        assert hashlib.sha256(package.content).hexdigest()==manifest['skill']['sha256']
        assert httpx.get(URL+'/connect.md',trust_env=False).status_code==200
        report['anonymous_guide_and_bundle_hash']=True
        report['business_data_unchanged'] = web.get('/api/workspace').raise_for_status().json() == baseline
        for identifier in access_ids:
            web.post('/api/account/mcp-access/' + identifier + '/revoke', json={}).raise_for_status()
        access_ids.clear()
        denied = httpx.get(URL + '/api/workspace', headers={'Authorization': 'Bearer ' + pat['token']}, timeout=20, trust_env=False)
        assert denied.status_code == 401
        report['temporary_tokens_revoked'] = True
        with httpx.Client(base_url='http://eliasliu.cc:11865', timeout=20, trust_env=False) as old:
            login = old.post('/api/auth/login', json=credentials)
            login.raise_for_status()
            assert login.headers['set-cookie'].startswith('shixu_session=')
            assert '; Secure' not in login.headers['set-cookie']
            old.headers['X-CSRF-Token'] = login.json()['csrf']
            assert old.get('/api/workspace').raise_for_status().json() == baseline
            assert old.get('/connect/manifest.json').raise_for_status().json()['mcp']==URL+'/mcp'
            old.post('/api/auth/logout', json={}).raise_for_status()
        report['old_http_login_and_read'] = True
    finally:
        for identifier in access_ids:
            web.post('/api/account/mcp-access/' + identifier + '/revoke', json={})
        web.post('/api/auth/logout', json={})
        web.close()
    target = Path(__file__).with_name('public-https-report.json')
    report.update(passed=True,delivery_id=json.loads((target.parent.parent/'project-contract.json').read_text(encoding='utf-8'))['delivery_id'],business_writes=0)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    target.with_name('public-http-report.json').write_text(json.dumps(dict(passed=True,delivery_id=report['delivery_id'],url='http://eliasliu.cc:11865',checks=['HTTP session login and read','canonical HTTPS MCP advertised','business workspace unchanged','HTTP logout'],business_writes=0),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    run()
