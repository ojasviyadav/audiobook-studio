# Narration engines

The app uses preset voices only. It does not use TADA or a voice-cloning model.

| Engine | Fixed checkpoint | Voices in the app | License on model page |
| --- | --- | --- | --- |
| Qwen3-TTS 1.7B CustomVoice, 6-bit | `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit` | Ryan (default), Aiden | Apache-2.0 |
| Voxtral 4B TTS, 4-bit | `mlx-community/Voxtral-4B-TTS-2603-mlx-4bit` | 20 presets | CC-BY-NC-4.0 |
| Kokoro 82M v1.0 | Existing local `kokoro-v1_0.pth` | Heart, Bella, Michael | See the Kokoro model license |

Qwen defaults to Ryan at 1.25× speed for new books. The earlier timing sample used 1.0×. Qwen accepts style instructions. The default is calm, clear audiobook narration. Its English language setting is fixed. Voxtral uses the language of its selected voice. English voices are casual male, casual female, cheerful female, neutral male, and neutral female. Other presets have language prefixes: `fr`, `es`, `de`, `it`, `pt`, `nl`, `ar`, and `hi`.

Sources: [Qwen checkpoint](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit), [Qwen API](https://github.com/Blaizzy/mlx-audio/blob/main/docs/models/tts/qwen3-tts.md), [Voxtral checkpoint and voices](https://huggingface.co/mlx-community/Voxtral-4B-TTS-2603-mlx-4bit).

## Processing

EPUB extraction is shared by all engines. New MLX projects use a default 1,000-character chunk limit. The app permits 500–1,500 characters. This is a maximum, not a minimum: a final paragraph or section can be shorter. Saved chunks use FLAC at 24 kHz. FFmpeg creates chapter audio and the final M4B.

Two independent workers use the GPU. This count is fixed. They work on separate sections. Each worker loads its own model. The GPU runtime chooses how to use the GPU cores. The new engines have not inherited a claim that two workers are faster than one: the earlier measured comparison applies to Kokoro only.

The temperature guard controls the complete process group, including encoding. The CPU target remains 90°C. On 17 September 2026, the user permitted a GPU target of 93°C. The updated monitor checks the two sensor groups separately. Qwen projects pause for CPU heat at 82°C and resume below 78°C. Qwen GPU defaults are pause at 89°C and resume below 85°C. Voxtral now uses CPU pause/resume 82°C/78°C, GPU 89°C/85°C, 3-second work periods, at least 10 seconds of rest, and 1 second of stable cool readings. Its first local test recorded a reading above 99°C while workers were paused. The test was paused manually and resumed with these shorter work periods. The record does not establish which workload caused the overshoot. Either group can stop work, and both must cool before it resumes. The completed Kokoro production run used shared 86°C/82°C controls. Its log recorded a 92.625°C peak. Sampling and GPU work already submitted mean these targets are not guaranteed physical ceilings.

MLX-Audio 0.5.4 is installed in a separate Python environment. The adapters use `generate_custom_voice` for Qwen and `generate` for Voxtral. They consume every returned audio result. They reject invalid, silent, or token-limited results. The app does not claim speech-to-text verification of generated words.

Qwen and Voxtral do not expose speed in these API calls. The app applies pitch-preserving tempo adjustment after generation. The style and generation controls are included in each chunk's saved identity. Changing an engine or its voice settings requires a new project once audio exists.

The model pages contain published throughput results. They are not measurements from this Mac. This repository keeps measured local results separate from those claims.
