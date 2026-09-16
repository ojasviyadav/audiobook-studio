"""Integration check: thermal signals must reach every worker in a process group."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent

def until(fn, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return
        time.sleep(0.1)
    raise AssertionError('Timed out waiting for expected process state')

with tempfile.TemporaryDirectory(prefix='kokoro-guard-check-') as folder:
    work = Path(folder)
    (work/'temperature').write_text('60')
    (work/'dummy.py').write_text('''import subprocess,sys,time,json,os
from pathlib import Path
children=[subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']) for _ in range(3)]
Path(sys.argv[1]).write_text(json.dumps([os.getpid()]+[p.pid for p in children]))
time.sleep(60)
''')
    script = '''import sys
from pathlib import Path
import temperature_guard as g
g.WORK=Path(sys.argv[1])
g.read_temperatures=lambda keys: {'Tp01':float((g.WORK/'temperature').read_text()),'Tg01':50}
base=g.Gate
class FastGate(base):
    def update(self, now, temperature, valid=True):
        return super().update(now*10, temperature, valid)
g.Gate=FastGate
sys.argv=['test',sys.executable,str(g.WORK/'dummy.py'),str(g.WORK/'pids')]
g.main()
'''
    supervisor = subprocess.Popen([sys.executable,'-c',script,str(work)], cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  env=dict(os.environ, AUDIOBOOK_PROJECT=str(work), AUDIOBOOK_SENSORS=str(ROOT.parent/'vendor/smctemp')))
    pids=[]
    try:
        until(lambda:(work/'pids').exists())
        pids=json.loads((work/'pids').read_text())
        assert all(os.getpgid(pid)==pids[0] for pid in pids)
        (work/'temperature').write_text('80')
        def states():
            return subprocess.check_output(['ps','-o','stat=','-p',','.join(map(str,pids))],text=True).split()
        until(lambda:len(states())==4 and all('T' in s for s in states()))
        (work/'temperature').write_text('60')
        until(lambda:len(states())==4 and all('T' not in s for s in states()))
        # A read failure must pause the whole process group too.
        (work/'temperature').write_text('unavailable')
        until(lambda:len(states())==4 and all('T' in s for s in states()))
        print('PASS: three workers share a group; temperature and sensor failure pause all; cooling resumes all.')
    finally:
        supervisor.terminate()
        output,_=supervisor.communicate(timeout=15)
        print(output)
        if pids:
            try:
                os.killpg(pids[0],signal.SIGKILL)
            except ProcessLookupError:
                pass
