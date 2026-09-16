"""Download fixed model files in verified, resumable HTTP ranges."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import fcntl
import json
import os
import sys
import threading
import time
from urllib.parse import quote
import requests
from huggingface_hub import HfApi
try:
    from .runtime_settings import atomic_json
    from .tts_contract import MODELS
except ImportError:
    from runtime_settings import atomic_json
    from tts_contract import MODELS

ROOT=Path(__file__).resolve().parents[1]
PART=1024*1024
local=threading.local()

def session():
    if not hasattr(local,'session'):local.session=requests.Session()
    return local.session

def digest(path,algorithm='sha256',git=False):
    h=hashlib.new(algorithm)
    if git:h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def valid(path,file):
    if not path.exists() or path.stat().st_size!=file['size']:return False
    if file['sha256']:return digest(path)==file['sha256']
    return digest(path,'sha1',True)==file['git_blob_sha1']

def fetch_part(url,start,end,path,total):
    length=end-start+1
    if path.exists() and path.stat().st_size==length:return length
    error=''
    for attempt in range(12):
        temp=path.with_suffix('.pending')
        try:
            # Each range has a separate URL so intermediate caches cannot reuse
            # a response for the wrong byte range.
            with session().get(url+f'?download=true&part={start}&attempt={attempt}&request={time.time_ns()}',headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','Cache-Control':'no-cache'},stream=True,timeout=(20,35)) as r:
                r.raise_for_status()
                if r.status_code==206:
                    if r.headers.get('Content-Range')!=f'bytes {start}-{end}/{total}':raise ValueError('Wrong response range')
                elif not (r.status_code==200 and start==0 and length==total):raise ValueError('Server ignored requested range')
                size=0
                with temp.open('wb') as out:
                    for block in r.iter_content(65536):
                        size+=len(block)
                        if size>length:raise ValueError('Response exceeded requested range')
                        out.write(block)
                if size!=length:raise ValueError('Incomplete response')
            temp.replace(path)
            return length
        except (requests.RequestException,OSError,ValueError) as exc:
            # Do not put signed CDN URLs from network exceptions in the log.
            error=type(exc).__name__
            if attempt in (0,5):
                status=getattr(getattr(exc,'response',None),'status_code',None)
                print(f'Retrying range {start}-{end}: {error}, HTTP {status}.',flush=True)
            temp.unlink(missing_ok=True)
            time.sleep(min(15,1+attempt*2))
    raise RuntimeError(f'Range {start}-{end} failed after retries: {error}')

def download(engine):
    model=MODELS[engine];folder=ROOT/'models'/engine;folder.mkdir(parents=True,exist_ok=True)
    info=HfApi().model_info(model,files_metadata=True)
    files=[dict(path=f.rfilename,size=f.size,sha256=f.lfs.sha256 if f.lfs else None,git_blob_sha1=f.blob_id) for f in info.siblings]
    manifest=dict(model=model,revision=info.sha,bytes=sum(f['size'] for f in files),files=files)
    atomic_json(ROOT/'models'/f'{engine}-manifest.json',manifest)
    print(f'{engine}: checking {len(files)} files at revision {info.sha[:12]}.',flush=True)
    for file in files:
        dest=folder/file['path']
        if not dest.resolve().is_relative_to(folder.resolve()):raise ValueError('Invalid model file path')
        dest.parent.mkdir(parents=True,exist_ok=True)
        if valid(dest,file):continue
        parts=folder/'.download-parts'/(file['sha256'] or file['git_blob_sha1']);parts.mkdir(parents=True,exist_ok=True)
        url='https://huggingface.co/'+model+'/resolve/'+info.sha+'/'+quote(file['path'])
        ranges=[(start,min(start+PART,file['size'])-1,parts/f'{start:012d}.part') for start in range(0,file['size'],PART)]
        completed=0;last_report=0
        print(f'{engine}: downloading {file["path"]}, {file["size"]/1e6:.1f} MB.',flush=True)
        failures=[]
        with ThreadPoolExecutor(max_workers=24) as pool:
            futures=[pool.submit(fetch_part,url,start,end,path,file['size']) for start,end,path in ranges]
            for future in as_completed(futures):
                try:completed+=future.result()
                except RuntimeError as exc:
                    failures.append(str(exc));continue
                if time.monotonic()-last_report>=15 or completed==file['size']:
                    print(f'{engine}: {file["path"]} {completed/file["size"]:.1%} ({completed/1e6:.1f} MB saved).',flush=True)
                    last_report=time.monotonic()
        if failures:raise RuntimeError(f'{len(failures)} ranges remain incomplete. Completed parts were kept. '+failures[0])
        temp=dest.with_suffix(dest.suffix+'.assembling')
        with temp.open('wb') as out:
            for _,_,path in ranges:
                with path.open('rb') as inp:
                    for block in iter(lambda:inp.read(PART),b''):out.write(block)
        if not valid(temp,file):raise RuntimeError('Checksum mismatch: '+file['path'])
        temp.replace(dest)
        for _,_,path in ranges:path.unlink()
        parts.rmdir()
        print(f'{engine}: verified {file["path"]}.',flush=True)
    atomic_json(folder/'ready.json',dict(model=model,revision=info.sha,verified=True))
    print(engine+' download complete.',flush=True)

if __name__=='__main__':
    for engine in sys.argv[1:] or MODELS:
        if engine not in MODELS:raise SystemExit('Select qwen or voxtral.')
        folder=ROOT/'models'/engine;folder.mkdir(parents=True,exist_ok=True)
        with (folder/'.download.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            download(engine)
