# Local Data And Privacy

Project Akiha is local-first. Runtime data is stored on the user's Windows
profile under:

```text
%LOCALAPPDATA%\Akiha\
```

The current app does not include cloud sync. Chat requests only leave the
machine when the user explicitly selects a hosted provider or configures a
provider URL that points outside the PC. Local mock and Ollama modes remain
available without subscriptions or API keys.

## Stored Data

| Data | Location | Purpose |
| --- | --- | --- |
| User config | `%LOCALAPPDATA%\Akiha\user_config.toml` | User-editable settings saved from the Settings window. |
| SQLite database | `%LOCALAPPDATA%\Akiha\akiha.sqlite3` | Conversations, messages, summaries, memories, embeddings, behavior history, assistant-action grants, and sanitized action history. |
| Pet window state | `%LOCALAPPDATA%\Akiha\state\pet_window.json` | Last saved pet position. |
| Encrypted credentials | `%LOCALAPPDATA%\Akiha\state\credentials.json` | DPAPI-encrypted hosted AI keys and Spotify refresh token scoped to the current Windows user. |
| Logs | `%LOCALAPPDATA%\Akiha\logs\app.log` | Startup, diagnostics, provider failures, migration failures, and runtime support logs. |
| Local voice models | `%LOCALAPPDATA%\Akiha\models\faster-whisper\` | Optional downloaded speech-recognition model files. |

Logs rotate at 1,000,000 bytes with 3 backups.

## Hosted AI Providers

Gemini, OpenAI, OpenRouter, Kimi, and custom OpenAI-compatible endpoints are
opt-in. Selecting one can send the companion system prompt, recent chat
messages, retrieved memory context, summary context, and internal
memory-processing prompts to that configured service.

API keys entered in Settings are encrypted with Windows DPAPI and are not
written to user configuration, logs, events, conversations, memories, or
transcript exports. Environment-variable credentials are also supported.

Project Akiha does not silently fail over between local and hosted providers.
Changing the destination requires an explicit Settings change.

## Spotify

Spotify integration is optional and uses Authorization Code with PKCE through
the fixed loopback callback `http://127.0.0.1:43821/callback`. Project Akiha
does not request or store a Spotify Client Secret.

- The public Client ID and non-secret integration settings are stored in
  `user_config.toml`.
- The refresh token is encrypted with Windows DPAPI in `credentials.json`.
- Access tokens remain in memory and are refreshed from the encrypted token.
- Search terms, library requests, device metadata, and playback commands are
  sent directly to Spotify only after the user connects the integration.
- Device snapshots are reduced to the fields needed for local selection.
  Device IDs are fetched fresh for playback and are not persisted or sent to
  an AI provider.
- Generic play, pause, resume, next, and previous phrases are parsed locally
  into typed actions. Their Spotify API mutations contain only the fresh target
  device ID and no library metadata.
- Catalog and library responses are reduced to minimal identifiers, names,
  artist/album or playlist-owner labels, duration, URI, and playability. Akiha
  does not retain artwork, descriptions, or raw provider responses.
- Liked Songs, top tracks, recent listening, and personal playlist metadata may
  form a bounded preference profile kept in memory for ten minutes. It is
  discarded when the Spotify session changes or Akiha exits and is never added
  to chat, memory, diagnostics, logs, or hosted-provider prompts.
- Favorite-music playback sends Spotify at most 50 validated track URIs. The
  local ranking inputs and unused library results are not included in the
  playback mutation.
- Library pagination is bounded and reconstructs requests against Spotify's
  fixed API host instead of following response-provided URLs.
- Akiha does not send Spotify library or listening-history metadata to a hosted
  AI provider. A hosted provider may interpret the user's own action sentence,
  but local Spotify lookup and execution remain typed and local.
- The historical local listening export was removed. Its former repository
  path remains ignored and prohibited from packaged artifacts as defense in
  depth; Akiha has no runtime importer for it.

