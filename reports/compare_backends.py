"""Compare warm single/parallel Kokoro inference under the production heat guard."""
from pathlib import Path
import json
import multiprocessing as mp
import os
import time

ROOT=Path(__file__).resolve().parent
REPORT=Path('/Users/ojasviyadav/Work/ebooks-to-audiobook-conversion/reports')
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',
                  HF_HUB_OFFLINE='1',PYTORCH_ENABLE_MPS_FALLBACK='1')

def worker(conn,device,threads,text):
    import torch
    from kokoro import KModel,KPipeline
    torch.set_num_threads(threads);torch.set_num_interop_threads(1)
    model_dir=ROOT.parent/'kokoro-model'
    model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(model_dir/'config.json'),model=str(model_dir/'kokoro-v1_0.pth')).to(device).eval()
    pipeline=KPipeline(lang_code='a',repo_id='hexgrad/Kokoro-82M',model=model)
    pipeline.load_voice('af_heart')
    conn.send('ready')
    while conn.recv()=='run':
        started=time.time();seconds=0
        for result in pipeline(text,voice='af_heart',speed=.95):
            audio=result.audio.detach().cpu()
            assert bool(torch.isfinite(audio).all())
            seconds+=len(audio)/24000
        if device=='mps':torch.mps.synchronize()
        conn.send({'device':device,'threads':threads,'audio_seconds':seconds,'elapsed_seconds':time.time()-started})

def main():
    from temperature_guard import start_guard_watchdog
    start_guard_watchdog()
    text=' '.join((ROOT/'build/sample.txt').read_text().split())
    context=mp.get_context('spawn');workers={};rows=[]
    try:
        for name,device,threads in [('cpu0','cpu',4),('gpu0','mps',2),('cpu1','cpu',4),('gpu1','mps',2)]:
            parent,child=context.Pipe()
            proc=context.Process(target=worker,args=(child,device,threads,text));proc.start()
            workers[name]=(proc,parent)
            assert parent.recv()=='ready'
            parent.send('run'); result=parent.recv()
            print('WARM',name,result,flush=True)
            time.sleep(2)
        configs=[('CPU × 1',['cpu0']),('GPU × 1',['gpu0']),('CPU × 2',['cpu0','cpu1']),
                 ('GPU × 2',['gpu0','gpu1']),('GPU + CPU',['gpu0','cpu0'])]
        for iteration in range(2):
            order=configs if iteration==0 else list(reversed(configs))
            for label,names in order:
                time.sleep(2)
                started=time.time()
                for name in names:workers[name][1].send('run')
                results=[workers[name][1].recv() for name in names]
                elapsed=time.time()-started
                row={'config':label,'iteration':iteration,'start_time':started,'end_time':time.time(),
                     'elapsed_seconds':elapsed,'audio_seconds':sum(r['audio_seconds'] for r in results),
                     'workers':results,'guard_pid':int(os.environ['KOKORO_THERMAL_GUARD_PID'])}
                row['speech_per_elapsed_second']=row['audio_seconds']/elapsed
                rows.append(row);(REPORT/'controlled-comparison.json').write_text(json.dumps(rows,indent=2))
                print('MEASURED',json.dumps(row),flush=True)
        print('COMPARISON COMPLETE',flush=True)
    finally:
        for proc,conn in workers.values():
            if proc.is_alive():proc.terminate()
        for proc,conn in workers.values():proc.join(timeout=5)

if __name__=='__main__':main()
