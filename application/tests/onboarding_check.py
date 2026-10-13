"""Real public HTTP, browser and MCP onboarding checks on an isolated account."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]

async def verify_mcp(url,token):
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token},trust_env=False) as http:
        async with Client(streamable_http_client(url+'/mcp',http_client=http)) as client:
            tools=await client.list_tools();assert len(getattr(tools,'tools',tools))==29
            response=await client.call_tool('get_connection_context',{'runtime_name':'SDK acceptance','runtime_version':'fixture','skill_version':'1.5.0'})
            assert not response.is_error
            context=response.structured_content or json.loads(response.content[0].text)
            assert context['verifiedAt'] and context['verification']=='authenticated-mcp-call'
            assert context['scopes']==['read']
            return context

def run(url):
    expect.set_options(timeout=20000)
    checks=[]
    with httpx.Client(base_url=url,trust_env=False) as api:
        health=api.get('/api/health').raise_for_status().json()
        assert health['backend']=='sqlite-test' or health['database'].endswith('_test')
        public=api.get('/connect/manifest.json').raise_for_status().json()
        bundle=api.get('/downloads/'+public['skill']['filename']).raise_for_status()
        assert hashlib.sha256(bundle.content).hexdigest()==public['skill']['sha256']
        assert api.get('/connect.md').status_code==200
        for runtime in public['runtimes']:
            assert api.get(runtime['guide']).status_code==200
        checks.append('anonymous guide/manifest/Skill download and digest')
        username='onboarding_'+uuid4().hex[:10];password=uuid4().hex
        auth=api.post('/api/auth/register',json=dict(username=username,password=password)).raise_for_status().json()
        api.headers['X-CSRF-Token']=auth['csrf']
        version=api.get('/api/workspace').raise_for_status().json()['revision']
        api.post('/api/identities',json=dict(name=username,kind='person',via='manual',request_id=str(uuid4()),expected_version=version)).raise_for_status()
        before=api.get('/api/workspace').raise_for_status().json()
        key=api.post('/api/account/mcp-access',json={'name':'MCP acceptance','scope':'read'}).raise_for_status().json()
        context=asyncio.run(verify_mcp(url,key['token']))
        assert context['account']['id']==auth['user']['id']
        row=api.get('/api/account/mcp-access').json()['items'][0]
        assert row['verifiedAt'] and row['lastSeenAt'] and row['skillVersion']=='1.5.0'
        assert api.get('/api/workspace').json()==before
        checks.append('real MCP diagnostic, readonly account/scope/version and device evidence; no business writes')
        errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            for width in (360,390,430,537,1440):
                page=browser.new_page(viewport={'width':width,'height':900},permissions=['clipboard-read','clipboard-write'])
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url+'/connect');expect(page.locator('#copy')).to_be_enabled()
                page.locator('#copy').click();expect(page.locator('#status')).to_contain_text('已复制')
                prompt=page.evaluate('navigator.clipboard.readText()')
                assert public['guide'] in prompt and key['token'] not in prompt
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.goto(url);page.locator('[name=username]').fill(username);page.locator('[name=password]').fill(password)
                page.locator('#account-auth-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_be_visible()
                page.locator('.account-pill:visible').click();page.locator('[data-account-action=connections]').click()
                expect(page.locator('#account-modal [role=tab]')).to_have_count(3)
                expect(page.locator('[role=tab][aria-selected=true]')).to_contain_text('快速接入')
                page.locator('#ai-runtime').select_option('codex');page.locator('[data-ai-action=copy-prompt]').click()
                expect(page.locator('#ai-copy-status')).to_contain_text('已复制')
                page.screenshot(path=str(ROOT/f'verification/onboarding-quick-{width}.png'),timeout=30000)
                page.locator('[role=tab][data-id=list]').click();expect(page.locator('#account-tabpanel')).to_contain_text('MCP 已验证')
                # Each viewport must wait for its own rename response/render, not a prior identical label.
                renamed='重命名设备'+str(width)
                page.locator('[data-ai-action=rename]').click();page.locator('#ai-rename-form [name=name]').fill(renamed)
                page.locator('#ai-rename-form [type=submit]').click();expect(page.locator('#account-tabpanel')).to_contain_text(renamed)
                expect(page.locator('#modal')).not_to_be_visible()
                page.locator('[role=tab][data-id=server]').click();expect(page.locator('#account-tabpanel')).to_contain_text('访问令牌')
                page.locator('[role=tab][data-id=server]').press('Home');expect(page.locator('[role=tab][aria-selected=true]')).to_contain_text('快速接入')
                page.keyboard.press('Escape');expect(page.locator('#account-modal')).not_to_be_visible()
                assert page.evaluate('document.activeElement.classList.contains("account-pill")'), {'width':width,'active':page.evaluate('document.activeElement.outerHTML'),'dialog':page.locator('#account-modal').get_attribute('open')}
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                checks.append(f'{width}px public copy, account top-right entry, three tabs, rename, keyboard and context return')
                page.close()
            browser.close()
        assert not errors,errors
        assert api.get('/api/workspace').json()==before
        api.post('/api/account/mcp-access/'+key['item']['id']+'/revoke',json={}).raise_for_status()
        assert httpx.get(url+'/api/connection-context',headers={'Authorization':'Bearer '+key['token']},trust_env=False).status_code==401
        checks.append('revocation immediately denies the previously verified connection')
    report=dict(passed=True,delivery_id=json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'))['delivery_id'],checks=checks,browser_errors=errors,scope='real isolated HTTP/MCP SDK and Chromium; no actual Codex/WorkBuddy installation claimed')
    (ROOT/'verification/onboarding-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);run(parser.parse_args().url)
