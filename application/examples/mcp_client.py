"""通过真实 stdio MCP 固定序列检查；不等同于 AI 自主验收。"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def run(url, write_demo=False, report=None):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'mcp_server.py')],
                                  env=dict(os.environ, SHIXU_API_URL=url, PYTHONIOENCODING='utf-8'))
    evidence = {'kind': 'real-stdio-sdk-fixed-sequence', 'ai_autonomous': False, 'steps': []}
    async with Client(params) as client:
        tools = await client.list_tools()
        evidence['tools'] = [tool.name for tool in tools.tools]
        assert len(evidence['tools']) == 22

        async def call(name, arguments=None, error=False):
            result = await client.call_tool(name, arguments or {})
            assert bool(result.is_error) == error, str(result)
            if error:
                assert 'HTTP 409' in result.content[0].text, result.content
            evidence['steps'].append({'tool': name, 'passed': True, 'expected_error': error})
            content = result.structured_content
            if content is None:
                content = json.loads(result.content[0].text) if not error else {}
            return content

        health = await call('get_system_status')
        evidence['backend'] = health.get('backend')
        await call('list_issues')
        state = await call('get_workspace')
        if write_demo:
            body = dict(title='合成演示：MCP 固定序列', request_id=str(uuid4()), expected_version=state['revision'], actor='MCP隔离验证')
            created = await call('create_issue', {'body': body})
            replay = await call('create_issue', {'body': body})
            assert created == replay
            identifier = created['resource']['id']
            read = await call('get_issue', {'issue_id': identifier})
            assert read['item']['title'] == body['title']
            await call('transition_issue', {'issue_id': identifier, 'body': dict(action='resolve', resolution='不允许跨阶段', request_id=str(uuid4()), expected_version=read['revision'])}, error=True)
            updated = await call('add_followup', {'issue_id': identifier, 'body': dict(content='MCP→API→数据库真实回读成功', request_id=str(uuid4()), expected_version=read['revision'])})
            assert updated['resource']['content']
            revision = updated['revision']
            async def write(name, values, **ids):
                nonlocal revision
                result = await call(name, dict(ids, body=dict(values, request_id=str(uuid4()), expected_version=revision, actor='MCP隔离验证')))
                revision = result['revision']
                return result['resource']
            await write('update_issue', {'tag': 'MCP演示', 'description': '仅包含合成记录'}, issue_id=identifier)
            await write('transition_issue', {'action': 'triage', 'nextStep': '验证全部工具', 'successCriteria': '每个工具可回读'}, issue_id=identifier)
            first = await write('create_task', {'title': 'MCP合成步骤一', 'issueId': identifier})
            second = await write('create_task', {'title': 'MCP合成步骤二', 'issueId': identifier})
            await write('update_task', {'due': '2099-01-01'}, task_id=first['id'])
            await call('get_task', {'task_id': first['id']})
            await write('set_task_dependencies', {'dependsOn': [first['id']]}, task_id=second['id'])
            await write('reorder_task', {'target_id': first['id'], 'after': False}, task_id=second['id'])
            await write('transition_task', {'status': '已完成'}, task_id=first['id'])
            await write('transition_task', {'status': '已完成'}, task_id=second['id'])
            await write('transition_issue', {'action': 'verify', 'successCriteria': '工具都可以回读', 'treatment': '通过stdio调用全部工具', 'verificationMethod': 'SDK断言与HTTP真实回读'}, issue_id=identifier)
            await write('transition_issue', {'action': 'resolve', 'resolution': 'SDK固定序列断言通过；不代表AI自主任务通过'}, issue_id=identifier)
            await write('delete_issue', {}, issue_id=identifier)
            trash = await call('list_trash')
            assert any(p['id'] == identifier for p in trash['issues'])
            await write('restore_issue', {}, issue_id=identifier)
            await write('set_task_dependencies', {'dependsOn': []}, task_id=second['id'])
            await write('delete_task', {}, task_id=first['id'])
            await write('restore_task', {}, task_id=first['id'])
        await call('list_tasks')
        await call('list_activity')
        await call('export_workspace')
        if write_demo:
            assert set(evidence['tools']) == {step['tool'] for step in evidence['steps']}
    evidence['passed'] = True
    if report:
        Path(report).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False))
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--write-demo', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()
    asyncio.run(run(args.url, args.write_demo, args.report))
