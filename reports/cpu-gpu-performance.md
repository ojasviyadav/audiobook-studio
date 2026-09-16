# CPU and GPU comparison on the M4 Pro

**Selected configuration: two Metal GPU workers, with CPU inference disabled.** This was the fastest of the five configurations tested. It is now the default for narration.

Hardware: M4 Pro, 14 CPU cores, 20 GPU cores, and 48 GB of memory. Software: macOS Tahoe 26.6.2, Kokoro 0.9.4, and PyTorch 2.14.0. Voice: Heart, speed 0.95, 24 kHz audio.

## Direct measurements

Each worker generated the same 33-second passage. Models and voices were loaded first. Each worker completed a warm-up. CPU workers used four threads each. GPU workers used two host threads each. Parallel tests started two jobs together and waited for both to finish.

| Configuration | Speech produced | Elapsed time | Cooling pauses | Speech per elapsed second |
|---|---:|---:|---:|---:|
| CPU × 1 | 33 s | 18.38 s | 15.14 s | 1.8× |
| GPU × 1 | 33 s | 1.59 s | 0.00 s | 20.7× |
| CPU × 2 | 66 s | 19.47 s | 16.01 s | 3.4× |
| GPU × 2 | 66 s | 2.49 s | 0.00 s | 26.5× |
| GPU + CPU | 66 s | 17.16 s | 13.91 s | 3.8× |

Two GPU workers produced **28% more speech per second than one GPU worker**. Both use the same physical 20-core GPU. One worker can also use multiple GPU cores.

CPU work caused long cooling pauses that stopped the whole group. After subtracting recorded pauses, one CPU worker took about 3.24 seconds and two CPU workers took about 3.46 seconds. The GPU was faster in this test even before cooling time was counted. An earlier standalone CPU test took 2.743 and 2.545 seconds for 33 seconds of speech.

## Temperature and limits

The supervisor pauses at 86°C and resumes below 82°C. The user target is 90°C. A reading reached **94.45°C** during the CPU-inclusive comparison despite the pause control. Further CPU trials were stopped. This controller cannot guarantee a 90°C hardware ceiling.

One measured trial per configuration completed. The planned second round was cancelled after the temperature overshoot. These are short tests on one passage, not a sustained full-book benchmark. Other apps were open. Cooling time is counted because it affects the time needed to finish a book. Pause durations were reconstructed from supervisor transitions.

The mixed CPU/GPU test waited for both jobs. An independent continuous queue can have different throughput. More than two GPU workers, other CPU thread counts, and other inference engines were not tested. Two GPU workers are the **best tested configuration**, not proof of the best possible configuration.

## Worker and core are different

A worker is a Python process with a Kokoro model. A GPU core is part of the chip. Metal schedules each worker's calculations on the same GPU. A worker is not assigned one core. Three GPU workers are possible, but they still share the same 20 cores and memory bandwidth. More workers can reduce idle time, but can also increase resource contention, memory use, and heat. Three workers have not been measured.

## Compute or memory limit

The model file is about 327 MB and fits in memory. Memory capacity is not the problem. These timings do not establish whether computation or memory bandwidth limits each model operation. No hardware-counter profile was collected. The useful result is that GPU inference gave higher measured throughput, while CPU inference added heat and cooling delays.

## Records

- [Raw timing data](controlled-comparison.json)
- [Comparison temperature records](controlled-comparison-thermal.json)
- [Exact comparison script](compare_backends.py)
- [Current production measurements](parallel-run-measurements.json)

## Completed production run

Emotional Design is complete: 77,001 source words, 21 sections, 31,799.143 seconds (8 hours 50 minutes), and 377,959,798 bytes. The final pipeline checked chapter titles, chapter count, duration, and full FFmpeg decode before it renamed the final M4B. The ebook, extracted text, and audio remain outside the repository.

The measured two-GPU interval begins at the saved baseline of 47,992 words. It produced another 28,855 words and 12,784.975 seconds of audio in 51.95 minutes. Recorded enabled time was 21.26 minutes; pauses took about 30.69 minutes. This is 4.10 seconds of speech per elapsed second. Pauses include cooling and missing temperature readings. Worker 1 finished about 16 minutes before worker 0, so the latter part did not use both workers.

At that sustained rate, all 77,001 words would take about **2 hours 19 minutes**. This is an estimate for the final configuration, not a measured clean full-book run. Earlier text was produced during different configurations. Model loading, passage differences, unequal section lengths, and final assembly can change the result.

The first measured interval stopped at the copyright-page text check. Kokoro omitted an apostrophe between digits and a slash-only paragraph. A narrow comparison fix retained checks for missing words and digits. The last 154 words were then generated, and the M4B was assembled and verified. Retry and repair time is excluded from the throughput estimate.

The supervisor recorded a **92.625°C peak** during the original production interval. The saved periodic samples reached 90.422°C for the CPU and 79.577°C for the GPU; their interval is too wide to recover every peak. The old run used shared pause/resume settings of 86°C/82°C. New runs have separate CPU and GPU targets: CPU 90°C, GPU 93°C as permitted later by the user. New MLX samples use CPU pause/resume of 82°C/78°C and GPU 89°C/85°C.

The measurement script now ends at the last recorded sample for guard 11617. It does not count later idle time or other guard sessions. It also recovers worker assignment from the original logs, because a resume rewrites the current assignment file.

Qwen and Voxtral have also completed local two-GPU sample conversions. Their results and the Qwen full-book estimate are in [the model comparison](qwen-vs-kokoro.md). These tests did not compare their CPU and GPU backends. Voxtral's test included interruptions and cooling changes; its elapsed time cannot establish a speed ranking.

Sources: [Kokoro](https://github.com/hexgrad/kokoro), [PyTorch Metal support](https://docs.pytorch.org/docs/2.14/notes/mps.html), [Apple GPU thread scheduling](https://developer.apple.com/documentation/metal/performing-calculations-on-a-gpu).
