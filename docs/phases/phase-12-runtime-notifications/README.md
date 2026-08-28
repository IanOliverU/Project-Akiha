# Phase 12: Runtime And Notification Reliability

**Status:** In progress - Phase 12A complete; Phase 12B is next

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

The future Notification Center may persist only bounded, rendered notification
records needed by the user-facing inbox, such as service, event kind, priority,
sanitized display text, timestamps, and read/delivery state. It must not persist
email bodies, Discord message content, attachments, OAuth credentials, bot
tokens, raw provider responses, or unrestricted external payloads.

Migration `0014`, if required by Phase 12B, is reserved for this bounded inbox
and queue state. Phase 12A requires no database migration.

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

- [ ] Define the bounded user-facing notification record.
- [ ] Add migration `0014` only if durable inbox state is approved and required.
- [ ] Add repository retention, read/unread state, and explicit clear controls.
- [ ] Build the Notification Center with existing UI patterns and semantic
  priority states.
- [ ] Prove that raw communication content and credentials cannot enter it.

### 12C: Pending-notification queue and aggregation

- [ ] Queue notifications while higher-priority presentation owns the surface.
- [ ] Aggregate compatible events by service, kind, and bounded time window.
- [ ] Preserve important events without repeatedly announcing low-priority
  activity.
- [ ] Resume delivery through the existing proactive path.

### 12D: Per-event visual, chat, and voice policy

- [ ] Add explicit channel policy without replacing `NotificationPolicy`.
- [ ] Support visual-only, chat, voice, and silent outcomes per event category.
- [ ] Preserve quiet hours, event preferences, cooldowns, deduplication, and
  voice arbitration.

### 12E: GPT-SoVITS crash detection and bounded recovery

- [ ] Add starting, healthy, degraded, unavailable, and recovering health states.
- [ ] Detect managed-process and API health failure without crashing Akiha.
- [ ] Attempt bounded recovery with backoff and an explicit retry limit.
- [ ] Keep chat, integrations, pet state, memory, and assistant actions available
  when speech is degraded.

### 12F: Unified provider health and startup diagnostics

- [ ] Define one bounded health snapshot for optional providers.
- [ ] Report startup duration and actionable unavailable/auth/network states.
- [ ] Reuse Settings and privacy-safe logs rather than adding a blocking startup
  screen.
- [ ] Keep optional providers from delaying core application readiness.

### 12G: Consolidated package

- [ ] Include the final accepted Phase 11 Gmail and Discord source corrections.
- [ ] Include completed Phase 12 runtime changes.
- [ ] Build a fast development candidate before any clean release candidate.
- [ ] Validate package privacy and dependency completeness.

### 12H: Reliability and packaged verification

- [ ] Run the complete automated quality gate.
- [ ] Verify second-launch activation in the packaged application.
- [ ] Verify notification persistence, aggregation, and channel policy.
- [ ] Verify GPT-SoVITS failure and bounded recovery.
- [ ] Verify Gmail, Discord, local voice, Gemini Live, and graceful shutdown.
- [ ] Record owner acceptance and formally close Phase 12.

## Exit Criteria

Phase 12 closes only when one Akiha process owns runtime resources, notification
delivery remains useful without becoming noisy, optional voice failure cannot
take down the companion, diagnostics are actionable and privacy-safe, and the
consolidated packaged candidate passes owner acceptance.
