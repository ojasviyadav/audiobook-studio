# App review — 17 September 2026

## Version 1.4 — model comparison

Build 7 adds **Compare models…** beside the engine selector. Three cards show the suggested quality order, estimated processing needs, model file sizes, and selection buttons. The panel reads the local Metal device and installed memory once. It does not start a model, download files, or change the fixed GPU configuration.

The quality order is explicitly a listening suggestion. Qwen remains the default. The relative positions of Voxtral and Kokoro are provisional. Qwen and Voxtral share a higher processing group because no fair local comparison establishes their relative speed or power use. The timing disclosure distinguishes measured local samples from published model claims.

Verification completed:

- All 13 Swift tests passed, including repeated draft-model changes and protection of saved recordings. Selection causes no bridge request, download, or conversion.
- The comparison was rendered from the actual SwiftUI view and visually inspected in light and dark appearances, for draft and saved-recording states. The first render exposed a transparent background problem; an explicit system background fixed it. All three model cards, selection state, evidence disclosure, and guidance fit in the final view.
- The main screen was rendered and inspected with the comparison entry beside the engine selector.
- The release app built successfully. Strict code-signature verification passed.
- No narration process was active before the old app was closed normally. The new app was launched after the build. Live UI control returned “Sky Computer Use native pipe closed before response,” so the running-window click path was not verified. Rendered views and model tests do not replace that check.

The reviewed comparison image is [model-guide.png](images/model-guide.png). No narration performance claim was added from these UI checks.

## Version 1.3 — saved recordings and reliability

Version 1.3, build 6, explains the difference between saved narration and the default for a new book. A completed Kokoro project still reports Kokoro. The new-version button selects Qwen, Ryan, and 1.25× in a separate draft. It does not start conversion or change existing audio.

## Task handling

The review covered project preparation, status checks, samples, playback, setup, and project changes. This app has no lessons, learner questions, or review sessions.

- UI state belongs to the main actor. Bridge inputs are copied before an asynchronous call.
- Project changes and duplicate commands are blocked while a command is pending.
- Every asynchronous response has a project-generation check. Old success and failure responses cannot replace a new project's state.
- Status checks do not overlap. View tasks stop checks when the window is inactive or the project is complete.
- Cancellation prevents status results from reaching the screen. It does not terminate an already started narration command.
- Sample playback timers are cancelled when a new sample or project replaces them.

## Errors

The app uses a replaceable error-monitoring protocol with local and no-operation implementations. No remote SDK or reporting account was added.

A failure gets a short recovery message and a report reference. Technical details, action names, engine, time, and build version are recorded under `~/Library/Logs/Audiobook Studio`. Breadcrumbs are limited to 20. The report file rotates at about 1 MB and keeps one previous file. Reports can contain local paths from an engine error. The app does not send them anywhere.

The bridge checks the process exit code and preserves stderr for diagnostics. Separate output files prevent a full stderr pipe from blocking the process. Normal status replies no longer carry conversion logs; the log command reads bounded tails only when requested.

## Performance measurements

Measurements used the real completed 77,001-word project on the M4 Pro. Five fresh Python status processes were measured before and after the change, on the same Mac with other applications open.

| Measure | Before | After |
|---|---:|---:|
| Median status command duration | 46.88 ms | 46.64 ms |
| Status reply size | 19,163 bytes | 3,009 bytes |
| Automatic checks for a completed project | About one every 2 seconds | None |

The single-request time is effectively unchanged. The useful reduction is removal of repeated work while a book is complete, plus an 84% smaller normal reply. Cover data is read off the main actor and retained for the current project instead of reopening the image during each view update.

Two-second process samples showed a 54.6 MB physical footprint before the update and 96.2 MB after reopening the new release. These short samples used different process ages and UI states. They do not establish a memory regression or a memory improvement. `BridgeRequest` signposts now mark command duration for Instruments. No claim is made about faster model inference: the model adapters, GPU worker count, and thermal guard are unchanged.

The new layout was rendered from the SwiftUI source and inspected. The live computer-control connection failed intermittently during verification. Automated task-order and bridge tests cover the affected paths; a rendered layout does not replace a live interaction check.

## Icon registration

The app includes a teal book-and-sound icon in PNG and ICNS formats. Build 6 sets the running Dock image at launch, names the ICNS file explicitly, and registers the app bundle after signing. The shared in-app icon is loaded once.
