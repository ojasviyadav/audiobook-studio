"""JSON interface for the Swift app. No shell interpolation and no model inference."""
from pathlib import Path
import argparse
import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import convert
from scripts.runtime_settings import DEFAULTS, AUDIO_KEYS, validate, atomic_json, lock_audio_settings
from scripts.tts_contract import narration_batches, audio_signature, MODELS

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
    total=saved=frames=0; recent=[0,0]; remaining=[0,0]; sections=[]
    plan=read(project/'kokoro-heart-build/parallel-plan.json');now=time.time()
    for chapter in read(project/'chapters.json',[]):
        done=words=0;worker=plan.get(chapter['file'],0);worker=min(worker,1)
        for n,text in enumerate(narration_batches((project/'build'/f'{chapter["file"]}.txt').read_text(),config),1):
            count=len(text.split());words+=count;total+=count
            path=project/'kokoro-heart-build'/chapter['file']/f'{n:04d}.json'
            receipt=read(path)
            signature=audio_signature(config,text)
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
    logs=[(f'GPU worker {i}: latest recorded output',project/f'kokoro-heart-build/parallel-{i}-mps.log') for i in range(2)]
    logs += [('App job history',project/'app-job.log'),
             ('Coordinator history: can contain errors from earlier runs',project/'kokoro-audiobook.log')]
    for label,file in logs:
        if file.exists():
            with file.open('rb') as stream:
                stream.seek(max(0,file.stat().st_size-4500))
                log+=label+'\n'+stream.read().decode('utf-8',errors='replace').replace('\0','')+'\n\n'
    return dict(config=config,progress=p,thermal=thermal,active=active,legacy=legacy,
                paused=paused,complete=complete,phase=phase,output=done.get('output',str(project/config['output_name'])),log=log)

def check(config):
    problems=[]
    if config['backend']=='kokoro':
        for file in ['kokoro-v1_0.pth','config.json']:
            if not (Path(config['model_dir'])/file).is_file():problems.append(f'Missing model file: {file}')
        python=sys.executable
        imports='import torch,kokoro,soundfile,spacy; assert torch.backends.mps.is_available(), "Metal GPU is unavailable"; spacy.load("en_core_web_sm")'
    else:
        python=str(REPO/'.venv-mlx/bin/python')
        model=REPO/'models'/config['backend']
        if read(model/'ready.json').get('model') != MODELS[config['backend']] or not (model/'config.json').is_file() or not list(model.glob('*.safetensors')):
            problems.append('Download the selected model in Setup.')
        imports='import mlx.core as mx; import mlx_audio,soundfile,scipy; from mlx_audio.tts.models.qwen3_tts import Model; from mlx_audio.tts.models.voxtral_tts import Model; from mistral_common.tokens.tokenizers.mistral import MistralTokenizer; assert mx.metal.is_available(), "Metal GPU is unavailable"'
        if not Path(python).is_file(): raise ValueError('Install the MLX runtime in Setup first.')
    for file in ['read_sensors','sensor_keys.json']:
        if not (Path(config['sensor_dir'])/file).is_file():problems.append(f'Missing temperature reader: {file}')
    for tool in ['ffmpeg','ffprobe']:
        if not shutil.which(tool):problems.append(f'{tool} was not found.')
    result=subprocess.run([python,'-c',imports],capture_output=True,text=True,timeout=60)
    if result.returncode:problems.append(result.stderr.strip().splitlines()[-1])
    if problems:raise ValueError('\n'.join(problems))
    return 'Setup is ready. Two Metal GPU workers are fixed.'

def dispatch(request):
    action=request['action'];project=Path(request.get('project') or '.').expanduser().resolve()
    if action=='check':return dict(message=check(validate(request['config'])))
    if action in ('install','download'):
        config=validate(request['config'])
        if config['backend']=='kokoro': raise ValueError('Kokoro already uses its existing runtime.')
        logpath=REPO/'models/setup.log';logpath.parent.mkdir(exist_ok=True)
        with logpath.open('a') as log:
            if action=='install':
                if not (REPO/'.venv-mlx/bin/python').exists():
                    subprocess.run([sys.executable,'-m','venv',str(REPO/'.venv-mlx')],check=True,stdout=log,stderr=log)
                cmd=[str(REPO/'.venv-mlx/bin/python'),'-m','pip','install','-r',str(REPO/'requirements-mlx.txt')]
            else:
                cmd=[str(REPO/'.venv-mlx/bin/python'),str(REPO/'scripts/download_models.py'),config['backend']]
            result=subprocess.run(cmd,stdout=log,stderr=log)
        if result.returncode: raise ValueError('Setup failed. See '+str(logpath))
        return dict(message='MLX runtime installed.' if action=='install' else 'Selected model downloaded.')
    if action=='preview':
        config=validate(request['config']);check(config)
        other=read(REPO/'.active-project.json').get('project')
        if other and state(Path(other))[1]:
            raise ValueError('Let the active book finish, or stop it before making a sample.')
        sample=REPO/'projects/previews'/str(uuid.uuid4())
        (sample/'build').mkdir(parents=True)
        text='The room was quiet. Through the open window, a cool breeze moved the curtains. She opened the book and began to read, slowly and clearly, while the city outside settled into the evening.'
        (sample/'build/01-sample.txt').write_text(text)
        atomic_json(sample/'chapters.json',[dict(file='01-sample',title='Voice sample',words=len(text.split()))])
        config.update(title='Voice sample',author='',source='',cover=None,output_name='Sample.m4b')
        atomic_json(sample/'book.json',config)
        atomic_json(REPO/'.active-project.json',dict(project=str(sample)))
        with (sample/'app-job.log').open('a') as log:
            result=subprocess.run([sys.executable,str(REPO/'convert.py'),'run',str(sample)],stdout=log,stderr=log)
        if result.returncode: raise ValueError('Sample failed. See '+str(sample/'kokoro-audiobook.log'))
        return dict(message='Sample ready. The book settings were not changed.',preview=str(sample/'Sample.m4b'))
    if action=='prepare':
        config=validate(request['config'])
        args=argparse.Namespace(source=Path(config['source']),project=project,model_dir=Path(config['model_dir']),sensor_dir=Path(config['sensor_dir']),voice=config['voice'],speed=config['speed'],backend=config['backend'])
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
        if active and any(new.get(k)!=old.get(k) for k in AUDIO_KEYS+('source','model_dir','sensor_dir','segment_rest','title','author','output_name')):
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
        if request['action'] in ('start','resume','preview','install','download'):
            with (REPO/'.app-action.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                result=dispatch(request)
        else:result=dispatch(request)
        print(json.dumps(dict(ok=True,**result)))
    except Exception as exc:print(json.dumps(dict(ok=False,error=str(exc))))
