# Codebase Structure

This is the maintained ownership map for Project Akiha. Historical architecture
inputs live under `docs/archive/` and must not be used as a current folder map.

```text
project_akiha/
|-- app/                  # Composition root and application coordinators
|-- config/               # Typed settings and bundled defaults
|-- core/                 # Framework-free domain models, policy, and state
|   `-- utilities/        # Non-executable utility ownership, result, and clock contracts
|-- database/             # SQLite repositories and ordered migrations
|-- integrations/         # Optional external-product integrations
|   |-- discord/          # Official bot Gateway and metadata normalization
|   |-- gmail/            # Desktop OAuth, metadata polling, classification
|   `-- spotify/          # Spotify OAuth, catalog, device, and playback logic
|-- providers/            # Swappable AI, animation, voice, and hosted-live adapters
|-- services/             # Cross-cutting application services
|-- tools/                # Package and release verification entry points
`-- ui/                   # PySide6 windows, renderers, and background workers

tests/unit/               # Mirrors the runtime ownership structure
spikes/                   # Non-packaged bounded architecture experiments
scripts/                  # Build, smoke, benchmark, and release automation
assets/                   # Runtime animation and visual assets
docs/                     # Phase, roadmap, reference, and archived documentation
```

## Ownership Rules

- `core/` does not import Qt, concrete providers, Spotify, or Windows APIs.
- `app/` coordinates use cases and performs dependency wiring; it does not own
  provider protocols or domain policy.
- `providers/` owns replaceable implementation adapters for a capability.
- `integrations/` owns optional third-party product workflows that combine
  authentication, API calls, and application-specific behavior.
- `services/` owns cross-cutting behavior shared by more than one UI or
  integration boundary.
- `ui/` owns presentation and Qt workers, not permission or execution policy.
- SQLite access remains behind repositories and schema changes remain ordered
  migrations.
- Assistant actions always cross the typed validation, scoped permission,
  execution, and sanitized audit boundary.
- Unit tests mirror source ownership so future moves remain discoverable.

## Current Integration Boundary

Spotify lives under `project_akiha/integrations/spotify/` because it is an
optional external product subsystem, not a generic service. Its UI authorization
worker remains under `ui/`, its permissions and action contracts remain under
the existing action system, and its composition remains in `app/main.py`.

This split keeps external API details out of framework-free core logic and does
not grant Spotify or any AI provider direct execution authority.

Gmail and Discord share provider-neutral contracts under
`core/integrations/`. Their concrete transports remain under
`integrations/gmail/` and `integrations/discord/`; lifecycle composition stays
in `app/external_integration_runtime.py`. Candidates cross
`ExternalEventValidator`, hashed receipt claiming, and the Qt application-thread
handoff before the existing proactive delivery path can see them.
`app/integration_notification_coordinator.py` owns preferences, expiry,
deduplication, bounded deferral/aggregation, per-event channels, and trusted
notification publication. It reuses the existing notification and speech
controllers and has no renderer, memory, pet-state, or assistant-action
authority. Migration `0013` stores only hashed receipts and sync cursors;
migration `0014` stores only rendered sanitized Notification Center records.
`ui/notification_center_window.py` owns read/clear presentation, while
`services/provider_health_registry.py` and `ui/provider_health_worker.py` expose
bounded optional-provider health without blocking application readiness. The
Settings OAuth worker and scheduler own Qt handoff only.

`app/single_instance.py` claims the user-scoped local activation endpoint before
runtime composition. A secondary process can request only activation and exits
without opening SQLite or starting providers.

Phase 13 utility declarations live under `core/utilities/`. They do not execute
actions or replace `core/actions/`: future utility proposals still cross
`ActionRequest`, the application-owned registry, permissions, confirmation,
execution, and audit. The utility catalog only fixes operation ownership,
allowed effects, network/storage limits, sanitized results, and clock injection
before implementations are exposed.

Hosted-live provider contracts remain in `core/voice_session/`, Gemini and its
Google SDK transport remain in `providers/live/`, and application ownership is
split between `app/conversation_runtime_router.py`,
`app/hosted_conversation_runtime.py`, and
`app/hosted_live_session_controller.py`. The persistent Qt/async handoff lives
in `ui/hosted_live_session_worker.py`; it owns no provider-selection policy.
This keeps Local Modular and Hosted Live as explicit sibling lanes rather than
allowing either provider to invoke the other as a fallback.

Pet simulation rules remain under `core/pet/`, revisioned persistence remains
in `database/sqlite_pet_repository.py`, and `services/pet_state.py` is the sole
mutation boundary. `ui/pet_care_window.py` presents validated snapshots and
emits only typed care requests; `ui/pet_care_worker.py` performs the Qt/async
handoff. Read-only pet values are assembled by
`services/pet_diagnostics.py`. `services/pet_status.py` aggregates those
values with typed local shop, appearance, activity, transaction, and privacy
diagnostics for `ui/pet_status_window.py` and Settings.
`ui/pet_maintenance_worker.py` owns the background status/reset handoff. Reset
remains an explicit confirmed UI operation and atomically replaces only pet
state, pet history, and pet reward grants; shop ownership, transactions, and
appearance selection remain intact. None of these UI modules accepts dialogue
or provider output as pet state.
The composition root settles runtime decay through a non-overlapping one-minute
worker. `app/proactive_controller.py` publishes validated need-band edges,
selects one deterministic priority cue, and reuses the existing notification
policy and delivery pipeline; `app/mood_controller.py` consumes only the
selected typed edge. Dialogue and provider modules have no reference to the
pet-state service or this mutation path.
