"""账号HTTP入口、会话/CSRF、独立MCP令牌和PKCE授权。"""
import base64, hashlib, hmac, json, os, re, secrets, time
from urllib.parse import urlparse, urlencode, parse_qs
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from .accounts import Accounts, digest, public_user
from .account_context import principal, bearer, AccountStore
from .domain import DomainError, require
from .onboarding_auth import normalize_scope, scope_text, metadata, issue_refresh, refresh

class Credentials(BaseModel):
 model_config=ConfigDict(extra='forbid')
 username:str=Field(min_length=2,max_length=40)
 password:str=Field(min_length=1,max_length=128)
 displayName:str=Field(default='',max_length=60)
class Profile(BaseModel):
 displayName:str=Field(min_length=1,max_length=60)
class Password(BaseModel):
 oldPassword:str=Field(max_length=128)
 newPassword:str=Field(min_length=8,max_length=128)
class Access(BaseModel):
 name:str=Field(min_length=1,max_length=60)
 scope:str='write'

COOKIE='shixu_session'
SECURE_COOKIE='__Host-shixu_session'
def session_cookie(request):
 return SECURE_COOKIE if request.url.scheme=='https' else COOKIE

def external_base(request):
 return (os.getenv('SHIXU_PUBLIC_URL') or str(request.base_url)).rstrip('/')

def mcp_connection(request):
 # Prefer the configured HTTPS entry even when the workspace was opened over HTTP.
 configured=os.getenv('SHIXU_PUBLIC_URL','').strip().rstrip('/')
 base=configured if urlparse(configured).scheme=='https' else str(request.base_url).rstrip('/')
 target=urlparse(base)
 return {'url':base+'/mcp','oauthAvailable':target.scheme=='https' or local_host(target.hostname),
         'encrypted':target.scheme=='https'}
def local_host(host):return host in ('localhost','127.0.0.1','::1','testserver')
def oauth_available(request):
 return request.url.scheme=='https' or local_host(request.url.hostname)

def secure_entry(request,oauth=False):
 if oauth:
  require(oauth_available(request),'OAuth登录授权需要HTTPS；当前HTTP地址请在MCP接入中生成访问令牌',400)
 else:
  require(oauth_available(request) or os.getenv('SHIXU_ALLOW_HTTP_AUTH','false').lower()=='true',
          '当前部署未开放HTTP认证，请使用HTTPS或配置SHIXU_ALLOW_HTTP_AUTH=true',400)
def require_session():
 value=principal.get();require(value and value['auth']=='session','请使用网页登录管理账号',401);return value

