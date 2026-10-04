-- Multi-account SQLite reference design, NOT a production migration script.
-- Production migration must backup and preserve every existing MySQL record and creation snapshot.
-- Existing workspace assigned user test; user-specified initial password set through hashed provisioning.
PRAGMA foreign_keys=ON;
CREATE TABLE app_user(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE workspace(owner_id TEXT PRIMARY KEY REFERENCES app_user(id),revision INTEGER NOT NULL DEFAULT 0,next_issue_number INTEGER NOT NULL DEFAULT 1,next_task_numbers TEXT NOT NULL DEFAULT '{}');
CREATE TABLE identity_profile(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL,via TEXT NOT NULL,model_name TEXT,model_provider TEXT,PRIMARY KEY(owner_id,id));
CREATE TABLE issue(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,number INTEGER NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT '中',tag TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT '待梳理',workflow_json TEXT NOT NULL DEFAULT '{}',created_by_actor_id TEXT,initiated_by_person_id TEXT,creator_name TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_info TEXT,deleted_at TEXT,PRIMARY KEY(owner_id,id),UNIQUE(owner_id,number));
CREATE TABLE task(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),id TEXT NOT NULL,issue_id TEXT,title TEXT NOT NULL,status TEXT NOT NULL DEFAULT '待办',due TEXT,required_action INTEGER NOT NULL DEFAULT 1,sequence_number INTEGER NOT NULL,number_group TEXT NOT NULL,created_by_actor_id TEXT,initiated_by_person_id TEXT,creator_name TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_info TEXT,deleted_at TEXT,PRIMARY KEY(owner_id,id),UNIQUE(owner_id,number_group,sequence_number),FOREIGN KEY(owner_id,issue_id) REFERENCES issue(owner_id,id));
CREATE TABLE task_dependency(owner_id TEXT NOT NULL,task_id TEXT NOT NULL,dependency_id TEXT NOT NULL,deleted_at TEXT,PRIMARY KEY(owner_id,task_id,dependency_id),FOREIGN KEY(owner_id,task_id) REFERENCES task(owner_id,id),FOREIGN KEY(owner_id,dependency_id) REFERENCES task(owner_id,id));
CREATE TABLE issue_event(owner_id TEXT NOT NULL,issue_id TEXT NOT NULL,id TEXT NOT NULL,event_kind TEXT NOT NULL,content_json TEXT NOT NULL,PRIMARY KEY(owner_id,id),FOREIGN KEY(owner_id,issue_id) REFERENCES issue(owner_id,id));
CREATE TABLE idempotency_request(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,response_json TEXT NOT NULL,PRIMARY KEY(owner_id,request_id));
CREATE TABLE activity(owner_id TEXT NOT NULL REFERENCES workspace(owner_id),revision INTEGER NOT NULL,operation TEXT NOT NULL,resource_id TEXT,actor TEXT,created_at TEXT NOT NULL,PRIMARY KEY(owner_id,revision));
CREATE TABLE auth_session(id_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),expires_at TEXT NOT NULL,revoked_at TEXT);
CREATE TABLE mcp_access(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),label TEXT NOT NULL,method TEXT NOT NULL CHECK(method IN ('oauth','token')),scope TEXT NOT NULL CHECK(scope IN ('read','write')),secret_hash TEXT,client_id TEXT,created_at TEXT NOT NULL,expires_at TEXT,revoked_at TEXT);
CREATE TABLE oauth_authorization_code(code_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES app_user(id),client_id TEXT NOT NULL,redirect_uri TEXT NOT NULL,pkce_challenge TEXT NOT NULL,scope TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
-- Tenant scope from verified session/token, not submitted owner_id. Prevent cross-owner access for get/write/restore/export/audit/MCP.
-- Soft deletion remains mandatory for business records; no physical deletion operations are exposed.

-- AI-ONBOARDING-DESIGN: reference only, NOT a production migration.
-- Existing mcp_access.label supports renaming; display last_seen as a timestamp, never online status.
CREATE TABLE mcp_device_observation(access_id TEXT PRIMARY KEY REFERENCES mcp_access(id),runtime_name TEXT,runtime_version TEXT,skill_version TEXT,last_seen_at TEXT,verification_state TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE oauth_refresh_token(token_hash TEXT PRIMARY KEY,access_id TEXT NOT NULL REFERENCES mcp_access(id),family_id TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT,revoked_at TEXT,replaced_by_hash TEXT);
-- Runtime/Skill observations are client-reported, not verified model-execution provenance.
-- Refresh reuse detection and family revocation must be transactional and account scoped.

-- REQ-090: prototype-only tool registry stored in local identity profiles.
-- Future implementation: owner-scoped stable source ID and display name; no production migration in this change.
