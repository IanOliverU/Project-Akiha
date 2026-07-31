# Distribution Decision

Phase 6 established the first packaged build as a standalone folder rather
than an installer. Phase 8 retains that decision for the permission-gated
assistant-action candidate.

## Decision

Use the Nuitka standalone output as the first release artifact:

```text
dist\nuitka\main.dist\
```

The current Phase 8 candidate package is:

```text
dist\nuitka-phase8-release\main.dist\
```

The user launches:

```text
Akiha.exe
```

The entire `main.dist` folder is the distributable artifact. `Akiha.exe`
depends on the adjacent packaged libraries and assets and should not be moved
or distributed by itself.

Installer work is postponed until after the standalone build has had daily-use
feedback.

## Why Standalone First

- The app is still in active companion-foundation development.
- The first standalone package has passed automated and manual smoke, but the
  project still benefits from easy inspection while feedback comes in.
- Standalone builds make it easier to inspect packaged files and logs.
- Local user data already lives outside the app folder in
  `%LOCALAPPDATA%\Akiha\`, so replacing the standalone folder does not wipe
  conversations, memories, config, behavior history, logs, or pet state.
- Installer choices around shortcuts, uninstall behavior, code signing, and
  data preservation should be made after the first standalone package has been
  exercised.

## Update Behavior

For the standalone build, updating means replacing the packaged app folder with
a newer `main.dist` folder.

User data is preserved because it is stored separately under:

```text
%LOCALAPPDATA%\Akiha\
```

If a future migration changes the SQLite schema, Akiha applies bundled database
migrations at startup.

## Remove Behavior

Removing the standalone app folder removes the packaged application files only.
It does not remove local user data.

To remove local user data too, quit Akiha and remove:

```text
%LOCALAPPDATA%\Akiha\
```

## Installer Backlog

Installer work should be treated as future distribution work, not as a Phase 6
blocker for the first standalone build.

When installer work starts, decide:

- installer tooling
- install location
- Start menu shortcut behavior
- desktop shortcut behavior
- whether the app should launch at login
- uninstall behavior
- whether uninstall preserves or removes `%LOCALAPPDATA%\Akiha\`
- whether code signing is required

## Ollama Distribution

Ollama remains optional and separately installed.

Project Akiha does not bundle Ollama in the first packaged build. Users who want
local model chat should install and run Ollama separately, then select the
Ollama provider in Akiha Settings.
