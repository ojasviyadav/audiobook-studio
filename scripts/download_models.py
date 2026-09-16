"""Download the fixed checkpoints with resumable ranges and file verification."""
from pathlib import Path
import fcntl
import sys
from download_models_resumable import download, ROOT, MODELS

for engine in sys.argv[1:] or MODELS:
    if engine not in MODELS:raise SystemExit('Select qwen or voxtral.')
    folder=ROOT/'models'/engine;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.download.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        download(engine)
