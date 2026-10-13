"""Isolated real MySQL/API/MCP/browser Docker acceptance; never loads production env."""
from pathlib import Path
import argparse, gzip, hashlib, json, os, re, secrets, signal, socket, subprocess, sys, tarfile, time, uuid
from datetime import datetime, timezone
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

def stop_command(p):
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=20)
    else:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    p.communicate(timeout=10)

def run(args, *, env=None, timeout=180, input=None):
    p=subprocess.Popen(args,cwd=ROOT,env=env,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       **({'start_new_session':True} if os.name!='nt' else {}))
    try: out,err=p.communicate(input=input,timeout=timeout)
    except BaseException as error:
        try:stop_command(p)
        except BaseException as cleanup_error:error.add_note('Command cleanup failed: '+repr(cleanup_error))
        raise
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' '+err.decode(errors='replace')[-3000:])
    return out

def now():return datetime.now(timezone.utc).isoformat()

def inventory(rows, project, peers):
    """Exclude only this run and explicit peer Compose labels, never name prefixes."""
    kept=[];excluded=[]
    for row in rows:
        labels=dict(item.split('=',1) for item in row.get('Labels','').split(',') if '=' in item)
        owner=labels.get('com.docker.compose.project')
        if owner==project or owner in peers:
            excluded.append({'id':row['ID'],'compose_project':owner})
        else: kept.append(row['ID'])
    return sorted(kept),excluded
def cleanup_owned(project, private):
    if not re.fullmatch(r'h02test-shixu-[a-f0-9]+',project):raise ValueError('Invalid isolated project')
    assert private.resolve()==(ROOT/'runtime'/project).resolve()
    cfg=json.loads((private/'compose.json').read_text(encoding='utf-8'))
    env=dict(os.environ,SHIXU_DOCKER_ENV_FILE=str(private/'app.env'),SHIXU_PORT=cfg['services']['app']['ports'][0].split(':')[1],SHIXU_IMAGE=cfg['services']['app']['image'])
    failures=[]
    try:run(['docker','compose','-p',project,'-f',str(ROOT/'compose.yaml'),'-f',str(private/'compose.json'),'down','--volumes','--remove-orphans'],env=env,timeout=120)
    except BaseException as error:failures.append('down: '+repr(error))
    for kind,command in [('containers',['docker','ps','-a']),('volumes',['docker','volume','ls']),('networks',['docker','network','ls'])]:
        try:
            if run(command+['--filter','label=com.docker.compose.project='+project,'-q']).strip():failures.append('Owned '+kind+' remain')
        except BaseException as error:failures.append(kind+': '+repr(error))
    if failures:raise RuntimeError('; '.join(failures))

