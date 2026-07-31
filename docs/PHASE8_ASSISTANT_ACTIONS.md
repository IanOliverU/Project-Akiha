# Phase 8: Permission-Gated Assistant Actions

**Status:** In progress - implementation complete; packaged verification pending

## Phase Goal

Let Akiha perform a deliberately shallow set of useful Windows desktop actions
without granting unrestricted operating-system access.

The first capabilities are:

- search for files by name or metadata inside user-approved directories
- open an approved directory in the system file browser
- open an allowlisted passive file from an approved directory after validation
- launch an explicitly allowlisted application such as Discord, Chrome,
  Spotify, or Visual Studio Code

The phase proves the complete action pipeline before any higher-risk
automation is considered.

The optional AI-assisted proposal layer remains off by default. When enabled,
the selected provider may classify an explicit app-launch or local-media
request, but it receives no local paths, directory listings, search results,
file metadata, or file contents added by Akiha. As with ordinary hosted chat,
text the user explicitly types is still sent to the selected provider.

## Security Position

AI output is untrusted input, never executable authority.

- An AI provider may propose a structured action request.
- Project Akiha validates the request against an application-owned registry.
- Permission policy decides whether the action and target are allowed.
- Only a small, typed executor owned by the application can perform the action.
- Unknown actions, arbitrary executable paths, command-line strings, and shell
  syntax are rejected.
- Windows elevation is never requested.
- Denied actions produce a safe result and an audit record instead of falling
  back to another execution path.

```text
User request
    -> local parser proposes ActionRequest
       or selected AI proposes a constrained app/media intent
          -> local resolver creates ActionRequest
        -> AssistantActionService
            -> ActionRegistry
            -> schema and target validation
            -> PermissionPolicy
            -> confirmation when required
                -> allowlisted ActionExecutor
                    -> sanitized ActionResult
                        -> audit repository
                        -> chat presentation
```

## Hard Architecture Rules

### No Direct AI Execution

AI providers do not receive an executor, filesystem repository, subprocess
handle, or permission service as a dependency. Provider output can create only
an untrusted `ActionRequest`.

There is no method that accepts raw shell text. The action service must not call
`eval`, `exec`, `cmd.exe`, PowerShell, Windows Script Host, or a generic
subprocess function with AI-provided arguments.

### Default Deny

Every action is denied unless all of the following are true:

1. The action identifier exists in `ActionRegistry`.
2. Its typed parameters satisfy the registered schema.
3. The target passes protected-path and capability-specific validation.
4. A matching permission grant exists or the user approves the request.
5. The selected executor supports the exact registered action.

Validation failure cannot be overridden by the AI or by wording in a chat
message.

### Capability-Specific Executors

Executors remain small and non-generic. Initial examples are:

- `FileSearchExecutor`
- `OpenDirectoryExecutor`
- `OpenSafeFileExecutor`
- `LaunchAllowlistedApplicationExecutor`

There is no `RunCommandExecutor`, arbitrary `LaunchExecutableExecutor`, or
generic filesystem mutation executor in Phase 8.

## Structured Domain Contracts

### `ActionRequest`

An immutable request contains:

- a registered action identifier
- typed action parameters
- a correlation identifier
- the requesting conversation or UI source
- no permission decision and no executable implementation

### `ActionDefinition`

The registry-owned definition contains:

- action identifier and user-facing description
- parameter schema
- risk classification
- required permission capability
- confirmation policy
- executor identifier
- timeout and result limits

### `PermissionGrant`

A grant is scoped to a capability and target rather than being a global
"assistant access" switch.

Examples:

- `files.search` for `C:\Users\<user>\Documents\Projects`
- `files.open` for `C:\Users\<user>\Documents`
- `applications.launch` for the registered app identifier `spotify`

Grants are revocable in Settings. A directory grant does not grant application
launching, and an application grant does not grant filesystem access.

### `ActionResult`

Executors return a bounded, structured result:

- success, denied, cancelled, timed out, or failed status
- a short user-facing summary
- sanitized metadata required by the UI
- no API keys, environment dumps, file contents, or unrestricted exception text

### `ActionAuditEntry`

The audit record includes:

- request and action identifiers
- time and requesting source
- normalized target metadata
- permission and confirmation decision
- result status and duration
- sanitized failure category

File contents and hosted-provider credentials are never stored in the action
audit.

## Safe File Access

### Approved Roots

