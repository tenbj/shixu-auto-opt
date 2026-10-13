"""Complete interrupted acceptance with explicit, immutable per-run evidence.

Only recovery/secrets/cleanup are supplemented. Earlier stages retain their
original failed-run report, image, source and test fingerprints.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import time
import uuid
import httpx
from docker_check import ROOT, run, now, cleanup_owned, finalize, inventory
from docker_contract import snapshot, STAGES


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prior-report',required=True,type=Path)
    options=parser.parse_args()
    prior_path=options.prior_report.resolve()
    assert prior_path.parent==(ROOT/'verification/docker').resolve()
    prior_bytes=prior_path.read_bytes();prior=json.loads(prior_bytes)
    required=set(STAGES)-{'failure_recovery','secrets','cleanup'}
    assert prior['passed'] is False and prior['finally_cleanup']['passed'] is True
    assert {x['name'] for x in prior['checks'] if x['status']=='passed'}==required
    contract=json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'))
    assert prior['inputs']==snapshot(ROOT,contract['docker']['inputs'])
    assert prior['delivery_id']==contract['delivery_id']
    image=next(x['id'] for x in prior['images'] if x['service']=='app')
    assert json.loads(run(['docker','image','inspect',image]))[0]['Id']==image
    rows=[json.loads(line) for line in run(['docker','ps','-a','--format','json']).decode().splitlines()]
    assert not any('com.docker.compose.project=h02test-' in x.get('Labels','') for x in rows),'Serialize acceptance projects'
    project='h02test-shixu-'+uuid.uuid4().hex[:8]
    private=ROOT/'runtime'/project;private.mkdir(parents=True)
    output=ROOT/'verification/docker';report_path=output/(project+'.json')
    raw_path=output/(project+'-recovery.json')
    app_port=port();password=secrets.token_hex(24);database='shixu_docker_test'
    envfile=private/'app.env'
    envfile.write_text('\n'.join(['SHIXU_SKIP_DOTENV=true','SHIXU_BACKEND=mysql','DB_HOST=db','DB_USER=root',
        'DB_PASSWORD='+password,'DB_NAME='+database,'DB_SSL=false','SHIXU_ALLOW_HTTP_AUTH=true',
        'SHIXU_INSTANCE='+project,'SHIXU_BOOTSTRAP_PASSWORD='+secrets.token_hex(24)])+'\n',encoding='utf-8')
    cfg={'services':{'db':{'image':'mysql:8.4','environment':{'MYSQL_ROOT_PASSWORD':password,'MYSQL_DATABASE':database},
        'command':['--performance-schema=OFF','--innodb-buffer-pool-size=32M','--max-connections=30'],
        'mem_limit':'512m','cpus':0.75,'restart':'no','volumes':['db:/var/lib/mysql'],
        'healthcheck':{'test':['CMD-SHELL','MYSQL_PWD="$$MYSQL_ROOT_PASSWORD" mysql -h 127.0.0.1 -uroot -e "SELECT 1"'],'interval':'5s','timeout':'5s','retries':160}},
        'app':{'image':image,'env_file':[str(envfile)],'ports':[f'127.0.0.1:{app_port}:8765'],
        'volumes':['runtime:/app/runtime'],'depends_on':{'db':{'condition':'service_healthy'}},'init':True,
        'restart':'no','mem_limit':'512m','cpus':0.75}},'volumes':{'db':{},'runtime':{}}}
    compose=private/'compose.json';write(compose,cfg)
    os.environ.update(SHIXU_DOCKER_ENV_FILE=str(envfile),SHIXU_PORT=str(app_port),SHIXU_IMAGE=image)
    cli=['docker','compose','-p',project,'-f',str(ROOT/'compose.yaml'),'-f',str(compose)]
    source_evidence=prior_path.relative_to(ROOT).as_posix()
    report={**prior,'passed':False,'execution':'segmented','run_id':project,'compose_project':project,'started_at':now(),
        'checks':[{**row,'source_run':prior['run_id'],'source_evidence':source_evidence} for row in prior['checks']],
        'test_inputs':snapshot(ROOT,['tests']),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'url':f'http://127.0.0.1:{app_port}','existing_containers':[],
        'prior_segments':[{'run_id':prior['run_id'],'evidence':source_evidence,'sha256':hashlib.sha256(prior_bytes).hexdigest(),
            'passed':False,'accepted_stages':sorted(required),'image':image,'inputs':prior['inputs'],'test_inputs':prior['test_inputs'],
            'failure_reason':'Incorrect test expectation: missing credentials short-circuit to 401; authenticating supplied credentials needs DB and returns 503 during outage.'}],
        'recovery_preconditions':[]}
    for key in ['error','finally_cleanup','finished_at','cold_start_evidence']:report.pop(key,None)
    write(report_path,report)
    print('Recovery project: '+project,flush=True)
    def wait_health():
        for _ in range(90):
            try:
                response=httpx.get(report['url']+'/api/health',timeout=5,trust_env=False)
                response.raise_for_status();return response.json()
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('Recovery application did not become ready')
    try:
        running=[json.loads(line) for line in run(['docker','ps','--format','json']).decode().splitlines()]
        report['existing_containers']=inventory(running,project,set())[0]
        run(cli+['config','--quiet'])
        run(cli+['up','-d','db','--wait','--wait-timeout','900'],timeout=960)
        run(cli+['run','--rm','--no-deps','app','python','scripts/init_mysql.py','--database',database],timeout=180)
        run(cli+['up','-d','app','--wait','--wait-timeout','180'],timeout=240)
        assert wait_health()['backend']=='mysql'
        containers=json.loads(run(['docker','inspect',project+'-app-1',project+'-db-1']))
        report['runtime_resources']=[{'service':c['Config']['Labels']['com.docker.compose.service'],'image':c['Image'],
            'created':c['Created'],'started_at':c['State']['StartedAt'],'memory_mib':c['HostConfig']['Memory']//(1024*1024),
            'cpus':c['HostConfig']['NanoCpus']/1e9,'restart':c['HostConfig']['RestartPolicy']['Name']} for c in containers]
        assert all(c['memory_mib']==512 and c['cpus']==.75 and c['restart']=='no' for c in report['runtime_resources'])
        assert next(c['image'] for c in report['runtime_resources'] if c['service']=='app')==image
        with httpx.Client(base_url=report['url'],trust_env=False,timeout=30) as api:
            auth=api.post('/api/auth/register',json={'username':'recovery_'+uuid.uuid4().hex[:10],'password':secrets.token_hex(24)}).raise_for_status().json()
            api.headers['X-CSRF-Token']=auth['csrf']
            api.post('/api/issues',json={'title':'Synthetic recovery record','expected_version':0,'request_id':str(uuid.uuid4())}).raise_for_status()
            key=api.post('/api/account/mcp-access',json={'name':'Recovery read','scope':'read'}).raise_for_status().json()['token']
            retained=api.get('/api/workspace').raise_for_status().json()
            report['recovery_preconditions']=['Fresh isolated MySQL initialized; same application image healthy; registration/session/PAT and synthetic workspace verified']
            print('recovery startup/auth passed',flush=True)
            run(cli+['stop','db'])
            matrix={'health':httpx.get(report['url']+'/api/health',trust_env=False).status_code,
                'session':api.get('/api/workspace').status_code,
                'pat':httpx.get(report['url']+'/api/workspace',headers={'Authorization':'Bearer '+key},trust_env=False).status_code,
                'anonymous':httpx.get(report['url']+'/api/workspace',trust_env=False).status_code}
            assert matrix=={'health':503,'session':503,'pat':503,'anonymous':401},matrix
            run(cli+['up','-d','db','--wait','--wait-timeout','900'],timeout=960);wait_health()
            assert api.get('/api/workspace').raise_for_status().json()==retained
            assert httpx.get(report['url']+'/api/workspace',headers={'Authorization':'Bearer '+key},trust_env=False).json()==retained
            report['outage_statuses']=matrix
            report['checks'].append({'name':'failure_recovery','status':'passed','source_run':project,
                'source_evidence':raw_path.relative_to(ROOT).as_posix(),
                'observations':['Database stopped: health/session/PAT 503; missing credentials correctly 401 without DB lookup; database restored and complete session/PAT workspace retained without app restart']})
        write(report_path,report);finalize(project,publish_summary=False)
        report=json.loads(report_path.read_text(encoding='utf-8'))
        for row in report['checks']:
            if row['name'] in {'secrets','cleanup'}:row.update(source_run=project,source_evidence=raw_path.relative_to(ROOT).as_posix())
        assert prior_path.read_bytes()==prior_bytes,'Original failed report must remain unchanged'
    except BaseException as error:
        report['passed']=False
        report['error']=type(error).__name__+': supplementary acceptance failed; private diagnostic retained'
        (private/'error.txt').write_text(str(error),encoding='utf-8')
        try:(private/'containers.log').write_bytes(run(cli+['logs','--no-color','--tail','100'],timeout=30))
        except BaseException:pass
        raise
    finally:
        original=sys.exception()
        try:
            cleanup_owned(project,private)
            report['finally_cleanup']={'passed':True,'scope':'Exact owned containers, volumes and networks independently confirmed absent'}
        except BaseException as error:
            report['passed']=False;report['finally_cleanup']={'passed':False}
            if original:original.add_note('Owned cleanup failed: '+repr(error))
        report['finished_at']=now();write(report_path,report)
        raw={k:v for k,v in report.items() if k not in {'prior_segments','checks','execution'}}
        raw['checks']=[x for x in report['checks'] if x.get('source_run')==project]
        raw['execution']='supplementary_recovery';write(raw_path,raw)
        if report['passed']:write(ROOT/'verification/docker-report.json',report)
    assert report['passed']
    print(json.dumps({'passed':True,'run_id':project,'execution':'segmented','report':str(report_path)}))


if __name__=='__main__':main()
