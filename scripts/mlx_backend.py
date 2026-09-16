"""Preset-only MLX-Audio backends; one loaded model per GPU worker."""
from pathlib import Path
import math
import subprocess
import time
import numpy as np
from scipy.signal import resample_poly
try:
    from .tts_contract import MODELS
except ImportError:
    from tts_contract import MODELS

RATE = 24000

def request_audio(model, config, text):
    common = dict(text=text, temperature=config['temperature'],
                  max_tokens=config['max_tokens'], stream=False, verbose=False)
    if config['backend'] == 'qwen':
        return model.generate_custom_voice(**common, speaker=config['voice'],
                    language='English', instruct=config['instruct'] or None)
    return model.generate(**common, voice=config['voice'])

def normalize_audio(audio, sample_rate, speed):
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError('The model returned invalid or empty audio.')
    if sample_rate != RATE:
        factor = math.gcd(int(sample_rate), RATE)
        audio = resample_poly(audio, RATE//factor, int(sample_rate)//factor).astype(np.float32)
    if speed != 1:
        # These model APIs have no speed argument. Preserve pitch with atempo.
        result = subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar',str(RATE),'-ac','1',
            '-i','pipe:0','-af',f'atempo={speed}','-f','f32le','pipe:1'],input=audio.tobytes(),
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        audio = np.frombuffer(result.stdout,dtype=np.float32).copy()
    if not audio.size or not np.isfinite(audio).all() or np.sqrt(np.mean(audio**2)) <= .0001:
        raise ValueError('The model returned silent or invalid audio.')
    return audio

class MLXAudioBackend:
    def __init__(self, config):
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model
        if not mx.metal.is_available(): raise RuntimeError('Metal GPU processing is unavailable.')
        mx.set_default_device(mx.gpu)
        self.config = config
        path = Path(__file__).resolve().parents[1]/'models'/config['backend']
        if not (path/'config.json').is_file():
            raise RuntimeError('Download this model in Setup before starting.')
        started = time.monotonic()
        self.model = load_model(str(path))
        self.load_seconds = time.monotonic() - started
        print(f'{config["backend"]} model loaded in {self.load_seconds:.3f} seconds.', flush=True)

    def generate(self, text):
        count = 0
        for result in request_audio(self.model,self.config,text):
            if result.token_count >= self.config['max_tokens']:
                raise RuntimeError('Generation reached its token limit. Use a smaller chunk or a larger token limit in a new project.')
            count += 1
            yield normalize_audio(result.audio,result.sample_rate,self.config['speed'])
        if not count: raise RuntimeError('The model returned no audio.')
