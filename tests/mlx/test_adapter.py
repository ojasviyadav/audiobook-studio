import unittest
from unittest.mock import Mock
import numpy as np
from scripts.mlx_backend import request_audio, normalize_audio, MLXAudioBackend
from types import SimpleNamespace
from scripts.runtime_settings import validate

class AdapterTests(unittest.TestCase):
    def test_token_limited_or_empty_generation_cannot_be_saved(self):
        engine=MLXAudioBackend.__new__(MLXAudioBackend)
        engine.config=validate({'backend':'qwen','voice':'Ryan'})
        engine.model=Mock()
        engine.model.generate_custom_voice.return_value=iter([SimpleNamespace(token_count=4096)])
        with self.assertRaisesRegex(RuntimeError,'token limit'):list(engine.generate('A passage.'))
        engine.model.generate_custom_voice.return_value=iter([])
        with self.assertRaisesRegex(RuntimeError,'no audio'):list(engine.generate('A passage.'))
    def test_presets_use_the_right_api_and_keep_all_results(self):
        model=Mock(); a=object(); b=object()
        model.generate_custom_voice.return_value=iter([a,b])
        c=validate({'backend':'qwen','voice':'Ryan','speed':1})
        self.assertEqual(list(request_audio(model,c,'Hello.')),[a,b])
        kw=model.generate_custom_voice.call_args.kwargs
        self.assertEqual(kw['speaker'],'Ryan')
        self.assertEqual(kw['language'],'English')
        self.assertFalse(kw['stream'])
        self.assertEqual(kw['instruct'],c['instruct'])
        model.generate.return_value=iter([a,b])
        c=validate({'backend':'voxtral','voice':'neutral_male','speed':1})
        self.assertEqual(list(request_audio(model,c,'Hello.')),[a,b])
        kw=model.generate.call_args.kwargs
        self.assertEqual(kw['voice'],'neutral_male')
        self.assertNotIn('instruct',kw)
        self.assertNotIn('ref_audio',kw)
    def test_sample_rate_and_speed_preserve_expected_duration(self):
        audio=(.2*np.sin(2*np.pi*440*np.arange(48000)/48000)).astype(np.float32)
        self.assertEqual(len(normalize_audio(audio,48000,1)),24000)
        slow=normalize_audio(audio,48000,.8)
        self.assertAlmostEqual(len(slow)/24000,1.25,delta=.06)
        with self.assertRaises(ValueError):normalize_audio(np.array([np.nan]),24000,1)
        with self.assertRaises(ValueError):normalize_audio(np.zeros(100),24000,1)

if __name__=='__main__':unittest.main()
