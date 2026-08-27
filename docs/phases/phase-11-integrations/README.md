# Phase 11: External Communication Integrations

**Status:** Architecture proposed on 2026-08-27; implementation awaiting owner
approval

## Purpose

Phase 11 makes Akiha more aware of important incoming communications without
turning her into an autonomous account agent. Gmail and Discord remain optional,
read-only integrations. They produce validated typed events and reuse Akiha's
existing proactive delivery, dialogue identity, voice, and presentation
boundaries.

Animation artwork development is paused. This phase does not remove or rewrite
the retained animation architecture and does not require new sprite assets.

## Non-Negotiable Boundaries

- No email or Discord message sending, replying, deleting, archiving, accepting,
  blocking, or account mutation.
- No Discord self-bot, normal-user token automation, browser-cookie scraping, or
  notification-screen scraping.
- No password, token, cookie, message body, or attachment enters a prompt, log,
  conversation transcript, behavior-history payload, or long-term memory.
- OAuth refresh tokens and bot credentials, where an approved mode requires
  them, use the existing Windows DPAPI credential store under separate
  namespaces.
- Providers never receive the event bus, voice controller, animation provider,
  pet state service, AI provider, or renderer.
- External content cannot directly mutate memory, pet state, animation, voice,
  or assistant permissions.
- Integration failure cannot block application startup or disable local Akiha
  features.

## Existing Architecture To Reuse

| Existing component | Phase 11 use |
| --- | --- |
| `EventBus` and `EventType` | Carry validated application-owned event envelopes after worker-thread handoff |
| `NotificationPolicy` | Enforce global proactive enablement, activity awareness, cooldowns, and quiet hours |
| `ProactiveDeliveryController` | Deliver approved notices to visible chat or the system tray |
| `ProactiveSpeechController` and `AssistantSpeechController` | Route approved notification speech through the current identity styling and GPT-SoVITS path |
| `VoiceController` and presentation arbitration | Prevent competing playback and preserve current speaking/listening ownership |
| `EncryptedCredentialStore` | Store namespaced OAuth refresh tokens or bot credentials as DPAPI ciphertext |
| `UserConfigStore` and `SettingsWindow` | Persist non-secret integration preferences and expose connection controls |
| SQLite migrator/repository pattern | Persist minimal sync cursors and deduplication receipts |
| `EventLogger` and diagnostics conventions | Record privacy-safe health and failure codes, never communication contents |

The existing `ProactiveSuggestionEngine` is specialized for activity and pet
check-ins. External integrations should not force service-specific logic into
that engine. They should enter immediately before the shared notification
policy and delivery path through one small integration coordinator.

## Proposed Architecture

```text
Official external API
    -> IntegrationProvider worker
        -> ExternalEvent candidate
            -> schema and privacy validator
                -> deduplication repository
                    -> deterministic classifier
                        -> IntegrationNotificationPolicy
                            -> trusted notification renderer
                                -> PROACTIVE_SUGGESTION_READY
                                    -> existing proactive delivery
                                        -> existing speech and presentation
```

### New abstractions that are justified

`ExternalIntegrationProvider`

- Owns `start`, `stop`, `refresh`, and privacy-safe health reporting.
- Emits candidates through a callback or Qt signal.
- Has no access to application presentation or AI services.

`ExternalEvent`

- Immutable typed envelope containing service, external ID, event kind,
  timestamp, bounded sender display metadata, classification, and confidence.
- Does not contain raw bodies, attachments, OAuth data, browser data, or
  arbitrary provider JSON.

`ExternalEventValidator`

- Rejects malformed, oversized, unsupported, stale, or secret-like fields.
- Produces an application-owned normalized event.

`ExternalEventRepository`

- Stores minimal receipts and sync cursors for deduplication and recovery.
- Does not become a communication archive.

`IntegrationNotificationCoordinator`

- Applies per-service preferences, priority mapping, coalescing, expiry, and the
  existing global notification policy.
- Publishes only a trusted bounded proactive delivery request.
- Maintains a small queue when Akiha is already speaking; it does not create a
  second voice or presentation controller.

`ExternalNotificationRenderer`

- Centralizes Akiha-style notification wording.
- The first implementation is deterministic and local.
- A future optional LLM renderer may receive only explicitly approved sanitized
  fields and must preserve uncertainty language for classifications.

### Proposed event kinds

```text
gmail.new_message
gmail.important_message
gmail.work_candidate
gmail.recruiter_candidate
gmail.interview_candidate
gmail.personal_candidate
gmail.newsletter_candidate
gmail.promotional_candidate

discord.bot_direct_message
discord.mention
discord.authorized_channel_message
discord.relationship_changed        # Social SDK feasibility dependent
discord.friend_request_candidate    # Social SDK feasibility dependent
discord.friend_direct_message       # Social SDK feasibility dependent
discord.unknown_direct_message      # Social SDK feasibility dependent
```

