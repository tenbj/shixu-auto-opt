"""Generate offline diagrams from the authoritative DDL; never read business records."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'static' / 'diagrams'
OUT.mkdir(parents=True, exist_ok=True)

INFO = {
    'identity_profiles': ('IP', '记录身份', 750, 1470, ['id','name','kind','via','model_name'], '通用人/AI身份。问题和行动的created_by_actor_id、initiated_by_person_id是经领域校验的历史逻辑引用，不是物理外键；创建名称、来源、模型保存独立快照，改名或改默认值不追溯更新。'),
    'issues': ('IS', '问题', 750, 70, ['id','number','title','status','created_via','creator_name','model_info','deleted_at'], '七状态问题工作流；软删除保留全部历史与编号。同批恢复；duplicate_of / deleted_with_issue 是逻辑引用，非数据库外键。'),
    'tasks': ('TA', '行动', 750, 710, ['id','issue_id','title','status','created_via','creator_name','model_info','deleted_at'], '软删除保留行动与依赖；随问题删除须同批恢复。deleted_with_issue 为逻辑引用，无新增外键。'),
    'issue_followups': ('FU', '跟进记录', 50, 70, ['id','issue_id','content','event_at'], '按问题追加跟进，actor 只是审计标签。'),
    'issue_history': ('HI', '状态历史', 50, 710, ['id','issue_id','position_number','from_status','to_status'], '问题内的状态变迁按 position_number 唯一排序。'),
    'issue_logs': ('LG', '问题日志', 1450, 70, ['issue_id','position_number','content'], '问题 ID 与位置序号组成联合主键。'),
    'task_dependencies': ('TD', '行动依赖', 1450, 710, ['task_id','dependency_id','position_number','deleted_at'], 'task_id 是当前行动，dependency_id 是前置行动；同一对任务保留原行；deleted_at标记已移除关系，可重新激活。'),
    'workspace_meta': ('WM', '工作台元数据', 50, 1120, ['id','application_id','revision','next_issue_number'], 'id=1 单行；保存全局版本及编号计数，写事务对该行加锁。无物理外键。'),
    'activity': ('AC', '操作审计', 750, 1120, ['revision','event_at','operation','resource_id'], '按 revision 记录操作；resource_id 为多态逻辑引用，非物理外键。'),
    'idempotency_requests': ('IR', '幂等请求', 1450, 1120, ['request_id','fingerprint','response'], '持久化请求指纹和响应；相同请求重试返回原结果。无物理外键。'),
}
DESCRIPTIONS = {
 'name':'自定义身份名称','kind':'person人 / agent AI','via':'手动或AI工具','model_name':'AI身份的默认模型名称/ID','model_provider':'AI身份的默认模型提供方','updated_at':'身份最后编辑的服务器UTC时间','created_by_actor_id':'实际提交身份的历史逻辑引用；非FK','initiated_by_person_id':'AI代录的人类发起者历史逻辑引用；非FK','creator_name':'创建人名称快照；不随身份改名改变','created_via':'创建来源快照；历史缺失为unknown','created_at':'服务器UTC创建时间；迁移历史未知为NULL','model_info':'JSON {name,provider}；手动或历史未知为NULL；AI空值表示未提供',
 'deleted_at':'软删除时间；NULL 为有效记录', 'deletion_batch':'删除批次 UUID；问题与当次关联行动一致', 'deleted_with_issue':'随删除问题的逻辑标识；非 FK；恢复时清空',
 'id':'实体标识；元数据表固定为 1', 'number':'固定问题编号', 'title':'标题', 'description':'问题背景',
 'priority':'优先级','tag':'分类标签','status':'当前状态，由领域规则约束', 'resolution':'验证结论',
 'next_step':'下一步','success_criteria':'成功标准','treatment':'处理说明','verification_method':'验证方法',
 'pause_reason':'暂缓原因','review_date':'复查日期；字符串','paused_from':'暂缓前状态','close_reason':'关闭原因',
 'close_type':'关闭类型','duplicate_of':'重复问题逻辑引用；无关联时为空字符串；非 FK',
 'row_order':'插入排序，自增唯一值','issue_id':'所属问题','due':'计划日期；字符串',
 'required_action':'是否本轮必要行动','cancel_reason':'取消原因','order_index':'组内展示排序',
 'number_group':'行动编号分组','sequence_number':'分组内固定编号','task_id':'当前行动',
 'dependency_id':'前置行动','position_number':'实体内的顺序位置','content':'正文',
 'event_at':'事件时间；字符串','actor':'审计标签，不是用户账号外键','from_status':'原状态','to_status':'目标状态',
 'reason':'流转原因','application_id':'应用身份标记','revision':'全局版本 / 审计事件号',
 'next_issue_number':'下一个问题编号','next_task_numbers':'各组行动编号计数 JSON',
 'operation':'操作类型','resource_id':'多态资源逻辑引用；非 FK','payload':'请求载荷 JSON',
 'request_id':'幂等请求标识','fingerprint':'请求 SHA-256 指纹','response':'已提交响应 JSON',
}


def model():
    source = (ROOT / 'data' / 'mysql-schema.sql').read_text(encoding='utf-8')
    tables, relations = [], []
    for name, body in re.findall(r'CREATE TABLE (\w+) \((.*?)\) ENGINE=InnoDB;', source, re.S):
        alias, title, x, y, core, note = INFO[name]
        fields = []
        for line in body.splitlines():
            match = re.match(r'\s*(\w+)\s+((?:VARCHAR|CHAR)\(\d+\)|BIGINT|TINYINT|INT|TEXT|JSON|BOOLEAN)(.*)', line.strip().rstrip(','))
            if not match:
                continue
            field, dtype, rest = match.groups()
            fields.append(dict(name=field, type=dtype, nullable='NOT NULL' not in rest and 'PRIMARY KEY' not in rest,
                               keys=[k for k, token in [('PK','PRIMARY KEY'),('UQ','UNIQUE'),('AI','AUTO_INCREMENT')] if token in rest], description=DESCRIPTIONS.get(field,'')))
        constraints=[]
        for kind, columns in re.findall(r'(PRIMARY KEY|UNIQUE KEY(?: \w+)?)\(([^)]+)\)', body):
            cols=[c.strip() for c in columns.split(',')]
            label='PK' if kind=='PRIMARY KEY' else 'UQ'
            constraints.append(label+' ('+', '.join(cols)+')')
            for f in fields:
                if f['name'] in cols and label not in f['keys']:
                    f['keys'].append(label)
                    if label=='PK': f['nullable']=False
        for fk, parent, pk in re.findall(r'FOREIGN KEY\((\w+)\) REFERENCES (\w+)\((\w+)\)',body):
            f=next(f for f in fields if f['name']==fk)
            f['keys'].append('FK')
            relations.append(dict(id=f'{alias}_{fk}',parent=INFO[parent][0],child=alias,pk=pk,fk=fk,optional=f['nullable']))
        tables.append(dict(id=alias,name=name,title=title,x=x,y=y,core=core,fields=fields,note=note,constraints=constraints))
    return dict(tables=tables,relations=relations)


def main():
    data=model()
    erd=(ROOT / 'scripts' / 'erd-template.html').read_text(encoding='utf-8')
    (OUT/'erd.html').write_text(erd.replace('__MODEL__',json.dumps(data,ensure_ascii=False)),encoding='utf-8')
    (OUT/'architecture.html').write_text((ROOT/'scripts'/'architecture-template.html').read_text(encoding='utf-8'),encoding='utf-8')
    print(f'ER model: {len(data["tables"])} entities, {len(data["relations"])} physical foreign keys')


if __name__=='__main__':
    main()
