"""Public bootstrap resources and authenticated connection diagnostics."""
import hashlib
import json
import os
from pathlib import Path
from fastapi import Request, Query
from fastapi.responses import FileResponse, PlainTextResponse
from .account_api import mcp_connection
from .account_context import principal, mcp_call
from .onboarding_auth import connection_context

ROOT=Path(__file__).resolve().parents[1]

def catalog(request):
    bundle=json.loads((ROOT/'downloads/skill-manifest.json').read_text(encoding='utf-8'))
    address=mcp_connection(request)['url'];base=address.removesuffix('/mcp')
    bundle['url']=base+'/downloads/'+bundle['filename']
    runtimes=json.loads((ROOT/'docs/connect/runtimes.json').read_text(encoding='utf-8'))
    return dict(version='1.0',interfaceVersion='3.1.0',mcp=address,guide=base+'/connect.md',
                skill=bundle,runtimes=runtimes,verificationTool='get_connection_context',
                stages=['downloaded','configured','authorized','runtime-loaded','mcp-verified','skill-discoverable'])

def install_onboarding(app):
    @app.get('/connect',include_in_schema=False)
    def connect_page():return FileResponse(ROOT/'static/connect.html')

    @app.get('/connect/manifest.json',summary='公开AI接入版本清单')
    def connect_manifest(request:Request):return catalog(request)

    @app.get('/connect.md',summary='公开AI接入指南',response_class=PlainTextResponse)
    def connect_guide(request:Request):
        data=catalog(request)
        guide=(ROOT/'docs/connect/guide.md').read_text(encoding='utf-8')
        return guide.replace('{{MCP}}',data['mcp']).replace('{{BASE}}',data['mcp'].removesuffix('/mcp')).replace('{{SKILL_VERSION}}',data['skill']['version']).replace('{{SKILL_SHA256}}',data['skill']['sha256'])

    @app.get('/connect/runtimes/{name}.md',summary='运行环境适配说明',response_class=PlainTextResponse)
    def runtime_guide(name:str):
        from .domain import require
        require(name in ('codex','workbuddy','claude','other'),'运行环境不存在',404)
        return (ROOT/'docs/connect'/f'{name}.md').read_text(encoding='utf-8')

    @app.get('/downloads/{filename}',summary='下载固定版本的拾序Skill包')
    def skill_download(filename:str):
        from .domain import require
        bundle=json.loads((ROOT/'downloads/skill-manifest.json').read_text(encoding='utf-8'))
        require(filename==bundle['filename'],'下载文件不存在',404)
        file=ROOT/'downloads'/filename
        require(hashlib.sha256(file.read_bytes()).hexdigest()==bundle['sha256'],'下载文件校验失败',503)
        return FileResponse(file,filename=filename,media_type='application/zip')

    @app.get('/api/connection-context',summary='读取认证账号、权限和MCP连接证据')
    def context(runtime_name:str=Query('',max_length=60),runtime_version:str=Query('',max_length=80),skill_version:str=Query('',max_length=40)):
        return connection_context(app.state.accounts,principal.get(),runtime_name,runtime_version,skill_version,verified=mcp_call.get())
