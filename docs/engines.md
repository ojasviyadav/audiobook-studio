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

### Model selection guide

The app's **Compare models…** panel uses these rules:

- **Quality order:** Qwen, then Voxtral, then Kokoro. This is a suggested listening order. Qwen is the user's preferred narrator; the positions of Voxtral and Kokoro are provisional. There is no measured quality score or blind comparison of these three local checkpoints.
- **Processing groups:** Kokoro has the lowest estimated load. Qwen and Voxtral are in the higher group. Their relative speed and power use have not been established. Model parameter count does not provide a fair speed rank across different model architectures.
- **Local evidence:** Qwen took 301.9 seconds and Kokoro took 115.3 seconds for the same 669 source words. Cooling settings, audio speeds, and some setup overhead differed. The Voxtral test had interruptions and changed cooling settings. Its 904.2-second elapsed time is not shown as a speed ranking. Full details are in the [timing report](../reports/qwen-vs-kokoro.md).
- **Device guidance:** The panel reads the Metal device name and installed memory locally. It identifies M4 Pro / 48 GB as the tested configuration. It does not claim measured speed on other devices. It gives sample-first guidance and does not change the fixed two-worker setup.
- **Model files:** Approximately 2.7 GB for Qwen, 2.5 GB for Voxtral, and 0.33 GB for Kokoro's main weights. These values exclude extra runtime memory and are not minimum RAM specifications. Each worker loads a model. No claim is made that two workers will double speed or use exactly twice the model file size in memory.

Model size and features were checked against the [Qwen MLX checkpoint](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit), [Qwen CustomVoice documentation](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice), [Voxtral MLX checkpoint](https://huggingface.co/mlx-community/Voxtral-4B-TTS-2603-mlx-4bit), and [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M) on 17 September 2026. The local Kokoro weights occupy 327,212,226 bytes. Published model throughput is kept separate from local measurements.

### Audio pipeline

EPUB extraction is shared by all engines. New MLX projects use a default 1,000-character chunk limit. The app permits 500–1,500 characters. This is a maximum, not a minimum: a final paragraph or section can be shorter. Saved chunks use FLAC at 24 kHz. FFmpeg creates chapter audio and the final M4B.

Two independent workers use the GPU. This count is fixed. They work on separate sections. Each worker loads its own model. The GPU runtime chooses how to use the GPU cores. The new engines have not inherited a claim that two workers are faster than one: the earlier measured comparison applies to Kokoro only.

The temperature guard controls the complete process group, including encoding. The CPU target remains 90°C. On 17 September 2026, the user permitted a GPU target of 93°C. The updated monitor checks the two sensor groups separately. Qwen projects pause for CPU heat at 82°C and resume below 78°C. Qwen GPU defaults are pause at 89°C and resume below 85°C. Voxtral now uses CPU pause/resume 82°C/78°C, GPU 89°C/85°C, 3-second work periods, at least 10 seconds of rest, and 1 second of stable cool readings. Its first local test recorded a reading above 99°C while workers were paused. The test was paused manually and resumed with these shorter work periods. The record does not establish which workload caused the overshoot. Either group can stop work, and both must cool before it resumes. The completed Kokoro production run used shared 86°C/82°C controls. Its log recorded a 92.625°C peak. Sampling and GPU work already submitted mean these targets are not guaranteed physical ceilings.

MLX-Audio 0.5.4 is installed in a separate Python environment. The adapters use `generate_custom_voice` for Qwen and `generate` for Voxtral. They consume every returned audio result. They reject invalid, silent, or token-limited results. The app does not claim speech-to-text verification of generated words.

Qwen and Voxtral do not expose speed in these API calls. The app applies pitch-preserving tempo adjustment after generation. The style and generation controls are included in each chunk's saved identity. Changing an engine or its voice settings requires a new project once audio exists.

The model pages contain published throughput results. They are not measurements from this Mac. This repository keeps measured local results separate from those claims.
