-- SQLite参考设计1.2.0，当前原型不使用数据库，严禁当成部署迁移脚本。
-- JS issueId -> issue_id, required -> required_for_resolution, 空日期 -> NULL。
-- 状态动作、原因校验、任务处置与history/logs写入由应用在同一事务执行。
PRAGMA foreign_keys=ON;
-- 创建身份参考：正式服务须校验主体，以下为离线原型设计合同。
CREATE TABLE issue(
 id TEXT PRIMARY KEY,
 created_by_actor_id TEXT,creator_name TEXT,initiated_by_person_id TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_name TEXT,model_provider TEXT,
 title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
 description TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT '中' CHECK(priority IN ('高','中','低')),
 tag TEXT NOT NULL DEFAULT '未分类',
 status TEXT NOT NULL DEFAULT '待梳理' CHECK(status IN ('待梳理','待处理','处理中','待验证','已解决','已暂缓','已关闭')),
 next_step TEXT NOT NULL DEFAULT '',success_criteria TEXT NOT NULL DEFAULT '',
 treatment TEXT NOT NULL DEFAULT '',verification_method TEXT NOT NULL DEFAULT '',resolution TEXT NOT NULL DEFAULT '',
 paused_from TEXT NOT NULL DEFAULT '',pause_reason TEXT NOT NULL DEFAULT '',review_date TEXT,
 close_type TEXT NOT NULL DEFAULT '',close_reason TEXT NOT NULL DEFAULT '',duplicate_of TEXT REFERENCES issue(id),
 CHECK(status<>'已解决' OR length(trim(resolution))>0),
 CHECK(status<>'已暂缓' OR (length(trim(pause_reason))>0 AND review_date IS NOT NULL)),
 CHECK(status<>'已关闭' OR length(trim(close_reason))>0)
);
CREATE TABLE task(
 id TEXT PRIMARY KEY,issue_id TEXT REFERENCES issue(id),
 created_by_actor_id TEXT,creator_name TEXT,initiated_by_person_id TEXT,created_via TEXT NOT NULL DEFAULT 'unknown',created_at TEXT,model_name TEXT,model_provider TEXT,

 title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),due TEXT,
 status TEXT NOT NULL DEFAULT '待办' CHECK(status IN ('待办','进行中','已完成','已取消')),
 required_for_resolution INTEGER NOT NULL DEFAULT 1 CHECK(required_for_resolution IN (0,1)),
 cancel_reason TEXT NOT NULL DEFAULT '',CHECK(status<>'已取消' OR length(trim(cancel_reason))>0)
);
CREATE TABLE issue_event(
 id INTEGER PRIMARY KEY,issue_id TEXT NOT NULL REFERENCES issue(id),
 from_state TEXT,to_state TEXT,reason TEXT NOT NULL DEFAULT '',actor TEXT NOT NULL DEFAULT '我',
 message TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX task_issue ON task(issue_id);
CREATE INDEX task_due ON task(due,status);
CREATE INDEX issue_status ON issue(status);
CREATE TRIGGER prevent_early_verification BEFORE UPDATE OF status ON issue
WHEN NEW.status IN ('待验证','已解决') AND EXISTS(SELECT 1 FROM task WHERE issue_id=NEW.id AND required_for_resolution=1 AND status NOT IN ('已完成','已取消'))
BEGIN SELECT RAISE(ABORT,'仍有未完成必要行动'); END;
CREATE TRIGGER resolve_requires_verification BEFORE UPDATE OF status ON issue
WHEN NEW.status='已解决' AND OLD.status NOT IN ('待验证','已解决')
BEGIN SELECT RAISE(ABORT,'先进入待验证'); END;
CREATE TRIGGER close_requires_task_disposition BEFORE UPDATE OF status ON issue
WHEN NEW.status='已关闭' AND EXISTS(SELECT 1 FROM task WHERE issue_id=NEW.id AND status NOT IN ('已完成','已取消'))
BEGIN SELECT RAISE(ABORT,'先处置未完成行动'); END;
-- 其余合法边、暂停恢复目标、重复问题引用、必填字段、必需行动重开联动等按interaction.json状态机在应用层强制验证。
-- issue_event中from/to非空的事件对应history；message供可读logs使用。旧数据导入须保留原状态与日志。

-- 人工跟进独立于自动状态事件；原型issue.followups映射此表。
CREATE TABLE issue_followup(
 id TEXT PRIMARY KEY, issue_id TEXT NOT NULL REFERENCES issue(id),
 content TEXT NOT NULL CHECK(length(trim(content)) BETWEEN 1 AND 5000),
 created_at TEXT NOT NULL, actor TEXT NOT NULL
);
CREATE INDEX ix_followup_issue_time ON issue_followup(issue_id,created_at DESC);
