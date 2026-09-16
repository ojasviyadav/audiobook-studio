"""Create a resumable local Kokoro audiobook from the verified EPUB text."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import time
import signal
import sys
import argparse

GUARDED = bool(os.environ.get('KOKORO_THERMAL_GUARD_PID')) and os.environ.get('KOKORO_PARENT_PID', os.environ.get('KOKORO_THERMAL_GUARD_PID')) == str(os.getppid())
if not GUARDED:
    raise SystemExit('Start this job with temperature_guard.py so live temperature control is active.')
from temperature_guard import start_guard_watchdog
start_guard_watchdog()
parser = argparse.ArgumentParser()
parser.add_argument('--device', choices=['cpu', 'mps'], default='mps')
parser.add_argument('--worker', type=int, choices=[0, 1, 2])
parser.add_argument('--assemble-only', action='store_true')
args = parser.parse_args()

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_OFFLINE', '1')

import numpy as np
import soundfile as sf
import torch
from kokoro import KModel, KPipeline

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ['AUDIOBOOK_PROJECT']).resolve()
WORK = ROOT / 'kokoro-heart-build'
WORK.mkdir(exist_ok=True)
RATE = 24000
CONFIG = json.loads((ROOT / 'book.json').read_text())
VOICE = CONFIG.get('voice', 'af_heart')
SPEED = CONFIG.get('speed', 0.95)
NORMAL = lambda x: re.sub(r'\s+', '', x)

def thermal_state():
    # Stop on probe failure. Nominal thermal state is required for more work.
    state = subprocess.check_output(['osascript', '-l', 'JavaScript', '-e',
        'ObjC.import("Foundation"); $.NSProcessInfo.processInfo.thermalState'],
        text=True, timeout=5).strip()
    if state not in {'0', '1', '2', '3'}:
        raise RuntimeError(f'Cannot read macOS thermal state: {state!r}')
    return int(state)

def wait_until_cool():
    if GUARDED:
        # The supervisor already samples real temperatures. A subprocess wall
        # timeout here would also count SIGSTOP cooling time and fail on resume.
        return
    while thermal_state() != 0:
        print('Cooling break: macOS thermal state is above nominal.', flush=True)
        time.sleep(30)

def cooling_break(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(min(30, max(0, deadline - time.monotonic())))
    wait_until_cool()

def run(args):
    # Also limit audio encoding and validation to short work periods.
    wait_until_cool()
    if GUARDED:
        # The separate supervisor controls this entire process group,
        # including ffmpeg, using live CPU/GPU sensor measurements.
        subprocess.run([str(x) for x in args], check=True)
        return
    proc = subprocess.Popen([str(x) for x in args])
    try:
        while proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.send_signal(signal.SIGSTOP)
                cooling_break(20)
                proc.send_signal(signal.SIGCONT)
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, args)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.send_signal(signal.SIGCONT)
            proc.wait()

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-show_chapters', '-of', 'json', str(path)]))

def batches(text, limit=1800):
    # Keep complete paragraphs together where possible. Kokoro handles the
    # phoneme limit within each paragraph without dropping text.
    pending = []
    size = 0
    for paragraph in text.split('\n\n'):
        if pending and size + len(paragraph) > limit:
            yield '\n\n'.join(pending)
            pending, size = [], 0
        pending.append(paragraph)
        size += len(paragraph) + 2
    if pending:
        yield '\n\n'.join(pending)

torch.set_num_threads(4 if args.device == 'cpu' and not args.assemble_only else 2)
torch.set_num_interop_threads(1)
os.nice(15)
chapters = json.loads((ROOT / 'chapters.json').read_text())
assignment = json.loads((WORK / 'parallel-plan.json').read_text()) if args.worker is not None else {}
if args.worker is not None:
    assert set(assignment) == {c['file'] for c in chapters}
    assert set(assignment.values()).issubset({0, 1, 2})
device = args.device
wait_until_cool()
model_dir = Path(CONFIG['model_dir'])
weights = model_dir / 'kokoro-v1_0.pth'
assert hashlib.sha256(weights.read_bytes()).hexdigest() == '496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4'
if not args.assemble_only:
    if device == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('Metal GPU processing is unavailable.')
    model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(model_dir / 'config.json'), model=str(weights)).to(device).eval()
    pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', model=model)
    pipeline.load_voice(VOICE)
total_words = sum(c['words'] for c in chapters)
completed_words = 0
for chapter in chapters:
    text = (ROOT / 'build' / (chapter['file'] + '.txt')).read_text()
    for number, part in enumerate(batches(text), 1):
        folder = WORK / chapter['file']
        receipt = folder / f'{number:04d}.json'
        signature = hashlib.sha256((VOICE + str(SPEED) + part).encode()).hexdigest()
        if (folder / f'{number:04d}.flac').exists() and receipt.exists() and json.loads(receipt.read_text())['signature'] == signature:
            completed_words += len(part.split())
started = time.monotonic()
print(f'{VOICE}, speed {SPEED}; device={device}, threads={torch.get_num_threads()}, temperature supervisor={GUARDED}. {completed_words:,}/{total_words:,} words already saved.', flush=True)

for index, chapter in enumerate(chapters, 1):
    # Disjoint section ownership prevents all audio/receipt/encoding collisions.
    if args.worker is not None and assignment[chapter['file']] != args.worker:
        continue
    stem = chapter['file']
    text = (ROOT / 'build' / (stem + '.txt')).read_text()
    parts = list(batches(text))
    assert NORMAL(''.join(parts)) == NORMAL(text)
    folder = WORK / stem
    folder.mkdir(exist_ok=True)
    print(f'[{index}/{len(chapters)}] {chapter["title"]}: {len(parts)} batches.', flush=True)
    samples = []
    for number, part in enumerate(parts, 1):
        dest = folder / f'{number:04d}.flac'
        receipt = folder / f'{number:04d}.json'
        signature = hashlib.sha256((VOICE + str(SPEED) + part).encode()).hexdigest()
        if dest.exists() and receipt.exists() and json.loads(receipt.read_text())['signature'] == signature:
            frames = sf.info(dest).frames
        else:
            if args.assemble_only:
                raise RuntimeError(f'Missing verified audio: {stem}/{number}; cannot assemble.')
            audio_parts, spoken = [], []
            wait_until_cool()
            segment_started = time.monotonic()
            for result in pipeline(part, voice=VOICE, speed=SPEED, split_pattern=r'\n\n+'):
                assert result.audio is not None, (stem, number, 'Missing audio')
                assert len(result.phonemes) <= 510, (stem, number, 'Phoneme limit')
                audio = result.audio.detach().cpu().numpy()
                assert len(audio) > 0 and np.isfinite(audio).all()
                assert np.sqrt(np.mean(audio ** 2)) > 0.0001
                audio_parts.extend([audio, np.zeros(round(RATE * CONFIG.get('paragraph_gap', 0.2)), dtype=np.float32)])
                spoken.append(result.graphemes)
                # Rest for at least three times the segment's processing time.
                # Small segments still receive a minimum 15-second break.
                cooling_break(CONFIG.get('segment_rest', 0.5) if GUARDED else max(15, 3 * (time.monotonic() - segment_started)))
                segment_started = time.monotonic()
            assert NORMAL(''.join(spoken)) == NORMAL(part), (stem, number, 'Text coverage mismatch', part, spoken)
            combined = np.concatenate(audio_parts)
            temp = folder / f'{number:04d}.part.flac'
            sf.write(temp, combined, RATE, subtype='PCM_16')
            temp.replace(dest)
            frames = len(combined)
            receipt.write_text(json.dumps({'signature': signature, 'frames': frames, 'text_coverage': True, 'voice': VOICE, 'speed': SPEED, 'device': device, 'threads': torch.get_num_threads()}))
            completed_words += len(part.split())
        samples.append(dest)
        elapsed = time.monotonic() - started
        status = {'section': index, 'sections': len(chapters), 'title': chapter['title'], 'batch': number, 'batches': len(parts), 'completed_words': completed_words, 'total_words': total_words, 'percent': round(100 * completed_words/total_words, 1), 'elapsed_seconds': round(elapsed, 1)}
        status['device'] = device
        status['worker'] = args.worker
        status['percent_is_lower_bound'] = args.worker is not None
        status_name = f'status-parallel-{args.worker}.json' if args.worker is not None else 'status-low-load.json'
        (WORK / status_name).write_text(json.dumps(status, indent=2))
        if number % 5 == 0 or number == len(parts):
            print(f'  Batch {number}/{len(parts)}; overall {status["percent"]}%; elapsed {elapsed/60:.1f} min.', flush=True)
    m4a = WORK / (stem + '.m4a')
    expected_duration = sum(sf.info(sample).frames for sample in samples) / RATE + CONFIG.get('chapter_gap', 1.0)
    if m4a.exists():
        try:
            duration = float(probe(m4a)['format']['duration'])
            if abs(duration - expected_duration) < 0.1:
                chapter['duration'] = duration
                print('  Reusing completed section audio.', flush=True)
                continue
        except (subprocess.CalledProcessError, KeyError, ValueError):
            pass
    chapter_wav = WORK / (stem + '.wav')
    with sf.SoundFile(chapter_wav, 'w', samplerate=RATE, channels=1, subtype='PCM_16') as target:
        for sample in samples:
            audio, sample_rate = sf.read(sample, dtype='float32')
            assert sample_rate == RATE
            target.write(audio)
        target.write(np.zeros(round(RATE * CONFIG.get('chapter_gap', 1.0)), dtype=np.float32))
    run(['ffmpeg', '-v', 'error', '-y', '-i', chapter_wav, '-c:a', 'aac', '-b:a', str(CONFIG.get('bitrate', 96)) + 'k', m4a])
    chapter['duration'] = float(probe(m4a)['format']['duration'])
    chapter_wav.unlink()
    print(f'  Section complete: {chapter["duration"]/60:.1f} min audio.', flush=True)

if args.worker is not None:
    print(f'Worker {args.worker} ({device}) completed its sections.', flush=True)
    sys.exit(0)

def escape(value):
    return re.sub(r'([\\=;#])', r'\\\1', value).replace('\n', ' ')

metadata = [';FFMETADATA1', 'title=' + escape(CONFIG['title'] + ' — ' + VOICE), 'artist=' + escape(CONFIG['author']), 'album=' + escape(CONFIG['title']), 'genre=Audiobook', 'comment=AI-generated narration: Kokoro ' + VOICE + ', speed ' + str(SPEED) + '. Refer to the EPUB for images.']
elapsed_ms = 0
for chapter in chapters:
    end = elapsed_ms + round(chapter['duration'] * 1000)
    metadata += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={elapsed_ms}', f'END={end}', 'title=' + escape(chapter['title'])]
    elapsed_ms = end
(WORK / 'metadata.txt').write_text('\n'.join(metadata) + '\n')
(WORK / 'concat.txt').write_text(''.join(f"file '{c['file']}.m4a'\n" for c in chapters))
cover = Path(CONFIG['cover']) if CONFIG.get('cover') else None
output = ROOT / CONFIG['output_name']
temporary = output.with_name(output.stem + '.partial.m4b')
print('Combining the audiobook and checking all audio.', flush=True)
mux = ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', WORK / 'concat.txt', '-i', WORK / 'metadata.txt']
if cover:
    mux += ['-i', cover, '-map', '0:a', '-map', '2:v', '-disposition:v', 'attached_pic']
else:
    mux += ['-map', '0:a']
mux += ['-map_metadata', '1', '-map_chapters', '1', '-c', 'copy', '-metadata', 'media_type=2', '-movflags', '+faststart', temporary]
run(mux)
info = probe(temporary)
assert len(info['chapters']) == len(chapters)
assert abs(float(info['format']['duration']) - sum(c['duration'] for c in chapters)) < 3
assert all(c['tags']['title'] == expected['title'] for c, expected in zip(info['chapters'], chapters))
run(['ffmpeg', '-v', 'error', '-xerror', '-i', temporary, '-map', '0:a', '-f', 'null', '-'])
temporary.replace(output)
(WORK / 'chapters.json').write_text(json.dumps(chapters, indent=2))
(WORK / 'verification.json').write_text(json.dumps(info, indent=2))
(WORK / 'status.json').write_text(json.dumps({'complete': True, 'output': str(output), 'duration_seconds': float(info['format']['duration']), 'chapters': len(chapters), 'size_bytes': output.stat().st_size}, indent=2))
print(f'COMPLETE: {output}; {float(info["format"]["duration"])/3600:.2f} hours, {output.stat().st_size/1000000:.1f} MB.', flush=True)
