"""Measure the recorded two-GPU Kokoro interval without counting later idle time."""
from pathlib import Path
import json
import re
from tts_contract import narration_batches

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO/'reports'
baseline = json.loads((REPORTS/'run-baseline.json').read_text())
project = Path(baseline['project']); work = project/'kokoro-heart-build'
config = json.loads((project/'book.json').read_text())
chapters = json.loads((project/'chapters.json').read_text())
readings = []
for line in (work/'temperature-readings.jsonl').read_text().splitlines():
    try:
        item=json.loads(line)
        if item.get('guard_pid') == baseline['source_guard_pid']: readings.append(item)
    except ValueError: pass
if not readings: raise RuntimeError('The recorded production guard was not found.')
started, ended = baseline['started_tracking_at'], readings[-1]['time']
# Resuming the book changes parallel-plan.json. Recover the original assignment
# from the corresponding worker log block instead of using today's plan.
assignment = {}
for worker in (0,1):
    log=(work/f'parallel-{worker}-mps.log').read_text()
    # The last original worker block precedes the newer "kokoro," log format.
    old=log.split('kokoro, af_heart',1)[0]
    old=re.split(r'^.*words already saved\.\s*$',old,flags=re.M)[-1]
    for match in re.finditer(r'^\[(\d+)/\d+\]',old,re.M):
        assignment[chapters[int(match.group(1))-1]['file']]=worker
workers=[dict(worker=i,device='mps',new_batches=0,words=0,audio_seconds=0,latest_batch_at=None) for i in (0,1)]
baseline_words=0
for chapter in chapters:
    for n,text in enumerate(narration_batches((project/'build'/f'{chapter["file"]}.txt').read_text(),config),1):
        path=work/chapter['file']/f'{n:04d}.json'
        key=str(path.relative_to(project))
        if key in baseline['existing_receipts']:
            baseline_words+=len(text.split());continue
        if not path.exists() or not path.with_suffix('.flac').exists():continue
        timestamp=path.stat().st_mtime
        if not started <= timestamp <= ended: continue
        receipt=json.loads(path.read_text())
        row=workers[assignment[chapter['file']]]
        row['new_batches']+=1;row['words']+=len(text.split())
        row['audio_seconds']+=receipt['frames']/24000
        row['latest_batch_at']=max(row['latest_batch_at'] or 0,timestamp)
elapsed=ended-started
active=sum(max(0, min(ended,b['time'])-max(started,a['time'])) for a,b in zip(readings,readings[1:]) if a['running'])
for row in workers:
    row['speech_seconds_per_total_elapsed_second']=row['audio_seconds']/elapsed
    row['speech_seconds_per_enabled_second']=row['audio_seconds']/active if active else None
words=sum(w['words'] for w in workers)
result=dict(source_guard_pid=baseline['source_guard_pid'],start_time=started,end_time=ended,
    elapsed_seconds=elapsed,observed_enabled_seconds=active,observed_paused_seconds=elapsed-active,
    baseline_words=baseline_words,new_words=words,workers=workers,
    projected_full_book_seconds=elapsed*sum(c['words'] for c in chapters)/words,
    peak_recorded_c=max(r.get('peak_observed_c') or r.get('temperature_c') or 0 for r in readings),
    peak_cpu_c=max(r.get('cpu_max_c') or 0 for r in readings),
    peak_gpu_c=max(r.get('gpu_max_c') or 0 for r in readings),
    limitations=['This interval ends with the copyright-page text-check failure. The later retry and final assembly are separate.',
        'The old assignment was recovered from worker logs because resumes replaced parallel-plan.json.',
        'Elapsed time begins at the saved baseline and includes cooling, missing-sensor pauses, and uneven worker completion.',
        'Pause time is estimated from supervisor transitions. Submitted GPU work can continue during host pauses.',
        'This is an extrapolation from the remaining book text, not a complete clean two-GPU book run.'])
(REPORTS/'parallel-run-measurements.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