## Pipelined Voice Modes

The Post-Phase 8 Voice Intent and Live Conversation architecture preserves
three explicit processing modes:

- **Fully Local Modular:** microphone audio, transcription, Ollama/local LLM
  generation, speech rendering, and VOICEVOX playback remain local.
- **Hybrid API Modular:** microphone audio and transcription remain local; the
  accepted transcript and bounded conversation context are sent to the
  explicitly selected hosted text provider; VOICEVOX playback remains local.
- **Hosted Live:** microphone audio is streamed to the explicitly selected
  realtime provider and its native audio may be played locally.

No failure silently switches between these modes. Settings must show whether
the current mode sends no conversation data, text, or microphone audio to a
hosted provider.

Ollama and custom OpenAI-compatible endpoints are treated as local only when
their URL is loopback-only (`localhost`, `127.0.0.0/8`, or `::1`). Any other
endpoint is conservatively disclosed as off-device text processing.

Gemini Live setup now has these additional boundaries:

- cloud microphone streaming requires a separate explicit user-started session
  and versioned privacy acknowledgement
- the first release will enforce a finite duration and mandatory context-window
  compression rather than permit unlimited sessions
- current Google pricing and data-use terms will be revalidated before release
- the notice will explain that current Gemini Developer API pricing labels
  free-tier content as eligible to improve Google's products and paid-tier
  content as not used for that purpose
- provider-reported token usage may be shown as privacy-safe support data, but
  Akiha will not promise a fixed per-minute cost
- local push-to-talk, local Conversation Session, Ollama, faster-whisper, and
  VOICEVOX will remain available without Gemini Live

`Start conversation` routes only to the lane visibly selected in Settings.
Direct cloud PCM frames bypass faster-whisper, while the ordinary `Talk` path
continues to use local microphone processing. A cloud failure stops that
session and does not start Local Modular, send its transcript to a text
provider, or replay buffered audio into another lane. Switching lanes in
Settings ends an active session and the user must explicitly start the newly
selected lane.

The V7 provider-tool boundary does not send local action metadata back to a
provider. Tool schemas contain only explicitly exposed action names,
descriptions, and primitive parameter constraints. Accepted requests still use
local permissions, confirmation, execution, and audit. Provider results contain
only bounded ownership identifiers, status, and a generic message; they exclude
paths, search results, Spotify candidates, credentials, and exception text.
Confirmation-pending request arguments remain memory-only and are cleared on
resolution or hosted-worker cleanup. Stale ownership makes them
non-executable. Gemini Live receives the explicit bounded tool declarations,
but SDK function calls become untrusted local proposals rather than direct
execution. Confirmation-required calls wait for a trusted local dialog; only
the final bounded status and generic message are returned with the matching
provider call ID. Stopping or changing the hosted lane clears replay and
pending-confirmation state.

Ollama-native calls use the same explicit schemas and generic-result boundary
while remaining local when the configured endpoint is loopback-only. If native
tool support is not reported, the constrained JSON fallback sends only the
normalized command and a bounded `IntentContextSnapshot` to the already
selected text provider. That snapshot can contain an allowlisted application
identifier, action identifier, Spotify playback state, and boolean recent-state
flags; it never contains paths, search results, file contents, credentials, or
conversation excerpts. The provider receives no action result from this JSON
classifier path. One-shot turn ownership prevents late or duplicate fallback
output from executing after provider changes, chat reset, or shutdown.

V7G composition verification additionally confirms that Gemini and Ollama
source identities receive only the same generic sanitized result even when a
local executor returns private summary or metadata values. The SQLite action
audit remains local and provider tools receive no repository access.

Approved directory display-name aliases are copied into the local proposal
gateway so a provider can request `Downloads folder` without receiving the
corresponding absolute Windows path. Alias resolution is application-owned;
an optional root-relative descendant such as `Downloads/Video` is joined only
after the approved root is found. Traversal is rejected, and only the resulting
local Phase 8 request enters path validation, permission evaluation, and any
required passive-file confirmation.