def install_accounts(app,base):
 accounts=Accounts(base)
 if accounts.mysql:
  # 服务不执行DDL或隐式迁移。
  with accounts.connection() as c:accounts.query(c,'SELECT id FROM app_users LIMIT 1')
 else:
  from .account_store import initialize_sqlite
  initialize_sqlite(base);accounts.initialize()
  if os.getenv('SHIXU_BOOTSTRAP_PASSWORD'):accounts.bootstrap(os.environ['SHIXU_BOOTSTRAP_PASSWORD'])
 app.state.accounts=accounts;app.state.store=AccountStore(base)
 @app.middleware('http')
 async def account_authentication(request,call_next):
  path=request.url.path
  auth=request.headers.get('authorization','');scheme,_,token=auth.partition(' ')
  is_bearer=scheme.lower()=='bearer'
  user=await run_in_threadpool(accounts.authenticate, token if is_bearer else request.cookies.get(session_cookie(request),''), 'bearer' if is_bearer else 'session')
  protected=(path.startswith('/api/') and path not in ('/api/health','/api/auth/login','/api/auth/register')) or path.rstrip('/')=='/mcp'
  try:
   if protected:require(user,'请先登录或提供有效访问令牌',401)
   if protected and path.rstrip('/')=='/mcp':require(is_bearer,'MCP需要访问令牌',401)
   if user and user['auth']=='session' and request.method not in ('GET','HEAD','OPTIONS') and path.startswith('/api/'):
    require(hmac.compare_digest(request.headers.get('x-csrf-token',''),user['csrf']),'会话校验失败，请刷新后重试',403)
   if is_bearer and path.startswith('/api/') and path not in ('/api/health',):
    require(not path.startswith(('/api/account','/api/auth','/api/oauth')),'令牌不能管理账号或授权',403)
    require(user and (user['scope']=='write' or request.method in ('GET','HEAD','OPTIONS')),'当前令牌只允许查询',403)
   oauth_path=path.startswith(('/oauth/','/api/oauth/','/.well-known/oauth-'))
   if protected or path.startswith('/api/auth/') or oauth_path:secure_entry(request,oauth=oauth_path)
  except DomainError as e:
   challenge=('Bearer resource_metadata="'+external_base(request)+'/.well-known/oauth-protected-resource"') if oauth_available(request) else 'Bearer realm="shixu"'
   headers={'WWW-Authenticate':challenge} if e.status==401 else {}
   return JSONResponse({'detail':e.message},status_code=e.status,headers=headers)
  context=principal.set(user);bt=bearer.set(token if is_bearer else '')
  try:return await call_next(request)
  finally:principal.reset(context);bearer.reset(bt)
 def login_response(request,user):
  token,csrf=accounts.session(user)
  result=JSONResponse(dict(user=public_user(user),csrf=csrf))
  result.set_cookie(session_cookie(request),token,max_age=43200,httponly=True,secure=request.url.scheme=='https',samesite='lax',path='/')
  return result
 @app.post('/api/auth/login',summary='账号登录')
 def login(body:Credentials,request:Request):
  return login_response(request,accounts.login(body.username,body.password,request.client.host if request.client else 'local'))
 @app.post('/api/auth/register',summary='注册独立空工作台')
 def register(body:Credentials,request:Request):
  require(os.getenv('SHIXU_ALLOW_REGISTRATION','true').lower()=='true','当前不开放注册',403)
  return login_response(request,accounts.register(body.username,body.displayName or body.username,body.password))
 @app.get('/api/auth/me',summary='当前登录账号')
 def me():
  u=require_session();return dict(user={k:u[k] for k in ('id','username','displayName')},csrf=u['csrf'])
 @app.post('/api/auth/logout',summary='退出并撤销当前会话')
 def logout(request:Request):
  require_session();accounts.logout(request.cookies.get(session_cookie(request),''));response=JSONResponse({'ok':True});response.delete_cookie(session_cookie(request),path='/',secure=request.url.scheme=='https',httponly=True,samesite='lax');return response
 @app.patch('/api/account',summary='修改账号显示名称')
 def profile(body:Profile):return accounts.profile(require_session()['id'],body.displayName)
 @app.post('/api/account/password',summary='修改密码并撤销全部网页登录会话')
 def password(body:Password):
  accounts.change_password(require_session()['id'],body.oldPassword,body.newPassword);return {'ok':True}
 @app.get('/api/account/mcp-access',summary='当前账号的MCP接入列表')
 def access_list(request:Request):
  return {'items':accounts.access_list(require_session()['id']),
          'connection':mcp_connection(request)}
 @app.post('/api/account/mcp-access',summary='发放独立访问令牌（仅本次返回明文）')
 def issue_access(body:Access,request:Request):
  row,token=accounts.issue(require_session()['id'],body.name,body.scope)
  return dict(item=row,token=token,url=mcp_connection(request)['url'])
 @app.post('/api/account/mcp-access/{access_id}/revoke',summary='撤销当前账号的接入')
 def revoke_access(access_id:str):accounts.revoke(require_session()['id'],access_id);return {'ok':True}
 @app.patch('/api/account/mcp-access/{access_id}',summary='重命名当前账号的接入设备')
 def rename_access(access_id:str,body:Profile):return accounts.rename_access(require_session()['id'],access_id,body.displayName)
 install_oauth(app,accounts)
 from fastapi.openapi.utils import get_openapi
 def account_openapi():
  if app.openapi_schema:return app.openapi_schema
  schema=get_openapi(title=app.title,version=app.version,description=app.description,routes=app.routes)
  schema.setdefault('components',{})['securitySchemes']={
   'AccountBearer':dict(type='http',scheme='bearer',description='当前账号的OAuth或PAT访问令牌'),
   'AccountSession':dict(type='apiKey',name=COOKIE,**{'in':'cookie'},description='HTTP网页登录会话；写请求同时需要X-CSRF-Token'),
   'SecureAccountSession':dict(type='apiKey',name=SECURE_COOKIE,**{'in':'cookie'},description='HTTPS独立Secure会话；写请求同时需要X-CSRF-Token')}
  for path,methods in schema['paths'].items():
   if not path.startswith('/api/') or path in ('/api/health','/api/auth/login','/api/auth/register'):continue
   for method,operation in methods.items():
    if method not in ('get','post','patch','delete','put'):continue
    session_only=path.startswith(('/api/auth/','/api/account','/api/oauth/'))
    sessions=[{'AccountSession':[]},{'SecureAccountSession':[]}]
    operation['security']=sessions if session_only else [{'AccountBearer':[]}]+sessions
    if method!='get':operation.setdefault('parameters',[]).append(dict(name='X-CSRF-Token',**{'in':'header'},required=session_only,schema={'type':'string'},description='使用网页登录Cookie时必填；业务Bearer请求无需此字段'))
  app.openapi_schema=schema;return schema
 app.openapi=account_openapi

