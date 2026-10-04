"""Optional local Codex configuration check; never touches the real CODEX_HOME."""
import argparse,json,os,subprocess,tempfile,tomllib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(command):
    with tempfile.TemporaryDirectory(prefix='shixu-codex-check-') as directory:
        file=Path(directory)/'config.toml'
        file.write_text('[mcp_servers.retained]\nurl="https://example.invalid/mcp"\n',encoding='utf-8')
        env=dict(os.environ,CODEX_HOME=directory)
        def cli(*args):
            return subprocess.run([command,*args],env=env,capture_output=True,text=True,encoding='utf-8',check=True,timeout=30,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {})).stdout
        version=cli('--version').strip()
        # Specifying the env-var adapter avoids triggering an interactive OAuth flow.
        cli('mcp','add','shixu','--url','https://shixu.eliasliu.cc/mcp','--bearer-token-env-var','SHIXU_MCP_TOKEN')
        config=tomllib.loads(file.read_text(encoding='utf-8'))['mcp_servers']
        assert config['retained']['url']=='https://example.invalid/mcp'
        assert config['shixu']['url']=='https://shixu.eliasliu.cc/mcp'
        assert config['shixu']['bearer_token_env_var']=='SHIXU_MCP_TOKEN'
        assert json.loads(cli('mcp','get','shixu','--json'))['name']=='shixu'
    report=dict(passed=True,version=version,scope='isolated PAT add/get and preservation of another MCP; no real credentials or user configuration used',
        oauth_login_verified=False,skill_discovery_verified=False,end_to_end_verified=False)
    (ROOT/'verification/codex-config-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--command',required=True,help='Actual Codex executable path');run(parser.parse_args().command)
