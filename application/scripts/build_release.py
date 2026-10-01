"""白名单打包、内容扫描、换目录运行验证与合同检查。不会发布或上传。"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
import httpx
from check import stop

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = {'app', 'static', 'docs', 'examples', 'tests', 'verification', 'scripts', 'data', '.github'}
INCLUDE_FILES = {'README.md', 'CHANGELOG.md', 'LICENSE', '.gitignore', '.env.example', 'requirements.txt',
                 'requirements-dev.txt', 'requirements-lock.txt', 'project-contract.json', 'mcp_server.py'}
SKIP_PARTS = {'__pycache__', '.pytest_cache', 'runtime', 'private', '.venv', '.git', 'dist'}


def files():
    result = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in SKIP_PARTS for part in relative.parts) or path.name.startswith('frp-public.'):
            continue
        if relative.parts[0] in INCLUDE_DIRS or str(relative) in INCLUDE_FILES:
            if path.suffix not in {'.pyc', '.sqlite3', '.log'}:
                result.append(path)
    return sorted(result)


def scan(paths):
    findings = []
    patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'(?<![A-Za-z])sk-[A-Za-z0-9_-]{25,}', r'ghp_[A-Za-z0-9]{30,}']
    for path in paths:
        if path.is_symlink():
            findings.append(str(path.relative_to(ROOT)) + ': symlink')
        if path.suffix in ['.md', '.json', '.py', '.html', '.txt', '.yml'] or path.name == '.env.example':
            content = path.read_text(encoding='utf-8')
            for pattern in patterns:
                if re.search(pattern, content):
                    findings.append(str(path.relative_to(ROOT)) + ': credential pattern')
    return {'passed': not findings, 'findings': findings, 'files_scanned': len(paths),
            'policy': '只包含白名单源码、文档、合成种子、验证证据；排除runtime/private/.env/缓存/依赖/Git；扫描私钥与常见令牌模式',
            'data_review': 'data/demo.json及verification中的业务记录均来自显式合成测试；不包含用户原型浏览器记录或本机数据库'}


def archive(destination, paths):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            bundle.write(path, 'shixu-system/' + path.relative_to(ROOT).as_posix())


def portable(zip_path, temporary):
    directory = Path(temporary) / 'relocated'
    with zipfile.ZipFile(zip_path) as bundle:
        bundle.extractall(directory)
    project = directory / 'shixu-system'
    assert not (project / 'runtime').exists()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, PYTHONIOENCODING='utf-8', SHIXU_BACKEND='sqlite')
    env.pop('SHIXU_DB', None)
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=project, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Portable service exited')
            try:
                response = httpx.get(url + '/api/health', timeout=1, trust_env=False)
                response.raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(.1)
        else:
            raise RuntimeError('Portable service timeout')
        assert response.json()['revision'] == 0
        assert httpx.get(url, trust_env=False).status_code == 200
        from uuid import uuid4
        created = httpx.post(url + '/api/issues', json=dict(title='便携验证合成对象', expected_version=0, request_id=str(uuid4())), trust_env=False).raise_for_status().json()
        assert httpx.get(url + '/api/issues/' + created['resource']['id'], trust_env=False).raise_for_status().json()['item']['title'] == '便携验证合成对象'
    finally:
        stop(process)
    return {'passed': True, 'scope': 'ZIP解压到另一临时目录，复用当前已安装依赖的Python；显式SQLite测试适配器启动、真实HTTP首页、创建与回读通过；MySQL真实联调另见mysql-report.json',
            'dependency_install_verified_separately': False, 'os': sys.platform, 'python': sys.version.split()[0],
            'not_claimed': '不是免安装exe；未在Linux/macOS实测；最终包的运行源码与此候选相同，仅补充报告和ready合同'}


def main():
    summary = json.loads((ROOT / 'verification/summary.json').read_text(encoding='utf-8'))
    if not summary.get('passed'):
        raise SystemExit('Run scripts/check.py successfully before packaging')
    report = scan(files())
    if not report['passed']:
        raise SystemExit(json.dumps(report))
    with tempfile.TemporaryDirectory(prefix='shixu-release-') as temporary:
        candidate = Path(temporary) / 'candidate.zip'
        archive(candidate, files())
        result = portable(candidate, temporary)
    (ROOT / 'verification/portable-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'verification/release-scan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, 'scripts/generate_docs.py'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'scripts/validate_project.py', '--project-dir', '.', '--report', 'verification/contract-report.json'], cwd=ROOT, check=True)
    final_files = files()
    report = scan(final_files)
    if not report['passed']:
        raise SystemExit('Final package scan failed')
    (ROOT / 'verification/release-scan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    directory = ROOT / 'dist'
    directory.mkdir(exist_ok=True)
    target = directory / 'shixu-system-2.0.1.zip'
    archive(target, files())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (directory / 'SHA256SUMS.txt').write_text(digest + '  ' + target.name + '\n', encoding='utf-8')
    with zipfile.ZipFile(target) as bundle:
        assert bundle.testzip() is None
        assert all(not any(part in SKIP_PARTS for part in Path(name).parts) for name in bundle.namelist())
        contract = json.loads(bundle.read('shixu-system/project-contract.json'))
        assert contract['status'] == 'ready'
    print(json.dumps({'zip': str(target), 'sha256': digest, 'files': len(files()), 'passed': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