The user selects directories through a native directory picker. A grant is
stored only after the selected path is canonicalized and passes policy.

File actions must remain inside the approved canonical root after resolving
relative segments, symbolic links, junctions, and reparse points. Search limits
include:

- maximum recursion depth
- maximum result count
- execution timeout
- cancellation support
- bounded metadata returned to chat

### Protected Locations

Filesystem permission cannot be granted to system-critical or ambiguous roots,
including:

- drive roots
- the Windows directory, System32, and SysWOW64
- Program Files and ProgramData
- boot, recovery, and system-volume locations
- device paths and alternate data streams
- network and UNC paths unless a future phase designs a separate policy
- Project Akiha's encrypted credential file

Allowlisted applications may be installed under Program Files, but that does
not create a filesystem grant. Their executable paths are resolved by the
trusted application catalog and are never supplied by AI output.

### Initial File Actions

`files.search` reads names and basic metadata only. It does not read file
contents, generate embeddings, upload results, or silently broaden its root.

`files.open_directory` can open an approved directory in the system file
browser.

`files.open` accepts only a validated regular file inside an approved root and
requires a visible confirmation. Openable types come from a conservative
application-owned allowlist for ordinary text, image, audio, video, and PDF
files. Executable, script, installer, registry, shortcut, control-panel, and
active-content types are never included. Reading file contents into an AI
prompt is outside Phase 8.

No Phase 8 file action creates, edits, renames, moves, copies, downloads, or
deletes a file.

## Allowlisted Application Launching

Application launch uses stable registry identifiers such as:

- `discord`
- `chrome`
- `spotify`
- `vscode`

The application catalog owns discovery and the resolved launch target. The AI
can request only the registered identifier; it cannot provide:

- an executable path
- command-line arguments
- a URL
- a working directory
- environment variables
- a request for elevation

The user enables each application separately. Settings shows whether the
application was discovered and allows its permission to be revoked.

System utilities, shells, script hosts, installers, registry editors, service
managers, administrative consoles, and security-control applications are not
valid catalog entries.

## Permission And Confirmation Model

Initial risk classes are:

| Risk | Examples | Required behavior |
| --- | --- | --- |
| Read-only | Search filenames in an approved root | Existing scoped grant |
| User-visible | Open a directory or launch an allowed app | Scoped grant and visible result |
| Sensitive open | Open a validated file | Scoped grant plus per-action confirmation |
| Prohibited | Shell, elevation, file mutation, system settings | Always deny |

Permissions are:

- off by default
- capability- and target-specific
- visible and revocable in Settings
- checked at execution time, not only when the request is created
- unaffected by prompt instructions or memory content

Proactive behavior cannot launch an app or open a file in Phase 8. Actions
require a current user request or a direct UI command.

## Persistence And Migration

Migration `0008` is reserved for:

- scoped assistant-action permission grants
- assistant-action audit history

Application discovery results remain refreshable runtime data and must not turn
an obsolete executable path into permanent authority.

## Privacy Boundary

Before the first assistant action is enabled:

- increment the versioned privacy notice
- explain approved-directory access and action auditing
- explain that local file search returns metadata only
- explain that action results stay local unless the user separately includes
  information in a hosted chat request
- provide Settings controls to review and revoke permissions

No file content is sent to a hosted AI provider as part of Phase 8.

## Planned Implementation Sequence

### Phase 8A: Contracts And Policy

- [x] Add framework-free action models and result types.
- [x] Implement the action registry and schema validation.
- [x] Implement protected-path and permission policy.
- [x] Add migration `0008`, permission repository, and audit repository.
- [x] Add tests proving provider text cannot execute an action.

Checkpoint: requests can be validated, denied, confirmed, and audited without
any real desktop executor enabled. The service now accepts explicitly supplied,
capability-specific executors while remaining unavailable by default.

### Phase 8B: Read-Only File Discovery And Passive Opening

- [x] Add approved-directory management.
- [x] Implement bounded, cancellable file search.
- [x] Add search-result presentation and audit history.
- [x] Add open-directory support for approved roots.
- [x] Connect direct chat or UI requests to the typed action service.
- [x] Finalize the passive file-extension allowlist.
- [x] Add safe-file opening with per-action confirmation.

Checkpoint: Akiha can find and reveal safe files only inside approved roots.

Approved-directory management now:

