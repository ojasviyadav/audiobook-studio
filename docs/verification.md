# Verification — 17 September 2026

Audiobook Studio 1.2, build 4, was built and signed on this Mac. The app was reopened only after the original book and all comparison conversions had finished.

- 16 base Python tests passed.
- 6 MLX adapter and download tests passed.
- The Swift/Python bridge test passed in the final build.
- The process-group test passed for CPU heat, GPU heat, cooling, manual pause/resume, sensor failure, and stop.
- The final release build and strict code-signature check passed. The monitored build peak was 80.875°C.
- Both downloaded MLX checkpoints passed their repository file digest checks.
- Qwen and Voxtral each converted the same 669 words to a two-chapter M4B. Chapter, duration, and full audio-decoding checks passed. Resume reused the saved chunks without changing their receipts.
- The original Emotional Design M4B passed the final audio checks: 21 chapters, 31,799.143 seconds, and 377,959,798 bytes.

The model test results, revisions, output paths, and timing method are in [the model comparison](../reports/qwen-vs-kokoro.md). Qwen used Ryan at speed 1.0. Voxtral used neutral male at speed 1.0. No reference audio was used.

Voxtral's test recorded a 100.438°C peak, above the requested target. High CPU readings also occurred after both narration workers had been stopped for about one minute, with an unrelated Xcode build active. The test included manual pauses and changes to cooling controls. It passed the functional checks, but its elapsed time is not a controlled speed comparison. The final Voxtral defaults retain the Qwen temperature thresholds and use 3-second work periods with at least 10 seconds of rest. Software pauses cannot guarantee a physical temperature ceiling for the whole Mac.

Offscreen layouts were inspected in light and dark appearances. Live window interaction checks could not run because the computer-control service returned “native pipe closed before response.” The original native M4B player load check passed. Audio validation does not prove perfect pronunciation or that every word was spoken; the samples are available for listening.

## Qwen speed update

Build 5 sets the default Qwen speed to 1.25× in the app, engine selection, Python settings, and command-line preparation. Explicit saved speeds remain valid. The 16 Python tests, Swift bridge test, release build, and strict signature check passed. The 30-second sample passed duration and audio-decoding checks. It uses the earlier Ryan recording with the app’s pitch-preserving speed change. See [the sample record](../reports/qwen-1.25x-sample.json).

## App clarity and task handling update

Version 1.3, build 6 adds saved-engine labels, a separate Qwen-version draft, local diagnostic reports, and guards against stale asynchronous results. The normal status response no longer reads conversion logs. Completed projects do not poll. See [the app review](app-review.md) for measurements and scope.

Final checks for build 6: 10 Swift tests, 16 base Python tests, 6 MLX tests, and the simulated process-group guard check passed. The release build and strict signature check passed. The new-book layout was rendered from SwiftUI source and inspected. The app was reopened after confirming that narration was complete. The native control service could open Finder and Activity Monitor but returned “native pipe closed before response” for the Audiobook Studio window, so live control testing remains limited.

The app now sets its running Dock icon from the bundled PNG. The build also registers the bundle with Launch Services, and the Info.plist names the ICNS file explicitly. No global icon cache was deleted.

Finder Get Info confirmed version 1.3 and displayed the teal book-and-sound icon after the update. The app process was reopened with the new binary.
