"""拾序业务规则。所有修改在 Store 的 SQLite 事务中执行。"""
from datetime import datetime, date, timezone, timedelta
from uuid import uuid4

ISSUE_STATES = ['待梳理', '待处理', '处理中', '待验证', '已解决', '已暂缓', '已关闭']
OPEN = ISSUE_STATES[:4]
TASK_STATES = ['待办', '进行中', '已完成', '已取消']


class DomainError(Exception):
    def __init__(self, message, status=422):
        self.message, self.status = message, status


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def require(condition, message, status=422):
    if not condition:
        raise DomainError(message, status)


def text(value, label, maximum=5000, required=False):
    require(isinstance(value, str), label + '必须是文本')
    value = value.strip()
    require(len(value) <= maximum and (bool(value) or not required), label + '为空或超过长度限制')
    return value


def valid_date(value):
    require(isinstance(value, str), '日期必须是文本')
    if value:
        try:
            require(date.fromisoformat(value).isoformat() == value, '日期格式应为 YYYY-MM-DD')
        except (ValueError, TypeError):
            raise DomainError('日期无效')
    return value


def empty_state():
    return dict(version=1, schemaVersion=2, nextIssueNumber=1, nextTaskNumbers={}, issues=[], tasks=[])


def get(state, kind, identifier):
    item = next((x for x in state[kind] if x['id'] == identifier), None)
    require(item is not None, '记录不存在', 404)
    return item


def linked(state, identifier):
    return [x for x in state['tasks'] if x['issueId'] == identifier]


def incomplete(task):
    return task['status'] not in ['已完成', '已取消']


def remaining(state, identifier):
    return [x for x in linked(state, identifier) if x['required'] and incomplete(x)]


def log(issue, message):
    if issue:
        issue['logs'].append(now() + ' · ' + message)


def transition(issue, target, reason, actor):
    issue['history'].append(dict(id=str(uuid4()), **{'from': issue['status']}, to=target, reason=reason, at=now(), actor=actor))
    log(issue, issue['status'] + ' → ' + target + '：' + reason)
    issue['status'] = target


def number_task(state, task):
    group = str(get(state, 'issues', task['issueId'])['number']) if task['issueId'] else '独立'
    if task.get('numberGroup') != group:
        sequence = state['nextTaskNumbers'].get(group, 1)
        task.update(numberGroup=group, sequence=sequence)
        state['nextTaskNumbers'][group] = sequence + 1


def create_issue(state, values, actor):
    issue = dict(id=str(uuid4()), number=state['nextIssueNumber'], status='待梳理', logs=[], history=[], followups=[])
    for key in ['description', 'resolution', 'nextStep', 'successCriteria', 'treatment', 'verificationMethod',
                'pauseReason', 'reviewDate', 'pausedFrom', 'closeReason', 'closeType', 'duplicateOf']:
        issue[key] = ''
    update_issue(state, issue, values, actor)
    state['nextIssueNumber'] += 1
    state['issues'].insert(0, issue)
    log(issue, '记录问题：默认待梳理')
    return issue


def update_issue(state, issue, values, actor):
    allowed = {'title', 'description', 'priority', 'tag'}
    require(set(values) <= allowed, '存在不允许直接修改的问题字段')
    if 'title' in values:
        issue['title'] = text(values['title'], '标题', 160, True)
    require(bool(issue.get('title')), '标题必填')
    for key, maximum in [('description', 5000), ('tag', 40)]:
        if key in values:
            issue[key] = text(values[key], key, maximum)
    issue['tag'] = issue.get('tag') or '未分类'
    priority = values.get('priority', issue.get('priority', '中'))
    require(priority in ['高', '中', '低'], '优先级无效')
    issue['priority'] = priority
    log(issue, '更新问题内容')
    return issue


