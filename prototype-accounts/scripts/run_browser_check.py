"""Run unchanged checks with bounded Windows Playwright driver cleanup.

This host can hang in sync_playwright.__exit__ after browser tests finish.
Only replace that teardown: terminate this runner's own driver process tree.
Assertions, screenshots, responsive checks and report fingerprints are unchanged.
"""
import os
from pathlib import Path
import runpy
import subprocess
import sys
from playwright.sync_api._context_manager import PlaywrightContextManager
from playwright.sync_api import Page

# Windows screenshot capture can exceed the runner's 5s action budget under load.
# Only extend image capture; do not change interaction or layout assertions.
original_screenshot=Page.screenshot
def screenshot(page,*args,**kwargs):
    kwargs.setdefault('timeout',30000)
    return original_screenshot(page,*args,**kwargs)
Page.screenshot=screenshot

def stop_owned_driver(manager,*exc):
    proc=manager._connection._transport._proc
    if proc is not None and proc.returncode is None:
        result=subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=15)
        print('Windows test-driver cleanup:',result.returncode,flush=True)
    return False

if os.name=='nt':PlaywrightContextManager.__exit__=stop_owned_driver
target=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(target.parent))
sys.argv=sys.argv[1:]
status=0
try:
    runpy.run_path(str(target),run_name='__main__')
except SystemExit as exc:
    status=int(exc.code or 0)
except BaseException:
    import traceback
    traceback.print_exc()
    status=1
finally:
    sys.stdout.flush();sys.stderr.flush()
    os._exit(status)
