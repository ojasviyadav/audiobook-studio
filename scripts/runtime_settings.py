"""Validated user controls. GPU topology is deliberately not configurable."""
import json
import math
import tempfile
from pathlib import Path

DEFAULTS = dict(voice='af_heart', speed=0.95, bitrate=96, paragraph_gap=0.2,
                chapter_gap=1.0, segment_rest=0.5, ceiling_c=90.0, pause_c=86.0,
                resume_c=82.0, work_seconds=60.0, rest_seconds=5.0, stable_seconds=1.0)
AUDIO_KEYS = ('voice', 'speed', 'bitrate', 'paragraph_gap', 'chapter_gap')

def validate(config):
    c = DEFAULTS | config
    if c['voice'] not in ('af_heart', 'af_bella', 'am_michael'):
        raise ValueError('Select Heart, Bella, or Michael.')
    limits = dict(speed=(0.5,2), paragraph_gap=(0,3), chapter_gap=(0,10),
                  segment_rest=(0,5), ceiling_c=(50,90), work_seconds=(1,600),
                  rest_seconds=(1,600), stable_seconds=(0.5,30))
    for key,(low,high) in limits.items():
        if not isinstance(c[key], (int,float)) or not math.isfinite(c[key]) or not low <= c[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
    if not 40 <= c['resume_c'] < c['pause_c'] <= c['ceiling_c'] - 2:
        raise ValueError('Resume must be below pause. Pause must be at least 2°C below the target.')
    if c['bitrate'] not in (64,96,128,192):
        raise ValueError('Select an audio rate of 64, 96, 128, or 192 kbps.')
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
    desired = {k:config[k] for k in AUDIO_KEYS}
    previous = json.loads(target.read_text()) if target.exists() else None
    if receipts and previous is None:
        receipt = json.loads(receipts[0].read_text())
        previous = {k:DEFAULTS[k] for k in AUDIO_KEYS}
        previous.update(voice=receipt['voice'],speed=receipt['speed'])
    if receipts and previous != desired:
        raise ValueError('Saved audio already exists. Create a new project to change voice, speed, gaps, or audio quality.')
    atomic_json(target, desired)
