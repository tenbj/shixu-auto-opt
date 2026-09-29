-- 拾序：SQLite 参考设计，当前 HTML 使用 localStorage，此脚本不连接任何数据库。
-- API issueId -> task.issue_id; due为空字符串 -> SQL NULL; logs -> issue_event按created_at,id排序。
PRAGMA foreign_keys = ON;
CREATE TABLE issue (
 id TEXT PRIMARY KEY,
 title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
 description TEXT NOT NULL DEFAULT '',
 priority TEXT NOT NULL DEFAULT '中' CHECK(priority IN ('高','中','低')),
 tag TEXT NOT NULL DEFAULT '未分类',
 status TEXT NOT NULL DEFAULT '待梳理' CHECK(status IN ('待梳理','处理中','已解决')),
 resolution TEXT NOT NULL DEFAULT '',
 CHECK(status <> '已解决' OR length(trim(resolution)) > 0)
);
CREATE TABLE task (
 id TEXT PRIMARY KEY,
 issue_id TEXT REFERENCES issue(id) ON DELETE RESTRICT,
 title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
 due TEXT,
 status TEXT NOT NULL DEFAULT '待办' CHECK(status IN ('待办','进行中','已完成'))
);
CREATE INDEX task_issue ON task(issue_id);
CREATE INDEX task_due_status ON task(due,status);
CREATE TABLE issue_event (
 id INTEGER PRIMARY KEY,
 issue_id TEXT NOT NULL REFERENCES issue(id) ON DELETE RESTRICT,
 message TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER prevent_early_resolve BEFORE UPDATE OF status ON issue
WHEN NEW.status = '已解决' AND EXISTS(SELECT 1 FROM task WHERE issue_id=NEW.id AND status<>'已完成')
BEGIN SELECT RAISE(ABORT,'仍有未完成行动'); END;
CREATE TRIGGER reject_new_task_on_closed_issue BEFORE INSERT ON task
WHEN NEW.status <> '已完成' AND EXISTS(SELECT 1 FROM issue WHERE id=NEW.issue_id AND status='已解决')
BEGIN SELECT RAISE(ABORT,'先重新打开问题'); END;
CREATE TRIGGER reopen_issue_with_task AFTER UPDATE OF status ON task
WHEN NEW.status <> '已完成' AND NEW.issue_id IS NOT NULL
BEGIN UPDATE issue SET status='处理中' WHERE id=NEW.issue_id AND status='已解决'; END;
-- 创建/修改关联时由应用在事务内同步旧、新问题状态（待梳理/处理中）并写入事件。
-- 禁止把未完成行动重新关联到已解决问题；重新打开同一问题的已完成行动则允许联动。
CREATE TRIGGER reject_move_to_closed_issue BEFORE UPDATE OF issue_id ON task
WHEN NEW.issue_id IS NOT OLD.issue_id AND NEW.status<>'已完成'
 AND EXISTS(SELECT 1 FROM issue WHERE id=NEW.issue_id AND status='已解决')
BEGIN SELECT RAISE(ABORT,'先重新打开目标问题'); END;
