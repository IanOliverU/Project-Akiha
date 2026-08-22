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
The runtime preference profile is bounded, memory-only, expires after ten
minutes, and is invalidated when the Spotify session changes. It can reorder
close visible candidates but cannot bypass textual confidence margins or
ambiguity confirmation.

Catalog and library lookup accepts bounded local query lengths and result
limits, retains only the metadata required for matching and confirmation, and
never follows pagination URLs supplied by a provider response. One HTTP 401 can
clear the memory-only access token and retry through the encrypted refresh-token
session; other failures remain privacy-safe and are not retried automatically.

Playback-device discovery uses a fresh minimal provider snapshot and does not
persist device identifiers. Restricted devices are rejected, ambiguous peers
are not guessed, and optional Spotify desktop activation can occur only through
the existing typed `applications.launch` permission, executor, and audit path.
Playback control has its own exact-target `spotify.playback` grant, separate
from account connection and desktop launch permission. Generic control phrases
are recognized by a strict local parser and can reach only registered Spotify
executors. Multi-track favorites playback accepts 1 to 50 unique validated
`spotify:track` URIs derived locally; arbitrary provider text and provider-
supplied URIs cannot enter that contract.

## First-Run Privacy Notice

A versioned application-modal notice now explains the microphone, local
provider, hosted provider, local storage, and encrypted credential boundaries.
Acknowledgement is persisted in the user config and the notice returns only
when its version is increased or local data is reset.

Hosted microphone audio has a second, independently versioned consent notice.
Gemini Live cannot be saved as the selected conversation-session provider until
that notice is accepted. The acknowledgement contains no conversation data.
The notice discloses off-device microphone processing, temporary raw audio,
final-transcript persistence, free- versus paid-tier data-use labels, bounded
session duration, and how to stop streaming.

The Gemini Live setup diagnostic is local-only. It checks optional SDK
availability, presence of the DPAPI-encrypted Gemini credential, current
consent, and non-secret model/voice/duration settings. It does not connect to a
provider, capture audio, decrypt a key into UI text, or inspect transcripts.
Context compression and bounded session resumption remain mandatory adapter
invariants and are not exposed as user-disableable settings.

The conversation runtime selector starts exactly one explicit Local Modular or
Gemini Live lane. Gemini microphone frames use a direct non-logging callback to
the hosted worker and never enter faster-whisper. Provider failures terminate
the cloud session visibly; no failure handler invokes the local runtime or a
hosted text provider. Changing lanes ends current ownership before a later,
separate user Start action can open the new lane.

V7C prepares hosted and local-model tool proposals without granting providers
direct action authority. Only a session- and turn-owned proposal exposed by the
explicit provider tool catalog can become an untrusted Phase 8 `ActionRequest`.
The existing validator, scoped permissions, local confirmation policy,
allowlisted executor, and SQLite audit path remain mandatory. Deterministic
local intent arbitration completes before a provider proposal can win whenever
a local parser participates in that lane. Hosted Live sends audio directly to
Gemini and currently has no parallel deterministic parser, so its worker
explicitly closes the empty local-routing stage before dispatch. The proposal
still receives no authority beyond the unchanged local policy boundary.

Providers cannot set the confirmation flag. A confirmation-required request is
held only in bounded process memory and can be resumed once by a separate local
UI decision. Provider-facing results exclude executor metadata, local paths,
search matches, Spotify candidates, credentials, and exception text. Gemini
function declarations are generated from the explicit V7A catalog. SDK calls
become provider-neutral proposals, and only ID-matched sanitized results return
through the transport. Confirmation-required calls pause for a trusted local
dialog; shutdown clears pending arguments. Gemini receives no executor,
permission repository, or audit repository reference.

Compatible Ollama models receive the same explicit V7A declarations through
their local native-tool protocol. Raw Ollama calls remain inside the adapter;
application-owned ephemeral turn IDs bind each call to V7B/V7C, and only
generic sanitized status text returns. A selected model that does not report
native tools, or whose capability lookup fails before a proposal exists, can
use the existing constrained JSON classifier once. This does not change the
selected provider or permit a retry after a native action has begun.

The V7F fallback gate stores only an opaque turn ID, random nonce, and bounded
lifecycle state. Deterministic local parsing runs before the gate opens. One
token can claim and consume at most one JSON callback; provider changes, chat
reset, cancellation cleanup, and shutdown invalidate late output. The JSON
classifier receives only normalized command text and sanitized action-state
labels. Exact schemas reject unknown actions, extra fields, paths, control
characters, unallowlisted applications, oversized values, prose, and malformed
JSON. Multiple recognizable actions produce a fixed local clarification rather
than provider-selected partial execution.