Provider-specific event kinds remain values inside a normalized event model.
The global `EventType` enum needs only a small number of lifecycle events such
as candidate received, notification ready, and integration health changed; it
does not need one application-bus member per external subtype.

## Gmail Integration

### Official approach

Use the Gmail REST API with a Google **Desktop app** OAuth client and a loopback
redirect on `127.0.0.1`. Request the narrow
`https://www.googleapis.com/auth/gmail.metadata` scope. Access tokens remain
memory-only; the refresh token is DPAPI-encrypted in the existing credential
store. The OAuth client ID is public configuration, not a password. No client
secret is embedded in the package.

Google classifies `gmail.metadata` as a restricted scope. Personal development
can use an explicitly configured OAuth test user, but test-mode authorization
and refresh tokens normally expire after seven days. Public distribution would
require the applicable Google OAuth verification and policy work. Because Akiha
keeps restricted Gmail data on the user's device and does not transmit it to a
server by default, a server-side data security assessment may not apply, but
that must be confirmed against Google's release requirements before publishing.

For a local desktop companion, begin with bounded incremental polling rather
than Gmail push notifications. Gmail push requires a Google Cloud Pub/Sub topic,
publisher permissions, subscription management, watch renewal at least every
seven days, and dropped-notification recovery. Google also recommends poll-based
synchronization for user-owned devices. A later opt-in Pub/Sub mode can implement
the same provider protocol without changing the rest of Akiha.

### Read path

1. Connection establishes a baseline without announcing old mail.
2. A bounded worker periodically requests mailbox changes.
3. `users.history.list` advances from the last committed history ID.
4. New message IDs are fetched with `users.messages.get(format=metadata)` and
   only required headers such as `From`, `Subject`, and `Date`.
5. Labels and local deterministic rules classify the event.
6. The cursor commits only after normalized events are safely recorded.
7. An expired history cursor triggers a bounded resynchronization, not a full
   historical notification flood.

The initial classifier uses Gmail labels plus local subject/sender rules.
`IMPORTANT` and `CATEGORY_PROMOTIONS` can provide useful signals. Recruiter,
interview, work, personal, and newsletter classifications remain candidates,
not facts. Hosted LLM classification is outside the first implementation.

## Discord Integration

### Confirmed official boundary

Automating a normal Discord account with a user token is a prohibited self-bot
pattern and is excluded.

The ordinary Bot/Gateway API can support:

- Mentions and configured messages in servers where the bot is installed and
  has permission.
- Direct messages sent to the bot account.
- Message content allowed by Discord intents and the bot's access.

It cannot represent the bot as the user's normal account, join the user's
existing private DMs, inspect the user's ordinary friends list, or detect the
user account's friend requests.

Discord's official Social SDK/RPC documentation exposes account linking,
relationships, friend-request relationship states, and communication events.
However, it is a native SDK oriented toward games/interactive applications,
requires Discord application setup and testers during development, and places
approval/rate-limit requirements on communication features for production.

### Phase 11 decision gate

Phase 11C begins with a contained feasibility spike, not an assumption:

1. Confirm Project Akiha is eligible for the Discord Social SDK and its terms.
2. Confirm the required Windows x64 SDK can be used from this Python/Qt product
   without placing account secrets in Python or prompts.
3. Confirm relationship and DM event access works for an approved tester.
4. Measure packaging and lifecycle impact.
5. Stop if official access is unavailable or requires unsupported behavior.

If the Social SDK path is approved and practical, isolate it behind a small
native adapter/sidecar implementing `ExternalIntegrationProvider`. The sidecar
may send only normalized bounded events to Akiha over a local authenticated
channel. It must not receive Akiha's AI, memory, action, or renderer objects.

If that path is not practical, Phase 11C is explicitly reduced to the official
bot scope: authorized server mentions/messages and DMs sent to Akiha's bot.
Personal friend DMs and friend requests remain unsupported. No workaround is
permitted.

## Notification Policy

External event priority is separate from the existing delivery urgency so the
old behavior system remains compatible:

| External priority | Existing delivery mapping | Default behavior |
| --- | --- | --- |
| `critical` | `high` | Visual and voice unless explicitly muted |
| `important` | `high` | Visual and voice, quiet-hours policy configurable |
| `normal` | `normal` | Visual; voice if enabled and available |
| `low` | `low` | Visual or digest |
| `silent` | none | Record receipt only |

The integration policy checks event-specific settings, duplicate status,
coalescing, expiry, current activity, current voice ownership, quiet hours, and
the existing global cooldown. Multiple low-priority events should form one
summary instead of repeated announcements. Important events may use a separate
configurable cooldown but must never interrupt active user speech.

