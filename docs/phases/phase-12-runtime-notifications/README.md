# Phase 12: Runtime And Notification Reliability

**Status:** Implementation and automated package gate complete; owner packaged
acceptance pending

## Purpose

Phase 12 hardens Akiha's runtime and notification delivery without expanding
external-account permissions. It prevents duplicate application runtimes,
adds a privacy-safe notification inbox and aggregation path, makes notification
channels configurable by event type, and improves optional provider recovery
and diagnostics.

Phase 12 does not add Gmail or Discord write access. It does not create a new
event bus, voice system, proactive delivery system, or presentation arbiter.

## Architecture

```text
Application launch
        |
        v
SingleInstanceCoordinator
   | primary                  | secondary
   v                          v
Runtime composition      Send activate request
   |                          |
   v                          v
Existing Akiha process   Exit without providers or SQLite

Validated ExternalEvent
        |
        v
Hashed deduplication receipt
        |
        v
Sanitized Notification Inbox
        |
        v
Pending queue and aggregation
        |
        v
Per-event channel policy
        |
        v
Existing proactive delivery and presentation arbitration
        |
        +--> Notification Center
        +--> Chat / tray
        +--> Existing GPT-SoVITS speech path
```

External providers remain information sources. They cannot control windows,
voice engines, assistant actions, pet state, or rendering directly.

## Privacy Boundary

The Notification Center persists only bounded, rendered notification records
needed by the user-facing inbox: service, event kind, priority, sanitized display
text, timestamps, aggregate count, and read/delivery state. It does not persist
email bodies, Discord message content, attachments, OAuth credentials, bot
tokens, raw provider responses, or unrestricted external payloads.

Migration `0014` owns only this bounded inbox. Deferred queue contents remain
bounded and in memory; Phase 12A requires no database migration.

## Plan And Todo

### 12A: Single-instance protection

- [x] Claim a user-scoped local IPC endpoint before opening SQLite or starting
  providers.
- [x] Make a second launch request activation of the existing Akiha process.
- [x] Show and focus the most relevant existing Akiha window.
- [x] Exit the second process without starting Gmail, Discord, voice, timers, or
  another tray icon.
- [x] Clean up stale endpoints safely and release ownership on graceful quit.
- [x] Add deterministic primary, secondary, activation, cleanup, and race tests.

The guard uses a user-scoped Qt local endpoint whose name contains only a hash
of Akiha's local-data location. Only the fixed `activate` command is accepted.
The primary acknowledges it and raises the active Akiha window, or shows the pet
when no application window is currently active.

### 12B: Sanitized Notification Center

- [x] Define the bounded user-facing notification record.
- [x] Add migration `0014` for durable sanitized inbox state.
- [x] Add repository retention, read/unread state, and explicit clear controls.
- [x] Build the Notification Center with existing UI patterns and semantic
  priority states.
- [x] Prove that raw communication content and credentials cannot enter it.

### 12C: Pending-notification queue and aggregation

- [x] Queue notifications while higher-priority presentation owns the surface.
- [x] Aggregate compatible events by service, kind, and bounded time window.
- [x] Preserve important events without repeatedly announcing low-priority
  activity.
- [x] Resume delivery through the existing proactive path.

### 12D: Per-event visual, chat, and voice policy

- [x] Add explicit channel policy without replacing `NotificationPolicy`.
- [x] Support visual-only, chat, voice, and silent outcomes per event category.
- [x] Preserve quiet hours, event preferences, cooldowns, deduplication, and
  voice arbitration.

### 12E: GPT-SoVITS crash detection and bounded recovery

- [x] Add starting, healthy, degraded, unavailable, and recovering health states.
- [x] Detect managed-process and API health failure without crashing Akiha.
- [x] Attempt bounded recovery with backoff and an explicit retry limit.
- [x] Keep chat, integrations, pet state, memory, and assistant actions available
  when speech is degraded.

### 12F: Unified provider health and startup diagnostics

- [x] Define one bounded health snapshot for optional providers.
- [x] Report startup duration and actionable unavailable/auth/network states.
- [x] Reuse Settings and privacy-safe logs rather than adding a blocking startup
  screen.
- [x] Keep optional providers from delaying core application readiness.

### 12G: Consolidated package

- [x] Include the final accepted Phase 11 Gmail and Discord source corrections.
- [x] Include completed Phase 12 runtime changes.
- [x] Build a fast development candidate before any clean release candidate.
- [x] Validate package privacy and dependency completeness.

### 12H: Reliability and packaged verification

- [x] Run the complete automated quality gate.
- [x] Verify second-launch activation in the packaged application.
- [x] Verify notification persistence, aggregation, and channel policy.
- [x] Verify GPT-SoVITS failure and bounded recovery.
- [x] Verify packaged Gemini Live and GPT-SoVITS with real provider smoke.
- [ ] Verify packaged Gmail, Discord, Local Modular voice, and tray shutdown with
  owner-controlled interactions.
- [ ] Record owner acceptance and formally close Phase 12.

## Verification Record

On 2026-09-02, the corrected source tree passed 1,684 tests with 3 expected
skips, Ruff, Black, Python compilation, migration coverage, and source startup
smoke. The cached PyInstaller one-folder candidate at
`dist/pyinstaller-phase12/Akiha` built in 114.570 seconds. It passed artifact
privacy/dependency validation, Windows GUI-subsystem validation, migration
`0014` on fresh and existing data, clean startup logs, and packaged
second-launch activation.

The packaged provider runtime smoke also passed the real Gemini SDK/session
boundary, GPT-SoVITS health, and real in-memory GPT-SoVITS synthesis. The
remaining owner checks are recorded in
`PHASE12_MANUAL_SMOKE_2026-09-02.md`; they are not represented as complete until
the packaged UI, account-event, Local Modular voice, and tray-exit behavior are
accepted.

## Exit Criteria

Phase 12 closes only when one Akiha process owns runtime resources, notification
delivery remains useful without becoming noisy, optional voice failure cannot
take down the companion, diagnostics are actionable and privacy-safe, and the
consolidated packaged candidate passes owner acceptance.