When Gemini requests an approved file or directory search, at most ten matches
are presented in Akiha's local action-results UI and ephemeral selection store.
Those names and paths remain local. Gemini receives only a generic action status
such as completed, denied, or unavailable and cannot read the match metadata.
An explicit local-media play request may turn one unique result into a separate
confirmation-gated file-open request. Multiple related titles are shown only
locally and require either an exact local candidate or an opaque numbered
follow-up; they are not sent back to Gemini and are not written into durable
companion memory.

Gemini may refer to one of those local rows only by an opaque number such as
`result 1`. Akiha keeps no more than ten corresponding paths in memory for five
minutes. The path is resolved locally and is never included in Gemini's tool
result, transcript, diagnostics, or companion memory. Replacement searches,
chat reset, provider change, and session shutdown clear the mapping early.
The same local-only mapping may retain at most five validated Spotify track
choices. Gemini receives only `result N`; track names, artist names, albums,
candidate lists, and Spotify URIs are not returned in the tool result or stored
as companion memory.

The hosted-audio acknowledgement is stored separately as
`privacy.hosted_live_notice_version_acknowledged`. Selecting or checking Gemini
Live in Settings does not contact Google or capture microphone audio. The
privacy-safe readiness check reports only whether the optional SDK, encrypted
Gemini key, and current acknowledgement are present, plus the selected model,
voice, and bounded duration.

## Chat Transcripts

Conversations and messages are stored in SQLite so Akiha can restore recent chat
context and export the current transcript.

- New chat closes the current conversation and starts a fresh one.
- Clear chat deletes messages from the current conversation after confirmation.
- Export writes the current visible transcript to a user-selected text file.
- System prompts, hidden memory context, and hidden summary context are not
  added to the visible chat history or transcript export.

## Memories

Memories are stored in SQLite and managed from the Memory Manager.

- Active memories can be edited, archived, deleted, or cleared.
- Archived memories are excluded from active retrieval until restored.
- Pending memories can be approved, rejected, or cleared before they are saved.
- Clearing memories removes memory entries from the local database.

## Behavior History

Behavior events are stored in SQLite so proactive suggestions and delivery
outcomes can be inspected later.

- Behavior History can clear all events.
- Behavior History can clear events matching an event type or kind filter.
- Behavior cleanup affects behavior history only; it does not delete chat
  transcripts or memories.

## Diagnostics

The Settings window includes actions for opening the logs folder and local data
folder. Startup logs also include a compact diagnostics summary with important
paths and file existence/size metadata. The diagnostics summary does not read or
print private chat, memory, or config contents.

## Voice Capture

Phase 7 microphone input is push-to-talk only.

The optional standalone VOICEVOX Engine executable path is stored in
`user_config.toml`. Automatic engine management is disabled by default, only
supports local HTTP endpoints, does not download an engine, and never stops an
external VOICEVOX process that Project Akiha did not launch.

- The microphone opens only after the user requests listening.
- PCM audio remains in memory and is discarded after transcription,
  cancellation, timeout, failure, or shutdown.
- Raw microphone bytes are not published through the application event bus,
  written to logs, or saved as audio files.
- Optional interim transcription is display-only and is not persisted or sent.
- The Settings microphone test discards recognized words and shows only a
  temporary result, coarse activity/level bands, a rounded silence countdown,
  and an optional qualitative confidence band.
- Exact microphone RMS values and exact recognition-confidence scores are not
  published through the event bus or written to logs.
- Final recognized text is inserted into the editable Chat input by default.
  It is sent automatically only when the user enables that Voice setting.
- A final transcript reported with low confidence is held in the editable Chat
  input for user review instead of being sent automatically.
