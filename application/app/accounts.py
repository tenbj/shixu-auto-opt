"""账号、会话与MCP授权存储。生产MySQL；SQLite仅隔离测试。"""
import base64, hashlib, hmac, json, os, re, secrets, time
from contextlib import contextmanager
from uuid import uuid4
from .domain import DomainError, require, empty_state
from .store import dumps

TABLES = {
'app_users': "id VARCHAR(36) PRIMARY KEY,username VARCHAR(40) NOT NULL UNIQUE,display_name VARCHAR(60) NOT NULL,password_hash VARCHAR(300) NOT NULL,created_at BIGINT NOT NULL",
'account_sessions': "digest CHAR(64) PRIMARY KEY,owner_id VARCHAR(36) NOT NULL,csrf CHAR(64) NOT NULL,expires_at BIGINT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0",
'account_access': "id VARCHAR(36) PRIMARY KEY,owner_id VARCHAR(36) NOT NULL,name VARCHAR(60) NOT NULL,scope VARCHAR(8) NOT NULL,method VARCHAR(8) NOT NULL,digest CHAR(64) NOT NULL UNIQUE,created_at BIGINT NOT NULL,expires_at BIGINT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0",
'oauth_clients': "id VARCHAR(36) PRIMARY KEY,name VARCHAR(60) NOT NULL,redirects TEXT NOT NULL,created_at BIGINT NOT NULL",
'oauth_codes': "digest CHAR(64) PRIMARY KEY,owner_id VARCHAR(36) NOT NULL,client_id VARCHAR(36) NOT NULL,redirect_uri TEXT NOT NULL,challenge VARCHAR(128) NOT NULL,scope VARCHAR(8) NOT NULL,resource VARCHAR(1000) NOT NULL,expires_at BIGINT NOT NULL,used INTEGER NOT NULL DEFAULT 0",
'oauth_pending': "digest CHAR(64) PRIMARY KEY,payload TEXT NOT NULL,expires_at BIGINT NOT NULL,used INTEGER NOT NULL DEFAULT 0",
'account_login_limits': "bucket CHAR(64) PRIMARY KEY,attempts INTEGER NOT NULL,reset_at BIGINT NOT NULL"
}

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password_hash(password):
 salt=secrets.token_bytes(16)
 return 'scrypt$'+salt.hex()+'$'+hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
def check_password(password,encoded):
 try:
  kind,salt,expected=encoded.split('$')
  return kind=='scrypt' and hmac.compare_digest(hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex(),expected)
 except (ValueError,TypeError):return False

def public_user(row):return dict(id=row['id'],username=row['username'],displayName=row['display_name'])

DUMMY_PASSWORD_HASH=password_hash('unavailable-account')

