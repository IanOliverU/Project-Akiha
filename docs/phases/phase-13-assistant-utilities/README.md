# Phase 13: Everyday Assistant Utilities

**Status:** In progress - Phase 13A complete; Phase 13B is next

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

- [x] Audit the existing action registry, permission policy, event bus,
  notification system, Settings architecture, and SQLite boundaries.
- [x] Define typed utility commands, results, reason codes, and capability
  ownership.
- [x] Define timezone, clock, restart, expiry, and privacy rules.
- [x] Explicitly prohibit arbitrary command execution and silent external or
  filesystem mutation.
- [x] Record the Phase 13 migration and package-data contract before coding.

## Phase 13A Architecture Record

### Reused boundaries

| Existing component | Phase 13 responsibility |
| --- | --- |
| `ActionRequest` and `ActionRegistry` | Remain the only typed command envelope and executable allowlist. |
| `ProviderActionProposalGateway` | Retains active-turn, replay, and opaque local-result protection for provider proposals. |
| `AssistantActionService` | Remains the validation, permission, confirmation, execution, cancellation, and audit coordinator. |
| `ActionPermissionPolicy` and `ProtectedPathPolicy` | Continue to own approved-directory scope and protected-path rejection. |
| `EventBus` | Remains the only in-process event transport. |
| `NotificationPolicy`, proactive delivery, and Notification Center | Remain the only reminder/timer presentation path. |
| `UserConfigStore` and Settings | Remain the only user-editable configuration boundary. |
| `DatabaseMigrator` | Remains the only ordered schema-change mechanism. |

Phase 13 does not introduce another command bus, permission service, scheduler
per utility, notification controller, voice path, or provider-controlled
executor.

### New framework-free contracts

`project_akiha/core/utilities/` contains a non-executable contract catalog. It
declares each approved operation's owner, maximum side effect, authorization,
network access, storage surface, approved-root requirement, and scheduled
notification capability. Merely appearing in this catalog does not expose an
operation to an AI provider or add it to the action registry.

The approved ownership matrix is:

| Utility group | Owner | Authorization | Maximum effect | Network | Storage |
| --- | --- | --- | --- | --- | --- |
| Timers and reminders | One schedule service | Active request | Local schedule only | None | Minimal schedule metadata |
| Current weather/forecast | Current-information provider | Active request | Read-only | Read-only | None |
| Directory search/open | Existing approved navigation | Scoped grant | Read-only/user-visible | None | None |
| Conversation/memory export | Export service | Confirm every time | User-selected local file write | None | User-selected export only |

`UtilityResult` permits only bounded summaries, scalar metadata, and closed
status/reason combinations. Raw provider payloads, nested objects, credentials,
message bodies, unrestricted paths, and arbitrary commands cannot cross this
result boundary.

### Clock and timezone rules

- Durable timestamps and due times use timezone-aware UTC.
- A reminder also retains the explicit user timezone used to interpret its
  local date/time. Ambiguous or nonexistent daylight-saving times require
  clarification instead of guessing.
- The monotonic clock is used only for elapsed time, active-process timers,
  cooldowns, and expiring proposals. Monotonic values are never persisted.
- While Akiha is running, a timer uses the monotonic clock to avoid wall-clock
  jumps. Its UTC due time is retained for restart recovery.
- Restart recovery compares persisted UTC due times with the current UTC wall
  clock and uses an explicit missed-delivery policy defined in 13D.
- Clarification and confirmation leases are request-bound, expiring, and replay
  protected. Their exact bounded lifetime is implemented in 13B, not stored as
  conversation memory.

`UtilityClock` is injectable so clock changes, restart, expiry, and timezone
behavior can be tested deterministically.

### Migration and package contract

Phase 13A adds no migration and persists no new user data. Migration `0015` is
reserved for 13C/13D and may contain only minimal timer/reminder schedule state
and delivery receipts: an opaque identifier, utility kind, bounded user label,
UTC due/created timestamps, explicit timezone, bounded status, and delivery or
cancellation timestamp. It must not contain prompts, transcripts, provider
responses, credentials, weather payloads, file contents, or export contents.

Clarification leases remain in memory. Weather responses are transient.
Navigation keeps the existing permission and sanitized audit tables. Exports
are written only to the destination selected by the user and are not copied
into SQLite.

When migration `0015` exists, both packaging paths must include it and the
artifact validator must require it. Any new weather dependency must be pinned,
explicitly collected, and exercised by package validation. Packages must never
include generated exports, local databases, credentials, location history, or
personal communication content.

### Explicit safety exclusions

The Phase 13 contract rejects arbitrary shell or script execution, unrestricted
URLs, provider-selected filesystem paths, traversal outside approved roots,
silent exports, external-account mutation, autonomous utility creation, and
direct LLM access to schedulers, network transports, repositories, or writers.

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
