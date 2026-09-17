# EPUB to audiobook conversion

Convert a local, readable EPUB to a chaptered M4B audiobook with Qwen, Voxtral, or Kokoro. Apple Books can import the result.

This repository was made for Emotional Design on a MacBook Pro with an M4 Pro, 14 CPU cores, 20 GPU cores, and 48 GB of memory. See [the performance report](reports/cpu-gpu-performance.md) for measured results and limits.

## Swift app

Open **Audiobook Studio.app** in this folder. New books default to **Qwen3-TTS 1.7B CustomVoice 6-bit**, **Ryan**, and **1.25× speed**. Existing projects keep their saved engine and speed. Codex does not need to be open for conversion.

1. Select **New Book**, then select an EPUB file or an unpacked EPUB folder.
2. Select the output folder. The app makes a project folder with the EPUB name. Use **Open Project** to resume an existing project.
3. Select the engine, preset voice, speed, audio quality, silence, and cooling controls. Qwen also accepts narration style instructions.
4. Select **Prepare and Start**. The app shows saved progress, an estimated time, CPU and GPU temperatures, and section progress.
5. Use **Pause**, **Resume**, or **Stop** as needed. Completed audio batches are kept. A stop can discard the current incomplete batch. Closing the app does not stop an active conversion. After a Mac restart, open the project and select **Resume**.
6. When conversion and checks are complete, select **Open in Apple Books**.

GPU settings are fixed at two Metal workers. Kokoro uses two host threads per worker; MLX manages its own execution. CPU inference is disabled. Only one book can run through the app at a time. The app will not start a duplicate of the current Emotional Design run.

Qwen offers Ryan and Aiden. Voxtral 4B 4-bit offers 20 preset voices, including five English voices. Kokoro offers Heart, Bella, and Michael. No reference audio is needed. **Make sample** creates a short test audiobook under temperature control and plays it. Samples wait until no other book is running. Kokoro uses its existing listening samples.

The controls include speed (0.5–2×), AAC quality (64–192 kbps), silence between speech segments and after chapters, and rest after each generated segment. Qwen and Voxtral speed uses FFmpeg to change the generated audio while keeping its pitch. **Chunk size and generation** sets a 500–1,500 character limit, voice variation, and the maximum output tokens. Paragraphs stay together where they fit. Long paragraphs split at sentence or word boundaries. All results from each model generator are saved. Reaching the token limit stops the job to prevent silent truncation.

The temperature controls have separate CPU and GPU targets, pause temperatures, and resume temperatures. The maximum CPU target is 90°C. The maximum GPU target is 93°C, as permitted on 17 September 2026. Qwen projects pause for CPU heat at 82°C and resume below 78°C. Their GPU defaults are pause at 89°C and resume below 85°C. Voxtral uses shorter work periods after a local test exceeded the temperature target: CPU pause/resume 82°C/78°C, GPU 89°C/85°C, 3 seconds of work, at least 10 seconds of rest, and 1 second of stable cool readings. Selecting an engine sets its cooling defaults; all cooling controls remain adjustable. Either sensor group can pause all workers. Both groups must cool before work resumes. Each pause must be at least 2°C below its target. Work time, minimum rest time, and time for stable cool readings remain adjustable. Existing CPU settings stay unchanged.

Use **Apply settings** to save changes. Resume also saves the current settings. Engine, voice, style, chunk size, generation options, speed, silence, and audio quality are locked after audio is saved, to keep the book consistent. Use a new project folder to change them. Temperature settings can change during a run started by the app.

The first Emotional Design run is complete. Its last section and final assembly ran through the app after a narrow text-check correction. Earlier legacy runs keep their fixed thermal controls until they stop and resume through the app.

**Setup** contains the repository, Kokoro Python, Kokoro model, and temperature reader paths. Qwen and Voxtral use `.venv-mlx` and the `models/qwen` and `models/voxtral` folders in this repository. **Install MLX Runtime**, **Download Selected Model**, and **Check Setup** prepare the selected engine. Downloads need an internet connection. Large files are saved in 1 MB parts and checked against the model repository’s SHA-256 digest before use. A retry reuses completed parts. Narration runs locally after download. Setup errors are recorded in `models/setup.log`. Keep the runtime and model folders on disk. The app itself is local and signed for this Mac; it is not a standalone distribution for other computers.

### Build and checks

```sh
zsh App/build-app.sh
swift test -j 1
python3 -m unittest discover -s tests
python3 scripts/check_parallel_guard.py
.venv-mlx/bin/python -m unittest discover -s tests/mlx
```

The source is in `App/Sources`. `app_bridge.py` connects the Swift app to the conversion engine. `scripts/app_job.py` keeps the job running after the app closes. Tests check Swift/Python data exchange, saved-audio locks, duplicate-job rejection, temperature limits, and group pause/resume/stop. The process tests use sleeping test workers; they do not run model inference. The build and tests passed. See [the verification record](docs/verification.md). Offscreen layouts were inspected in light and dark appearances. Live window checks could not run because the computer-control service returned “native pipe closed before response.”

## Operation