def transition_issue(state, issue, values, actor):
    action = values['action']
    allowed = {'triage': ['待梳理'], 'start': ['待处理'], 'verify': OPEN[:3], 'resolve': ['待验证'],
               'reject': ['待验证'], 'pause': OPEN, 'resume': ['已暂缓'], 'close-issue': OPEN + ['已暂缓'],
               'reopen': ['已解决', '已关闭'], 'retriage': ['待处理']}
    require(issue['status'] in allowed.get(action, []), '当前问题状态不允许此操作', 409)
    v = {k: text(value, k) for k, value in values.items() if isinstance(value, str)}
    reason = v.get('reason', '')
    targets = dict(triage='待处理', start='处理中', verify='待验证', resolve='已解决', reject='处理中',
                   pause='已暂缓', resume=issue['pausedFrom'] if issue['pausedFrom'] in OPEN else '待梳理',
                   reopen='待梳理' if issue['status'] == '已关闭' else '处理中', retriage='待梳理')
    targets['close-issue'] = '已关闭'
    if action in ['pause', 'close-issue', 'reject', 'reopen', 'retriage']:
        require(bool(reason), '请填写原因')
    if action == 'triage':
        for key in ['nextStep', 'successCriteria']:
            issue[key] = text(v.get(key, ''), key, required=True)
    if action == 'start':
        require(bool(issue['nextStep'] and issue['successCriteria']), '请先完成梳理')
    if action == 'verify':
        require(issue['status'] == '处理中' or not linked(state, issue['id']), '请先开始处理')
        require(not remaining(state, issue['id']), '还有未完成的必要行动')
        for key in ['successCriteria', 'treatment', 'verificationMethod']:
            issue[key] = text(v.get(key, ''), key, required=True)
    if action == 'resolve':
        require(not remaining(state, issue['id']), '还有未完成的必要行动')
        issue['resolution'] = text(v.get('resolution', ''), '验证结论与依据', required=True)
        reason = issue['resolution']
    if action == 'pause':
        review = valid_date(v.get('reviewDate', ''))
        require(bool(review) and review >= today(), '回看日期不能早于今天（Asia/Shanghai）')
        issue.update(pausedFrom=issue['status'], pauseReason=reason, reviewDate=review)
    if action == 'resume' and targets['resume'] == '待验证' and remaining(state, issue['id']):
        targets['resume'] = '处理中'
    if action == 'close-issue':
        close_type = v.get('closeType')
        require(close_type in ['不再处理', '重复问题', '问题不成立', '收益不足'], '关闭类型无效')
        duplicate = v.get('duplicateOf', '')
        if close_type == '重复问题':
            require(duplicate != issue['id'], '不能关联自己')
            get(state, 'issues', duplicate)
        pending = [t for t in linked(state, issue['id']) if incomplete(t)]
        policy = v.get('taskPolicy')
        require(not pending or policy in ['detach', 'cancel'], '请选择未完成行动的处置方式')
        if policy == 'detach':
            require(not any(has_edges(state, t) for t in pending), '请先解除行动依赖或选择取消')
        issue.update(closeReason=reason, closeType=close_type, duplicateOf=duplicate if close_type == '重复问题' else '')
        for task in pending:
            if policy == 'detach':
                task['issueId'] = None
                number_task(state, task)
            else:
                task.update(status='已取消', cancelReason='问题关闭：' + reason)
    transition(issue, targets[action], reason or {'triage': '已明确下一步和解决标准', 'start': '开始执行方案',
               'verify': '已提交处理说明与验证方式', 'resume': '主动恢复处理'}.get(action, action), actor)
    return issue


def has_edges(state, task):
    return bool(task['dependsOn'] or any(task['id'] in t['dependsOn'] for t in state['tasks']))


def started_dependents(state, task):
    return any(task['id'] in t['dependsOn'] and t['status'] in ['进行中', '已完成'] for t in state['tasks'])


def create_task(state, values, actor):
    task = dict(id=str(uuid4()), status='待办', issueId=None, due='', required=True, cancelReason='', dependsOn=[], order=0)
    update_task(state, task, values, actor, new=True)
    task['order'] = max([-1] + [t['order'] for t in state['tasks'] if t['issueId'] == task['issueId']]) + 1
    state['tasks'].insert(0, task)
    return task


def update_task(state, task, values, actor, new=False):
    require(set(values) <= {'title', 'issueId', 'due', 'required'}, '存在不允许直接修改的行动字段')
    if 'title' in values:
        task['title'] = text(values['title'], '标题', 160, True)
    require(bool(task.get('title')), '标题必填')
    issue_id = values.get('issueId', task['issueId']) or None
    issue = get(state, 'issues', issue_id) if issue_id else None
    required = values.get('required', task['required'])
    require(type(required) is bool, 'required 必须是布尔值')
    changed_link = issue_id != task['issueId']
    if issue and (new or changed_link):
        require(issue['status'] in OPEN, '请先恢复或重新打开目标问题')
    if changed_link and not new:
        require(not has_edges(state, task), '请先解除前置和后续依赖，再修改关联问题')
        if issue and task['status'] in ['进行中', '已完成']:
            require(issue['status'] != '待梳理', '请先梳理目标问题')
            if issue['status'] == '待处理':
                transition_issue(state, issue, {'action': 'start'}, actor)
    if issue and issue['status'] in ['已暂缓', '已关闭'] and required and not task['required']:
        raise DomainError('请先恢复问题，再指定必要行动')
    if 'due' in values:
        task['due'] = valid_date(values['due'])
    task.update(issueId=issue_id, required=required)
    number_task(state, task)
    if issue and required and incomplete(task) and issue['status'] in ['待验证', '已解决']:
        transition(issue, '处理中', '新增或重新指定必要行动，需要再次验证', actor)
    log(issue, ('新增' if new else '更新') + '行动：' + task['title'])
    return task


