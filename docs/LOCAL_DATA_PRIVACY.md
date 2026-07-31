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
- Library pagination is bounded and reconstructs requests against Spotify's
  fixed API host instead of following response-provided URLs.
- Akiha does not send Spotify library or listening-history metadata to a hosted
  AI provider. A hosted provider may interpret the user's own action sentence,
  but local Spotify lookup and execution remain typed and local.
- Optional listening exports are local ranking seeds. They are ignored by Git,
  prohibited from packaged artifacts, and are not uploaded by Akiha.

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
actions. Its design is documented in `docs/PHASE8_ASSISTANT_ACTIONS.md`.

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
  classification.
- Akiha never adds approved roots, local paths, directory listings, search
  results, file metadata, or file contents to that proposal prompt. Text the
  user explicitly enters remains part of the provider request, as it does in
  normal hosted chat.
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
- additional hosted requests for subtitles, summaries, and memory extraction
- local conversation, memory, settings, and log storage
- Windows-user encryption for hosted API credentials
- optional Spotify cloud requests and encrypted OAuth refresh-token storage
- approved-directory and allowlisted-application grants
- optional provider classification of explicit app/media requests without
  local filesystem details
- sanitized assistant-action audit history and prohibited action categories

Revisit and version the notice again before adding persistent or always-listening
capture, sync, plugins, file-content ingestion, or broader local commands.
