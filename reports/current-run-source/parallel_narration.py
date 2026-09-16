"""Two Metal workers and one CPU worker in the temperature guard's process group."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time
from temperature_guard import start_guard_watchdog

ROOT = Path(__file__).resolve().parent
assert os.environ.get('KOKORO_THERMAL_GUARD_PID') == str(os.getppid())
start_guard_watchdog()

def stop(signum, frame):
    raise SystemExit(128 + signum)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
env = dict(os.environ, KOKORO_PARENT_PID=str(os.getpid()))
children, logs = [], []
try:
    for worker, device in enumerate(('mps', 'mps', 'cpu')):
        log = (ROOT / f'kokoro-heart-build/parallel-{worker}-{device}.log').open('a', buffering=1)
        logs.append(log)
        # Inherit the process group: the guard pauses/resumes ALL workers,
        # their host threads, the coordinator and every ffmpeg child together.
        child = subprocess.Popen([sys.executable, str(ROOT / 'kokoro_audiobook.py'),
            '--worker', str(worker), '--device', device], env=env, stdout=log, stderr=subprocess.STDOUT)
        children.append(child)
        print(f'Started {device} worker {worker}, PID {child.pid}.', flush=True)
    while any(child.poll() is None for child in children):
        for child in children:
            if child.poll() not in (None, 0):
                raise RuntimeError(f'Worker PID {child.pid} failed with status {child.returncode}.')
        time.sleep(0.5)
    if any(child.returncode != 0 for child in children):
        raise RuntimeError('A narration worker failed.')
    print('All workers finished. Assembling and verifying the audiobook.', flush=True)
    child = subprocess.Popen([sys.executable, str(ROOT / 'kokoro_audiobook.py'),
        '--assemble-only', '--device', 'cpu'], env=env)
    children.append(child)
    if child.wait() != 0:
        raise RuntimeError('Audiobook assembly failed.')
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
            child.send_signal(signal.SIGCONT)
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    for log in logs:
        log.close()
