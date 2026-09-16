"""Persistent app job. Closing the window does not terminate narration."""
from pathlib import Path
import os
import subprocess
import sys
import time
from runtime_settings import atomic_json

repo = Path(__file__).resolve().parents[1]
project = Path(sys.argv[1]).resolve()
state = project/'app-run.json'
# The bridge records the PID before releasing this job. This prevents an early
# failure from being overwritten with a stale "starting" record.
if sys.stdin.buffer.read(1) != b'1':
    raise SystemExit('The app did not finish starting the job.')
result = subprocess.run([sys.executable, str(repo/'convert.py'), 'run', str(project)])
atomic_json(state, dict(pid=os.getpid(), finished=time.time(), exit_code=result.returncode))
raise SystemExit(result.returncode)
