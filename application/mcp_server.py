"""MCP stdio 入口；所有工具调用 HTTP API，不直接写数据库。"""
import os
from urllib.parse import quote, urlparse
import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from app.models import (IssueCreate, IssueUpdate, IssueTransition, Followup, TaskCreate,
                        TaskUpdate, TaskTransition, Dependencies, Reorder, IdentityCreate, IdentityUpdate, Write)

def create_server(api_transport=None):
    BASE = os.getenv('SHIXU_API_URL', 'http://127.0.0.1:8765').rstrip('/')
    if urlparse(BASE).hostname not in ['127.0.0.1', 'localhost', '::1']:
        raise ValueError('本地版本 MCP 只连接回环地址')
    server = MCPServer('shixu', version='2.4.0', instructions='先 health，再 list/get 获取 revision，写入携带 request_id 和 expected_version。重试同号；409重读，422修正输入，503不得声称成功。提交验证必须填写处理说明、方法；确认解决必须填写验证依据。actor仅为审计标签。创建前list_identities；creation.identityId指定实际提交身份，initiatedByPersonId可指定人类发起者；modelInfo记录实际模型，空对象表示未提供，不能从工具名猜测。')
    READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


    async def call(method, path, body=None, params=None):
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False, transport=api_transport) as client:
                response = await client.request(method, BASE + path, json=body, params=params)
            if response.is_error:
                detail = response.json().get('detail', '请求失败')
                raise ToolError(f'HTTP {response.status_code}: {detail}')
            return response.json()
        except httpx.RequestError:
            raise ToolError('HTTP 503: 拾序 API 无法连接或响应超时，结果未确认；恢复后用同一 request_id 重试') from None


    def payload(body):
        values = body.model_dump(exclude_unset=isinstance(body, (IssueUpdate, TaskUpdate, IdentityUpdate)))
        values.setdefault('actor', body.actor)
        return values


    def key(value):
        return quote(value, safe='')


    @server.tool(annotations=READ)
    async def get_system_status() -> dict:
        """先检查服务/数据库可用性，返回 status、revision；只读。"""
        return await call('GET', '/api/health')


    @server.tool(annotations=READ)
    async def list_identities() -> dict:
        """查询人/AI记录身份及默认模型、revision。创建问题或行动前选择真实提交身份；不推测模型。"""
        return await call('GET','/api/identities')


    @server.tool(annotations=WRITE)
    async def create_identity(body: IdentityCreate) -> dict:
        """新增自定义人或AI身份。人使用manual；AI指定工具与实际模型（可空）。不做身份认证。写入并审计，409重读，同请求同号重试。"""
        return await call('POST','/api/identities',payload(body))


    @server.tool(annotations=WRITE)
    async def update_identity(identity_id: str, body: IdentityUpdate) -> dict:
        """修改名称及新建默认工具/模型，类型不可变，已有记录的创建快照不变。先读revision；409重读；重试同号。"""
        return await call('PATCH','/api/identities/'+key(identity_id),payload(body))


    @server.tool(annotations=READ)
    async def get_workspace() -> dict:
        """读取完整工作台与全局 revision；跨资源操作前使用；只读。"""
        return await call('GET', '/api/workspace')


    @server.tool(annotations=READ)
    async def list_issues(q: str = '', status: str = '', priority: str = '', tag: str = '', creator: str = '', created_via: str = '', model: str = '') -> dict:
        """搜索/筛选问题，返回 items、revision；先 list 再 get 详情；只读。"""
        return await call('GET', '/api/issues', params=dict(q=q, status=status, priority=priority, tag=tag, creator=creator, created_via=created_via, model=model))


    @server.tool(annotations=READ)
    async def get_issue(issue_id: str) -> dict:
        """读取问题、关联行动与最新 revision，写入前获取并发版本；404表示不存在。"""
        return await call('GET', '/api/issues/' + key(issue_id))


    @server.tool(annotations=WRITE)
    async def create_issue(body: IssueCreate) -> dict:
        """创建待梳理问题。标题必填；写数据库与审计。返回 resource、revision、data；409重读，422修正，503不确认成功。"""
        return await call('POST', '/api/issues', payload(body))


    @server.tool(annotations=WRITE)
    async def update_issue(issue_id: str, body: IssueUpdate) -> dict:
        """编辑标题、背景、分类或优先级，不直接修改状态。先get取revision；同请求重试同号。"""
        return await call('PATCH', '/api/issues/' + key(issue_id), payload(body))


    @server.tool(annotations=WRITE)
    async def transition_issue(issue_id: str, body: IssueTransition) -> dict:
        """七状态流转：triage/start/verify/resolve/reject/pause/resume/close-issue/reopen/retriage。verify必填successCriteria/treatment/verificationMethod；resolve必填resolution依据；暂缓/关闭/重开须原因。关闭须处置未完成行动。写入并审计，409先重读，422补充条件，503不声称成功。"""
        return await call('POST', '/api/issues/' + key(issue_id) + '/transitions', payload(body))


    @server.tool(annotations=WRITE)
    async def add_followup(issue_id: str, body: Followup) -> dict:
        """追加1至5000字跟进；不改变问题状态。先get取revision；写入并审计。"""
        return await call('POST', '/api/issues/' + key(issue_id) + '/followups', payload(body))


    @server.tool(annotations=READ)
    async def list_tasks(issue_id: str | None = None, status: str = '', creator: str = '', created_via: str = '', model: str = '') -> dict:
        """查询行动及revision；issue_id省略为全部、空字符串为独立行动；只读。"""
        return await call('GET', '/api/tasks', params={k: v for k, v in dict(issue_id=issue_id, status=status, creator=creator, created_via=created_via, model=model).items() if v is not None})


    @server.tool(annotations=READ)
    async def get_task(task_id: str) -> dict:
        """读取行动详情、依赖、编号与revision；推进前确认前置行动；只读。"""
        return await call('GET', '/api/tasks/' + key(task_id))


    @server.tool(annotations=WRITE)
    async def create_task(body: TaskCreate) -> dict:
        """创建关联或独立待办，默认本轮必要；新增必要行动可能使待验证问题回到处理中。先读版本，写入并审计。"""
        return await call('POST', '/api/tasks', payload(body))


    @server.tool(annotations=WRITE)
    async def update_task(task_id: str, body: TaskUpdate) -> dict:
        """编辑标题、日期、必要性、关联。变更关联须先解除依赖，可能更新问题状态和行动分组编号。先get版本。"""
        return await call('PATCH', '/api/tasks/' + key(task_id), payload(body))


    @server.tool(annotations=WRITE)
    async def transition_task(task_id: str, body: TaskTransition) -> dict:
        """推进、完成、取消、重开行动；取消须reason；前置行动必须完成。可能同时改变问题状态；409重读，422补条件。"""
        return await call('POST', '/api/tasks/' + key(task_id) + '/transitions', payload(body))


    @server.tool(annotations=WRITE)
    async def set_task_dependencies(task_id: str, body: Dependencies) -> dict:
        """设置同组前置行动，拒绝自依赖、跨组、循环及已开始行动依赖未完成项；先list/get版本，写入并审计。"""
        return await call('POST', '/api/tasks/' + key(task_id) + '/dependencies', payload(body))


    @server.tool(annotations=WRITE)
    async def reorder_task(task_id: str, body: Reorder) -> dict:
        """调整同组行动前后顺序，保持编号和依赖；先list/get版本，写入并审计。"""
        return await call('POST', '/api/tasks/' + key(task_id) + '/reorder', payload(body))


    @server.tool(annotations=READ)
    async def list_activity(after: int = 0, limit: int = 100) -> dict:
        """按revision增序读取最多500条审计事件；用于验证操作发生过；只读。"""
        return await call('GET', '/api/activity', params=dict(after=after, limit=limit))


    @server.tool(annotations=READ)
    async def export_workspace() -> dict:
        """导出全部问题行动及状态历史；返回revision与data，不写磁盘；只读。"""
        return await call('GET', '/api/export')


    @server.tool(annotations=READ)
    async def list_trash() -> dict:
        """读取回收站问题与行动以及revision。恢复前检查批次与依赖；只读。"""
        return await call('GET', '/api/trash')


    @server.tool(annotations=WRITE)
    async def delete_issue(issue_id: str, body: Write) -> dict:
        """移入回收站，保留编号历史；问题同时删除有效关联行动；外部依赖阻挡删除。先读版本，request_id幂等；409重读或补前置，503不得声称成功。"""
        return await call('POST', '/api/issues/' + key(issue_id) + '/trash', payload(body))


    @server.tool(annotations=WRITE)
    async def restore_issue(issue_id: str, body: Write) -> dict:
        """恢复原记录；问题仅恢复同批行动，单删行动须关联问题有效且前置可用；必要行动可能重开验证。先读版本，request_id幂等；409重读或补前置，503不得声称成功。"""
        return await call('POST', '/api/issues/' + key(issue_id) + '/restore', payload(body))


    @server.tool(annotations=WRITE)
    async def delete_task(task_id: str, body: Write) -> dict:
        """移入回收站，保留编号历史；问题同时删除有效关联行动；外部依赖阻挡删除。先读版本，request_id幂等；409重读或补前置，503不得声称成功。"""
        return await call('POST', '/api/tasks/' + key(task_id) + '/trash', payload(body))


    @server.tool(annotations=WRITE)
    async def restore_task(task_id: str, body: Write) -> dict:
        """恢复原记录；问题仅恢复同批行动，单删行动须关联问题有效且前置可用；必要行动可能重开验证。先读版本，request_id幂等；409重读或补前置，503不得声称成功。"""
        return await call('POST', '/api/tasks/' + key(task_id) + '/restore', payload(body))
    return server


server = create_server()


if __name__ == "__main__":
    server.run(transport="stdio")
