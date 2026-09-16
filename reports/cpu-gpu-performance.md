# CPU and GPU performance on the M4 Pro

Status: conversion is in progress. Final measurements will be added when it finishes.

## Hardware and software

- MacBook Pro, 14-inch, November 2024.
- Apple M4 Pro: 14 CPU cores, 20 GPU cores, 48 GB of memory. Core counts were read from macOS.
- macOS Tahoe 26.6.2.
- Kokoro 0.9.4, PyTorch 2.14.0, Heart (`af_heart`), speed 0.95, 24 kHz audio.
- The model file is about 327 MB. It fits in memory. This does not establish whether memory bandwidth limits inference.

## Completed measurements

A previous CPU test used four PyTorch threads and the same passage twice. The model was already loaded.

| Trial | Speech produced | Processing time | Speech / processing time |
|---|---:|---:|---:|
| CPU, trial 1 | about 33 seconds | 2.743 seconds | about 12.0× |
| CPU, trial 2 | about 33 seconds | 2.545 seconds | about 13.0× |

Earlier GPU sample times included voice download or startup work. They are not a fair CPU/GPU comparison. A later controlled comparison could not start because of temperature limits. No result from that comparison is claimed.

## Current parallel run

Two processes use Metal on the same 20-core GPU. One process uses four CPU threads. Each process has its own model and owns separate book sections. A single GPU process can use multiple GPU cores. Two GPU processes do not mean two physical GPUs.

The remaining work was assigned by word count: 10,594 words to GPU worker 0, 10,251 to GPU worker 1, and 9,376 to the CPU worker. This is a production workload, not a controlled benchmark. Text, sentence lengths, speech duration, compilation, and cooling pauses can differ between workers.

All workers pause together at 80°C and resume below 74°C. The user target is 90°C. CPU readings exceeded 90°C during some paused periods. The monitor cannot enforce a limit on unrelated applications. Therefore, do not report that the full run stayed below 90°C.

## Interpretation so far

CPU processing is already faster than playback. There is not yet enough comparable evidence to say that GPU processing is faster for this installed Kokoro implementation. Parallel processing must be assessed by total output per elapsed time, including cooling breaks. More workers can increase heat and reduce the time available for processing.

Neither model size nor core count alone establishes a compute or memory-bandwidth limit. Kokoro performs neural network calculations and also spends time on text preparation, device scheduling, synchronization, and audio output. A firm compute-versus-bandwidth diagnosis needs hardware counters or a suitable profile. That measurement has not been made here.

Sources: [Kokoro](https://github.com/hexgrad/kokoro), [PyTorch Metal support](https://docs.pytorch.org/docs/2.14/notes/mps.html).
