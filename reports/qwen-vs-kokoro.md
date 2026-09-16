# Qwen and Kokoro on this M4 Pro

Qwen planning estimate for Emotional Design: **6 h 32 min to 9 h 39 min**. Kokoro production estimate: **2 h 19 min**.
These Qwen estimates are **2.8–4.2 times** the Kokoro estimate, or about **4 h 13 min to 7 h 20 min longer**.

## Measured samples

Both MLX samples use the same 669 source words from Chapter One, split into two sections of 416 and 253 words. They run sequentially. Each conversion uses two GPU workers. Elapsed time starts after that model is ready and includes setup, loading, generation, thermal pauses, encoding, and validation. Voxtral was still downloading during part of the Qwen test. This background work can affect temperature and elapsed time. No model quality score is claimed.

| Engine | Voice / speed | Elapsed time | Output audio | Peak temperature | Cached-audio reuse |
| --- | --- | ---: | ---: | ---: | --- |
| Qwen | Ryan / 1× | 301.9 s | 407.6 s | 88.1°C | Passed |
| Voxtral | neutral_male / 1× | 904.2 s | 252.5 s | 100.4°C | Passed |
| Kokoro | Heart / 0.95× | 115.3 s | 280.2 s | 87.2°C | Saved |

On this matched sample, Qwen took 2.62 times as long as Kokoro. The thermal settings differ as listed below. Kokoro timing starts at its first supervisor reading and excludes the app setup check; MLX timings include that small setup check.

Voxtral is a functional test, not a controlled timing comparison. Its run recorded a 100.438°C peak, above the requested target. Readings above 90°C also occurred after the narration workers had been stopped for about one minute; a separate Xcode build was active. The test was paused manually and then resumed with shorter work periods. Its elapsed time includes the interruptions and changes to cooling controls. The record does not establish which workload caused each overshoot.

The peak is the highest monitored sensor reading during the first conversion. Sampling cannot establish a physical maximum between readings.

## Exact configuration

- Qwen: `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit`, Ryan, English, speed 1.0. Style: “Natural audiobook narration. Calm, clear, steady pacing.”
- Qwen and Voxtral: MLX-Audio 0.5.4, 1,000-character chunk limit, temperature 0.8, 4,096 maximum tokens, two Metal workers. Qwen CPU target 90°C, pause 82°C, resume below 78°C. GPU target 93°C, pause 89°C, resume below 85°C. Voxtral started with these controls.
- Voxtral final controls and new app defaults: CPU pause 82°C, resume below 78°C; GPU pause 89°C, resume below 85°C; 3-second work periods, at least 10 seconds of rest, 1 second of stable cool readings. Targets remain CPU 90°C and GPU 93°C.
- Kokoro production: 82M v1.0, Heart, speed 0.95, two Metal workers, two CPU host threads each, 1,800-character paragraph grouping. Original shared thermal target 90°C, pause 86°C, resume below 82°C.
- All runs: 0.5-second rest per generated segment and 96 kbps AAC output. Qwen, Kokoro, and the initial Voxtral settings use a 60-second maximum work interval, 5-second minimum break, and 1 second of stable cool readings. Different engines can return different numbers of segments.

## Estimate method and limits

The full book has 77,001 source words. Direct scaling of the complete Qwen sample gives 9 h 39 min. This deliberately includes repeated model-loading and final-validation overhead in each scaled sample.
The second estimate, 6 h 32 min, removes the recorded model-load time from each worker’s chunk intervals, averages their seconds per word, assigns half the book to each worker, and adds one parallel model load. It still includes cooling inside chunk intervals. It excludes gaps between chunks and final assembly. First-use compilation can remain in the chunk time.
The two values form a planning range, not a statistical confidence interval or a guaranteed bound. Longer books can have different thermal behaviour, text difficulty, speech pace, and worker balance. A 669-word sample does not prove sustained full-book performance.
The Kokoro estimate uses 28,855 newly saved words in 51.95 minutes after a saved baseline. It includes 30.69 minutes of observed pauses. It excludes the later copyright-page repair and final assembly. Earlier book sections used other configurations.
Different voices and speeds can produce different audio durations. Word throughput is used for the book estimate so that slower speech is not mistaken for more source text processed.
The successful M4B checks establish valid audio, duration, and chapter structure. They do not establish perfect pronunciation or prove that the MLX models spoke every word. Listen to the sample files before selecting a narrator.

## Local outputs

- Qwen: `/Users/ojasviyadav/Work/ebooks-to-audiobook-conversion/projects/engine-comparison/qwen/qwen-comparison.m4b`
- Voxtral: `/Users/ojasviyadav/Work/ebooks-to-audiobook-conversion/projects/engine-comparison/voxtral/voxtral-comparison.m4b`

## Downloaded model revisions

- Qwen: `1c6c0ff58c43afa8df571facde2efa077efd85e2`. Downloaded files passed their repository digest checks.
- Voxtral: `f98fc91b9cb5adc7dab56102c690458276c14c6a`. Downloaded files passed their repository digest checks.

Raw measurements: `mlx-comparison.json`, `kokoro-matched-sample.json`, and `parallel-run-measurements.json`.
