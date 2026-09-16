"""Read verified receipts from all narration workers without loading the model."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'kokoro-heart-build'
tree = ast.parse((ROOT / 'kokoro_audiobook.py').read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'batches')
scope = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), 'batches', 'exec'), scope)
chapters = json.loads((ROOT / 'chapters.json').read_text())
saved, total, frames = 0, 0, 0
remaining = []
for chapter in chapters:
    missing = 0
    for n, part in enumerate(scope['batches']((ROOT / 'build' / (chapter['file'] + '.txt')).read_text()), 1):
        words = len(part.split())
        total += words
        receipt = WORK / chapter['file'] / f'{n:04d}.json'
        signature = hashlib.sha256(('af_heart0.95' + part).encode()).hexdigest()
        try:
            data = json.loads(receipt.read_text())
            good = data['signature'] == signature and receipt.with_suffix('.flac').exists()
        except (OSError, ValueError, KeyError):
            good = False
        if good:
            saved += words
            frames += data['frames']
        else:
            missing += words
    if missing:
        remaining.append({'section': chapter['file'], 'remaining_words': missing})
status = {'saved_words': saved, 'total_words': total, 'percent': round(saved / total * 100, 1),
          'audio_hours_saved': round(frames / 24000 / 3600, 2), 'remaining': remaining,
          'thermal': json.loads((WORK / 'temperature-status.json').read_text())}
print(json.dumps(status, indent=2))
