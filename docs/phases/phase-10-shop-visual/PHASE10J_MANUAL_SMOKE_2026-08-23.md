# Phase 10J Manual Standalone Smoke

**Status:** Passed - Phase 10 formally closed 2026-08-24
**Candidate:** `dist\nuitka-development\main.dist\Akiha.exe`  
**Built:** 2026-08-23 with Python 3.13.14, Nuitka 4.1.3, and Zig 0.16.0

## Candidate Correction

The initial Nuitka candidate omitted Qt's multimedia backend plugins. Both
Local Modular and Gemini Live could hear and produce text, while their shared
`QMediaPlayer` owner retained audio without starting playback or reporting a
decoder error. The candidate now includes the matching PySide6
FFmpeg multimedia backend and matching codec runtime DLLs and passes artifact
validation. The Windows Media backend alone could start an in-memory WAV but
did not reliably report segment completion, which cut off queued Local Modular
speech after its first segment.

Future Nuitka builds explicitly include the `multimedia` Qt plugin group, and
artifact validation now rejects packages that do not contain a multimedia
backend. This correction did not require recompiling the existing candidate.

Local Modular testing then exposed a separate latency issue: short sentences
were synthesized independently, allowing playback to outrun GPT-SoVITS and
pause between queued segments. Source mode now batches short replies into one
speech derivative, preserves segmentation for longer replies, and collapses
paragraph whitespace only for synthesis. Canonical chat and persisted text are
unchanged. The owner accepted the source behavior on 2026-08-24. The scheduled
consolidated FastBuild completed later that day and includes this correction.

## Required Setup

- [x] Open Settings, re-enter the Gemini API key, and save it so Windows DPAPI
  replaces the currently undecryptable credential.
- [x] Keep the external GPT-SoVITS runtime/reference directory available at the
  configured location. It is intentionally not bundled into Akiha.

## Manual Acceptance

- [x] Start `Akiha.exe`; confirm there is no console and the pet is visible,
  sharp, draggable, and responsive.
- [x] Confirm tray Show/Hide, Chat, Settings, Memories, Behavior History,
  Assistant Actions, Status, Shop, and Quit work.
- [x] Confirm Seifuku remains selected and unavailable Dress/Vermillion sets
  fail closed without changing the canonical sprite.
- [x] Confirm Status displays current level, XP, currency, mood, care state,
  activity, and appearance without exposing secrets or filesystem data.
- [x] Confirm feed, rest, and interact actions update pet state; cooldown and
  anti-farming behavior remain enforced.
- [x] Confirm the trusted Shop lists products, purchases atomically, preserves
  non-negative currency, and survives restart.
- [x] Confirm autonomous idle/walk/sleep behavior does not block dragging,
  voice, care actions, or assistant actions.
- [x] Confirm Local Modular conversation hears multiple turns and GPT-SoVITS
  speaks without synthesis errors.
- [x] Confirm Gemini Live starts, transcribes, speaks, accepts interruption,
  returns to listening, and does not silently fall back to Local Modular.
- [x] Confirm approved applications, directories, nested directories, and local
  passive media still open; denied targets remain denied and audited.
- [x] Confirm Spotify search, numbered results, playback, current-track lookup,
  volume, shuffle, seek, playlist, artist page, pause/resume, and next/previous.
- [x] Move Akiha, quit from the tray, relaunch, and confirm position plus Phase
  10 pet/shop/appearance state persists.
- [x] Inspect `%LOCALAPPDATA%\Akiha\logs\app.log` for unexpected tracebacks or
  provider errors after the run.

## Closure

Every required item passed and the owner accepted both source mode and the
corrected Nuitka candidate. Phase 10 formally closed on 2026-08-24. Obsolete
package cleanup remains a separate maintenance action and is not required to
preserve this acceptance record.

## Consolidated Build Completion

The scheduled consolidated FastBuild completed on 2026-08-24 from the current
source tree. It includes adaptive short-response speech batching and GPT-SoVITS
speech-only whitespace normalization. Static artifact checks, isolated fresh-
and existing-data startup checks, the Gemini Live connection check, and real
GPT-SoVITS health and synthesis checks passed. The accepted candidate is
`dist\nuitka-development\main.dist`.

The owner completed the final manual smoke test of this consolidated candidate
on 2026-08-25 and confirmed that the packaged application works as expected.
