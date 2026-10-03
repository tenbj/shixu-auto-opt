"""通过私有配置验证HTTP MCP；默认只读，不向终端输出访问密钥。"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def check(config, write_demo=False):
    settings = json.loads(Path(config).read_text(encoding='utf-8'))['mcpServers']['shixu']
    async with httpx2.AsyncClient(headers=settings['headers'], trust_env=False) as http:
        async with Client(streamable_http_client(settings['url'], http_client=http)) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 25
            async def call(name, args):
                result = await client.call_tool(name, args)
                assert not result.is_error, 'MCP tool failed: ' + name
                return result.structured_content or json.loads(result.content[0].text)
            health = await call('get_system_status', {})
            assert health['mcp']['running']
            await call('list_identities', {})
            checks = ['authenticated SDK initialize', '25 tools discovered', 'health', 'identity list']
            if write_demo:
                arguments = {'body': {'title': 'HTTP MCP隔离演示', 'tag': '合成验证',
                    'actor': 'HTTP MCP测试', 'expected_version': health['revision'], 'request_id': str(uuid4())}}
                first = await call('create_issue', arguments)
                replay = await call('create_issue', arguments)
                assert first == replay
                readback = await call('get_issue', {'issue_id': first['resource']['id']})
                # MySQL详情补齐可空的软删除字段；创建响应的每个字段须完全保留。
                assert {key: readback['item'][key] for key in first['resource']} == first['resource']
                checks += ['real API write', 'idempotent replay', 'readback']
            return {'passed': True, 'transport': 'streamable-http', 'tools': len(tools),
                    'checks': checks, 'scope': 'SDK固定序列；不代表AI自主验收', 'token_printed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--write-demo', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = asyncio.run(check(args.config, args.write_demo))
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    print(output)
