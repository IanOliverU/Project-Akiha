# Local Data And Privacy

Project Akiha is local-first. Runtime data is stored on the user's Windows
profile under:

```text
%LOCALAPPDATA%\Akiha\
```

The current app does not include cloud sync. Chat requests only leave the
machine when the user chooses a provider URL that points outside the PC. As of
Phase 6, the implemented providers are the local mock provider and optional
Ollama over HTTP. The default Ollama URL points to the user's PC at
`http://localhost:11434`.

## Stored Data

| Data | Location | Purpose |
| --- | --- | --- |
| User config | `%LOCALAPPDATA%\Akiha\user_config.toml` | User-editable settings saved from the Settings window. |
| SQLite database | `%LOCALAPPDATA%\Akiha\akiha.sqlite3` | Conversations, messages, summaries, memories, embeddings, and behavior history. |
| Pet window state | `%LOCALAPPDATA%\Akiha\state\pet_window.json` | Last saved pet position. |
| Logs | `%LOCALAPPDATA%\Akiha\logs\app.log` | Startup, diagnostics, provider failures, migration failures, and runtime support logs. |

Logs rotate at 1,000,000 bytes with 3 backups.

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

## Reset

To reset all local Project Akiha data, quit the app first, then remove:

```text
%LOCALAPPDATA%\Akiha\
```

This removes user config, chat history, memories, behavior history, logs, and
pet window state. If only the pet position should be reset, use Settings ->
Reset position instead.

## First Packaged Build Privacy Decision

The first packaged build remains local-first and does not include a blocking
first-run privacy modal. Privacy behavior is documented here and visible through
Settings diagnostics actions.

Revisit a first-run privacy notice before adding cloud AI providers, voice
capture, sync, plugins, or local assistant commands.