- aggregates active `files.search` and `files.open` grants by canonical root
- atomically creates, updates, or revokes both directory capabilities
- requires an existing, non-protected directory when granting access
- reports missing or newly unsafe approved roots as unavailable
- can revoke stale roots after a directory is moved or deleted
- excludes application permissions from directory listings and revocation
- remains service-only until the Settings management UI is added in Phase 8D
- passed full verification with 651 tests; no file executor was enabled at this
  management-only checkpoint

Bounded file search now:

- enumerates only regular filenames and basic metadata inside a granted root
- searches case-insensitively without reading file contents
- limits recursion depth, result count, and registry-owned execution time
- streams directory enumeration so cancellation and timeout checks occur during
  traversal rather than after collecting a complete directory listing
- skips symbolic links, junctions, reparse points, unavailable directories, and
  inaccessible entries
- returns a sanitized cancelled, timed-out, unavailable-root, or success result
  and records it through the existing action audit repository
- remains unavailable until an application composition root explicitly provides
  `FileSearchExecutor`; chat and AI provider text still have no direct executor
  access

Search-result and audit presentation now:

- adds an Assistant actions window to the Settings surface
- presents the latest bounded file metadata separately from audit history
- supports refresh, action-text filtering, and result-status filtering
- shows only sanitized action fields such as action id, source, target, status,
  duration, and failure category
- never renders file contents, credentials, or unrestricted exception text

Approved-directory opening now:

- uses the registered `files.open_directory` action and `files.open` capability
- opens only an existing directory inside an active approved root
- uses Windows' normal directory opener without shell commands, arguments, or
  AI-controlled executable paths
- skips links and reparse-point targets and reports unavailable or failed opens
  through the existing sanitized result and audit path
- supports cancellation before the desktop opener is called

The conversational trigger remains separate from the executor. Plain provider
text cannot open a directory. The chat bridge now recognizes only explicit
`open directory: <absolute path>` and `search files: <query> | <absolute root>`
commands, creates typed requests, and passes them through the same validation,
permission, executor, and audit pipeline. Ordinary chat text and provider
responses never enter this bridge.

Passive file allowlist now:

