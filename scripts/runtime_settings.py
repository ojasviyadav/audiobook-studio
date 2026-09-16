"""Validated user controls. GPU topology is deliberately not configurable."""
import json
import math
import tempfile
from pathlib import Path
try:
    from .tts_contract import VOICES, audio_settings
except ImportError:
    from tts_contract import VOICES, audio_settings

DEFAULTS = dict(voice='af_heart', speed=0.95, bitrate=96, paragraph_gap=0.2,
                chapter_gap=1.0, segment_rest=0.5, ceiling_c=90.0, pause_c=86.0,
                resume_c=82.0, work_seconds=60.0, rest_seconds=5.0, stable_seconds=1.0,
                gpu_ceiling_c=93.0, gpu_pause_c=89.0, gpu_resume_c=85.0,
                backend='kokoro', chunk_chars=1000, temperature=.8, max_tokens=4096,
                instruct='Natural audiobook narration. Calm, clear, steady pacing.')
AUDIO_KEYS = ('voice', 'speed', 'bitrate', 'paragraph_gap', 'chapter_gap',
              'backend','chunk_chars','temperature','max_tokens','instruct')

def validate(config):
    c = DEFAULTS | config
    if c['backend'] != 'kokoro':
        c['pause_c'] = config.get('pause_c',82.0)
        c['resume_c'] = config.get('resume_c',78.0)
    if c['backend'] == 'voxtral':
        for key,value in dict(work_seconds=3.,rest_seconds=10.).items():
            c[key] = config.get(key,value)
    if c['backend'] not in VOICES: raise ValueError('Select Kokoro, Qwen, or Voxtral.')
    if c['voice'] not in VOICES[c['backend']]:
        raise ValueError('Select a preset voice for this engine.')
    if not isinstance(c['instruct'],str) or len(c['instruct']) > 2000:
        raise ValueError('Style instructions must have no more than 2,000 characters.')
    limits = dict(speed=(0.5,2), paragraph_gap=(0,3), chapter_gap=(0,10),
                  segment_rest=(0,5), ceiling_c=(50,90), gpu_ceiling_c=(50,93), work_seconds=(1,600),
                  rest_seconds=(1,600), stable_seconds=(0.5,30), temperature=(.1,1.5))
    for key,(low,high) in limits.items():
        if not isinstance(c[key], (int,float)) or not math.isfinite(c[key]) or not low <= c[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    if not 40 <= c['resume_c'] < c['pause_c'] <= c['ceiling_c'] - 2:
        raise ValueError('CPU resume must be below pause. Pause must be at least 2°C below the CPU target.')
    if not 40 <= c['gpu_resume_c'] < c['gpu_pause_c'] <= c['gpu_ceiling_c'] - 2:
        raise ValueError('GPU resume must be below pause. Pause must be at least 2°C below the GPU target.')
    if c['bitrate'] not in (64,96,128,192):
        raise ValueError('Select an audio rate of 64, 96, 128, or 192 kbps.')
    for key,low,high in [('chunk_chars',500,1500),('max_tokens',512,8192)]:
        if type(c[key]) is not int or not low <= c[key] <= high:
            raise ValueError(f'{key} must be a whole number between {low} and {high}.')
    if Path(c.get('output_name','book.m4b')).name != c.get('output_name','book.m4b') or not c.get('output_name','book.m4b').lower().endswith('.m4b'):
        raise ValueError('Use a file name ending in .m4b, without a folder path.')
    return c

def atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name+'.', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, indent=2))
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

def lock_audio_settings(project, config):
    project = Path(project)
    target = project/'narration-settings.json'
    receipts = list((project/'kokoro-heart-build').glob('*/*.json'))
    desired = audio_settings(config)
    previous = json.loads(target.read_text()) if target.exists() else None
    if receipts and previous is None:
        receipt = json.loads(receipts[0].read_text())
        previous = dict(DEFAULTS)
        previous.update(voice=receipt['voice'],speed=receipt['speed'])
    if previous is not None: previous = audio_settings(previous)
    if receipts and previous != desired:
        raise ValueError('Saved audio already exists. Create a new project to change the engine, voice, style, chunks, speed, or audio quality.')
    atomic_json(target, desired)