The first renderer uses centralized local wording such as "This appears to be
an interview invitation." It never presents a heuristic classification as a
certainty. Dialogue generation may be added later only behind an explicit
privacy setting.

## Voice And Presentation

After successful proactive delivery, the existing speech path remains:

```text
Proactive delivery result
    -> ProactiveSpeechController
        -> AssistantSpeechController
            -> VOICE_SPEAK_REQUESTED
                -> configured GPT-SoVITS provider
```

`ProactiveSpeechController` currently resolves speech from a fixed event-kind
table. Phase 11 may extend it to accept a trusted rendered speech field or a
renderer callback, but it must continue to call the same
`AssistantSpeechController`. If voice is busy, the integration coordinator may
retain a bounded expiring notification until the existing voice state becomes
idle.

No integration controls animation. An important notification may request an
existing checking-in/attention presentation through the established typed
presentation owner. Missing or unavailable visual states simply leave Akiha in
her current safe presentation.

## Persistence And Migration

The next migration number is `0013`. The proposed migration owns two small
tables:

`external_event_receipts`

- `service`
- `external_id`
- `event_kind`
- bounded sender display value or sender hash, according to the final privacy
  setting
- `occurred_at`
- `classification`
- `priority`
- `notification_status`
- `notified_at`
- `created_at`
- unique key on `(service, external_id)`

`integration_sync_state`

- service and local account key
- provider cursor/history ID
- last successful check
- last privacy-safe health code
- backoff state

No body, snippet, attachment, conversation history, token, or arbitrary provider
response is persisted. Retention is bounded and user-clearable. Disconnecting
an integration removes its credential and optionally its receipts/cursor after
explicit confirmation.

## Settings Impact

Extend the existing Settings navigation with one **Integrations** page. Do not
redesign Settings.

Gmail controls:

- Enable/disable, Connect, Disconnect, connection health, and last successful
  check.
- New, important, recruiter, interview, work, personal, newsletter, and
  promotional notification toggles.
- Poll interval within a safe bounded range.

Discord controls:

- Clearly display the active official mode: Social SDK or Bot.
- Connect/Disconnect or encrypted bot-credential controls as applicable.
- Bot DM, mention, and authorized-channel toggles.
- Relationship/friend controls appear only if the Social SDK feasibility gate
  passes.
- Server monitoring defaults off and requires an explicit channel allowlist.

Shared controls:

- Visual notifications, voice notifications, event retention, and a link to
  existing quiet-hours settings.
- Test notification and Check connection diagnostics using synthetic metadata,
  never a real private message.

## Privacy And Logging Requirements

The current `EventLogger` returns most event payloads unchanged. Therefore no
external communication event may be published until the logger has an explicit
redaction branch for external event types. This is a Phase 11A blocker.

Similarly, the existing behavior repository must receive only the sanitized
notification outcome, never raw Gmail or Discord provider data. External event
receipts use their dedicated minimal repository and do not enter memory or chat
persistence unless the user explicitly asks Akiha to discuss a visible notice.

Privacy diagnostics may include service, connection state, event kind, result
code, duration, retry count, and whether optional metadata was present. They may
not include sender addresses, subjects, message text, guild/channel names,
tokens, URLs containing identifiers, or raw exception bodies.

## Offline And Failure Behavior

- Providers start asynchronously after the main UI and local systems are ready.
- Network calls run outside the Qt UI thread with bounded timeouts and explicit
  cancellation.
- Rate limits use provider-directed retry timing plus capped exponential
  backoff and jitter.
- Expired/revoked OAuth moves only that integration to `reauthorization_needed`.
- Malformed responses are rejected before cursor advancement.
- A provider crash changes health state and schedules a bounded retry; it does
  not close Akiha.
- Shutdown cancels workers, waits for bounded cleanup, and rejects late
  callbacks.
- Application restart resumes from the committed cursor and dedupe receipts.

Because `EventBus` is synchronous, worker threads must marshal validated events
onto the Qt/application thread before publishing. Providers must never publish
directly from their network worker thread.

## Testing Strategy

### Unit tests

- External event schema, size limits, and secret-like field rejection.
- Classification uncertainty and priority mapping.
- Event preference, cooldown, quiet-hours, busy-voice, coalescing, and expiry.
- Stable-ID deduplication and bounded retention.
- Event logger and diagnostics redaction.
- OAuth state/PKCE validation, token refresh, revocation, and disconnect.
- Gmail baseline, incremental history, cursor expiry, pagination, and malformed
  response handling.
- Discord mode capability restrictions and unsupported-event rejection.
- No external event enters memory or pet state.

### Integration tests

- Fake Gmail and Discord transports feed the same normalized pipeline.
- Repository migration works with fresh and existing databases.
- Qt-thread handoff prevents direct worker-thread UI/event-bus mutation.
- A delivered notice reuses chat/tray and existing speech arbitration.
- Offline/rate-limit/provider-crash cases leave local Akiha operational.