def install_oauth(app,accounts):
 @app.get('/.well-known/oauth-protected-resource',summary='受保护资源元数据')
 @app.get('/.well-known/oauth-protected-resource/mcp',summary='MCP资源元数据')
 def resource_metadata(request:Request):
  base=external_base(request);return dict(resource=base+'/mcp',authorization_servers=[base],scopes_supported=['read','write'],bearer_methods_supported=['header'])
 @app.get('/.well-known/oauth-authorization-server',summary='授权服务器元数据')
 def server_metadata(request:Request):
  base=external_base(request);return dict(issuer=base,authorization_endpoint=base+'/oauth/authorize',token_endpoint=base+'/oauth/token',registration_endpoint=base+'/oauth/register',response_types_supported=['code'],grant_types_supported=['authorization_code','refresh_token'],token_endpoint_auth_methods_supported=['none'],code_challenge_methods_supported=['S256'],scopes_supported=['read','write'])
 @app.post('/oauth/register',summary='注册公共OAuth客户端')
 async def register_client(request:Request):
  body=await request.json();redirects=body.get('redirect_uris',[])
  require(isinstance(redirects,list) and 0<len(redirects)<=5,'redirect_uris无效',400)
  for uri in redirects:
   require(isinstance(uri,str) and len(uri)<=1000,'回调地址无效',400);u=urlparse(uri)
   require(not u.fragment and not u.username and u.hostname and (u.scheme=='https' or (u.scheme=='http' and local_host(u.hostname))),'回调地址必须为HTTPS或本机回环',400)
  require(body.get('token_endpoint_auth_method','none')=='none','仅支持公共客户端PKCE',400)
  name=str(body.get('client_name','MCP客户端'))[:60];identifier=str(uuid4())
  with accounts.connection() as c:accounts.query(c,'INSERT INTO oauth_clients VALUES (?,?,?,?)',(identifier,name,json.dumps(redirects),int(time.time())))
  return JSONResponse(dict(client_id=identifier,client_name=name,redirect_uris=redirects,token_endpoint_auth_method='none',grant_types=['authorization_code','refresh_token'],response_types=['code']),status_code=201)
 @app.get('/oauth/authorize',summary='开始客户端授权')
 def authorize(request:Request,client_id:str,redirect_uri:str,code_challenge:str,resource:str,response_type:str='code',code_challenge_method:str='S256',scope:str='read',state:str=''):
  require(response_type=='code' and code_challenge_method=='S256' and re.fullmatch('[A-Za-z0-9_-]{43}',code_challenge),'需要S256 PKCE授权码请求',400)
  scope=normalize_scope(scope)
  require(len(state)<=1024,'state无效',400)
  require(resource==external_base(request)+'/mcp','resource不匹配',400)
  with accounts.connection() as c:
   client=accounts.one(c,'SELECT * FROM oauth_clients WHERE id=?',(client_id,))
   require(client and redirect_uri in json.loads(client['redirects']),'客户端或回调地址不匹配',400)
   key=secrets.token_urlsafe(32);payload=json.dumps(dict(client_id=client_id,redirect_uri=redirect_uri,challenge=code_challenge,scope=scope,state=state,resource=resource))
   accounts.query(c,'INSERT INTO oauth_pending VALUES (?,?,?,0)',(digest(key),payload,int(time.time())+600))
  return RedirectResponse('/?authorize='+key,status_code=303)
 def pending(c,key):
  row=accounts.one(c,'SELECT * FROM oauth_pending WHERE digest=?'+(' FOR UPDATE' if accounts.mysql else ''),(digest(key),))
  require(row and not row['used'] and row['expires_at']>time.time(),'授权请求已过期',400)
  data=json.loads(row['payload']);client=accounts.one(c,'SELECT * FROM oauth_clients WHERE id=?',(data['client_id'],));return data,client
 @app.get('/api/oauth/requests/{key}',summary='读取待确认授权')
 def consent_info(key:str):
  require_session()
  with accounts.connection() as c:data,client=pending(c,key)
  return dict(client=client['name'],scope=data['scope'],resource=data['resource'])
 @app.post('/api/oauth/requests/{key}',summary='允许或拒绝客户端授权')
 async def consent(key:str,request:Request):
  user=require_session();body=await request.json()
  with accounts.connection() as c:
   if not accounts.mysql:c.execute('BEGIN IMMEDIATE')
   data,client=pending(c,key);accounts.query(c,'UPDATE oauth_pending SET used=1 WHERE digest=?',(digest(key),))
   query={'state':data['state']}
   if body.get('allow') is True:
    scope=normalize_scope(body.get('scope',data['scope']));require(not (data['scope']=='read' and scope=='write'),'权限范围不得扩大',400)
    code=secrets.token_urlsafe(32)
    accounts.query(c,'INSERT INTO oauth_codes VALUES (?,?,?,?,?,?,?,?,0)',(digest(code),user['id'],data['client_id'],data['redirect_uri'],data['challenge'],scope,data['resource'],int(time.time())+120))
    query['code']=code
   else:query['error']='access_denied'
  return {'redirect':data['redirect_uri']+('&' if '?' in data['redirect_uri'] else '?')+urlencode(query)}
 @app.post('/oauth/token',summary='交换授权码或轮换刷新令牌',openapi_extra={
  'requestBody':{'required':True,'content':{'application/x-www-form-urlencoded':{'schema':{
   'type':'object','required':['grant_type','client_id'],'properties':{
    'grant_type':{'type':'string','enum':['authorization_code','refresh_token']},
    'client_id':{'type':'string'},'code':{'type':'string'},'redirect_uri':{'type':'string'},
    'code_verifier':{'type':'string'},'resource':{'type':'string'},'refresh_token':{'type':'string'},
    'scope':{'type':'string','description':'read、write或空格分隔集合；续期仅能缩小范围'}}}}}},
  'responses':{'200':{'description':'新的访问令牌及轮换刷新令牌；Cache-Control: no-store',
   'content':{'application/json':{'schema':{'type':'object','properties':{
    'access_token':{'type':'string'},'refresh_token':{'type':'string'},'token_type':{'type':'string'},
    'expires_in':{'type':'integer'},'scope':{'type':'string'}}}}}}}})
 async def exchange(request:Request):
  values=parse_qs((await request.body()).decode());v={k:x[0] for k,x in values.items()}
  if v.get('grant_type')=='refresh_token':return JSONResponse(refresh(accounts,v),headers={'Cache-Control':'no-store','Pragma':'no-cache'})
  require(v.get('grant_type')=='authorization_code','unsupported_grant_type',400)
  verifier=v.get('code_verifier','');require(re.fullmatch('[A-Za-z0-9._~-]{43,128}',verifier),'invalid_grant',400)
  with accounts.connection() as c:
   if not accounts.mysql:c.execute('BEGIN IMMEDIATE')
   code=accounts.one(c,'SELECT * FROM oauth_codes WHERE digest=?'+(' FOR UPDATE' if accounts.mysql else ''),(digest(v.get('code','')),))
   challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
   require(code and not code['used'] and code['expires_at']>time.time() and code['client_id']==v.get('client_id') and code['redirect_uri']==v.get('redirect_uri') and code['resource']==v.get('resource') and hmac.compare_digest(code['challenge'],challenge),'invalid_grant',400)
   accounts.query(c,'UPDATE oauth_codes SET used=1 WHERE digest=?',(code['digest'],))
   client=accounts.one(c,'SELECT * FROM oauth_clients WHERE id=?',(code['client_id'],))
   token='sx_'+secrets.token_urlsafe(32);key=str(uuid4());now=int(time.time())
   accounts.query(c,'INSERT INTO account_access VALUES (?,?,?,?,?,?,?,?,0)',(key,code['owner_id'],client['name'],code['scope'],'oauth',digest(token),now,now+3600))
   metadata(accounts,c,key,code['client_id'],code['resource'])
   renewal=issue_refresh(accounts,c,key,code['client_id'],code['resource'])
  return JSONResponse(dict(access_token=token,refresh_token=renewal,token_type='Bearer',expires_in=3600,scope=scope_text(code['scope'])),headers={'Cache-Control':'no-store','Pragma':'no-cache'})
