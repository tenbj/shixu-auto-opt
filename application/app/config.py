"""只从环境/本机私有文件加载凭据，不打印配置值。"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_environment():
    if os.getenv('SHIXU_SKIP_DOTENV', '').lower() == 'true':
        return
    load_dotenv(ROOT / '.env', override=False)
    private = os.getenv('SHIXU_ENV_FILE')
    if private:
        load_dotenv(Path(private), override=False)


load_environment()