class Accounts:
 def __init__(self,base):self.base=base;self.mysql=getattr(base,'backend','')=='mysql'
 @contextmanager
 def connection(self):
  with self.base.connect() as c:
   if not self.mysql:c.row_factory=__import__('sqlite3').Row
   yield c
 def query(self,c,sql,args=()):
  cur=c.cursor();cur.execute(sql.replace('?', '%s') if self.mysql else sql,args);return cur
 def initialize(self):
  from .onboarding_auth import EXTRA_TABLES
  tables={**TABLES,**EXTRA_TABLES}
  with self.connection() as c:
   for name,fields in tables.items():
    self.query(c,f'CREATE TABLE IF NOT EXISTS {name} ({fields})'+(' ENGINE=InnoDB' if self.mysql else ''))
    if not self.mysql:self.query(c,f"CREATE TRIGGER IF NOT EXISTS no_delete_{name} BEFORE DELETE ON {name} BEGIN SELECT RAISE(ABORT,'Physical deletion is disabled'); END")
 def one(self,c,sql,args=()):
  row=self.query(c,sql,args).fetchone();return dict(row) if row else None
 def user(self,identifier):
  with self.connection() as c:return self.one(c,'SELECT * FROM app_users WHERE id=?',(identifier,))
 def create_workspace(self,c,identifier,legacy=False):
  if self.mysql:
   if legacy:
    self.query(c,'UPDATE workspace_meta SET owner_id=? WHERE id=1 AND owner_id IS NULL',(identifier,))
    for table in ['issues','tasks','identity_profiles','activity','idempotency_requests']:
     self.query(c,f'UPDATE {table} SET owner_id=? WHERE owner_id IS NULL',(identifier,))
   else:self.query(c,'INSERT INTO workspace_meta (owner_id,application_id,revision,next_issue_number,next_task_numbers) VALUES (?,?,0,1,?)',(identifier,__import__('app.mysql_store',fromlist=['APP_ID']).APP_ID,'{}'))
  else:
   if legacy:
    self.query(c,'INSERT INTO account_workspace SELECT ?,revision,payload FROM workspace WHERE id=1',(identifier,))
    self.query(c,'INSERT INTO account_activity SELECT ?,revision,at,actor,operation,resource_id,payload FROM activity',(identifier,))
    self.query(c,'INSERT INTO account_requests SELECT ?,request_id,fingerprint,response FROM requests',(identifier,))
   else:self.query(c,'INSERT INTO account_workspace VALUES (?,0,?)',(identifier,dumps(empty_state())))
 def bootstrap(self,password):
  with self.connection() as c:
   if self.one(c,'SELECT id FROM app_users WHERE username=?',('test',)):return
   require(bool(password),'首次迁移需要通过私有环境提供初始密码',503)
   self.query(c,'INSERT INTO app_users VALUES (?,?,?,?,?)',('test','test','test',password_hash(password),int(time.time())))
   self.create_workspace(c,'test',True)
 def register(self,username,name,password):
  username=username.strip().lower();require(bool(re.fullmatch(r'[a-z0-9_-]{2,40}',username)),'账号使用2–40位字母、数字、下划线或短横线')
  require(8<=len(password)<=128,'新账号密码至少8位且不超过128位')
  require(0<len(name.strip())<=60,'请输入显示名称')
  with self.connection() as c:
   require(not self.one(c,'SELECT id FROM app_users WHERE username=?',(username,)),'账号已被使用',409)
   identifier=str(uuid4());self.query(c,'INSERT INTO app_users VALUES (?,?,?,?,?)',(identifier,username,name.strip(),password_hash(password),int(time.time())))
   self.create_workspace(c,identifier)
  return self.user(identifier)
 def login(self,username,password,remote):
  now=int(time.time());bucket=digest(remote+'|'+username.strip().lower())
  with self.connection() as c:
   row=self.one(c,'SELECT * FROM account_login_limits WHERE bucket=?',(bucket,))
   require(not row or row['reset_at']<=now or row['attempts']<10,'登录尝试过多，请稍后重试',429)
   if row:self.query(c,'UPDATE account_login_limits SET attempts=?,reset_at=? WHERE bucket=?',(row['attempts']+1 if row['reset_at']>now else 1,row['reset_at'] if row['reset_at']>now else now+600,bucket))
   else:self.query(c,'INSERT INTO account_login_limits VALUES (?,1,?)',(bucket,now+600))
  with self.connection() as c:row=self.one(c,'SELECT * FROM app_users WHERE username=?',(username.strip().lower(),))
  # 相同代价的未知账号校验，避免明显的计时枚举。
  valid=check_password(password,row['password_hash'] if row else DUMMY_PASSWORD_HASH)
  require(row and valid,'账号或密码不正确',401)
  return row
 def session(self,user):
  token=secrets.token_urlsafe(32);csrf=secrets.token_hex(32)
  with self.connection() as c:self.query(c,'INSERT INTO account_sessions VALUES (?,?,?,?,0)',(digest(token),user['id'],csrf,int(time.time())+43200))
  return token,csrf
 def authenticate(self,token,kind):
  if not token or len(token)>256:return None
  with self.connection() as c:
   table='account_sessions' if kind=='session' else 'account_access'
   row=self.one(c,f'SELECT * FROM {table} WHERE digest=? AND revoked=0 AND expires_at>?',(digest(token),int(time.time())))
   if not row:return None
   user=self.one(c,'SELECT * FROM app_users WHERE id=?',(row['owner_id'],))
   if not user:return None
   if kind!='session':self.query(c,'UPDATE access_metadata SET last_seen_at=? WHERE access_id=?',(int(time.time()),row['id']))
   value=public_user(user);value.update(auth=kind,scope='write' if kind=='session' else row['scope'],csrf=row.get('csrf'),access_id=row.get('id'))
   return value
 def logout(self,token):
  with self.connection() as c:self.query(c,'UPDATE account_sessions SET revoked=1 WHERE digest=?',(digest(token),))
 def profile(self,identifier,name):
  require(0<len(name.strip())<=60,'请输入显示名称')
  with self.connection() as c:self.query(c,'UPDATE app_users SET display_name=? WHERE id=?',(name.strip(),identifier))
  return public_user(self.user(identifier))
 def change_password(self,identifier,old,new):
  require(check_password(old,self.user(identifier)['password_hash']),'当前密码不正确',422)
  require(8<=len(new)<=128,'新密码至少8位且不超过128位')
  with self.connection() as c:
   self.query(c,'UPDATE app_users SET password_hash=? WHERE id=?',(password_hash(new),identifier))
   self.query(c,'UPDATE account_sessions SET revoked=1 WHERE owner_id=?',(identifier,))
 def access_list(self,identifier):
  with self.connection() as c:
   rows=self.query(c,'SELECT a.*,m.last_seen_at,m.verified_at,m.runtime_name,m.runtime_version,m.skill_version FROM account_access a LEFT JOIN access_metadata m ON a.id=m.access_id WHERE a.owner_id=? ORDER BY a.created_at DESC',(identifier,)).fetchall()
   result=[]
   for row in rows:
    r=dict(row);renewal=self.one(c,'SELECT MAX(expires_at) AS expiry FROM oauth_refresh_tokens WHERE access_id=? AND revoked=0 AND used=0',(r['id'],))
    expiry=max(r['expires_at'],(renewal or {}).get('expiry') or 0)
    result.append(dict(id=r['id'],name=r['name'],scope=r['scope'],method=r['method'],createdAt=r['created_at'],expiresAt=expiry,accessExpiresAt=r['expires_at'],enabled=not r['revoked'] and expiry>time.time(),revoked=bool(r['revoked']),lastSeenAt=r['last_seen_at'],verifiedAt=r['verified_at'],runtimeName=r['runtime_name'],runtimeVersion=r['runtime_version'],skillVersion=r['skill_version']))
  return result
 def rename_access(self,identifier,key,name):
  require(0<len(name.strip())<=60,'请输入设备名称')
  with self.connection() as c:
   require(self.one(c,'SELECT id FROM account_access WHERE owner_id=? AND id=?',(identifier,key)),'接入不存在',404)
   self.query(c,'UPDATE account_access SET name=? WHERE owner_id=? AND id=?',(name.strip(),identifier,key))
  return {'ok':True}
 def issue(self,identifier,name,scope,method='token'):
  require(scope in ['read','write'] and 0<len(name.strip())<=60,'名称或权限范围无效')
  token='sx_'+secrets.token_urlsafe(32);key=str(uuid4());now=int(time.time());expiry=now+(3600 if method=='oauth' else 31536000)
  with self.connection() as c:
   require(not self.one(c,'SELECT id FROM account_access WHERE owner_id=? AND name=? AND revoked=0 AND expires_at>?',(identifier,name.strip(),now)),'已有同名有效接入',409)
   self.query(c,'INSERT INTO account_access VALUES (?,?,?,?,?,?,?,?,0)',(key,identifier,name.strip(),scope,method,digest(token),now,expiry))
   from .onboarding_auth import metadata
   metadata(self,c,key)
  return dict(id=key,name=name.strip(),scope=scope,method=method,createdAt=now,expiresAt=expiry,enabled=True),token
 def revoke(self,identifier,key):
  with self.connection() as c:
   require(self.one(c,'SELECT id FROM account_access WHERE owner_id=? AND id=?',(identifier,key)),'接入不存在',404)
   from .onboarding_auth import revoke_family
   revoke_family(self,c,key)
