# Phase 6 Security Review

This review records the security posture for the first Project Akiha standalone
Windows package.

## Current Scope

- AI output is only rendered as chat text or used as memory/summarization text.
- AI output is not passed to `eval`, `exec`, a shell, subprocess APIs, or local
  assistant commands.
- There is no plugin API, command runner, browser automation, file automation,
  or operating-system control path in Phase 6.
- The only app action that opens the operating system is the Settings action
  that opens the logs or data folder through Qt's desktop-services API.
- The app supports local mock/Ollama modes and explicitly selected hosted
  OpenAI-compatible endpoints.

## Provider Boundary

The default provider is `mock`, which is local and deterministic.

Ollama is optional and configured by URL. Akiha validates that the configured
Ollama URL uses `http` or `https` and includes a host. The default value points
to `http://localhost:11434`. If a user changes the URL to a remote host, chat
content, hidden memory context, and summarization/extraction prompts are sent to
that configured endpoint.

Hosted provider URLs also require `http` or `https` plus a host. Provider
selection is explicit and there is no silent cloud fallback. Hosted API keys
entered in Settings are encrypted with Windows DPAPI for the current Windows
account and stored separately from TOML configuration. Keys are not included in
provider logs, application events, chat history, memory records, or exports.
Environment-variable credentials are supported as an alternative.

## First-Run Privacy Notice

A versioned application-modal notice now explains the microphone, local
provider, hosted provider, local storage, and encrypted credential boundaries.
Acknowledgement is persisted in the user config and the notice returns only
when its version is increased or local data is reset.

## Local Data

Runtime data stays under `%LOCALAPPDATA%\Akiha\`:

- user config
- SQLite conversations/messages/summaries
- memories and embeddings
- behavior history
- logs
- pet window state
- encrypted hosted AI credentials

Diagnostics logs include paths and support metadata, but do not intentionally
print chat transcripts, memory contents, or user config contents.

## Planned Phase 8 Assistant-Action Boundary

Phase 8 is specified in `docs/PHASE8_ASSISTANT_ACTIONS.md`. No assistant action
is enabled until its typed registry, validation, scoped permissions,
confirmation policy, capability-specific executor, and audit path are in place.

The planned scope is intentionally shallow:

- read-only filename and metadata search inside user-approved directories
- opening an approved directory or validated safe file
- launching an explicitly enabled catalog application such as Discord, Chrome,
  Spotify, or Visual Studio Code

The design rejects shell text, arbitrary executable paths and arguments,
administrator elevation, filesystem mutation, protected Windows locations,
system utilities, and autonomous background actions. AI output remains an
untrusted request and never becomes direct execution authority.

## Deferred Before Public Distribution

- Code signing.
- Dependency auditing.
- Installer-specific permissions and uninstall behavior.
- Implementation and verification of the Phase 8 permission and audit boundary
  before any assistant action executor is enabled.
- A revised privacy-notice version before sync, plugins, persistent microphone
  capture, or local assistant commands are added.
