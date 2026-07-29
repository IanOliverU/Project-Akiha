# Phase 6 Packaging, Release Hardening, And Maintainability

Phase 6 prepares Project Akiha for longer-term daily use and eventual Windows
distribution. Phases 1 through 5 focused on product capability: desktop pet,
chat, memory, activity, mood, proactive behavior, and companion polish. Phase 6
focuses on reliability, packaging, diagnostics, privacy, and release readiness.

## Phase Goal

Turn the current developer-runnable app into a hardened Windows desktop build
that can be installed, launched, debugged, and maintained with confidence.

Phase 6 is not complete yet. This checklist defines the work we should do next.

## Checklist

### 1. Packaging Pipeline

- [x] Validate the existing Nuitka standalone build path on the current app.
- [x] Use `scripts/build_akiha_nuitka.ps1` as the Phase 6 packaging entry point.
- [x] Keep `scripts/build_phase1_nuitka.ps1` only as a compatibility wrapper.
- [x] Use Nuitka with Zig on the current Windows/Python 3.14 environment.
- [x] Ensure package data is included:
  - `assets/animations`
  - `assets/animations/manifest.toml`
  - `project_akiha/config/default.toml`
  - `project_akiha/database/migrations/*.sql`
- [x] Confirm PySide6 plugins are bundled correctly.
- [ ] Confirm the packaged app starts without a console window.
- [x] Confirm the packaged app can create and use `%LOCALAPPDATA%\Akiha\`.

Validation note, 2026-07-29:

- `scripts/build_akiha_nuitka.ps1 -SkipBuild` passed the quality gate and Nuitka
  availability check.
- `scripts/build_akiha_nuitka.ps1 -SkipQualityChecks -OutputDir
  dist\nuitka-phase6-validation` produced
  `dist\nuitka-phase6-validation\main.dist\Akiha.exe`.
- `assets/animations/manifest.toml`, `project_akiha/config/default.toml`, and
  `project_akiha/database/migrations/*.sql` were present in the standalone
  output.
- `scripts/smoke_packaged_app.ps1 -ExePath
  dist\nuitka-phase6-smoke\main.dist\Akiha.exe -RunExistingDataPass` passed
  against an isolated `LOCALAPPDATA` directory. The packaged app created logs
  and a SQLite database with the expected behavior, conversation, memory,
  message, and schema tables, then started again with existing user config,
  state, and database files.
- The non-interactive smoke script successfully requested `CloseMainWindow()`,
  but still had to force-stop the process. Manual tray Quit validation remains
  part of the runtime smoke checklist.
- `scripts/smoke_source_app.ps1` passed against an isolated `LOCALAPPDATA`
  directory. The source app created logs and a SQLite database with the expected
  behavior, conversation, memory, message, and schema tables.
- Nuitka 4.1.3 reports Python 3.14 support as experimental. Continue with this
  environment for local validation, but consider Python 3.13 before public
  release if packaging instability appears.

### 2. Runtime Smoke Tests

- [x] Start the app from source.
- [x] Start the packaged app.
- [ ] Confirm the pet appears and can be dragged.
- [ ] Confirm tray controls work.
- [ ] Confirm Settings opens and saves.
- [ ] Confirm Chat opens and can send a mock-provider message.
- [ ] Confirm Memory Manager opens.
- [ ] Confirm Behavior History opens.
- [ ] Confirm proactive behavior does not crash when timers tick.
- [ ] Confirm Quit saves pet position and stops active chat workers.

Runtime smoke note, 2026-07-29:

- Tray menu actions for Show, Hide, Chat, Settings, Behavior History, and Quit
  have automated offscreen unit coverage. Manual packaged tray validation
  remains required because Windows tray behavior must be checked in the real
  packaged app.
- Manual packaged runtime checks are documented in
  `docs/MANUAL_PACKAGED_SMOKE.md`.

### 3. Startup And Shutdown Hardening

- [x] Verify startup with no existing `%LOCALAPPDATA%\Akiha\` folder.
- [x] Verify startup with existing config/state/database files.
- [x] Verify startup with a missing animation manifest.
- [x] Verify startup with missing or invalid sprite files.
- [ ] Verify shutdown during idle state.
- [ ] Verify shutdown while chat is generating.
- [ ] Verify shutdown while Settings, Chat, Memory, or Behavior History windows are
  open.
- [x] Ensure top-level startup failures are logged clearly.

Startup hardening note, 2026-07-29:

- Animation manifests now fail fast when referenced frame or filmstrip image
  files are missing. The app-level animation provider builder logs the manifest
  load failure and falls back to the placeholder animation provider.
- `tests.unit.app.test_animation_bootstrap` covers missing manifests, missing
  sprite references, and valid sprite manifests.
- User config loading now accepts UTF-8 files with a byte-order mark, which
  protects startup when config files are edited by Windows tools that emit a
  BOM.
- `main()` logs unrecoverable startup failures to
  `%LOCALAPPDATA%\Akiha\logs\app.log` before reraising the original exception.
- Shutdown cleanup is isolated in `project_akiha.app.shutdown` and has automated
  coverage for idle cleanup, cooperative chat cancellation, unfinished chat
  workers, position-save failures, timer-stop failures, and thread cancellation
  failures.

### 4. Diagnostics And Logs

- [x] Review log file locations and rotation behavior.
- [x] Add a user-facing way to open diagnostics if needed.
- [x] Confirm provider failures are logged without crashing the UI.
- [x] Confirm migration failures are visible in logs.
- [x] Consider adding a compact diagnostics summary for support/debugging.

Diagnostics note, 2026-07-29:

- Logs are written to `%LOCALAPPDATA%\Akiha\logs\app.log` with rotating file
  handling at 1,000,000 bytes and 3 backups.
- Settings now exposes both log and data-folder open actions.
- Startup logs include a compact diagnostics snapshot with the local data,
  logs, database, user config, and state paths without reading private content.
- Chat provider failures are caught by the worker thread, logged as AI provider
  response failures, and surfaced as visible chat errors without raising through
  the UI path.
- Database migration failures log both the failing migration file, when known,
  and the database/migrations directory involved before reraising the original
  exception.

### 5. Data And Privacy Review

- [x] Document local storage clearly:
  - user config
  - SQLite conversations
  - memories
  - behavior history
  - logs
  - pet window state
- [x] Confirm transcript export behavior.
- [x] Confirm memory deletion, archiving, pending review, and clear actions behave as
  documented.
- [x] Confirm behavior history cleanup behaves as documented.
- [x] Decide whether packaged builds need a first-run privacy note.

Data and privacy note, 2026-07-29:

- Local storage, transcript export behavior, memory controls, behavior history
  cleanup, diagnostics behavior, and reset steps are documented in
  `docs/LOCAL_DATA_PRIVACY.md`.
- The first packaged build remains local-first and does not need a blocking
  first-run privacy modal. Revisit a first-run notice before adding cloud AI
  providers, voice capture, sync, plugins, or local assistant commands.

### 6. Dependency And Build Review

- [x] Confirm supported Python version.
- [x] Confirm dependency groups:
  - runtime
  - dev
  - package
- [x] Decide whether to add a lockfile workflow later.
- Use `scripts/smoke_packaged_app.ps1 -RunExistingDataPass` after packaging to
  verify packaged startup, local data creation, log creation, SQLite schema
  creation, and restart with existing local data.
- Run the quality gate before every packaged build:

```powershell
pip install -e .[package]
.\scripts\build_akiha_nuitka.ps1
```

Use this command when you want to validate the script and quality gate without
creating a packaged build:

```powershell
.\scripts\build_akiha_nuitka.ps1 -SkipBuild
```

Run the quality gate before every packaged build:

```powershell
python -m unittest discover tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
python -m compileall project_akiha tests
```

Dependency and build note, 2026-07-29:

- Build workflow, dependency groups, supported Python notes, quality gate,
  packaging command, packaged smoke command, and lockfile decision are documented
  in `docs/BUILD_RELEASE.md`.
- The `package` extra includes Ruff, Black, and Nuitka so
  `pip install -e .[package]` installs the tools used by the packaging script.
- No lockfile workflow is being added in Phase 6. Revisit this when provider,
  voice, installer, or reproducible public release requirements grow.

### 7. Installer And Distribution Prep

- [x] Decide whether Phase 6 ships a standalone folder or installer first.
- [x] Defer installer-specific choices to the post-standalone backlog:
  - choose installer tooling
  - define install location
  - define shortcut behavior
  - define uninstall behavior
  - confirm local user data is preserved or clearly removed by choice
- [x] Document Ollama as optional and separately installed.
- [x] Do not bundle Ollama in the first packaged build.

Distribution note, 2026-07-29:

- Phase 6 ships a standalone folder first. Installer work is postponed until
  after the standalone package passes manual smoke testing and daily-use
  feedback.
- Removing or replacing the standalone folder does not remove local user data,
  which remains under `%LOCALAPPDATA%\Akiha\`.
- Distribution behavior and future installer backlog are documented in
  `docs/DISTRIBUTION_DECISION.md`.
- Draft release notes for the first standalone package are in
  `docs/RELEASE_NOTES_DRAFT.md`.

### 8. Security Checklist

- Keep AI output away from direct execution paths.
- Confirm no shell execution path is exposed to the model.
- Keep future assistant commands behind explicit command validation.
- Keep logs useful without leaking unnecessary sensitive data.
- Consider code signing before public distribution.
- Consider dependency auditing before public distribution.

### 9. Documentation Pass

- [x] Update `README.md` after packaging validation.
- [ ] Add a Phase 6 completion summary when this phase is done.
- [x] Document source run, packaged run, and uninstall/reset steps.
- [x] Document local data reset steps.
- [x] Document known limitations.
- [x] Prepare release notes for the first packaged build.

Documentation note, 2026-07-29:

- Build workflow is documented in `docs/BUILD_RELEASE.md`.
- Local data and reset behavior are documented in `docs/LOCAL_DATA_PRIVACY.md`.
- Distribution behavior is documented in `docs/DISTRIBUTION_DECISION.md`.
- Manual packaged smoke is documented in `docs/MANUAL_PACKAGED_SMOKE.md`.
- Draft release notes are documented in `docs/RELEASE_NOTES_DRAFT.md`.

## Exit Criteria

Phase 6 should be considered done when:

- The app builds successfully as a Windows standalone package.
- The packaged app passes the runtime smoke tests.
- Startup and shutdown behavior is verified.
- Local data behavior is documented.
- Diagnostics and logs are easy to find.
- README and release notes match the actual packaged app.
- The project has a clear post-Phase-6 backlog instead of open-ended phase creep.

## Post-Phase-6 Backlog

The current roadmap ends at Phase 6. Future work can continue, but it should be
treated as a new roadmap rather than silently expanding Phase 6.

Possible future roadmap areas:

- Local assistant commands with permission gates.
- Voice input and output.
- Richer character animation assets.
- Live2D or another advanced model backend.
- Plugin API.
- Cloud model providers.
- Multi-character support.
- Optional sync or backup.
