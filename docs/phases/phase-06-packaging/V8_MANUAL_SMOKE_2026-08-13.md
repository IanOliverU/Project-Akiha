# V8 Manual Standalone Smoke Report

**Status:** Passed - V8 formally closed  
**Date:** 2026-08-13  
**Platform:** Windows 11, Python 3.13.14 build environment  
**Executable:** `dist/nuitka-v8-final/main.dist/Akiha.exe`  
**SHA-256:** `0E53B858FBEB05531EB5EE0B32AC21CBE3B640F1A51026C932179FE606AD5F3A`

## Automated Evidence

- [x] Complete suite passed: 1,372 tests with 3 optional-environment skips.
- [x] Ruff, Black, Python compilation, and Git diff checks passed.
- [x] Windows GUI subsystem validation passed.
- [x] Packaged-artifact dependency and private-data validation passed.
- [x] Package contains 193 files and is approximately 393.2 MiB.
- [x] Fresh-data packaged startup, schema, window, and log smoke passed.
- [x] Existing-data packaged startup, schema, window, and log smoke passed.
- [x] No visible console window appeared.

## Manual Acceptance

- [x] Desktop pet, tray controls, Settings, Chat, and normal interaction work.
- [x] Local microphone and configured voice behavior work in the package.
- [x] Gemini Live continues listening across successive conversation turns.
- [x] User and assistant Cloud transcripts appear immediately as revisions arrive.
- [x] Delayed or unavailable optional English subtitles do not block conversation.
- [x] Approved applications open through the permission-gated action boundary.
- [x] Approved directories open through the permission-gated action boundary.
- [x] Spotify commands execute through the typed, permission-gated integration.
- [x] Provider tool responses remain sanitized and conversation continues.
- [x] Tray or pet-menu Quit exits gracefully without Task Manager.

## Artifact Retention

After acceptance, obsolete V5/V8 candidates, the failed diagnostic build,
compiler trees, temporary rollback copies, and isolated smoke-data directories
were removed. The retained executable package is `dist/nuitka-v8-final`.

## Closure

The user confirmed that the final standalone behaves correctly on the real
desktop environment. Milestones V0 through V8 are complete, and the Voice
Intelligence roadmap is formally closed. Work may proceed to separately scoped
side-track tasks before Phase 9 begins.
