# Manual Packaged Smoke Report

Use this report with
`docs/phases/phase-06-packaging/MANUAL_PACKAGED_SMOKE.md`.

## Build Under Test

- Date:
- Tester:
- Package path:
- Commit or working tree note:
- Automated source smoke passed: yes/no
- Automated packaged smoke passed: yes/no
- Fresh `%LOCALAPPDATA%\Akiha\` used: yes/no
- Existing `%LOCALAPPDATA%\Akiha\` used: yes/no

## Results

| Area | Result | Notes |
| --- | --- | --- |
| First-run privacy | pending | |
| Visual startup | pending | |
| Tray controls | pending | |
| Settings window | pending | |
| Chat window | pending | |
| Voice | pending | |
| Conversation lanes | pending | |
| Assistant actions | pending | |
| Memory Manager | pending | |
| Behavior History | pending | |
| Proactive behavior | pending | |
| Pet Sim | pending | |
| Graceful Quit | pending | |

Use `pass`, `fail`, or `blocked` for each result.

## Required Evidence

- No visible console window appeared: yes/no
- Pet appeared and dragged correctly: yes/no
- Tray Quit exited without Task Manager: yes/no
- Saved position restored after relaunch: yes/no
- Privacy notice appeared once and stayed dismissed after relaunch: yes/no
- Microphone transcription and Japanese voice playback worked: yes/no
- Local Modular Talk and Conversation worked: yes/no
- Gemini Live conversation, interruption, and return-to-listening worked: yes/no
- Packaged application, directory, local-media, and Spotify actions worked: yes/no
- Missing permission and confirmation behavior remained enforced: yes/no
- Provider-visible action results remained sanitized: yes/no
- Japanese deterministic memory fallback produced a pending candidate: yes/no
- Care actions, progression, diagnostics, and confirmed pet reset worked: yes/no
- Canonical idle remained sharp and walking direction remained correct: yes/no
- `%LOCALAPPDATA%\Akiha\logs\app.log` had no unexpected failures: yes/no
- `%LOCALAPPDATA%\Akiha\state\pet_window.json` was written: yes/no

## Failures

Record each failure with the exact checklist step, observed behavior, and any
attached screenshot/log path.

| Step | Failure | Evidence |
| --- | --- | --- |
| | | |

## Final Decision

- Manual packaged smoke result: pending
- Release readiness decision: pending
- Follow-up items:
