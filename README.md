# EPUB to audiobook conversion

Convert a local, readable EPUB to a chaptered M4B audiobook with Kokoro. Apple Books can import the result.

This repository was made for Emotional Design on a MacBook Pro with an M4 Pro, 14 CPU cores, 20 GPU cores, and 48 GB of memory. See [the performance report](reports/cpu-gpu-performance.md) for measured results and limits.

## Operation

- Two workers use the Metal GPU. CPU inference is disabled. The CPU prepares text and writes audio.
- Workers own different sections. A saved section is not generated again.
- Each audio batch has a text signature and a record of the voice, speed, sample count, and processing device.
- One temperature monitor controls the full process group, including audio encoding.
- Processing pauses at 86°C and resumes below 82°C after a cooling break. The user target is 90°C.
- A missing temperature reading pauses processing. A failed monitor stops its workers.
- Final checks verify section order, chapter markers, duration, text coverage, and audio decoding.

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

The current Emotional Design run remains in `/Users/ojasviyadav/Work/Audiobooks/Emotional Design`. It uses the scripts that were started there. Repository preparation does not restart that run. Its ebook, text, voices, model, and audio are outside Git.

Open the completed M4B in Apple Books, or use File → Import. The M4B contains chapters and cover art when the EPUB provides a cover.

## Third-party source

The temperature reader includes code from [smctemp](https://github.com/narugit/smctemp). Its GPL license is in `vendor/smctemp/LICENSE`. Local changes make read errors explicit and return current readings as JSON. Inactive sensor values are omitted. The supervisor requires valid CPU and GPU sensor groups.

Kokoro and the model have their own licenses. See their [official repository](https://github.com/hexgrad/kokoro).
