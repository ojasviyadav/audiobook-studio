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

The audiobook was 61.8% saved before the selected configuration resumed. Final production time and output validation will be added after completion. The ebook, text, and audio are outside the repository.

Sources: [Kokoro](https://github.com/hexgrad/kokoro), [PyTorch Metal support](https://docs.pytorch.org/docs/2.14/notes/mps.html), [Apple GPU thread scheduling](https://developer.apple.com/documentation/metal/performing-calculations-on-a-gpu).