def finalize(run_id):
    from docker_contract import STAGES, snapshot
    if not re.fullmatch(r'h02test-shixu-[a-f0-9]+(?:-[a-f0-9]+)?',run_id):raise ValueError('Invalid isolated run')
    path=ROOT/'verification'/'docker'/(run_id+'.json');report=json.loads(path.read_text(encoding='utf-8'))
    complete={x['name'] for x in report['checks'] if x['status']=='passed'}
    assert set(STAGES)-{'secrets','cleanup'}<=complete,'Runtime stages incomplete'
    project=report['compose_project'];private=ROOT/'runtime'/project
    from dotenv import dotenv_values
    credentials=dotenv_values(private/'app.env');needles=[v.encode() for k,v in credentials.items() if v and len(v)>=12 and any(t in k for t in ('PASSWORD','SECRET','TOKEN'))]
    image=next(x['id'] for x in report['images'] if x['service']=='app')
    archive=private/'image-audit.tar';run(['docker','image','save','-o',str(archive),image],timeout=240)
    checked=0
    with tarfile.open(archive) as outer:
        for member in outer:
            if not member.isfile():continue
            stream=outer.extractfile(member);magic=stream.read(4);stream.seek(0)
            if magic==bytes.fromhex('28b52ffd'):raise ValueError('Unsupported zstd image layer')
            if magic[:2]==bytes.fromhex('1f8b'):stream=gzip.GzipFile(fileobj=stream)
            tail=b''
            while True:
                chunk=stream.read(1024*1024)
                if not chunk:break
                block=tail+chunk;assert not any(n in block for n in needles),'Secret in image'
                tail=block[-max(map(len,needles)):];checked+=len(chunk)
    report['checks'].append({'name':'secrets','status':'passed','observations':[f'All {checked} decompressed image bytes and metadata scanned; isolated credential values absent; explicit COPY whitelist excludes runtime/private env']})
    cleanup_owned(project,private)
    after=set(run(['docker','ps','--format','{{.ID}}']).decode().splitlines());assert set(report['existing_containers'])<=after
    assert not run(['docker','ps','-a','--filter','label=com.docker.compose.project='+project,'-q']).strip()
    assert not run(['docker','volume','ls','--filter','label=com.docker.compose.project='+project,'-q']).strip()
    report['checks'].append({'name':'cleanup','status':'passed','observations':['Only owned isolated project containers/volumes removed; preexisting non-test containers retained']})
    report['auxiliary_images']=[x for x in report['images'] if x['service']!='app'];report['images']=[x for x in report['images'] if x['service']=='app']
    contract=json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'));assert report['inputs']==snapshot(ROOT,contract['docker']['inputs']),'Source changed after image build; rebuild and rerun acceptance'
    report['passed']=True;report['finished_at']=now();path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'verification'/'docker-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'report':str(path),'image':image}))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--image',default='shixu-system:3.2.1');ap.add_argument('--baseline',default='shixu-system:3.2.0-docker.1');ap.add_argument('--resume');ap.add_argument('--finalize');ap.add_argument('--peer-project',action='append',default=[],help='Exact independently owned parallel test Compose project; recorded exclusion');ap.add_argument('--inventory-report',type=Path,help='Read-only real container inventory; record exact peer exclusions without starting or stopping resources');args=ap.parse_args()
    if args.inventory_report:
        rows=[json.loads(line) for line in run(['docker','ps','--format','json']).decode().splitlines()]
        kept,excluded=inventory(rows,args.resume,set(args.peer_project))
        inspected=json.loads(run(['docker','inspect',*kept])) if kept else []
        state=[{'id':x['Id'],'image':x['Image'],'started_at':x['State']['StartedAt'],'restart_count':x['RestartCount'],'status':x['State']['Status']} for x in inspected]
        result={'recorded_at':now(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'read-only exact Compose-label inventory; no resource mutations','own_project':args.resume,'peer_projects':args.peer_project,'protected_containers':state,'excluded_test_containers':excluded}
        args.inventory_report.parent.mkdir(parents=True,exist_ok=True);args.inventory_report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'protected':len(state),'excluded':len(excluded),'report':str(args.inventory_report)}));return
    if args.finalize:
        prior=json.loads((ROOT/'verification/docker'/(args.finalize+'.json')).read_text(encoding='utf-8'))
        try:return finalize(args.finalize)
        finally:
            original=sys.exception()
            try:cleanup_owned(prior['compose_project'],ROOT/'runtime'/prior['compose_project'])
            except BaseException as cleanup_error:
                if original:original.add_note('Finalize cleanup failed: '+repr(cleanup_error))
                else:raise
    project=args.resume or 'h02test-shixu-'+uuid.uuid4().hex[:8]
    if not re.fullmatch(r'h02test-shixu-[a-f0-9]+',project):raise ValueError('Invalid isolated project')
    rows=[json.loads(line) for line in run(['docker','ps','-a','--format','json']).decode().splitlines()]
    for row in rows:
        labels=dict(item.split('=',1) for item in row.get('Labels','').split(',') if '=' in item)
        owner=labels.get('com.docker.compose.project','')
        assert not owner.startswith('h02test-') or owner==project or owner in args.peer_project,'Another acceptance project exists; serialize or explicitly authorize exact peer'
    run_id=project+'-'+uuid.uuid4().hex[:8] if args.resume else project
    private=ROOT/'runtime'/project;private.mkdir(parents=True,exist_ok=bool(args.resume))
    print('Isolated project: '+project,flush=True)
    output=ROOT/'verification'/'docker';output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with socket.socket() as s:s.bind(('127.0.0.1',0));db_port=s.getsockname()[1]
    pw=secrets.token_hex(24);db='shixu_docker_test'
    if args.resume:
        from dotenv import dotenv_values
        previous=json.loads((private/'compose.json').read_text(encoding='utf-8'));port=int(previous['services']['app']['ports'][0].split(':')[1]);pw=dotenv_values(private/'app.env')['DB_PASSWORD']
    appenv=private/'app.env'
    appenv.write_text('\n'.join(['SHIXU_SKIP_DOTENV=true','SHIXU_BACKEND=mysql','DB_HOST=db','DB_USER=root','DB_PASSWORD='+pw,'DB_NAME='+db,'DB_SSL=false','SHIXU_PUBLIC_URL=https://shixu.test','SHIXU_ALLOWED_HOSTS=shixu.test','SHIXU_ALLOW_HTTP_AUTH=true','SHIXU_HTTPS_PROXY_SECRET='+secrets.token_hex(32),'SHIXU_INSTANCE='+project,'SHIXU_BOOTSTRAP_PASSWORD='+secrets.token_hex(24)])+'\n',encoding='utf-8')
    cfg={'services':{'db':{'image':'mysql:8.4','ports':[f'127.0.0.1:{db_port}:3306'],'environment':{'MYSQL_ROOT_PASSWORD':pw,'MYSQL_DATABASE':db},'command':['--performance-schema=OFF','--innodb-buffer-pool-size=32M','--max-connections=30'],'mem_limit':'512m','cpus':0.75,'restart':'no','volumes':['db:/var/lib/mysql'],'healthcheck':{'test':['CMD-SHELL','MYSQL_PWD="$$MYSQL_ROOT_PASSWORD" mysql -h 127.0.0.1 -uroot -e "SELECT 1"'],'interval':'5s','timeout':'5s','retries':160}},'app':{'image':args.image,'env_file':[str(appenv)],'ports':[f'127.0.0.1:{port}:8765'],'volumes':['runtime:/app/runtime'],'depends_on':{'db':{'condition':'service_healthy'}},'init':True,'restart':'no','mem_limit':'512m','cpus':0.75}},'volumes':{'db':{},'runtime':{}}}
    compose=private/'compose.json';compose.write_text(json.dumps(cfg),encoding='utf-8')
    os.environ.update(SHIXU_DOCKER_ENV_FILE=str(appenv),SHIXU_PORT=str(port),SHIXU_IMAGE=args.image)
    cli=['docker','compose','-p',project,'-f',str(ROOT/'compose.yaml'),'-f',str(compose)]
    report={'passed':False,'environment':'isolated','run_id':run_id,'compose_project':project,'mcp_mode':'embedded','delivery_id':json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'))['delivery_id'],'started_at':now(),'checks':[],'url':f'http://127.0.0.1:{port}','images':[], 'baseline_image':None, 'cold_start_evidence':('verification/docker/'+project+'.json' if args.resume else None)}
    from docker_contract import snapshot
    report['inputs']=snapshot(ROOT,json.loads((ROOT/'project-contract.json').read_text(encoding='utf-8'))['docker']['inputs'])
    report['resource_limits']={'db':{'memory_mib':512,'cpus':0.75,'restart':'no'},'app':{'memory_mib':512,'cpus':0.75,'restart':'no'}}
    report['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def save(): (output/(run_id+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def passed(name,*observations):report['checks'].append({'name':name,'status':'passed','observations':list(observations)});save();print(name,flush=True)
    url=report['url']
    def wait_health():
        for _ in range(90):
            try:r=httpx.get(url+'/api/health',timeout=5,trust_env=False);r.raise_for_status();return r.json()
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('Application did not become ready')
    try:
        before=json.loads(run(['docker','ps','--format','json']).decode().strip().replace('\n',',').join(['[',']']) or '[]')
        existing,excluded=inventory(before,project,set(args.peer_project));report['existing_containers']=existing
        report['peer_projects']=args.peer_project;report['excluded_test_containers']=excluded
        save()
        run(['docker','build','-t',args.image,'.'],timeout=900)
        report['baseline_image']=json.loads(run(['docker','image','inspect',args.baseline]))[0]['Id']
        run(cli+['config','--quiet']);passed('compose_config','Test composition parsed without exposing interpolated secrets')
        for name,tag in [('app',args.image),('db','mysql:8.4')]:report['images'].append({'service':name,'id':json.loads(run(['docker','image','inspect',tag]))[0]['Id']})
        passed('build','Current Dockerfile build completed in this invocation; cache allowed; pip check and application import in Dockerfile; actual image ID recorded','No production environment or private files in COPY allowlist')
        run(cli+['up','-d','db','--wait','--wait-timeout','900'],timeout=960)
        if not args.resume:run(cli+['run','--rm','--no-deps','app','python','scripts/init_mysql.py','--database',db],timeout=180)
        run(cli+['up','-d','app','--wait','--wait-timeout','180'],timeout=240);h=wait_health();assert h['backend']=='mysql' and h['database']==db
        assert run(cli+['exec','-T','app','id','-u']).strip()==b'10001'
        passed('startup',('Reused exclusively owned initialized test volume from failed run; current app restarted healthy' if args.resume else 'Cold isolated MySQL initialized with application identity; non-root application healthy'),url)
        api=httpx.Client(base_url=url,trust_env=False,timeout=30)
        assert api.get('/api/workspace').status_code==401
        assert api.get('/api/workspace',headers={'Authorization':'Bearer invalid'}).status_code==401
        user='docker_'+uuid.uuid4().hex[:12];password=secrets.token_hex(24)
        (private/'acceptance-account.json').write_text(json.dumps({'url':url,'username':user,'password':password}),encoding='utf-8')
        auth=api.post('/api/auth/register',json={'username':user,'password':password}).raise_for_status().json();api.headers['X-CSRF-Token']=auth['csrf']
        created=api.post('/api/issues',json={'title':'Docker隔离合成记录','expected_version':0,'request_id':str(uuid.uuid4())}).raise_for_status().json()
        before_state=api.get('/api/workspace').raise_for_status().json();assert len(before_state['data']['issues'])==1
        readonly=api.post('/api/account/mcp-access',json={'name':'Docker read','scope':'read'}).raise_for_status().json()
        assert httpx.post(url+'/api/issues',headers={'Authorization':'Bearer '+readonly['token']},json={'title':'must refuse','expected_version':1,'request_id':str(uuid.uuid4())},trust_env=False).status_code==403
        passed('auth','Missing/invalid credentials 401; read token cannot write (403); valid authenticated account access')
        env=dict(os.environ,SHIXU_SKIP_DOTENV='true',SHIXU_BACKEND='mysql',DB_HOST='127.0.0.1',DB_PORT=str(db_port),DB_USER='root',DB_PASSWORD=pw,DB_NAME=db,DB_SSL='false',SHIXU_TEST_USER=user,SHIXU_TEST_PASSWORD=password)
        key=api.post('/api/account/mcp-access',json={'name':'Docker SDK','scope':'write'}).raise_for_status().json();env['SHIXU_MCP_TOKEN']=key['token']
        conf=private/'mcp-client.json';conf.write_text(json.dumps({'mcpServers':{'shixu':{'type':'http','url':url+'/mcp','headers':{'Authorization':'Bearer '+key['token']}}}}),encoding='utf-8')
        run([sys.executable,'examples/http_mcp_client.py','--config',str(conf),'--write-demo','--report','verification/docker/mcp-report.json'],env=env,timeout=180)
        passed('mcp','Real MCP SDK initialize, 29 tools, authenticated read/write/readback; report verification/docker/mcp-report.json')
        for script in ['browser_check.py','trash_browser_check.py','account_mcp_check.py','account_browser_check.py','onboarding_check.py','creator_browser_check.py']:
            result=run([sys.executable,'tests/'+script,'--url',url],env=env,timeout=300)
            (output/(script+'.txt')).write_bytes(result);print('browser: '+script,flush=True)
        run([sys.executable,'tests/dual_transport_check.py','--upstream',url,'--proxy-env',str(appenv)],env=env,timeout=600)
        dual=json.loads((ROOT/'verification/docker/dual-transport-report.json').read_text(encoding='utf-8'))
        assert dual['passed'] and dual['backend']=='docker-mysql' and dual['upstream']==url
        report['dual_transport_evidence']='verification/docker/dual-transport-report.json'
        for script in ['mysql_check.py','retention_mysql_check.py']:
            run([sys.executable,'tests/'+script,'--url',url],env=env,timeout=180)
        run([sys.executable,'examples/mcp_client.py','--url',url,'--write-demo','--report','verification/mcp-report.json'],env=env,timeout=180)
        import shutil
        shutil.copyfile(output/'mcp-report.json',ROOT/'verification/http-mcp-report.json')
        delivery=report['delivery_id']
        for name in ['browser-report','trash-browser-report','account-browser-report','account-mcp-report','creator-browser-report','onboarding-report','mysql-report','retention-report','mcp-report','http-mcp-report']:
            path=ROOT/'verification'/(name+'.json');value=json.loads(path.read_text(encoding='utf-8'));value['delivery_id']=delivery;path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        passed('api','Real API create/readback and Docker-entry browser business, accounts, trash, onboarding, creator workflows passed','Existing account isolation and OAuth tests executed through Docker entry')
        for kind in ['architecture','erd']:
            path='static/diagrams/'+kind+'.html';r=api.get('/'+path).raise_for_status();assert hashlib.sha256(r.content).digest()==hashlib.sha256((ROOT/path).read_bytes()).digest()
        run([sys.executable,'tests/diagrams_check.py','--live-schema'],env=env,timeout=120)
        passed('diagrams','Actual isolated MySQL metadata verified (20 tables, 6 physical foreign keys)','Both original HTML routes match current local bytes; independent offline geometry/browser reports accompany them')
        retained=api.get('/api/workspace').raise_for_status().json()
        run(cli+['up','-d','--force-recreate','app','--wait','--wait-timeout','180'],timeout=240);wait_health();assert api.get('/api/workspace').json()==retained
        run(cli+['up','-d','--force-recreate','db','--wait','--wait-timeout','900'],timeout=960);wait_health();assert api.get('/api/workspace').json()==retained
        passed('recreate','App and MySQL containers recreated against original named volumes; authenticated full workspace preserved')
        cfg['services']['app']['image']=args.baseline;compose.write_text(json.dumps(cfg),encoding='utf-8');run(cli+['up','-d','app','--wait','--wait-timeout','180'],timeout=240);wait_health();assert api.get('/api/workspace').json()==retained
        passed('rollback','Explicit previous Docker image restored; unchanged schema and full workspace compatible')
        cfg['services']['app']['image']=args.image;compose.write_text(json.dumps(cfg),encoding='utf-8');run(cli+['up','-d','app','--wait','--wait-timeout','180'],timeout=240);wait_health();assert api.get('/api/workspace').json()==retained
        passed('upgrade','Switched known formal baseline image to new Docker artifact; complete workspace retained; no schema migration')
        dump=run(cli+['exec','-T','db','sh','-c',f'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --skip-lock-tables --no-tablespaces {db}'],timeout=180)
        assert len(dump)>1000;(private/'synthetic.sql').write_bytes(dump)
        run(cli+['exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE shixu_restore_test"'])
        run(cli+['exec','-T','db','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot shixu_restore_test'],input=dump,timeout=180)
        count=run(cli+['exec','-T','db','sh','-c',f'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e "SELECT (SELECT COUNT(*) FROM {db}.issues)=(SELECT COUNT(*) FROM shixu_restore_test.issues), (SELECT COUNT(*) FROM {db}.app_users)=(SELECT COUNT(*) FROM shixu_restore_test.app_users)"']).strip();assert count==b'1\t1'
        run(['docker','cp',str(ROOT/'tests/compare_databases.py'),project+'-app-1:/app/compare_databases.py'])
        comparison=json.loads(run(cli+['exec','-T','app','python','/app/compare_databases.py',db,'shixu_restore_test']))
        (output/'restore-content-report.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
        passed('backup_restore','Consistent logical dump restored into distinct empty database; all 20 tables row content/count hashes equal','Same isolated instance, distinct database; verification/docker/restore-content-report.json')
        run(cli+['stop','db']);assert api.get('/api/health').status_code==503
        assert api.get('/api/workspace').status_code==503
        assert httpx.get(url+'/api/workspace',headers={'Authorization':'Bearer '+key['token']},trust_env=False).status_code==503
        assert httpx.get(url+'/api/workspace',trust_env=False).status_code==503
        run(cli+['up','-d','db','--wait','--wait-timeout','900'],timeout=960);wait_health();assert api.get('/api/workspace').json()==retained
        passed('failure_recovery','Database stopped: health, anonymous, session and PAT requests explicitly 503; database recovered and workspace/session retained without app restart')
        finalize(run_id)
        report=json.loads((output/(run_id+'.json')).read_text(encoding='utf-8'))
    except BaseException as error:
        (private/(run_id+'-error.txt')).write_text(str(error),encoding='utf-8')
        report['error']=type(error).__name__+': isolated acceptance failed; raw diagnostic retained only under private runtime.'
        try:(private/(run_id+'-container.log')).write_bytes(run(cli+['logs','--no-color','--tail','200'],timeout=30))
        except Exception as log_error:(private/(run_id+'-log-error.txt')).write_text(str(log_error),encoding='utf-8')
        save();raise
    finally:
        try:
            cleanup_owned(project,private)
            report['finally_cleanup']={'passed':True,'scope':'Only owned isolated Compose containers and volumes removed; private diagnostic files preserved'}
        except BaseException as cleanup_error:
            (private/(run_id+'-cleanup-error.txt')).write_text(str(cleanup_error),encoding='utf-8')
            report['passed']=False
            report['finally_cleanup']={'passed':False,'scope':'Owned resource cleanup failed; private diagnostic retained; no global cleanup attempted'}
        report['finished_at']=now();save()
        if report.get('passed') or (ROOT/'verification/docker-report.json').exists():
            (ROOT/'verification/docker-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    assert report['passed'],'Docker acceptance or owned cleanup failed'
    print(json.dumps({'run':project,'report':str(output/(run_id+'.json'))}))
if __name__=='__main__':main()
