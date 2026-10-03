-- 仅在专门新建的拾序数据库中执行。应用运行时不会自动创建或覆盖已有表。
CREATE TABLE workspace_meta (
  id TINYINT PRIMARY KEY,
  application_id VARCHAR(80) NOT NULL,
  revision BIGINT NOT NULL,
  next_issue_number BIGINT NOT NULL,
  next_task_numbers JSON NOT NULL
) ENGINE=InnoDB;

CREATE TABLE identity_profiles (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(60) NOT NULL,
  kind VARCHAR(8) NOT NULL,
  via VARCHAR(32) NOT NULL,
  model_name VARCHAR(160) NOT NULL,
  model_provider VARCHAR(80) NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  updated_at VARCHAR(40) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE issues (
  id VARCHAR(36) PRIMARY KEY,
  number BIGINT NOT NULL UNIQUE,
  title VARCHAR(160) NOT NULL,
  description TEXT NOT NULL,
  priority VARCHAR(8) NOT NULL,
  tag VARCHAR(40) NOT NULL,
  status VARCHAR(16) NOT NULL,
  resolution TEXT NOT NULL,
  next_step TEXT NOT NULL,
  success_criteria TEXT NOT NULL,
  treatment TEXT NOT NULL,
  verification_method TEXT NOT NULL,
  pause_reason TEXT NOT NULL,
  review_date VARCHAR(10) NOT NULL,
  paused_from VARCHAR(16) NOT NULL,
  close_reason TEXT NOT NULL,
  close_type VARCHAR(40) NOT NULL,
  duplicate_of VARCHAR(36) NOT NULL,
  created_by_actor_id VARCHAR(36) NULL,
  initiated_by_person_id VARCHAR(36) NULL,
  creator_name VARCHAR(60) NULL,
  created_via VARCHAR(32) NOT NULL DEFAULT 'unknown',
  created_at VARCHAR(40) NULL,
  model_info JSON NULL,
  deleted_at VARCHAR(40) NULL,
  deletion_batch VARCHAR(36) NULL,
  deleted_with_issue VARCHAR(36) NULL,
  INDEX idx_issue_deleted(deleted_at),
  INDEX idx_issue_status(status),
  INDEX idx_issue_tag(tag)
) ENGINE=InnoDB;

CREATE TABLE tasks (
  id VARCHAR(36) PRIMARY KEY,
  row_order BIGINT NOT NULL AUTO_INCREMENT UNIQUE,
  title VARCHAR(160) NOT NULL,
  issue_id VARCHAR(36) NULL,
  due VARCHAR(10) NOT NULL,
  status VARCHAR(16) NOT NULL,
  required_action BOOLEAN NOT NULL,
  cancel_reason TEXT NOT NULL,
  order_index BIGINT NOT NULL,
  number_group VARCHAR(40) NOT NULL,
  sequence_number BIGINT NOT NULL,
  created_by_actor_id VARCHAR(36) NULL,
  initiated_by_person_id VARCHAR(36) NULL,
  creator_name VARCHAR(60) NULL,
  created_via VARCHAR(32) NOT NULL DEFAULT 'unknown',
  created_at VARCHAR(40) NULL,
  model_info JSON NULL,
  deleted_at VARCHAR(40) NULL,
  deletion_batch VARCHAR(36) NULL,
  deleted_with_issue VARCHAR(36) NULL,
  INDEX idx_task_deleted(deleted_at),
  UNIQUE KEY unique_task_number(number_group,sequence_number),
  FOREIGN KEY(issue_id) REFERENCES issues(id),
  INDEX idx_task_status(status)
) ENGINE=InnoDB;

CREATE TABLE task_dependencies (
  task_id VARCHAR(36) NOT NULL,
  dependency_id VARCHAR(36) NOT NULL,
  position_number INT NOT NULL,
  deleted_at VARCHAR(40) NULL,
  INDEX idx_dependency_deleted(deleted_at),
  PRIMARY KEY(task_id,dependency_id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(dependency_id) REFERENCES tasks(id)
) ENGINE=InnoDB;

CREATE TABLE issue_followups (
  id VARCHAR(36) PRIMARY KEY,
  issue_id VARCHAR(36) NOT NULL,
  content TEXT NOT NULL,
  event_at VARCHAR(40) NOT NULL,
  actor VARCHAR(80) NOT NULL,
  FOREIGN KEY(issue_id) REFERENCES issues(id),
  INDEX idx_followup_time(issue_id,event_at)
) ENGINE=InnoDB;

CREATE TABLE issue_history (
  id VARCHAR(36) PRIMARY KEY,
  issue_id VARCHAR(36) NOT NULL,
  position_number INT NOT NULL,
  from_status VARCHAR(16) NOT NULL,
  to_status VARCHAR(16) NOT NULL,
  reason TEXT NOT NULL,
  event_at VARCHAR(40) NOT NULL,
  actor VARCHAR(80) NOT NULL,
  FOREIGN KEY(issue_id) REFERENCES issues(id),
  UNIQUE KEY unique_history_position(issue_id,position_number)
) ENGINE=InnoDB;

CREATE TABLE issue_logs (
  issue_id VARCHAR(36) NOT NULL,
  position_number INT NOT NULL,
  content TEXT NOT NULL,
  PRIMARY KEY(issue_id,position_number),
  FOREIGN KEY(issue_id) REFERENCES issues(id)
) ENGINE=InnoDB;

CREATE TABLE activity (
  revision BIGINT PRIMARY KEY,
  event_at VARCHAR(40) NOT NULL,
  actor VARCHAR(80) NOT NULL,
  operation VARCHAR(80) NOT NULL,
  resource_id VARCHAR(36) NULL,
  payload JSON NOT NULL
) ENGINE=InnoDB;

CREATE TABLE idempotency_requests (
  request_id VARCHAR(120) PRIMARY KEY,
  fingerprint CHAR(64) NOT NULL,
  response JSON NOT NULL
) ENGINE=InnoDB;

-- 数据库层禁止物理DELETE；业务记录通过删除时间标识失效。
CREATE TRIGGER shixu_no_delete_workspace_meta BEFORE DELETE ON workspace_meta FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_issues BEFORE DELETE ON issues FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_tasks BEFORE DELETE ON tasks FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_task_dependencies BEFORE DELETE ON task_dependencies FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_issue_followups BEFORE DELETE ON issue_followups FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_issue_history BEFORE DELETE ON issue_history FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_issue_logs BEFORE DELETE ON issue_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_activity BEFORE DELETE ON activity FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
CREATE TRIGGER shixu_no_delete_idempotency_requests BEFORE DELETE ON idempotency_requests FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';

CREATE TRIGGER shixu_no_delete_identity_profiles BEFORE DELETE ON identity_profiles FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical deletion is disabled';
