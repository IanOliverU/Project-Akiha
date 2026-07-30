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
| SQLite database | `%LOCALAPPDATA%\Akiha\akiha.sqlite3` | Conversations, messages, summaries, memories, embeddings, and behavior history. |
| Pet window state | `%LOCALAPPDATA%\Akiha\state\pet_window.json` | Last saved pet position. |
| Encrypted credentials | `%LOCALAPPDATA%\Akiha\state\credentials.json` | DPAPI-encrypted hosted AI keys scoped to the current Windows user. |
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
- The Settings microphone test discards recognized words and retains only a
  temporary pass/fail result.
- Final recognized text is inserted into the editable Chat input by default.
  It is sent automatically only when the user enables that Voice setting.
- faster-whisper runs locally. Its model may be downloaded on first use and is
  cached under `%LOCALAPPDATA%\Akiha\models\faster-whisper\`.

## Phase 8 Assistant Actions

Phase 8 introduces a new local privacy boundary for permission-gated desktop
actions. Its design is documented in `docs/PHASE8_ASSISTANT_ACTIONS.md`.

- Directory access is off by default and limited to roots selected through a
  native directory picker.
- Initial file search reads names and basic metadata only.
- File actions cannot leave an approved root or access protected Windows
  locations.
- Opening a file requires visible confirmation and a conservative allowlist of
  passive file types.
- Applications launch only through separately enabled catalog entries such as
  Discord, Chrome, Spotify, or Visual Studio Code.
- Action audit records contain decisions and sanitized metadata, not file
  contents or credentials.
- No file content is added to an AI prompt or sent to a hosted provider in
  Phase 8.
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
behavior history, logs, local voice models, and pet window state. If only the
pet position should be reset, use Settings -> Reset position instead.

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

Revisit and version the notice again before adding persistent or always-listening
capture, sync, plugins, file-content ingestion, or broader local commands.
