# Codebase Structure

This is the maintained ownership map for Project Akiha. Historical architecture
inputs live under `docs/archive/` and must not be used as a current folder map.

```text
project_akiha/
|-- app/                  # Composition root and application coordinators
|-- config/               # Typed settings and bundled defaults
|-- core/                 # Framework-free domain models, policy, and state
|-- database/             # SQLite repositories and ordered migrations
|-- integrations/         # Optional external-product integrations
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

Hosted-live provider contracts remain in `core/voice_session/`, Gemini and its
Google SDK transport remain in `providers/live/`, and application ownership is
split between `app/conversation_runtime_router.py`,
`app/hosted_conversation_runtime.py`, and
`app/hosted_live_session_controller.py`. The persistent Qt/async handoff lives
in `ui/hosted_live_session_worker.py`; it owns no provider-selection policy.
This keeps Local Modular and Hosted Live as explicit sibling lanes rather than
allowing either provider to invoke the other as a fallback.