V7G exercises Gemini and Ollama source identities through one real SQLite
permission and audit composition path. The closure regression proves missing
permission cannot execute, one scoped grant permits one executor call, replay
cannot execute again, deterministic ownership preempts provider dispatch, and
private executor summaries or metadata do not cross the sanitized-result
boundary. The real Gemini Live source sign-off passed approved application,
Spotify, approved-directory, passive-media, local result-selection, and
continued-conversation checks on 2026-08-13. Standalone verification remains a
separate V8 release gate.

The V8 build gate compiles the statically imported Gemini SDK modules while
applying an artifact deny scan across the complete standalone directory. Environment files,
common secret files, private Spotify exports, and SQLite databases fail the
build validation. The release process uses isolated fresh and existing-data
smoke roots and never copies the developer's `%LOCALAPPDATA%\Akiha\` state into
the candidate.

Provider requests to open an approved root use only its user-facing display
name. The proposal gateway resolves that alias locally from the current
approved-directory snapshot before constructing the existing path-based Phase
8 request. Directory and passive-file actions may include a root-relative
descendant, such as `Downloads/Video`; traversal segments and unknown roots are
not resolved. The existing path policy, scoped permission evaluation, target
availability checks, and passive-file confirmation remain authoritative.
Approved absolute paths are never inserted into provider schemas or results.
For provider-requested searches, raw bounded matches are emitted only through a
local Qt signal to the existing action-results UI and ephemeral selection
store. The provider receives the generic sanitized completion status; filename,
path, executor metadata, and raw summary fields do not cross that boundary.
Provider searches also declare a bounded local result mode: present,
open-unique, or open-any. Both opening modes create a separate typed
`files.open` request and therefore retain path validation, scoped permission,
passive-extension policy, and trusted local confirmation. Relaxed title
matching can broaden only the local candidate list; it never chooses among
multiple matches for an open-unique request.
Numbered Cloud follow-ups contain only an opaque `result N` string. The local
proposal gateway maps indexes 1 through 10 to its latest in-memory result set,
which expires after five minutes and is cleared by replacement results, chat
reset, provider change, hosted shutdown, or application shutdown. The mapping
is absent from provider schemas, sanitized results, diagnostics, and durable
memory. Resolution creates the same typed open action and cannot bypass target
validation, permission checks, passive-file policy, or trusted confirmation.
Spotify track candidates use the same opaque-reference rule with at most five
locally retained validated track URIs. Gemini receives neither candidate
metadata nor a URI, and a numbered selection re-enters the existing typed
Spotify action validator and playback executor.

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

Phase 8 is specified in `docs/phases/phase-08-actions/README.md`. Its enabled
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
  allowlisted-app, passive-media, directory, or Spotify playback request

The design rejects shell text, arbitrary executable paths and arguments,
administrator elevation, filesystem mutation, protected Windows locations,
system utilities, and autonomous background actions. AI output remains an
untrusted request and never becomes direct execution authority.

Launch and close grants are separate. Graceful closing matches top-level
windows to the catalog-resolved executable and posts `WM_CLOSE`; it cannot
accept a process identifier or arbitrary path and never falls back to
`taskkill`, shell execution, or force termination.

The optional AI proposal gateway is disabled by default and accepts exact JSON
for only allowlisted application identifiers, directory names, media
title/artist terms, or bounded Spotify playback operations. The provider
receives the user's request and coarse expiring labels for recent action,
application, directory-context presence, and Spotify playback state. Akiha
does not append approved roots, local paths, directory listings, search
results, metadata, file contents, Spotify library data, device IDs, or
conversation history. Discovery, permission evaluation, confirmation,
execution, and auditing remain local.

Directory navigation does not build a persistent full-tree index. It searches
on demand with depth, result, timeout, and cancellation bounds, skips links and
reparse points, and keeps only temporary current-directory context.

## Phase 10 Shop And Appearance Boundary

Phase 10 uses closed local TOML catalogs and owner-approved complete appearance
manifests. Provider output and ordinary dialogue have no purchase, selection,
pet-state, activity-scheduling, asset-path, or renderer mutation interface.
Purchases use an atomic SQLite transaction and cannot create negative currency,
duplicate ownership, or a partial debit.

The Status and Settings diagnostic surfaces read only typed local state and
bounded counts. They exclude dialogue, credentials, filesystem paths, provider
content, and asset contents. Pet reset remains separately confirmed and affects
only pet progress, care history, and reward cooldowns; shop ownership,
transactions, appearance selection, credentials, permissions, and unrelated
history are preserved.

There is no payment processing, real-money store, telemetry, cloud asset upload,
remote catalog, or remote marketplace. Autonomous activity selection is local,
deterministic, data-driven, and lower priority than drag, voice, care, and direct
user control.

## Deferred Before Public Distribution

- Code signing.
- Dependency auditing.
- Installer-specific permissions and uninstall behavior.
- A revised privacy-notice version before sync, plugins, persistent microphone
  capture, or broader assistant-action capabilities are added.
