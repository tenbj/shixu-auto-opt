"""Shared bounded process shutdown for verification and portable packaging."""
import os, subprocess
def stop(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        else: process.terminate()
        process.wait(timeout=10)
