"""JSON interface for the Swift app. No shell interpolation and no model inference."""
from pathlib import Path
import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import convert
from scripts.runtime_settings import DEFAULTS, AUDIO_KEYS, validate, atomic_json, lock_audio_settings

REPO = Path(__file__).resolve().parent

def read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError): return default if default is not None else {}

def command(pid):
    if not isinstance(pid,int) or pid <= 1: return ''
    p=subprocess.run(['/bin/ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
    return p.stdout.strip()

def state(project):
    thermal=read(project/'kokoro-heart-build/temperature-status.json')
    guard=thermal.get('guard_pid'); cmd=command(guard)
    guard_alive='temperature_guard.py' in cmd and time.time()-thermal.get('time',0)<20
    job=read(project/'app-run.json')
    launching=job.get('exit_code') is None and str(REPO/'scripts/app_job.py') in command(job.get('pid')) and str(project) in command(job.get('pid'))
    legacy=guard_alive and str(project/'temperature_guard.py') in cmd
    return thermal, guard_alive or launching, legacy

def settings(project):
    config=read(project/'book.json')
    if not config:
        raise ValueError('This folder has no book.json. Select a conversion project.')
    return validate(config)

def progress(project, config):
    tree=ast.parse((REPO/'scripts/kokoro_audiobook.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='batches')
    scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'batches','exec'),scope)
    total=saved=frames=0; recent=[0,0]; remaining=[0,0]; sections=[]
    plan=read(project/'kokoro-heart-build/parallel-plan.json');now=time.time()
    for chapter in read(project/'chapters.json',[]):
        done=words=0;worker=plan.get(chapter['file'],0);worker=min(worker,1)
        for n,text in enumerate(scope['batches']((project/'build'/f'{chapter["file"]}.txt').read_text()),1):
            count=len(text.split());words+=count;total+=count
            path=project/'kokoro-heart-build'/chapter['file']/f'{n:04d}.json'
            receipt=read(path)
            signature=hashlib.sha256((config['voice']+str(config['speed'])+text).encode()).hexdigest()
            if receipt.get('signature')==signature and path.with_suffix('.flac').exists():
                done+=count;saved+=count;frames+=receipt['frames']
                if now-path.stat().st_mtime<=300:recent[worker]+=count
            else:remaining[worker]+=count
        sections.append(dict(title=chapter['title'],done=done,total=words))
    eta=max((remaining[i]*300/recent[i] for i in range(2) if remaining[i] and recent[i]),default=0)
    if any(remaining[i] and not recent[i] for i in range(2)):eta=0
    return dict(saved=saved,total=total,percent=100*saved/total if total else 0,
                audio_seconds=frames/24000,eta_seconds=eta+120 if eta else None,sections=sections)

def snapshot(project):
    config=settings(project);thermal,active,legacy=state(project)
    paused=(project/'pause.request').exists()
    done=read(project/'kokoro-heart-build/status.json')
    complete=done.get('complete',False) and Path(done.get('output','')).is_file()
    p=progress(project,config)
    phase='Complete' if complete else ('Paused by you' if paused else (thermal.get('reason','Starting') if active else 'Ready to resume'))
    if active and p['percent']>=100:phase='Assembling and checking audio'
    job=read(project/'app-run.json')
    if not active and not complete and not paused and job.get('exit_code') not in (None,0):phase='Stopped after an error'
    log=''
    for file in [project/'app-job.log',project/'kokoro-audiobook.log']:
        if file.exists():
            with file.open('rb') as stream:
                stream.seek(max(0,file.stat().st_size-12000));log+=stream.read().decode('utf-8',errors='replace').replace('\0','')+'\n'
    return dict(config=config,progress=p,thermal=thermal,active=active,legacy=legacy,
                paused=paused,complete=complete,phase=phase,output=done.get('output',str(project/config['output_name'])),log=log[-20000:])

def check(config):
    problems=[]
    for file in ['kokoro-v1_0.pth','config.json']:
        if not (Path(config['model_dir'])/file).is_file():problems.append(f'Missing model file: {file}')
    for file in ['read_sensors','sensor_keys.json']:
        if not (Path(config['sensor_dir'])/file).is_file():problems.append(f'Missing temperature reader: {file}')
    for tool in ['ffmpeg','ffprobe']:
        if not shutil.which(tool):problems.append(f'{tool} was not found.')
    result=subprocess.run([sys.executable,'-c','import torch,kokoro,soundfile,spacy; assert torch.backends.mps.is_available(), "Metal GPU is unavailable"; spacy.load("en_core_web_sm")'],capture_output=True,text=True,timeout=30)
    if result.returncode:problems.append(result.stderr.strip().splitlines()[-1])
    if problems:raise ValueError('\n'.join(problems))
    return 'Setup is ready. Two Metal GPU workers are fixed.'

def dispatch(request):
    action=request['action'];project=Path(request.get('project') or '.').expanduser().resolve()
    if action=='check':return dict(message=check(validate(request['config'])))
    if action=='prepare':
        config=validate(request['config'])
        args=argparse.Namespace(source=Path(config['source']),project=project,model_dir=Path(config['model_dir']),sensor_dir=Path(config['sensor_dir']),voice=config['voice'],speed=config['speed'])
        with contextlib.redirect_stdout(io.StringIO()):convert.prepare(args)
        extracted=read(project/'book.json')
        extracted.update({k:v for k,v in config.items() if k not in ('title','author','cover','output_name')})
        for k in ('title','author'):
            if config.get(k,'').strip():extracted[k]=config[k].strip()
        atomic_json(project/'book.json',validate(extracted))
        return snapshot(project)
    if action in ('load','status'):return snapshot(project)
    if action=='save':
        old=settings(project);new=validate(old|request['config']);thermal,active,legacy=state(project)
        if active and any(new.get(k)!=old.get(k) for k in ('source','model_dir','sensor_dir','voice','speed','bitrate','paragraph_gap','chapter_gap','segment_rest','title','author','output_name')):
            raise ValueError('Pause or stop the conversion before changing these settings.')
        if active and legacy:raise ValueError('This earlier run uses its current settings until you stop and resume it in the app.')
        lock_audio_settings(project,new);atomic_json(project/'book.json',new);return snapshot(project)
    if action in ('start','resume'):
        other=read(REPO/'.active-project.json').get('project')
        if other and Path(other)!=project and state(Path(other))[1]:
            raise ValueError('Another book is running. Stop it or let it finish before starting this book.')
        thermal,active,legacy=state(project)
        if active:
            if legacy:raise ValueError('This book is already running. No duplicate job was started.')
            (project/'pause.request').unlink(missing_ok=True);return snapshot(project)
        config=settings(project);check(config);lock_audio_settings(project,config)
        for name in ('pause.request','stop.request'):(project/name).unlink(missing_ok=True)
        with (project/'app-job.log').open('a') as log:
            p=subprocess.Popen([sys.executable,str(REPO/'scripts/app_job.py'),str(project)],stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        atomic_json(REPO/'.active-project.json',dict(project=str(project)))
        # Write immediately so repeated clicks cannot race the job's startup.
        atomic_json(project/'app-run.json',dict(pid=p.pid,started=time.time(),exit_code=None))
        p.stdin.write(b'1');p.stdin.close()
        return snapshot(project)
    if action in ('pause','stop'):
        thermal,active,legacy=state(project)
        (project/('pause.request' if action=='pause' else 'stop.request')).touch()
        if action=='stop':(project/'pause.request').unlink(missing_ok=True)
        if legacy:
            # Only the exact legacy supervisor in this project may be signaled.
            pid=thermal['guard_pid']
            if str(project/'temperature_guard.py') not in command(pid):raise ValueError('The earlier process changed. Refresh and try again.')
            os.kill(pid,signal.SIGTERM)
        return snapshot(project)
    raise ValueError('Unknown app command.')

if __name__=='__main__':
    try:
        import fcntl
        request=json.load(sys.stdin)
        if request['action'] in ('start','resume'):
            with (REPO/'.app-action.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                result=dispatch(request)
        else:result=dispatch(request)
        print(json.dumps(dict(ok=True,**result)))
    except Exception as exc:print(json.dumps(dict(ok=False,error=str(exc))))
