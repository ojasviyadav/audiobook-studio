"""Save observed throughput for the first production run; no model computation."""
from pathlib import Path
import json
import time

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / 'reports'
baseline = json.loads((REPORTS/'run-baseline.json').read_text())
project = Path(baseline['project'])
work = project/'kokoro-heart-build'
assignment = json.loads((work/'parallel-plan.json').read_text())
workers = [{'worker':i,'device':device,'new_batches':0,'audio_seconds':0,'latest_batch_at':None}
           for i,device in enumerate(baseline['topology'])]
for path in work.glob('*/*.json'):
    key=str(path.relative_to(project))
    if key in baseline['existing_receipts']:
        continue
    try:
        receipt=json.loads(path.read_text())
        if not path.with_suffix('.flac').exists(): continue
        row=workers[assignment[path.parent.name]]
        row['new_batches']+=1
        row['audio_seconds']+=receipt['frames']/24000
        row['latest_batch_at']=max(row['latest_batch_at'] or 0,path.stat().st_mtime)
    except (ValueError, KeyError):
        continue
readings=[]
for line in (work/'temperature-readings.jsonl').read_text().splitlines():
    try:
        item=json.loads(line)
        if item.get('guard_pid')==baseline['source_guard_pid'] or readings: readings.append(item)
    except ValueError: pass
started=readings[0]['time'] if readings else baseline['started_tracking_at']
observed_at=time.time()
elapsed=observed_at-started
active=sum(b['time']-a['time'] for a,b in zip(readings,readings[1:]) if a['running'])
for row in workers:
    row['speech_seconds_per_total_elapsed_second']=row['audio_seconds']/elapsed if elapsed else None
    row['speech_seconds_per_enabled_second']=row['audio_seconds']/active if active else None
result={'observed_at':observed_at,'start_time':started,'elapsed_seconds':elapsed,
        'observed_enabled_seconds':active,'workers':workers,
        'peak_recorded_c':max((r.get('temperature_c') or 0 for r in readings),default=None),
        'limitations':['Different source passages and two GPU workers versus one CPU worker.',
                      'Elapsed time includes startup and cooling; enabled time is derived from supervisor transitions.',
                      'GPU commands already submitted can finish during a host-process pause.',
                      'These measurements do not establish a compute or memory-bandwidth bottleneck.']}
(REPORTS/'parallel-run-measurements.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
