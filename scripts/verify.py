"""Run tests, contract checks and the offline demo from any working directory."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, APP_MODE="offline", PYTHONUTF8="1")
for command in ([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                [sys.executable, "scripts/contracts.py"],
                [sys.executable, "demo.py"]):
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
