# Project Akiha Documentation

This directory is the maintained documentation home. Phase-specific material
is grouped with the phase that owns it; shared operational and architecture
material is separated by purpose.

## Completed Phases

| Phase | Status | Documentation |
| --- | --- | --- |
| 1 - Desktop Pet | Complete | [`phases/phase-01-desktop-pet/`](phases/phase-01-desktop-pet/) |
| 2 - Chat | Complete | [`phases/phase-02-chat/`](phases/phase-02-chat/) |
| 3 - Memory | Complete | [`phases/phase-03-memory/`](phases/phase-03-memory/) |
| 4 - Behavior | Complete | [`phases/phase-04-behavior/`](phases/phase-04-behavior/) |
| 5 - Polish | Complete | [`phases/phase-05-polish/`](phases/phase-05-polish/) |
| 6 - Packaging | Complete | [`phases/phase-06-packaging/`](phases/phase-06-packaging/) |
| 7 - Voice | Complete | [`phases/phase-07-voice/`](phases/phase-07-voice/) |
| 8 - Assistant Actions | Complete | [`phases/phase-08-actions/`](phases/phase-08-actions/) |
| 9 - Pet Simulation | Complete | [`phases/phase-09-pet-sim/`](phases/phase-09-pet-sim/) |
| 10 - Shop And Visual Expansion | Complete | [`phases/phase-10-shop-visual/`](phases/phase-10-shop-visual/) |
| 11 - External Integrations | Complete | [`phases/phase-11-integrations/`](phases/phase-11-integrations/) |

## Active Phase

| Phase | Status | Documentation |
| --- | --- | --- |
| 12 - Runtime And Notification Reliability | Automated package gate complete; owner acceptance pending | [`phases/phase-12-runtime-notifications/`](phases/phase-12-runtime-notifications/) |

Phase 11A-11G provide typed provider-neutral events, fail-closed validation,
hashed SQLite deduplication receipts, Gmail metadata-only OAuth/polling, an
official Discord Bot Gateway adapter, proactive delivery through the existing
voice/presentation system, and privacy-safe Settings diagnostics. Automated and
packaged gates pass, and the owner accepted real Gmail and Discord delivery on
2026-08-28. Animation artwork work remains paused without removing its
infrastructure.

Phase 12 now provides the pre-runtime single-instance guard, sanitized
Notification Center, bounded aggregation and channel policy, GPT-SoVITS
recovery, unified provider diagnostics, and a consolidated PyInstaller
candidate. Automated packaged verification passes; final owner interaction and
tray-shutdown acceptance remain open.

## Current Roadmap

- [`roadmap/VOICE_INTELLIGENCE_V0_V8.md`](roadmap/VOICE_INTELLIGENCE_V0_V8.md)
  is the single authoritative plan and progress record for Post-Phase 8 Voice
  Intelligence. V0 through V7 are complete; V8 owns the final standalone
  hosted-live build and packaged smoke gate.
- [`roadmap/PROJECT_BACKLOG.md`](roadmap/PROJECT_BACKLOG.md) contains deferred
  project work that does not belong to an active phase.

## Shared Reference

- [`reference/CODEBASE_STRUCTURE.md`](reference/CODEBASE_STRUCTURE.md):
  maintained source and test ownership map.
- [`reference/AKIHA.md`](reference/AKIHA.md): character identity reference.
- [`reference/AI_PROVIDERS.md`](reference/AI_PROVIDERS.md): AI provider setup.
- [`reference/LOCAL_DATA_PRIVACY.md`](reference/LOCAL_DATA_PRIVACY.md): local
  data and privacy behavior.
- [`reference/SECURITY_REVIEW.md`](reference/SECURITY_REVIEW.md): maintained
  security posture.
- [`reference/PET_ANIMATION_ARCHITECTURE.md`](reference/PET_ANIMATION_ARCHITECTURE.md):
  retained animation boundaries and canonical-asset rules while artwork work is
  paused.

## Archive

`archive/` contains historical architecture inputs. These files explain early
decisions but are not authoritative for current status or module paths.
