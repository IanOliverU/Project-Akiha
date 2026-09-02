# Phase 13: Everyday Assistant Utilities

**Status:** Planned - Phase 13A is next

## Purpose

Phase 13 makes Akiha more useful in ordinary desktop work through safe,
deterministic utilities. It improves clarification and confirmation, then adds
timers, one-shot reminders, read-only current information, contextual navigation
inside approved directories, and privacy-safe backup/export.

Akiha remains an assistant and companion rather than an unrestricted autonomous
agent. Phase 13 does not add arbitrary shell execution, silent filesystem
mutation, unrestricted web browsing, external-account write access, or
LLM-controlled execution.

## Architecture

```text
User request
    |
    v
Existing intent and proposal boundary
    |
    v
Ambiguity / confirmation policy
    |
    v
Typed utility command
    |
    +--> Timer / reminder service --> SQLite schedule
    +--> Read-only information provider
    +--> Approved-directory navigation
    +--> Explicit backup/export service
    |
    v
Sanitized result event
    |
    v
Existing dialogue, Notification Center, voice, and presentation arbitration
```

Provider text may propose a typed operation, but it cannot invoke schedulers,
filesystem APIs, network providers, or export writers directly.

## Plan And Todo

### 13A: Product, safety, and utility contract

- [ ] Audit the existing action registry, permission policy, event bus,
  notification system, Settings architecture, and SQLite boundaries.
- [ ] Define typed utility commands, results, reason codes, and capability
  ownership.
- [ ] Define timezone, clock, restart, expiry, and privacy rules.
- [ ] Explicitly prohibit arbitrary command execution and silent external or
  filesystem mutation.
- [ ] Record the Phase 13 migration and package-data contract before coding.

### 13B: Ambiguity and confirmation handling

- [ ] Detect missing targets, multiple plausible matches, uncertain times, and
  incomplete consequential requests.
- [ ] Ask one concise clarification instead of guessing.
- [ ] Reuse existing scoped permissions and confirmations for consequential
  operations.
- [ ] Bind a clarification response to the original typed proposal with an
  expiry and replay protection.
- [ ] Add deterministic ambiguity, cancellation, stale-response, and injection
  tests.

### 13C: One-shot timers

- [ ] Add create, list, inspect, cancel, and optional snooze operations for
  one-shot timers.
- [ ] Use monotonic timing while running and persist enough wall-clock state for
  restart recovery.
- [ ] Deliver elapsed timers through the existing Notification Center, chat,
  tray, voice, and presentation arbitration.
- [ ] Prevent duplicate delivery after restart or clock changes.
- [ ] Add simultaneous-timer, cancellation, shutdown, and recovery tests.

### 13D: Durable reminders

- [ ] Add one-shot reminders with explicit local date, time, and timezone
  interpretation.
- [ ] Add list, cancel, and snooze operations without introducing a second
  scheduler.
- [ ] Define a bounded missed-reminder grace policy for application downtime.
- [ ] Add migration `0015` only for minimal timer/reminder state and delivery
  receipts.
- [ ] Keep recurring reminders deferred until one-shot behavior is accepted.

### 13E: Read-only weather and current information

- [ ] Define a provider-neutral, read-only current-information contract.
- [ ] Start with weather, forecast timestamps, and relevant official weather
  alerts using an explicitly configured location.
- [ ] Show source, freshness, uncertainty, and offline/error states.
- [ ] Keep network results out of long-term memory unless the user explicitly
  requests a separate saved memory.
- [ ] Do not add unrestricted browsing or allow information providers to invoke
  assistant actions.

### 13F: Contextual file and directory navigation

- [ ] Reuse approved-directory grants and the existing typed action boundary.
- [ ] Resolve contextual names only inside approved roots and ask when multiple
  matches exist.
- [ ] Support read-only discovery and explicit opening through existing action
  permissions.
- [ ] Do not read file contents, mutate files, traverse outside approved roots,
  or accept provider-supplied arbitrary paths.
- [ ] Add path traversal, symlink/reparse-point, ambiguity, and revocation tests.

### 13G: Conversation and memory backup/export

- [ ] Define a versioned, user-controlled export format and manifest.
- [ ] Export only explicitly selected conversations or memories to a selected
  destination.
- [ ] Exclude credentials, integration tokens, raw provider responses, logs,
  private notification receipts, and local voice references.
- [ ] Require explicit confirmation before writing and report partial failures
  safely.
- [ ] Keep restore/import deferred until export integrity and privacy are
  accepted.

### 13H: Settings, diagnostics, privacy, and failure recovery

- [ ] Add focused controls for timers, reminders, location, provider health,
  retention, and export.
- [ ] Reuse the unified provider-health and Notification Center surfaces.
- [ ] Add bounded diagnostics for scheduler drift, missed reminders, network
  failure, and export errors.
- [ ] Verify logs, events, exports, and packages contain no credentials or
  unnecessary private content.
- [ ] Confirm every utility degrades without breaking chat, voice, pet state,
  memory, Gmail, Discord, or startup.

### 13I: Final verification and consolidated release gate

- [ ] Run the complete source quality and migration gate.
- [ ] Verify fresh and existing databases, restart recovery, deduplication,
  timezone behavior, and offline operation.
- [ ] Perform owner-controlled timer, reminder, weather, navigation, and export
  smoke tests.
- [ ] Build one fast consolidated PyInstaller candidate after source acceptance.
- [ ] Verify package privacy, dependency completeness, single-instance behavior,
  providers, voice, and graceful shutdown.
- [ ] Record owner acceptance and formally close Phase 13.

## Explicitly Deferred

- Recurring reminders and calendar synchronization.
- General-purpose web browsing or autonomous research.
- File-content ingestion, file mutation, restore/import, and cloud backup.
- Gmail or Discord write actions.
- Arbitrary shell commands or unrestricted application control.
- New animation artwork while the approved animation architecture remains
  preserved.
- Installer, code signing, auto-update, and public-distribution work.

## Exit Criteria

Phase 13 closes only when Akiha asks rather than guesses, timers and reminders
survive restart without duplicate delivery, current information is sourced and
read-only, navigation stays inside approved roots, exports exclude secrets, and
the consolidated package passes automated and owner acceptance.
