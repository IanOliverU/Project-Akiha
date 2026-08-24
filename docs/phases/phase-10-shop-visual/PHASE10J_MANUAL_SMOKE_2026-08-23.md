# Phase 10J Manual Standalone Smoke

**Status:** Pending owner acceptance  
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
unchanged. This source correction requires owner acceptance before the next
cached candidate build.

## Required Setup

- [ ] Open Settings, re-enter the Gemini API key, and save it so Windows DPAPI
  replaces the currently undecryptable credential.
- [ ] Keep the external GPT-SoVITS runtime/reference directory available at the
  configured location. It is intentionally not bundled into Akiha.

## Manual Acceptance

- [ ] Start `Akiha.exe`; confirm there is no console and the pet is visible,
  sharp, draggable, and responsive.
- [ ] Confirm tray Show/Hide, Chat, Settings, Memories, Behavior History,
  Assistant Actions, Status, Shop, and Quit work.
- [ ] Confirm Seifuku remains selected and unavailable Dress/Vermillion sets
  fail closed without changing the canonical sprite.
- [ ] Confirm Status displays current level, XP, currency, mood, care state,
  activity, and appearance without exposing secrets or filesystem data.
- [ ] Confirm feed, rest, and interact actions update pet state; cooldown and
  anti-farming behavior remain enforced.
- [ ] Confirm the trusted Shop lists products, purchases atomically, preserves
  non-negative currency, and survives restart.
- [ ] Confirm autonomous idle/walk/sleep behavior does not block dragging,
  voice, care actions, or assistant actions.
- [ ] Confirm Local Modular conversation hears multiple turns and GPT-SoVITS
  speaks without synthesis errors.
- [ ] Confirm Gemini Live starts, transcribes, speaks, accepts interruption,
  returns to listening, and does not silently fall back to Local Modular.
- [ ] Confirm approved applications, directories, nested directories, and local
  passive media still open; denied targets remain denied and audited.
- [ ] Confirm Spotify search, numbered results, playback, current-track lookup,
  volume, shuffle, seek, playlist, artist page, pause/resume, and next/previous.
- [ ] Move Akiha, quit from the tray, relaunch, and confirm position plus Phase
  10 pet/shop/appearance state persists.
- [ ] Inspect `%LOCALAPPDATA%\Akiha\logs\app.log` for unexpected tracebacks or
  provider errors after the run.

## Closure

Phase 10 closes only after every item above passes. Obsolete package folders
remain untouched until this candidate is accepted.
