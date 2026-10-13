"""Real HTTP and TLS browser/MCP checks with synthetic data and an ephemeral certificate."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import httpx
import httpx2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from playwright.sync_api import sync_playwright, expect
from docker_check import stop_command

ROOT=Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


async def mcp_check(url,token,verify):
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token,'Host':'shixu.test:'+url.rsplit(':',1)[1]},verify=verify,trust_env=False,timeout=30) as http:
        async with Client(streamable_http_client(url+'/mcp',http_client=http)) as client:
            async def call(name,args=None):
                r=await client.call_tool(name,args or {})
                assert not r.is_error
                return r.structured_content or json.loads(r.content[0].text)
            tools=await client.list_tools();assert len(tools.tools)==29
            state=await call('get_workspace')
            made=await call('create_issue',{'body':dict(title='Synthetic dual transport',expected_version=state['revision'],request_id=str(uuid4()))})
            assert (await call('get_issue',{'issue_id':made['resource']['id']}))['item']['title']=='Synthetic dual transport'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--upstream');ap.add_argument('--proxy-env',type=Path);options=ap.parse_args()
    if bool(options.upstream)!=bool(options.proxy_env):ap.error('--upstream and --proxy-env must be supplied together')
    checks=[];errors=[];processes=[]
    with tempfile.TemporaryDirectory(prefix='shixu-tls-test-') as folder:
        temp=Path(folder);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'shixu.test')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
              .not_valid_after(now+datetime.timedelta(days=1))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('shixu.test'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
              .sign(key,hashes.SHA256()))
        (temp/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (temp/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        trust=ssl.create_default_context(cafile=str(temp/'cert.pem'))
        ports={'http':port(),'https':port()}
        if options.upstream:
            from urllib.parse import urlparse
            from dotenv import dotenv_values
            parsed=urlparse(options.upstream)
            assert parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port
            private=options.proxy_env.resolve()
            assert private.is_relative_to((ROOT/'runtime').resolve()) and private.parent.name.startswith('h02test-shixu-')
            values=dotenv_values(private)
            upstream_backend=httpx.get(options.upstream+'/api/health',trust_env=False,timeout=10).raise_for_status().json()['backend']
            assert values['SHIXU_PUBLIC_URL']=='https://shixu.test'
            ports={'http':parsed.port,'https':443}
            with socket.socket() as listener:listener.bind(('127.0.0.1',443))
        env=dict(os.environ,SHIXU_BACKEND='sqlite',SHIXU_DB=str(temp/'test.sqlite3'),SHIXU_ALLOW_HTTP_AUTH='true',SHIXU_ALLOWED_HOSTS='shixu.test',PYTHONIOENCODING='utf-8',SHIXU_SKIP_DOTENV='true',SHIXU_PUBLIC_URL='',SHIXU_HTTPS_PROXY_SECRET='')
        if options.upstream:env.update(SHIXU_TEST_UPSTREAM=options.upstream,SHIXU_TEST_PROXY_PROOF=values['SHIXU_HTTPS_PROXY_SECRET'])
        def origin(scheme,p):return f'{scheme}://shixu.test'+('' if scheme=='https' and p==443 else ':'+str(p))
        try:
            for scheme,p in ports.items():
                if options.upstream and scheme=='http':continue
                args=[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(p),'--forwarded-allow-ips','']
                if env.get('SHIXU_TEST_UPSTREAM'):args[3]='tls_proxy:app';args+=['--app-dir',str(ROOT/'tests'),'--lifespan','off']
                if scheme=='https':args+=['--ssl-keyfile',str(temp/'key.pem'),'--ssl-certfile',str(temp/'cert.pem')]
                process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}));processes.append(process)
                for _ in range(100):
                    try:
                        httpx.get(f'{scheme}://127.0.0.1:{p}/api/health',verify=trust,trust_env=False,timeout=1).raise_for_status();break
                    except httpx.HTTPError:
                        assert process.poll() is None
                        time.sleep(.1)
                else:raise RuntimeError('Test service unavailable')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',args=['--host-resolver-rules=MAP shixu.test 127.0.0.1','--no-proxy-server'])
                for scheme,p in ports.items():
                    # Certificate is synthetic. Browser ignores trust only for this isolated context;
                    # MCP separately verifies the exact generated certificate through a private CA context.
                    context=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
                    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    browser_origin=origin(scheme,p);url=f'{scheme}://127.0.0.1:{p}'
                    pending=[];page.route('**/api/auth/me',lambda route:pending.append(route))
                    page.goto(browser_origin,wait_until='domcontentloaded');page.wait_for_function("!!document.querySelector('[data-account-action=register-mode]')")
                    page.locator('[data-account-action=register-mode]').click()
                    page.locator('[name=username]').fill('preserve_registration_draft')
                    assert len(pending)==1
                    pending[0].continue_();page.wait_for_function("document.documentElement.dataset.accountBoot==='complete'")
                    expect(page.locator('#account-auth-form')).to_have_attribute('data-mode','register')
                    expect(page.locator('[name=username]')).to_have_value('preserve_registration_draft')
                    expect(page.locator('[name=confirm]')).to_be_visible();page.unroute('**/api/auth/me')
                    username='transport_'+uuid4().hex[:10];password=uuid4().hex
                    for name,value in [('username',username),('displayName','协议验收'),('password',password),('confirm',password)]:page.locator('[name='+name+']').fill(value)
                    page.locator('#account-auth-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_contain_text('协议验收')
                    assert page.evaluate('isSecureContext')==(scheme=='https')
                    page.locator('.account-pill:visible').click();page.locator('#account-dropdown [data-account-action=connections]').click()
                    page.locator('[role=tab][data-id=server]').click()
                    page.locator('[data-account-action=new-access]').click();page.locator('#account-access-form [name=name]').fill('协议验收端')
                    page.locator('#account-access-form [name=scope]').select_option('write');page.locator('#account-access-form [type=submit]').click()
                    expect(page.locator('#issued-config')).to_be_visible();config=json.loads(page.locator('#issued-config').input_value())['mcpServers']['shixu']
                    assert config['url']==('https://shixu.test' if options.upstream else browser_origin)+'/mcp'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    # Do not capture the one-time credential modal.
                    token=config['headers']['Authorization'][7:]
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        executor.submit(lambda:asyncio.run(mcp_check(url,token,trust))).result(timeout=90)
                    page.locator('#modal .modal-head [data-action=close]').click()
                    page.locator('[data-account-action=revoke-access]').click();page.locator('[data-account-action=confirm-revoke]').click()
                    expect(page.locator('#account-modal')).to_contain_text('已撤销')
                    assert httpx.get(url+'/api/workspace',headers={'Authorization':'Bearer '+token,'Host':'shixu.test:'+str(p)},verify=trust,trust_env=False).status_code==401
                    page.screenshot(path=str(ROOT/f'verification/transport-{scheme}-390.png'),full_page=True)
                    cookies=context.cookies();cookie=next(c for c in cookies if c['name']==('__Host-shixu_session' if scheme=='https' else 'shixu_session'))
                    assert cookie['secure']==(scheme=='https') and cookie['httpOnly']
                    page.locator('[data-account-action=close-account-panel]').click();page.locator('.account-pill:visible').click();page.locator('#account-dropdown [data-account-action=logout]').click()
                    expect(page.locator('#account-auth')).to_be_visible()
                    checks.append(dict(scheme=scheme,passed=True,scope='Non-loopback browser origin; register/login session, mobile tabs, generated URL, 29 MCP tools, create/read, revoke, logout, Cookie attributes, and delayed real ME response preserves registration draft'))
                    context.close()
                # Same browser, same hostname, two schemes: each session must survive the other's login/logout.
                shared=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
                pages={};credentials={};users={};issue_ids={}
                def json_request(page,path):
                    return page.evaluate("async path=>{const r=await fetch(path);return {status:r.status,body:await r.json()}}",path)
                def logout(page):
                    page.locator('.account-pill:visible').click();page.locator('#account-dropdown [data-account-action=logout]').click()
                    expect(page.locator('#account-auth')).to_be_visible()
                def login(page,scheme):
                    user,password=credentials[scheme]
                    page.locator('[name=username]').fill(user);page.locator('[name=password]').fill(password)
                    page.locator('#account-auth-form [type=submit]').click()
                    expect(page.locator('.account-pill:visible')).to_contain_text('双入口'+scheme)
                for scheme,p in ports.items():
                    page=shared.new_page();pages[scheme]=page
                    response=page.goto(origin(scheme,p),wait_until='domcontentloaded')
                    assert response.status==200 and page.url.startswith(scheme+'://')
                    page.locator('[data-account-action=register-mode]').click()
                    user='shared_'+uuid4().hex[:10];password=uuid4().hex;credentials[scheme]=(user,password)
                    for name,value in [('username',user),('displayName','双入口'+scheme),('password',password),('confirm',password)]:page.locator('[name='+name+']').fill(value)
                    page.locator('#account-auth-form [type=submit]').click();expect(page.locator('.account-pill:visible')).to_contain_text('双入口'+scheme)
                    me=json_request(page,'/api/auth/me');assert me['status']==200;users[scheme]=me['body']['user']['id']
                    made=page.evaluate("""async input=>{const me=await (await fetch('/api/auth/me')).json();const ws=await (await fetch('/api/workspace')).json();const r=await fetch('/api/issues',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf},body:JSON.stringify({title:input.title,request_id:input.request,expected_version:ws.revision})});return {status:r.status,body:await r.json()}}""",{'title':'Synthetic shared browser '+scheme,'request':str(uuid4())})
                    assert made['status']==200;issue_ids[scheme]=made['body']['resource']['id']
                    assert json_request(page,'/api/issues/'+issue_ids[scheme])['body']['item']['title']=='Synthetic shared browser '+scheme
                assert users['http']!=users['https']
                for scheme,page in pages.items():
                    page.reload(wait_until='domcontentloaded')
                    assert json_request(page,'/api/auth/me')['body']['user']['id']==users[scheme]
                    assert json_request(page,'/api/issues/'+issue_ids['https' if scheme=='http' else 'http'])['status']==404
                logout(pages['http']);assert json_request(pages['http'],'/api/auth/me')['status']==401
                assert json_request(pages['https'],'/api/auth/me')['body']['user']['id']==users['https']
                login(pages['http'],'http');logout(pages['https'])
                assert json_request(pages['https'],'/api/auth/me')['status']==401
                assert json_request(pages['http'],'/api/auth/me')['body']['user']['id']==users['http']
                login(pages['https'],'https')
                for scheme,page in pages.items():assert json_request(page,'/api/issues/'+issue_ids[scheme])['status']==200
                checks.append(dict(scheme='http+https',passed=True,same_browser_context=True,scope='Both origins stay on original scheme; UI registration and explicit login; session-authenticated business create/read; cross-account 404; each logout preserves the other scheme session; login restores own data'))
                shared.close()
                browser.close()
            assert not errors,errors
            assert httpx.post(f'http://127.0.0.1:{ports["http"]}/oauth/register',headers={'Host':'shixu.test','X-Forwarded-Proto':'https'},json={},trust_env=False).status_code==400
        finally:
            original=sys.exception();failures=[]
            for process in processes:
                try:
                    if process.poll() is None:stop_command(process)
                    else:process.wait(timeout=10)
                except BaseException as error:failures.append(type(error).__name__)
            if failures:
                failure=RuntimeError('Test proxy process cleanup failed: '+','.join(failures))
                if original:original.add_note(str(failure))
                else:raise failure
    report=dict(passed=True,delivery_id=json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'))['delivery_id'],checks=checks,browser_errors=errors,
                public_tls_deployed=False,production_writes=0,tls='Real TLS with ephemeral self-signed test certificate; MCP verifies test CA; no change to public TLS',forwarded_header_spoof_rejected=True)
    report['backend']=('docker-mysql' if upstream_backend=='mysql' else 'proxy-'+upstream_backend) if options.upstream else 'isolated-sqlite'
    report['upstream']=options.upstream
    target=ROOT/('verification/docker/dual-transport-report.json' if options.upstream and upstream_backend=='mysql' else 'verification/proxy-transport-report.json' if options.upstream else 'verification/dual-transport-report.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