- text: `.txt`, `.md`, `.csv`, `.json`, `.log`, `.yaml`, `.yml`, `.toml`, `.ini`
- images: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`
- audio: `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`
- video: `.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`
- documents: `.pdf`
- unknown extensions, executables, scripts, installers, shortcuts, registry
  files, control-panel files, Office files, and other active content are
  rejected by default
- the target must exist and be a regular non-link file before a future opener
  can run

The allowlist is finalized and enforced during typed `files.open` validation;
the passive-file executor rechecks the file immediately before opening. The
explicit `/open-file <absolute path>` chat command and `open file: <absolute
path>` form require an active approved-directory grant, show a visible Yes/No
confirmation, and open the file only after confirmation. Ordinary conversation
does not enter this path.

Passive-file opening now:

- rechecks existence, regular-file status, link/reparse-point status, and the
  passive allowlist immediately before invoking the system opener
- uses the Windows default file handler without shell commands or AI-provided
  executable paths or arguments
- supports cancellation before the desktop opener is called
- returns sanitized success, unavailable, timeout, or execution-failure results
  and records each decision through the existing audit repository
- refuses the action when the approved-directory permission is missing or the
  user declines confirmation

### Phase 8C: Allowlisted Applications

- [x] Add the trusted application catalog.
- [x] Discover Discord, Chrome, Spotify, and Visual Studio Code where installed.
- [x] Add service-level per-application permission controls.
- [x] Implement argument-free application launch.
- [x] Add missing, moved, denied, and launch-failure diagnostics.

Checkpoint: Akiha can launch only enabled catalog applications without shell
execution or AI-controlled arguments.

Application launching now:

- uses the stable identifiers `discord`, `chrome`, `spotify`, and `vscode`
- resolves executable paths only from known Windows installation locations
- refuses unknown identifiers, arbitrary executable paths, URLs, working
  directories, environment overrides, elevation, and command-line arguments
- starts the resolved GUI executable with `shell=False` and no arguments
- reports missing installations and launch failures through sanitized results
  and the existing action audit repository
- accepts explicit chat forms such as `/launch-app chrome` or `launch app:
  chrome`; ordinary conversation is not parsed as an application action
- keeps application grants separate from approved-directory permissions; the
  Settings UI for managing these grants remains in Phase 8D

### Phase 8D: UX, Privacy, And Packaging

- [x] Add Assistant settings for directories, applications, and grants.
- [x] Complete confirmation and denial UI for the remaining action surfaces.
- [x] Add action history with clear controls.
- [x] Update the versioned privacy notice.
- [x] Add diagnostics and reset behavior.
- [x] Run the automated test suite and static checks.
- [ ] Rebuild the release package and complete packaged smoke verification.

Phase 8D now:

- exposes approved-directory controls for search and directory/passive-file
  opening in Settings
- exposes enable, disable, discovery, and reset controls for the four
  allowlisted applications
- lets the user clear sanitized assistant-action history after confirmation
- reports missing, unavailable, and failed permission operations without
  exposing exception details
- versions the first-run privacy notice to explain assistant-action boundaries

### Phase 8E: Constrained AI-Assisted Proposals

- [x] Add a default-off Settings control for AI-assisted proposals.
- [x] Accept only strict typed proposals for allowlisted app launch or passive
  local media lookup.
- [x] Keep Akiha's approved roots, search results, paths, metadata, and file
  contents out of provider prompts.
- [x] Resolve media titles through the bounded local file-search executor.
- [x] Present multiple matches as local numbered results.
- [x] Preserve existing permission checks, audit records, and file-open
  confirmation.
- [x] Fall back to normal chat when the provider returns no action or an
  unusable proposal.
- [x] Add proposal, filtering, result-follow-up, worker, config, and privacy
  tests.

The provider has no executor reference and cannot return a path. A successful
proposal is still only an intent such as `launch_application: chrome` or
`play_media: Elis / Megurine Luka`. Akiha performs discovery locally and turns
the result into the same typed action request used by direct commands.

## Required Boundary Tests

- [x] Provider or chat text alone cannot invoke an executor.
- [x] Unknown action identifiers are denied and audited.
- [x] Invalid typed parameters are denied before permission checks.
- [x] A path outside an approved root is denied.
- [x] Traversal, junction, reparse-point, device-path, and protected-path
  escapes are denied.
- [x] Search limits, cancellation, and timeout behavior are enforced.
- [x] Approved-directory opening remains scoped, argument-free, and audited.
- [x] Only allowlisted passive file types can be opened through file actions.
- [x] Passive file opening requires a scoped grant and visible confirmation.
- [x] An unregistered application or AI-provided executable path is denied.
- [x] AI proposals containing paths, commands, URLs, or extra fields are
  rejected.
- [x] AI-assisted media resolution searches only approved roots and exposes
  only opaque numbered follow-ups to the conversation.
- [x] Application arguments and elevation requests are denied.
- [x] Revoked permission prevents the next matching action.
- [x] Denied and failed actions do not fall back to shell execution.
- [x] Audit records exclude file contents and credentials.
- [x] Migration `0008` applies cleanly to fresh and existing databases.

## Phase 8A Completion

- Added immutable action requests, definitions, validation results, permission
  grants, sanitized results, and audit records.
- Registered only file search, approved-directory/file open, and allowlisted
  application-launch action identifiers.
- Added protected-root, drive-root, network/device path, alternate-stream,
  traversal, link, junction, reparse-point, and credential-path guards.
- Added typed directory and application permission management.
- Added SQLite permission and audit persistence through migration `0008`.
- Added fail-closed request evaluation that stops at `executor_unavailable`
  after validation and authorization.
- No executor was enabled at the Phase 8A checkpoint; Phase 8B now adds only
  explicitly supplied file-search and approved-directory executors.
- Full verification passed with 643 tests; one environment-dependent live
  symlink test was skipped while deterministic reparse rejection passed.

## Out Of Scope

- Arbitrary shell or PowerShell execution
- User-provided or AI-provided command lines
- Administrator elevation
- Writing, renaming, moving, copying, downloading, or deleting files
- Reading file contents into AI context
- Sending local paths, directory listings, search results, or file metadata to
  an AI provider
- Registry, service, driver, task-scheduler, or Windows settings changes
- Keyboard, mouse, browser, or anti-AFK automation
- Autonomous or silent background actions
- Plugin execution
- Network-share access
- Package installation, update, or process termination

## Exit Criteria

Phase 8 is complete only when:

- every executable action is registered, typed, permission-checked, and audited
- file search cannot escape user-approved non-system directories
- only explicitly enabled catalog applications can launch
- no action path invokes a shell or accepts AI-controlled executable arguments
- permissions can be reviewed and revoked
- the revised privacy notice is acknowledged
- automated tests and packaged smoke checks pass