def transition_task(state, task, values, actor):
    target = values['status']
    require(target in TASK_STATES, '行动状态无效')
    require(target != task['status'], '行动已在目标状态', 409)
    allowed = {'待办': ['进行中', '已完成', '已取消'], '进行中': ['待办', '已完成', '已取消'],
               '已完成': ['待办'], '已取消': ['待办']}
    require(target in allowed[task['status']], '请先重新打开行动', 409)
    issue = get(state, 'issues', task['issueId']) if task['issueId'] else None
    require(not issue or issue['status'] not in ['已暂缓', '已关闭'], '请先恢复或重新打开问题')
    if target in ['进行中', '已完成']:
        require(all(get(state, 'tasks', key)['status'] == '已完成' for key in task['dependsOn']), '请先完成前置行动')
        require(not issue or issue['status'] != '待梳理', '请先完成问题梳理')
        if issue and issue['status'] == '待处理':
            transition_issue(state, issue, {'action': 'start'}, actor)
    if task['status'] == '已完成' or target == '已取消':
        require(not started_dependents(state, task), '请先将已开始的后续行动退回待办')
    if target == '已取消':
        task['cancelReason'] = text(values.get('reason', ''), '取消原因', required=True)
    task['status'] = target
    if issue and task['required'] and incomplete(task) and issue['status'] in ['待验证', '已解决']:
        transition(issue, '处理中', '必要行动重新打开，需要再次验证', actor)
    log(issue, '行动“' + task['title'] + '”更新为' + target)
    return task


def dependencies(state, task, values, actor):
    deps = values['dependsOn']
    require(len(deps) == len(set(deps)), '依赖不能重复')
    require(task['id'] not in deps, '行动不能依赖自己')
    for key in deps:
        require(get(state, 'tasks', key)['issueId'] == task['issueId'], '前置行动必须属于同一问题')
    task['dependsOn'] = deps
    visiting, visited = set(), set()

    def visit(key):
        require(key not in visiting, '依赖形成循环')
        if key in visited:
            return
        visiting.add(key)
        for child in get(state, 'tasks', key)['dependsOn']:
            visit(child)
        visiting.remove(key)
        visited.add(key)

    for item in state['tasks']:
        visit(item['id'])
    if task['status'] in ['进行中', '已完成']:
        require(all(get(state, 'tasks', key)['status'] == '已完成' for key in deps), '进行中或已完成行动不能依赖未完成行动')
    return task


def reorder(state, task, values, actor):
    target = get(state, 'tasks', values['target_id'])
    require(task['id'] != target['id'] and task['issueId'] == target['issueId'], '只能在同一分组内排序')
    group = sorted([t for t in state['tasks'] if t['issueId'] == task['issueId'] and t['id'] != task['id']], key=lambda t: t['order'])
    at = group.index(target) + int(values['after'])
    group.insert(at, task)
    for index, item in enumerate(group):
        item['order'] = index
    return task


def followup(state, issue, values, actor):
    entry = dict(id=str(uuid4()), content=text(values['content'], '跟进正文', required=True), at=now(), actor=actor)
    issue['followups'].insert(0, entry)
    return entry


def apply(state, operation, identifier, values, actor):
    if operation == 'create_issue':
        return create_issue(state, values, actor)
    if operation == 'create_task':
        return create_task(state, values, actor)
    kind = 'issues' if operation in ['update_issue', 'transition_issue', 'followup'] else 'tasks'
    item = get(state, kind, identifier)
    handlers = dict(update_issue=update_issue, transition_issue=transition_issue, followup=followup,
                    update_task=update_task, transition_task=transition_task, dependencies=dependencies, reorder=reorder)
    return handlers[operation](state, item, values, actor)
