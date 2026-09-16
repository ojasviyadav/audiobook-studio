"""Small, serial CPU/MPS comparison; run only under temperature_guard.py."""
from pathlib import Path
import json
import os
import time

assert os.environ.get('KOKORO_THERMAL_GUARD_PID') == str(os.getppid())
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', HF_HUB_OFFLINE='1', PYTORCH_ENABLE_MPS_FALLBACK='1')
from temperature_guard import start_guard_watchdog
start_guard_watchdog()
import torch
from kokoro import KModel, KPipeline

ROOT = Path(os.environ['AUDIOBOOK_PROJECT']).resolve()
config = json.loads((ROOT / 'book.json').read_text())
torch.set_num_interop_threads(1)
torch.set_num_threads(2)
os.nice(15)
model_dir = Path(config['model_dir'])
model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(model_dir/'config.json'), model=str(model_dir/'kokoro-v1_0.pth')).eval()
pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', model=model)
pipeline.load_voice(config['voice'])
chapters = json.loads((ROOT / 'chapters.json').read_text())
passage = next((ROOT/'build'/(c['file']+'.txt')).read_text() for c in chapters if c['words'] >= 100)
text = ' '.join(passage.split()[:100])
report = []
for device, threads in [('cpu', 2), ('mps', 2), ('cpu', 4)]:
    model.to(device)
    torch.set_num_threads(threads)
    for iteration in range(3):
        time.sleep(20)
        if device == 'mps':
            torch.mps.synchronize()
        start = time.monotonic()
        audio_seconds = 0
        for result in pipeline(text, voice=config['voice'], speed=config['speed']):
            audio = result.audio.detach().cpu()
            assert bool(torch.isfinite(audio).all())
            audio_seconds += len(audio)/24000
        if device == 'mps':
            torch.mps.synchronize()
        row = dict(device=device, threads=threads, iteration=iteration,
                   start_unix=time.time()-(time.monotonic()-start), end_unix=time.time(),
                   seconds=time.monotonic()-start, audio_seconds=audio_seconds)
        row['timing_includes_any_thermal_pauses'] = True
        report.append(row)
        (ROOT/'kokoro-heart-build/benchmark.json').write_text(json.dumps(report, indent=2))
        print('BENCHMARK', json.dumps(row), flush=True)
print('Benchmark complete.', flush=True)