- Two workers use the Metal GPU. CPU inference is disabled. A worker with no assigned section is not loaded. The CPU prepares text and writes audio.
- Workers own different sections. A saved section is not generated again.
- Each audio batch has a text signature and a record of the voice, speed, sample count, and processing device.
- One temperature monitor controls the full process group, including audio encoding.
- The completed original Kokoro run used a shared 90°C target and 86°C/82°C controls. The updated monitor uses separate CPU and GPU controls as described above.
- A missing temperature reading pauses processing. A failed monitor stops its workers.
- Final checks verify section order, chapter markers, duration, and audio decoding. Chunks cover all input text. Kokoro also reports the text it processed. Qwen and Voxtral do not prove that every input word was spoken correctly; listen to samples and check the result.

The temperature limit is a target, not a hardware guarantee. Other apps and GPU work already in progress can raise the temperature after a pause. Sensor names are not a public Apple interface. This sensor configuration has only been checked on the current M4 Pro.

## Setup

Use Python 3.11, FFmpeg, and the Xcode command line tools. Make a virtual environment and install the recorded dependencies:

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
make -C vendor/smctemp -j1
cd vendor/smctemp
c++ -std=c++17 -DARCH_TYPE_ARM64 -framework IOKit -o read_sensors read_sensors.cc smctemp.o smctemp_string.o
cd ../..
```

The current Mac already has a working environment at `/Users/ojasviyadav/Work/Audiobooks/.kokoro-venv` and model files at `/Users/ojasviyadav/Work/Audiobooks/kokoro-model`. These large files are outside this repository.

For Qwen and Voxtral, the app setup buttons perform the equivalent of:

```sh
python3 -m venv .venv-mlx
.venv-mlx/bin/python -m pip install -r requirements-mlx.txt
.venv-mlx/bin/python scripts/download_models.py qwen voxtral
```

The installed package versions are recorded in `requirements-mlx-lock.txt`. See [engine details](docs/engines.md) for model IDs, voices, and licenses.

Both fixed MLX checkpoints are downloaded and passed their file digest checks on this Mac. Each engine completed a real 669-word, two-section conversion and a resume check that reused the saved audio. Qwen used Ryan; Voxtral used neutral male. See [the measured comparison](reports/qwen-vs-kokoro.md) for the samples, model revisions, temperature records, and limits.

The Qwen sample took 301.9 seconds; the matching Kokoro sample took 115.3 seconds. The estimated Qwen time for all of Emotional Design is 6 hours 32 minutes to 9 hours 39 minutes, compared with a Kokoro production estimate of 2 hours 19 minutes. These are estimates, not complete clean book runs. Voxtral's test included manual pauses and cooling changes after a temperature overshoot, so its elapsed time is not a controlled speed comparison.

For a new installation, obtain `config.json` and `kokoro-v1_0.pth` from [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M). The required model SHA-256 is `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4`. Install the `en_core_web_sm` spaCy model and cache the selected Kokoro voice before an offline run. Heart uses `voices/af_heart.pt` from the same model repository.

## Prepare and run a book

The source can be an EPUB ZIP file or an unpacked EPUB directory. Preparation reads the EPUB spine and creates section text and book metadata. It does not remove encryption. It does not describe images.

```sh
.venv/bin/python convert.py prepare '/path/Book.epub' \
  --project '/path/audiobooks/Book' \
  --model-dir '/path/kokoro-model' \
  --voice af_heart --speed 0.95
.venv/bin/python convert.py run '/path/audiobooks/Book'
```

Keep the run command open until it finishes. Ctrl+C stops the run. To resume, use the same run command. Do not start another conversion directly from a worker script. The main command holds a project lock to prevent duplicate work.

The `status` command reads saved progress:

```sh
.venv/bin/python convert.py status '/path/audiobooks/Book'
```

`book.json` holds the title, author, voice, speed, model path, sensor path, and output name. Use a new project directory if the source book or voice changes. The internal `kokoro-heart-build` directory name is retained for compatibility with the first conversion; the selected voice comes from `book.json`.

## Checks

```sh
python3 -m unittest discover -s tests
python3 scripts/check_parallel_guard.py
python3 -m py_compile convert.py scripts/*.py
```

The process test uses small sleeping processes. It checks that all test workers pause when the simulated temperature reaches the pause point, resume after cooling, and pause when readings fail. It does not heat the Mac.

## First conversion

The completed Emotional Design audiobook is in `/Users/ojasviyadav/Work/Audiobooks/Emotional Design`. It has 21 chapters and runs for about 8 hours 50 minutes. The final pipeline checked chapter markers, titles, duration, and full audio decoding. Its ebook, text, voices, model, and audio are outside Git.

Open the completed M4B in Apple Books, or use File → Import. The M4B contains chapters and cover art when the EPUB provides a cover.

## Third-party source

The temperature reader includes code from [smctemp](https://github.com/narugit/smctemp). Its GPL license is in `vendor/smctemp/LICENSE`. Local changes make read errors explicit and return current readings as JSON. Inactive sensor values are omitted. The supervisor requires valid CPU and GPU sensor groups.

Kokoro and the model have their own licenses. See their [official repository](https://github.com/hexgrad/kokoro).

## App appearance

Version 1.2 uses a teal book-and-sound icon, matching control colours, book-cover details, and clear progress and temperature cards. Advanced cooling controls remain available in expandable sections. The GPU card shows its own live target.

The icon source is `scripts/generate-icon.swift`. Run it with `swift scripts/generate-icon.swift` to regenerate the three colour variants and the selected teal PNG and ICNS files in `App/Resources`. The app build copies both selected files into the signed bundle.
