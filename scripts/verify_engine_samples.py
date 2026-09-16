"""Run the prepared two-worker samples and record wall time and cache reuse."""
from pathlib import Path
import fcntl
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app_bridge
from scripts.runtime_settings import atomic_json
from scripts.tts_contract import MODELS
PYTHON=str(ROOT.parent/'Audiobooks/.kokoro-venv/bin/python')

def call(action,project):
    p=subprocess.run([PYTHON,str(ROOT/'app_bridge.py')],input=json.dumps(dict(action=action,project=str(project))),capture_output=True,text=True,check=True)
    result=json.loads(p.stdout)
    if not result['ok']:raise RuntimeError(result['error'])
    return result

def wait_idle():
    while True:
        other=app_bridge.read(ROOT/'.active-project.json').get('project')
        if not other or not app_bridge.state(Path(other))[1]:return
        time.sleep(5)

def main():
    report_path=ROOT/'reports/mlx-comparison.json'
    report=app_bridge.read(report_path,{'trials':[]})
    for engine in ('qwen','voxtral'):
        if any(r['engine']==engine and r.get('saved_audio_reused') for r in report['trials']):continue
        print('Waiting for '+engine+' model.',flush=True)
        marker=ROOT/'models'/engine/'ready.json'
        while app_bridge.read(marker).get('model')!=MODELS[engine]:
            # Compatibility with the already-running first downloader, which
            # predates ready.json. Only its successful completion marks ready.
            oldlog=Path('/tmp/audiobook-model-download.log')
            if oldlog.exists() and engine+' download complete.' in oldlog.read_text():
                atomic_json(marker,{'model':MODELS[engine]});break
            time.sleep(5)
        wait_idle()
        project=ROOT/'projects/engine-comparison'/engine
        while (project/'pause.request').exists() or (project/'stop.request').exists():time.sleep(5)
        config=app_bridge.settings(project)
        print(engine+' setup: '+app_bridge.check(config),flush=True)
        before_words=app_bridge.progress(project,config)['saved']
        started=time.time();call('start',project)
        previous=-1
        while True:
            state=app_bridge.snapshot(project);pct=round(state['progress']['percent'])
            if pct!=previous:print(engine+' saved '+str(pct)+'%',flush=True);previous=pct
            if not state['active']:
                if not state['complete']:raise RuntimeError(engine+' failed. See '+str(project/'kokoro-heart-build'))
                break
            time.sleep(3)
        final=app_bridge.read(project/'kokoro-heart-build/status.json')
        job=app_bridge.read(project/'app-run.json')
        ended=job.get('finished',time.time())
        first_guard=app_bridge.read(project/'kokoro-heart-build/temperature-status.json')
        paths=list((project/'kokoro-heart-build').glob('*/*.json'))
        receipts=[app_bridge.read(p) for p in paths]
        before={str(p):p.stat().st_mtime_ns for p in paths}
        call('resume',project)
        while app_bridge.state(project)[1]:time.sleep(2)
        if app_bridge.read(project/'app-run.json').get('exit_code')!=0:raise RuntimeError('Cache reuse run failed')
        if before!={str(p):p.stat().st_mtime_ns for p in paths}:raise RuntimeError('Resume changed saved audio')
        rows=[]
        for line in (project/'kokoro-heart-build/temperature-readings.jsonl').read_text().splitlines():
            row=json.loads(line)
            if row.get('guard_pid')==first_guard['guard_pid']:rows.append(row)
        active=sum(b['time']-a['time'] for a,b in zip(rows,rows[1:]) if a['running'])
        trial=dict(engine=engine,model=MODELS[engine],config=config,words=state['progress']['total'],previously_saved_words=before_words,
            start_time=started,end_time=ended,elapsed_seconds=ended-started,audio_seconds=final['duration_seconds'],
            chapters=final['chapters'],output=final['output'],saved_audio_reused=True,
            first_guard=first_guard,observed_enabled_seconds=active,receipts=receipts)
        trial['final_config']=app_bridge.settings(project)
        trial['test_adjustments']=app_bridge.read(project/'test-adjustments.json')
        report['trials']=[r for r in report['trials'] if r['engine']!=engine]+[trial]
        atomic_json(report_path,report)
        print(engine+' verified: '+final['output'],flush=True)
    print('Both model conversions and cache reuse checks passed.',flush=True)

if __name__=='__main__':
    with (ROOT/'.engine-verification.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        main()