- faster-whisper runs locally. Its model may be downloaded on first use and is
  cached under `%LOCALAPPDATA%\Akiha\models\faster-whisper\`.

## Phase 8 Assistant Actions

Phase 8 introduces a new local privacy boundary for permission-gated desktop
actions. Its design is documented in `docs/phases/phase-08-actions/README.md`.

- Directory access is off by default and limited to roots selected through a
  native directory picker.
- Ordinary child directories inherit the selected root's scope and are
  enumerated by name only when the user asks to navigate; Akiha does not retain
  a persistent copy of the full directory tree.
- Initial file search reads names and basic metadata only.
- File actions cannot leave an approved root or access protected Windows
  locations.
- Opening a file requires visible confirmation and a conservative allowlist of
  passive file types.
- Applications launch only through separately enabled catalog entries such as
  Discord, Chrome, Spotify, VLC, or Visual Studio Code.
- Graceful application closing uses a separate permission, posts a normal
  Windows close request, and never force-terminates a process.
- Action audit records contain decisions and sanitized metadata, not file
  contents or credentials.
- AI-assisted action proposals are off by default. When enabled, the selected
  provider receives the user's explicit action sentence for constrained intent
  classification plus coarse, expiring action labels such as the last action
  category, recent allowlisted application, whether directory context exists,
  and Spotify's `playing` / `paused` state.
- Akiha never adds approved roots, local paths, directory listings, search
  results, file metadata, file contents, Spotify library data, device IDs, or
  conversation history to that proposal prompt. Text the user explicitly
  enters remains part of the provider request, as it does in normal hosted
  chat.
- Temporary directory-navigation context stores only the last opened local
  path in memory and is cleared with chat lifecycle or permission changes.
- Settings provides local controls to review, enable, disable, and reset
  directory and application permissions.
- Assistant-action audit history can be cleared from its history window.

The current first-run privacy notice is versioned to include this assistant
action boundary. Permissions are stored locally in the SQLite database and are
revocable; they do not grant access to arbitrary shells, system-critical paths,
or file mutation.

## Reset

To reset all local Project Akiha data, quit the app first, then remove:

```text
%LOCALAPPDATA%\Akiha\
```

This removes user config, encrypted API credentials, chat history, memories,
behavior history, assistant-action grants and audit history, logs, local voice
models, and pet window state. If only the pet position should be reset, use
Settings -> Reset position instead.

## First-Run Privacy Notice

The app shows a versioned privacy notice until the current notice is
acknowledged. The acknowledgement version is stored as
`privacy.notice_version_acknowledged` in `user_config.toml`; it contains no
personal content and can be incremented when the privacy boundary materially
changes.

The notice explains:

- push-to-talk microphone behavior and temporary raw audio
- local processing through faster-whisper, VOICEVOX, and Ollama
- hosted-provider transmission of chat text and relevant context
- optional hosted-live transmission of microphone audio with a separate
  versioned acknowledgement and visible active-session state
- additional hosted requests for subtitles, summaries, and memory extraction
- local conversation, memory, settings, and log storage
- Windows-user encryption for hosted API credentials
- optional Spotify cloud requests and encrypted OAuth refresh-token storage
- ephemeral local Spotify preference ranking and bounded favorite queues
- approved-directory and allowlisted-application grants
- optional provider classification of explicit app/media requests without
  local filesystem details
- sanitized assistant-action audit history and prohibited action categories

Revisit and version the notice again before adding persistent or always-listening
capture, sync, plugins, file-content ingestion, or broader local commands.

## Packaged Artifact Privacy

Release builds include application code, public default configuration, database
migrations, UI assets, and required runtime libraries. They do not copy the
user's `%LOCALAPPDATA%\Akiha\` directory. The artifact validator rejects
environment files, common secret files, private Spotify exports, and SQLite
database files anywhere in the standalone folder. Gemini credentials and
Spotify refresh tokens remain in the current Windows user's DPAPI-protected
local state and are never embedded in `Akiha.exe` or its adjacent data files.
