# Phase 6 Security Review

This review records the security posture for the first Project Akiha standalone
Windows package.

## Current Scope

- AI output is rendered as chat/memory text or, when explicitly enabled,
  parsed as a narrow app/media proposal with no direct execution authority.
- AI output is never passed to `eval`, `exec`, a shell, or a generic command
  runner.
- Typed assistant actions can search approved roots, open approved directories
  or confirmed passive files, and launch separately enabled catalog apps.
- There is no plugin API, shell runner, browser automation, filesystem
  mutation, keyboard/mouse automation, or unrestricted operating-system
  control path.
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

## Spotify OAuth Boundary

The optional Spotify integration uses Authorization Code with PKCE for a
desktop public client. It binds a bounded callback listener only to
`127.0.0.1:43821`, validates the exact callback path and one-time state value,
and never accepts or stores a Client Secret. The short-lived access token stays
in memory; the refresh token is encrypted with Windows DPAPI under a dedicated
credential namespace.

Spotify account data is not exposed to the AI provider. Providers may propose
a constrained typed music intent from text the user supplied, but search,
library ranking, device selection, ambiguity handling, and playback execution
remain local. Personal preference exports are forbidden from release packages.

Catalog and library lookup accepts bounded local query lengths and result
limits, retains only the metadata required for matching and confirmation, and
never follows pagination URLs supplied by a provider response. One HTTP 401 can
clear the memory-only access token and retry through the encrypted refresh-token
session; other failures remain privacy-safe and are not retried automatically.

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

## Implemented Phase 8 Assistant-Action Boundary

Phase 8 is specified in `docs/PHASE8_ASSISTANT_ACTIONS.md`. Its enabled
assistant actions pass through a typed registry, validation, scoped
permissions, confirmation policy, capability-specific executor, and sanitized
audit path.

The implemented scope is intentionally shallow:

- read-only filename and metadata search inside user-approved directories
- bounded directory-name discovery beneath approved roots, with inherited
  scope validated again before opening a descendant
- opening an approved directory or validated safe file
- launching an explicitly enabled catalog application such as Discord, Chrome,
  Spotify, VLC, or Visual Studio Code
- gracefully closing an explicitly enabled catalog application through a
  normal window-close request
- optionally asking the selected AI provider to classify an explicit
  allowlisted-app or passive-media request

The design rejects shell text, arbitrary executable paths and arguments,
administrator elevation, filesystem mutation, protected Windows locations,
system utilities, and autonomous background actions. AI output remains an
untrusted request and never becomes direct execution authority.

Launch and close grants are separate. Graceful closing matches top-level
windows to the catalog-resolved executable and posts `WM_CLOSE`; it cannot
accept a process identifier or arbitrary path and never falls back to
`taskkill`, shell execution, or force termination.

The optional AI proposal gateway is disabled by default and accepts exact JSON
for only allowlisted application identifiers, directory names, or media
title/artist terms. The provider receives the user's request, but Akiha does
not append approved roots, local paths, directory listings, search results,
metadata, or file contents. Discovery, permission evaluation, confirmation,
execution, and auditing remain local.

Directory navigation does not build a persistent full-tree index. It searches
on demand with depth, result, timeout, and cancellation bounds, skips links and
reparse points, and keeps only temporary current-directory context.

## Deferred Before Public Distribution

- Code signing.
- Dependency auditing.
- Installer-specific permissions and uninstall behavior.
- A revised privacy-notice version before sync, plugins, persistent microphone
  capture, or broader assistant-action capabilities are added.
