"""OAuth renewal and device evidence. Secrets are stored only as digests."""
import secrets
import time
from .accounts import digest
from .domain import require

EXTRA_TABLES = {
    'access_metadata': 'access_id VARCHAR(36) PRIMARY KEY,client_id VARCHAR(36),resource VARCHAR(1000),last_seen_at BIGINT,verified_at BIGINT,runtime_name VARCHAR(60),runtime_version VARCHAR(80),skill_version VARCHAR(40)',
    'oauth_refresh_tokens': 'digest CHAR(64) PRIMARY KEY,access_id VARCHAR(36) NOT NULL,client_id VARCHAR(36) NOT NULL,resource VARCHAR(1000) NOT NULL,expires_at BIGINT NOT NULL,used INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0',
}

def normalize_scope(value):
    require(isinstance(value, str) and 0 < len(value) <= 64, 'invalid_scope', 400)
    scopes = set(value.split())
    require(bool(scopes) and scopes <= {'read', 'write'}, 'invalid_scope', 400)
    # Existing write credentials include read access; retain that contract.
    return 'write' if 'write' in scopes else 'read'

def scope_text(scope):
    return 'read write' if scope == 'write' else 'read'

def metadata(accounts, c, key, client_id=None, resource=None):
    accounts.query(c, 'INSERT INTO access_metadata (access_id,client_id,resource) VALUES (?,?,?)', (key, client_id, resource))

def issue_refresh(accounts, c, key, client_id, resource, expires_at=None):
    token = 'sxr_' + secrets.token_urlsafe(32)
    accounts.query(c, 'INSERT INTO oauth_refresh_tokens VALUES (?,?,?,?,?,0,0)',
                   (digest(token), key, client_id, resource, expires_at or int(time.time()) + 2592000))
    return token

def revoke_family(accounts, c, key):
    accounts.query(c, 'UPDATE account_access SET revoked=1 WHERE id=?', (key,))
    accounts.query(c, 'UPDATE oauth_refresh_tokens SET revoked=1 WHERE access_id=?', (key,))

def refresh(accounts, values):
    token = values.get('refresh_token', '')
    require(0 < len(token) <= 256, 'invalid_grant', 400)
    replay = False
    with accounts.connection() as c:
        if not accounts.mysql:
            c.execute('BEGIN IMMEDIATE')
        row = accounts.one(c, 'SELECT * FROM oauth_refresh_tokens WHERE digest=?', (digest(token),))
        require(row and row['client_id'] == values.get('client_id') and
                row['resource'] == values.get('resource', row['resource']), 'invalid_grant', 400)
        lock = ' FOR UPDATE' if accounts.mysql else ''
        access = accounts.one(c, 'SELECT * FROM account_access WHERE id=?' + lock, (row['access_id'],))
        row = accounts.one(c, 'SELECT * FROM oauth_refresh_tokens WHERE digest=?' + lock, (digest(token),))
        require(access and not access['revoked'] and not row['revoked'] and row['expires_at'] > time.time(), 'invalid_grant', 400)
        if row['used']:
            # Commit revocation before returning an error; never roll it back.
            revoke_family(accounts, c, row['access_id'])
            replay = True
        else:
            scope = normalize_scope(values.get('scope', access['scope']))
            require(access['scope'] == 'write' or scope == 'read', 'invalid_scope', 400)
            accounts.query(c, 'UPDATE oauth_refresh_tokens SET used=1 WHERE digest=?', (row['digest'],))
            new_token = 'sx_' + secrets.token_urlsafe(32)
            accounts.query(c, 'UPDATE account_access SET digest=?,expires_at=?,scope=? WHERE id=?',
                           (digest(new_token), int(time.time()) + 3600, scope, access['id']))
            renewal = issue_refresh(accounts, c, access['id'], row['client_id'], row['resource'], row['expires_at'])
    require(not replay, 'invalid_grant', 400)
    return dict(access_token=new_token, refresh_token=renewal, token_type='Bearer', expires_in=3600, scope=scope_text(scope))

def connection_context(accounts, user, runtime_name='', runtime_version='', skill_version='', verified=False):
    key = user.get('access_id')
    evidence = None
    if key:
        with accounts.connection() as c:
            if verified:
                accounts.query(c, 'UPDATE access_metadata SET verified_at=?,runtime_name=?,runtime_version=?,skill_version=? WHERE access_id=?',
                               (int(time.time()), runtime_name, runtime_version, skill_version, key))
            evidence = accounts.one(c, 'SELECT verified_at FROM access_metadata WHERE access_id=?', (key,))
    return dict(account={k: user[k] for k in ('id', 'username', 'displayName')},
                scopes=scope_text(user['scope']).split(), accessId=key, interfaceVersion='3.1.0',
                verifiedAt=evidence['verified_at'] if evidence else None,
                runtime={'name': runtime_name, 'version': runtime_version, 'skillVersion': skill_version, 'source': 'client-declared'},
                verification='authenticated-mcp-call' if verified else 'authenticated-api-read')