### Manual and packaged checks

- Browser OAuth success, denial, timeout, and reconnect.
- New events notify once across restart.
- Quiet hours and toggles suppress expected channels.
- GPT-SoVITS speaks only approved notifications and does not overlap active
  conversation.
- Disconnect removes access and does not leave plaintext credentials.
- Standalone artifact contains no developer credentials or private event data.

## Phase 11 Plan And Todo

### 11A: Integration foundation

- [x] Audit existing event, proactive delivery, credential, settings,
  persistence, voice, and presentation boundaries.
- [x] Verify current official Gmail and Discord integration options.
- [ ] Add provider-neutral external event models and provider lifecycle protocol.
- [ ] Add privacy validation and explicit `EventLogger` redaction before event
  publication.
- [ ] Add the integration coordinator and Qt-thread handoff.
- [ ] Add focused foundation tests.

### 11B: Gmail read-only integration

- [ ] Add desktop OAuth with PKCE/loopback callback and DPAPI refresh-token
  storage.
- [ ] Add metadata-only Gmail client and bounded incremental polling.
- [ ] Establish a no-history-flood baseline and cursor recovery.
- [ ] Add deterministic best-effort classification.
- [ ] Add Gmail fake-transport and failure tests.

### 11C: Discord read-only integration

- [ ] Complete the Discord Social SDK eligibility and Windows feasibility spike.
- [ ] Record the approved capability mode and unsupported events.
- [ ] Implement either the approved Social SDK adapter or the restricted Bot
  Gateway adapter.
- [ ] Add mention/DM/channel allowlist handling only within the selected official
  mode.
- [ ] Add disconnect, rate-limit, resume, and failure tests.

### 11D: Proactive notification integration

- [ ] Add per-event preferences, priority mapping, cooldowns, coalescing, and
  expiry.
- [ ] Add stable-ID deduplication and minimal receipt persistence.
- [ ] Add centralized uncertainty-aware Akiha notification wording.
- [ ] Reuse existing chat/tray delivery and GPT-SoVITS speech arbitration.
- [ ] Reuse only existing presentation cues; add no artwork.

### 11E: Settings and diagnostics

- [ ] Add the Integrations Settings page using existing UI patterns.
- [ ] Add connection, reconnect, disconnect, and per-event controls.
- [ ] Add privacy-safe health, last-check, rate-limit, and retry diagnostics.
- [ ] Add synthetic Test notification controls.

### 11F: Security, privacy, deduplication, and failure verification

- [ ] Add migration `0013` and fresh/existing-data tests.
- [ ] Verify no body, attachment, secret, raw response, or private URL is logged
  or persisted.
- [ ] Verify external content cannot enter memory, pet state, assistant actions,
  voice, or animation directly.
- [ ] Verify restart deduplication, retention cleanup, offline behavior, and
  graceful shutdown.
- [ ] Reconcile privacy notice, local-data, security-review, and packaging docs.

### 11G: Final verification and release gate

- [ ] Run the complete automated quality gate.
- [ ] Complete real-account source smoke tests using owner-controlled test
  messages.
- [ ] Build one consolidated candidate only after source acceptance.
- [ ] Validate fresh and existing packaged data, credentials, shutdown, and
  artifact privacy.
- [ ] Record manual acceptance and formally close Phase 11.

## Explicitly Deferred

- Sending or modifying Gmail/Discord content.
- Automatic acceptance, blocking, moderation, or account changes.
- Raw-body or attachment analysis.
- Hosted LLM classification of private communications.
- Gmail Pub/Sub infrastructure.
- Discord self-bot/user-token automation.
- New notification artwork or animation assets.
- Single-instance, GPT-SoVITS recovery, weather, reminders, backup/export, and
  broader assistant improvements unless a direct Phase 11 dependency is found.

## Approval Gate

No Phase 11 runtime implementation begins until the owner approves this
architecture, including the Discord feasibility gate and the Gmail
metadata-only polling decision.

## Official References

- Gmail desktop OAuth:
  <https://developers.google.com/identity/protocols/oauth2/native-app>
- Gmail message metadata:
  <https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get>
- Gmail restricted-scope classification:
  <https://developers.google.com/workspace/gmail/api/auth/scopes>
- Gmail push notifications and polling guidance:
  <https://developers.google.com/workspace/gmail/api/guides/push>
- Discord self-bot policy:
  <https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots>
- Discord Gateway and intents:
  <https://docs.discord.com/developers/events/gateway>
- Discord RPC:
  <https://docs.discord.com/developers/topics/rpc>
- Discord Social SDK:
  <https://docs.discord.com/developers/discord-social-sdk/getting-started>
