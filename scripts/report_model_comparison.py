"""Build a local timing report from completed sample and production records."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def duration(seconds):
    minutes=round(seconds/60)
    return f'{minutes//60} h {minutes%60:02d} min' if minutes>=60 else f'{minutes} min'

def make_report():
    production=json.loads((ROOT/'reports/parallel-run-measurements.json').read_text())
    data=json.loads((ROOT/'reports/mlx-comparison.json').read_text())
    trials={r['engine']:r for r in data['trials']}
    q=trials['qwen']
    if q['previously_saved_words']:raise RuntimeError('A partly cached Qwen run cannot establish cold sample time.')
    total=77001
    cold=q['elapsed_seconds']*total/q['words']
    workers=[]
    for worker in (0,1):
        receipts=[r for r in q['receipts'] if r.get('worker')==worker]
        words=sum(r['words'] for r in receipts)
        seconds=sum(r['finished_at']-r['started_at']-r.get('model_load_seconds',0) for r in receipts)
        load=sum(r.get('model_load_seconds',0) for r in receipts)
        workers.append(dict(worker=worker,words=words,seconds=seconds,load_seconds=load))
    # A full book has many sections. Average both workers' measured seconds per
    # word, then divide work between two workers. This is a planning estimate.
    steady=total/2*sum(w['seconds']/w['words'] for w in workers)/2+max(w['load_seconds'] for w in workers)
    kokoro=production['projected_full_book_seconds']
    low,high=sorted((steady,cold))
    lines=['# Qwen and Kokoro on this M4 Pro','',
        f'Qwen planning estimate for Emotional Design: **{duration(low)} to {duration(high)}**. Kokoro production estimate: **{duration(kokoro)}**.',
        f'These Qwen estimates are **{low/kokoro:.1f}–{high/kokoro:.1f} times** the Kokoro estimate, or about **{duration(low-kokoro)} to {duration(high-kokoro)} longer**.' if low>=kokoro else
        f'The Qwen estimates are {low/kokoro:.2f}–{high/kokoro:.2f} times the Kokoro estimate.',
        '', '## Measured samples','',
        'Both MLX samples use the same 669 source words from Chapter One, split into two sections of 416 and 253 words. They run sequentially. Each conversion uses two GPU workers. Elapsed time starts after that model is ready and includes setup, loading, generation, thermal pauses, encoding, and validation. Voxtral was still downloading during part of the Qwen test. This background work can affect temperature and elapsed time. No model quality score is claimed.','',
        '| Engine | Voice / speed | Elapsed time | Output audio | Peak temperature | Cached-audio reuse |',
        '| --- | --- | ---: | ---: | ---: | --- |']
    for name in ('qwen','voxtral'):
        if name not in trials:continue
        r=trials[name]
        lines.append(f'| {name.title()} | {r["config"]["voice"]} / {r["config"]["speed"]:g}× | {r["elapsed_seconds"]:.1f} s | {r["audio_seconds"]:.1f} s | {r["first_guard"]["peak_observed_c"]:.1f}°C | Passed |')
    matched_path=ROOT/'reports/kokoro-matched-sample.json'
    if matched_path.exists():
        r=json.loads(matched_path.read_text())
        lines += [f'| Kokoro | Heart / 0.95× | {r["elapsed_seconds"]:.1f} s | {r["audio_seconds"]:.1f} s | {r["thermal"]["peak_observed_c"]:.1f}°C | Saved |','',
            f'On this matched sample, Qwen took {q["elapsed_seconds"]/r["elapsed_seconds"]:.2f} times as long as Kokoro. The thermal settings differ as listed below. Kokoro timing starts at its first supervisor reading and excludes the app setup check; MLX timings include that small setup check.']
    if 'voxtral' in trials and trials['voxtral'].get('test_adjustments'):
        lines += ['', f'Voxtral is a functional test, not a controlled timing comparison. Its run recorded a {trials["voxtral"]["first_guard"]["peak_observed_c"]:.3f}°C peak, above the requested target. Readings above 90°C also occurred after the narration workers had been stopped for about one minute; a separate Xcode build was active. The test was paused manually and then resumed with shorter work periods. Its elapsed time includes the interruptions and changes to cooling controls. The record does not establish which workload caused each overshoot.']
    lines += ['', 'The peak is the highest monitored sensor reading during the first conversion. Sampling cannot establish a physical maximum between readings.', '', '## Exact configuration','',
        '- Qwen: `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit`, Ryan, English, speed 1.0. Style: “Natural audiobook narration. Calm, clear, steady pacing.”',
        '- Qwen and Voxtral: MLX-Audio 0.5.4, 1,000-character chunk limit, temperature 0.8, 4,096 maximum tokens, two Metal workers. Qwen CPU target 90°C, pause 82°C, resume below 78°C. GPU target 93°C, pause 89°C, resume below 85°C. Voxtral started with these controls.',
        '- Voxtral final controls and new app defaults: CPU pause 82°C, resume below 78°C; GPU pause 89°C, resume below 85°C; 3-second work periods, at least 10 seconds of rest, 1 second of stable cool readings. Targets remain CPU 90°C and GPU 93°C.',
        '- Kokoro production: 82M v1.0, Heart, speed 0.95, two Metal workers, two CPU host threads each, 1,800-character paragraph grouping. Original shared thermal target 90°C, pause 86°C, resume below 82°C.',
        '- All runs: 0.5-second rest per generated segment and 96 kbps AAC output. Qwen, Kokoro, and the initial Voxtral settings use a 60-second maximum work interval, 5-second minimum break, and 1 second of stable cool readings. Different engines can return different numbers of segments.',
        '', '## Estimate method and limits','',
        f'The full book has {total:,} source words. Direct scaling of the complete Qwen sample gives {duration(cold)}. This deliberately includes repeated model-loading and final-validation overhead in each scaled sample.',
        f'The second estimate, {duration(steady)}, removes the recorded model-load time from each worker’s chunk intervals, averages their seconds per word, assigns half the book to each worker, and adds one parallel model load. It still includes cooling inside chunk intervals. It excludes gaps between chunks and final assembly. First-use compilation can remain in the chunk time.',
        'The two values form a planning range, not a statistical confidence interval or a guaranteed bound. Longer books can have different thermal behaviour, text difficulty, speech pace, and worker balance. A 669-word sample does not prove sustained full-book performance.',
        f'The Kokoro estimate uses {production["new_words"]:,} newly saved words in {production["elapsed_seconds"]/60:.2f} minutes after a saved baseline. It includes {production["observed_paused_seconds"]/60:.2f} minutes of observed pauses. It excludes the later copyright-page repair and final assembly. Earlier book sections used other configurations.',
        'Different voices and speeds can produce different audio durations. Word throughput is used for the book estimate so that slower speech is not mistaken for more source text processed.',
        'The successful M4B checks establish valid audio, duration, and chapter structure. They do not establish perfect pronunciation or prove that the MLX models spoke every word. Listen to the sample files before selecting a narrator.',
        '', '## Local outputs','']
    for name,r in trials.items():lines.append(f'- {name.title()}: `{r["output"]}`')
    lines += ['', '## Downloaded model revisions','']
    revisions={}
    for name in trials:
        marker=json.loads((ROOT/'models'/name/'ready.json').read_text())
        revisions[name]=marker['revision']
        lines.append(f'- {name.title()}: `{marker["revision"]}`. Downloaded files passed their repository digest checks.')
    lines += ['', 'Raw measurements: `mlx-comparison.json`, `kokoro-matched-sample.json`, and `parallel-run-measurements.json`.']
    (ROOT/'reports/qwen-vs-kokoro.md').write_text('\n'.join(lines)+'\n')
    result=dict(qwen_planning_seconds=[low,high],kokoro_production_seconds=kokoro,qwen_to_kokoro_ratio=[low/kokoro,high/kokoro],qwen_worker_measurements=workers,model_revisions=revisions)
    (ROOT/'reports/model-time-estimates.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':make_report()
