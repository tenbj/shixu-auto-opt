# MySQL 部署与数据边界

本系统默认采用 MySQL 实体存储。当前机器已经自动加载仓库外私有连接文件，服务与 MCP API 入口无需再次配置即可使用。真实凭据不会进入此文档、仓库或 ZIP。

## 本机配置方式

服务启动时先读取项目根 `.env` 中的 `SHIXU_ENV_FILE` 指针，再读取该指针指定的仓库外文件。已有进程环境变量优先。私有文件包含 `SHIXU_BACKEND=mysql`、`DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`、`DB_CHARSET` 和 `DB_SSL`。默认 utf8mb4；SSL 默认开启并验证证书，可指定 `DB_SSL_CA`。

本次实际实例是 MySQL 8.0.28，服务器报告未启用 TLS，因此本机私有配置显式设置 `DB_SSL=false`；没有修改实例的网络、安全或其他数据库配置。

## 新环境初始化

1. 用管理员指定的连接信息，在 MySQL 新建独立的 `shixu_` 前缀数据库，字符集 utf8mb4、排序规则 utf8mb4_bin。创建时不用 `IF NOT EXISTS`，重名应停止，不复用旧库。
2. 将 DB_NAME 设置为该新库，配置仓库外私有文件及 `.env` 指针。
3. 在 system 目录执行 `python scripts/init_mysql.py --database shixu_your_workspace`。脚本检查目标库为空才创建表，非空直接拒绝；不会 DROP、覆盖或自动迁移已有表。
4. 执行 `python scripts/service.py start`，检查 `/api/health` 的 backend 为 mysql，database 为指定的新库。
5. 如需真实集成测试，另外新建并初始化 `shixu_your_workspace_test`，运行 `python scripts/check.py --mysql`。该命令只将测试数据写入新建的 `_test` 库。

运行服务只验证专属库标记，不执行建库或建表。数据库必须为 `shixu_` 前缀且包含正确的应用标记。涉及数据库结构变化需显式迁移，不在每次启动时更改用户库结构。

## 实体与事务

| 表 | 实体/用途 |
|---|---|
| identity_profiles | 通用人/AI身份、工具、模型默认值；类型固定 |
| issues | 问题背景、分类、优先级、状态、解决标准及验证信息 |
| tasks | 行动、关联问题、日期、状态、编号和排序 |
| task_dependencies | 行动间的依赖边 |
| issue_followups | 人工或AI提交的跟进记录 |
| issue_history | 问题状态变更历史 |
| issue_logs | 可读操作日志 |
| workspace_meta | 应用标记、全局版本、编号计数器 |
| activity | 每笔成功业务写入的审计事件 |
| idempotency_requests | 幂等请求指纹及成功响应 |

MySQL 是正式数据源。每次请求从数据库读取实体，执行规则后在单个 InnoDB 事务中更新变更实体、审计、幂等与版本；全局元数据 `SELECT ... FOR UPDATE` 防止并发陈旧写入。内存仅暂存单次请求数据；关闭服务不会丢失持久化记录。

## 迁移与保留

本次从当前系统 SQLite 只读迁入新建 MySQL 库，保留对象ID、编号、依赖、状态历史、审计、幂等请求和全局版本。迁移后完整回读一致，源文件未修改或删除。不会自动读取原型浏览器的 localStorage。

`scripts/migrate_sqlite_to_mysql.py --source runtime/shixu.sqlite3` 仅允许目标 MySQL 工作台完全为空时运行，否则拒绝覆盖；迁移不是日常启动步骤。当前机器已完成，不应再运行。

页面 JSON 导出包含业务对象；完整恢复应使用 MySQL 专属库的备份策略，恢复操作同样只面向专属新库。应用不包含 DROP DATABASE、删除旧库或跨库查询逻辑。

## 从2.1升级到2.2

停止API后执行 python scripts/migrate_trash.py，再重新启动。脚本核对应用身份与shixu专属库，仅追加issues/tasks各3个可空软删除字段和deleted_at索引，可重复运行；业务数据、历史、编号和依赖不删除。正式库迁移前须保留完整备份；DDL自动提交，发生中断可检查报告并重新运行补齐。迁移完成后普通列表不包含回收站，workspace/export仍保留全部记录。

## 2.2.1 禁止物理删除

依赖表新增deleted_at及索引。移除关联保留原行，当前依赖只读取deleted_at IS NULL；重新添加用原主键激活，不删除再插入。migrate_trash.py同时安装9个BEFORE DELETE触发器，任何业务表DELETE都会由数据库拒绝；初始化账户须有TRIGGER权限。应用数据库游标拒绝DELETE/TRUNCATE/DROP/REPLACE语句。没有永久清空入口。数据库管理员的人工DDL维护属于应用外操作，不由页面/API提供。SQLite隔离适配器也有禁止DELETE触发器。

## 2.3.0 创建快照增量迁移

停止API后执行 `python scripts/migrate_creators.py --report runtime/creator-migration.json`，完成后重启。旧于2.2.1的库先执行migrate_trash.py。迁移校验APP_ID，备份完整表结构、旧行和触发器至runtime/backups，追加identity_profiles和issues/tasks的created_by_actor_id、initiated_by_person_id、creator_name、created_via、created_at、model_info，并对所有旧列逐表比对摘要。不会改写旧记录的历史值；来源缺失为unknown，时间为NULL。

identity_profiles增加第10个BEFORE DELETE防护。创建身份及业务对象的引用由领域层在同一锁定事务校验；这些ID是历史逻辑引用（不定义物理FK），ER图明确说明。显示名称、工具、模型JSON独立快照，配置编辑不回写。原有6个物理FK及软删除机制保持有效。

DDL自动提交，中断后可重复运行补齐；脚本没有物理删除或逆向删列功能。回退代码可以保留新列、新表；若需要数据恢复，将备份恢复到独立新库核对并切换DB_NAME，不能用旧备份覆盖新增业务。生产备份只留本机，不进入项目分发。schema与迁移一致性由真实数据库元数据和双图报告核对。
