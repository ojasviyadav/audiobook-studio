import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from scripts.runtime_settings import validate, lock_audio_settings, atomic_json
from scripts.tts_contract import narration_batches, audio_signature, VOICES


class EngineTests(unittest.TestCase):
    def test_voxtral_starts_with_short_work_periods_but_keeps_explicit_controls(self):
        c=validate({'backend':'voxtral','voice':'neutral_male'})
        self.assertEqual((c['pause_c'],c['resume_c'],c['work_seconds'],c['rest_seconds']),(82,78,3,10))
        self.assertEqual((c['ceiling_c'],c['gpu_ceiling_c']),(90,93))
        self.assertEqual(validate(c|{'work_seconds':2})['work_seconds'],2)

    def test_legacy_settings_and_receipts_keep_their_identity(self):
        c=validate({'voice':'af_heart','speed':.95})
        text='A short paragraph.\n\nThe next paragraph.'
        self.assertEqual(c['backend'],'kokoro')
        self.assertEqual(list(narration_batches(text,c)),[text])
        self.assertEqual(audio_signature(c,text),hashlib.sha256(('af_heart0.95'+text).encode()).hexdigest())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); receipt=p/'kokoro-heart-build/01/0001.json';receipt.parent.mkdir(parents=True)
            atomic_json(receipt,{'voice':'af_heart','speed':.95})
            atomic_json(p/'narration-settings.json',{'voice':'af_heart','speed':.95,'bitrate':96,'paragraph_gap':.2,'chapter_gap':1})
            lock_audio_settings(p,c)
            with self.assertRaisesRegex(ValueError,'Saved audio'):
                lock_audio_settings(p,validate(c|{'backend':'qwen','voice':'Ryan'}))

    def test_chunks_are_bounded_and_keep_every_character_of_text(self):
        text=('One complete sentence. '*130)+'\n\n'+('Another paragraph. '*90)+'\n\nLast.'
        for backend in ('qwen','voxtral'):
            for limit in (500,1000,1500):
                pieces=list(narration_batches(text,{'backend':backend,'chunk_chars':limit}))
                self.assertTrue(all(0<len(p)<=limit for p in pieces))
                normal=lambda value:re.sub(r'\s+','',value)
                self.assertEqual(normal(''.join(pieces)),normal(text))
                self.assertEqual(sum(len(p.split()) for p in pieces),len(text.split()))

    def test_engine_voice_style_and_chunk_changes_invalidate_saved_audio(self):
        c=validate({'backend':'qwen','voice':'Ryan','speed':1})
        sig=audio_signature(c,'Read this.')
        for delta in ({'voice':'Aiden'},{'instruct':'Excited'},{'chunk_chars':500},
                      {'temperature':.6},{'backend':'voxtral','voice':'neutral_male'}):
            self.assertNotEqual(sig,audio_signature(validate(c|delta),'Read this.'))
        with self.assertRaises(ValueError): validate(c|{'backend':'voxtral'})
        self.assertEqual(len(VOICES['voxtral']),20)

    def test_generation_options_lock_with_saved_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); c=validate({'backend':'qwen','voice':'Ryan'})
            lock_audio_settings(p,c)
            receipt=p/'kokoro-heart-build/01/0001.json';receipt.parent.mkdir(parents=True)
            atomic_json(receipt,dict(voice='Ryan',speed=.95))
            lock_audio_settings(p,c)
            with self.assertRaises(ValueError):lock_audio_settings(p,c|{'instruct':'Different'})


if __name__=='__main__':unittest.main()
