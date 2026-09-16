"""Shared model choices, chunk boundaries and cache identity. No ML imports."""
import hashlib
import json
import re

def kokoro_coverage(text):
    """Match two observed tokenizer normalizations without removing words.

    Numeric apostrophes are omitted by the English tokenizer. A paragraph that
    consists only of a slash has no phonemes and produces no speech result.
    All other characters retain the existing strict comparison.
    """
    text = '\n\n'.join(p for p in text.split('\n\n') if p.strip() != '/')
    text = re.sub(r"(?<=\d)[‘’'](?=\d)", '', text)
    return re.sub(r'\s+', '', text)

MODELS = {
    'qwen': 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit',
    'voxtral': 'mlx-community/Voxtral-4B-TTS-2603-mlx-4bit',
}
VOICES = {
    'kokoro': ('af_heart', 'af_bella', 'am_michael'),
    'qwen': ('Ryan', 'Aiden'),
    'voxtral': ('casual_male', 'casual_female', 'cheerful_female', 'neutral_male',
                'neutral_female', 'fr_male', 'fr_female', 'es_male', 'es_female',
                'de_male', 'de_female', 'it_male', 'it_female', 'pt_male', 'pt_female',
                'nl_male', 'nl_female', 'ar_male', 'hi_male', 'hi_female'),
}

def legacy_batches(text, limit=1800):
    pending, size = [], 0
    for paragraph in text.split('\n\n'):
        if pending and size + len(paragraph) > limit:
            yield '\n\n'.join(pending)
            pending, size = [], 0
        pending.append(paragraph)
        size += len(paragraph) + 2
    if pending:
        yield '\n\n'.join(pending)

def narration_batches(text, config):
    if config.get('backend', 'kokoro') == 'kokoro':
        yield from legacy_batches(text)
        return
    limit = int(config.get('chunk_chars', 1000))
    pending = ''
    for paragraph in text.split('\n\n'):
        paragraph = paragraph.strip()
        if not paragraph: continue
        if pending and len(pending) + len(paragraph) + 2 > limit:
            yield pending; pending = ''
        while len(paragraph) > limit:
            # Prefer a sentence or word boundary. Never discard source text.
            end = max(paragraph.rfind('. ', 0, limit), paragraph.rfind('! ', 0, limit), paragraph.rfind('? ', 0, limit))
            end = end + 1 if end >= limit // 2 else paragraph.rfind(' ', 0, limit)
            if end <= 0: end = limit
            yield paragraph[:end].strip()
            paragraph = paragraph[end:].strip()
        if paragraph:
            pending = pending + '\n\n' + paragraph if pending else paragraph
    if pending: yield pending

def audio_settings(config):
    engine = config.get('backend', 'kokoro')
    values = {k:config.get(k, d) for k,d in dict(voice='af_heart', speed=.95,
        bitrate=96, paragraph_gap=.2, chapter_gap=1).items()}
    values['backend'] = engine
    if engine != 'kokoro':
        values.update(model=config.get('model',MODELS[engine]), chunk_chars=config.get('chunk_chars',1000),
                      temperature=config.get('temperature',.8), max_tokens=config.get('max_tokens',4096))
        if engine == 'qwen': values['instruct'] = config.get('instruct','')
    return values

def audio_signature(config, text):
    if config.get('backend', 'kokoro') == 'kokoro':
        # Preserve all existing Kokoro receipts exactly.
        payload = config['voice'] + str(config['speed']) + text
    else:
        payload = json.dumps(audio_settings(config),sort_keys=True) + '\n' + text
    return hashlib.sha256(payload.encode()).hexdigest()
