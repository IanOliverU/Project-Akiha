# Consolidated Phase 13 owner checklist

Historical checklist. Current owner checks are consolidated in [OWNER_CHECKLIST_CURRENT_HEAD.md](OWNER_CHECKLIST_CURRENT_HEAD.md).
Do not repeat this historical list as an additional acceptance requirement.


Final acceptance remains pending this checklist. Use the **entire candidate
folder**, not Akiha.exe by itself. Candidate:
`dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe` once the fresh build and
verification are recorded in `docs/UI_OVERHAUL_VERIFICATION.md`. The earlier
2026-10-09 candidate predates the UI overhaul and is superseded for owner testing.
Close the source/older app using its tray **Quit** first so the candidate owns
your usual single-instance namespace. Keep a copy of existing application data
before testing the new migration. Use synthetic labels/files for privacy tests.
Never send credentials, private dialogue or reference audio in returned results.

Report each numbered item as PASS/FAIL/N/A with a short failure description.
For account/voice/network items, N/A means unverified and must be explicitly
resolved before final acceptance; it is not a pass. Controls named below are
existing local controls. “Close chat” hides the chat window; **Quit** exits Akiha.

The workspace sidebar opens the same existing managers. Music and Utilities open
their Settings pages; Utilities contains Timer, Reminder, Weather and Data/export
tabs. Reminder date/time and timezone are native local inputs. Complete
`docs/UI_OWNER_CHECKLIST.md` as well. Testing remains paused until the new candidate
is ready; this update records no passed owner checks.

1. **Package startup and existing data.** Launch the candidate with your normal
   profile. Expect the pet, chat and Settings to open without a crash; existing
   preferences, conversations, memories, music registration, grants and inbox
   entries remain. Quit and restart; expect those records intact.
2. **Single instance.** While the candidate runs, launch the same EXE again.
   Expect the existing window activated and the second process to exit; no
   second pet, schedule owner or duplicate notifications.
3. **Ordinary conversation and existing features.** Send `Hello Akiha` and a
   harmless ordinary preference, change an existing pet/appearance setting,
   inspect memory and existing health/integration settings. Expect normal chat,
   persistence, pet behavior and read-only Gmail/Discord behavior if configured.
   No unsolicited account writes or utility execution.
4. **App picker.** Type `Open an app`, then `Akiha, please open an app`.
   Expect locally available allowlisted apps only. Select an approved app and
   use its normal permission/confirmation flow. Expect that exact app launched.
   With no eligible app, expect a configuration explanation, not a raw path field.
5. **Approved-root picker.** In Actions, configure a synthetic folder named
   `Phase13TestMusic`. Type/say `Open a folder`. Expect configured eligible root
   choices; select that folder. Expect it opened through permissions. A label
   such as `Downloads` is never treated as an absolute executable path.
6. **Typed/local voice convergence.** With your local transcription configured,
   say `Akiha, please open an app` and `Open a folder`. Compare the “Heard” text
   and picker with typing the same recognized text. Expect the same local
   operation and choices; no provider claim that these functions are unavailable.
7. **Music registration and album folders.** In Settings → Music files, drag
   synthetic supported MP3/WAV/FLAC/OGG/M4A files and a folder containing songs;
   also use Add files. Expect registration of existing locations, no file move,
   copy or archive extraction, and the existing explicit local folder-permission
   policy. Type `Open a music file`; expect registered choices. Choose one;
   expect that exact file opened by the default player.
8. **Music management/failure.** Filter by a registered filename, remove a
   registration and refresh. Expect list changes, no deletion of the actual
   file. Temporarily move a synthetic registered file or revoke its root grant;
   expect unavailable/denied opening, no arbitrary replacement and no validation
   relaxation. Restore the fixture/grant afterward.
9. **Spotify generic request.** With Spotify connected, type/say
   `Play music on Spotify`. Expect local choice between recently played and
   specific search. Expect no automatic arbitrary song and no ordinary-chat
   claim that integrated Spotify control is impossible.
10. **Spotify recent picker.** Choose recently played. Expect the latest 20
    history entries fetched and up to ten **distinct** available tracks shown
    newest-first, title and artist. Repeated plays count once; fewer than ten
    unique usable tracks means a shorter list. Select one and expect normal
    playback/device/account/permission checks. Search results must not substitute
    for history. Empty/unavailable history should explain locally.
11. **Spotify scope/account failures.** If the saved connection lacks
    `user-read-recently-played`, expect an explicit reconnect/history-permission
    explanation, no silent authorization expansion. Disconnect or switch the
    account while the picker is pending; the old selection must fail closed.
    A temporary offline/rate-limited service must explain failure locally.
12. **Spotify specific routes.** Use a known available target with each supported
    form: `Play track Blinding Lights by The Weeknd on Spotify`,
    `Play artist The Weeknd on Spotify`, `Play album After Hours on Spotify`,
    and `Play playlist <your known playlist name> on Spotify` (replace brackets).
    Expect existing specific search/selection routes, at most five search
    choices, not recent-history substitution. No automatic choice on ambiguity.
13. **Cancel, timeout, supersession, replay and revocation.** Open a picker and
    Cancel; no action executes. Open another, wait over 120 seconds; selection
    must expire. Open a picker then issue a newer explicit `Open an app`; the
    old selection/confirmation must be unusable. Repeated clicking must not
    execute twice. Remove/revoke an offered local target before selection;
    expect failure. Unrelated non-path ordinary chat must preserve the picker.
14. **Clarification privacy/explicit override.** While folder/file clarification
    is pending, submit synthetic `I prefer Downloads/ SPACE_SECRET.mp3`,
    `the path is /home/PRIVATE_TEST/file.mp3`, a quoted Windows path, UNC path,
    `file:///PRIVATE_TEST/file.mp3`, and `%2525252FENCODED_SECRET.mp3` through
    the composer. Expect local handling/rejection and a safe local message,
    no canonical transcript/export/provider echo. Ordinary `I prefer coffee`
    should remain chat. Only deliberate **Continue as normal chat** may route
    the held text to chat; it is request-bound, expires and cannot replay.
    Do not deliberately override with actual private content. Automated connected
    tests additionally cover SQLite, summaries, memories, notifications/events/logs.
15. **Gemini Live suspension/restart.** In a real configured hosted Live session,
    issue a local incomplete action. Expect cloud audio forwarding suspended
    before answering the question; speaking while suspended must not reach the
    provider. Resolve/Cancel via the current local controls, then explicitly
    resume/restart as presented. A newer clarification/session must not be
    resumed by old callbacks. Record actual microphone/provider testing separately.
16. **Timer create/list/inspect/cancel.** Type `Set a timer for 10 seconds named tea`,
    then `List timers`; copy its opaque ID. Use `Inspect timer <ID>` and
    `Cancel timer <ID>` before due. Expect exact timer details/cancellation and
    no elapsed notification for the cancelled timer. `Set a timer` must ask
    locally for duration; invalid/oversized durations must not start a timer.
17. **Timer delivery/presentation.** Create two `Set a timer for 5 seconds`
    requests. Expect each delivered once through your configured inbox/chat/
    tray/voice arbitration; private purpose labels do not enter those channels.
    Repeat with quiet/away or disabled-channel preferences and expect policy
    suppression with inbox evidence, not delayed duplicate speech. Restore settings.
18. **Timer restart recovery.** Create `Set a timer for 30 seconds`, Quit before
    due, restart shortly afterward. Expect one retained timer and one due receipt,
    no duplicate on another restart. Completed/cancelled timers must not resume.
19. **Reminder create/clarify/deliver.** Type `Set a reminder`; provide a future
    `YYYY-MM-DDTHH:MM` and explicit `Asia/Taipei` when asked. Alternatively use
    Settings → Utilities to enter a time a few minutes ahead and a synthetic
    private label, then Create reminder. Expect one local schedule and one
    generic notification at the chosen time. `List reminders` shows opaque ID,
    UTC due time and the explicit timezone, not purpose labels in chat.
20. **Reminder cancel/snooze.** Copy a pending reminder ID and use
    `Snooze reminder <ID> for 5 minutes`, then `Cancel reminder <ID>`.
    Expect only that reminder's deadline updated, then cancelled; no second
    scheduler, duplicate receipt or recurrence. Settings Cancel selected and
    Snooze reminder must behave consistently. Cancelled reminders cannot snooze.
21. **Reminder DST and downtime.** For a future DST transition, use e.g.
    `Set a reminder at 2026-11-01 01:30 America/New_York` while that date is
    still future. Expect a local choice for first/second occurrence, no guessing.
    A nonexistent local spring-forward time must ask for another time. Quit with
    a future reminder and restart around due; expect at most one receipt. An
    overdue reminder over one hour appears silently, not a burst of old alerts.
    Do not alter the machine clock to test this; automated clocks cover boundaries.
22. **Weather opt-in and source.** Before enabling weather, type `Weather`;
    expect a local configuration explanation. In Utilities enter your explicitly
    chosen coordinates, check enable/location consent and Save Changes. Type
    `Weather`, then `Weather forecast`. Expect current conditions/three days in
    Utilities with source, UTC timestamp, age, units and uncertainty; no weather
    payload or coordinates in canonical chat/export/memory. NWS alerts outside
    coverage explicitly direct you to your local authority, not an all-clear.
23. **Weather failure/recovery.** Disable network temporarily, request `Weather`,
    and inspect health. Expect bounded offline failure while chat/Settings stay
    usable. Restore network and retry explicitly; expect recovery. Disable weather
    or change location during a pending lookup; old results must not display.
24. **Contextual navigation and safety.** Under approved `Phase13TestMusic`, make
    two synthetic subdirectories with matching names and a `Compressed` folder.
    Open the approved root through the picker, then
    `Open Compressed folder inside it`. Expect bounded search under the current
    approved directory; ambiguity asks for a choice. Revoke the root and retry;
    expect denial. `..`, file URIs or traversal-shaped provider aliases must not
    grant access. No file contents are read or modified by navigation.
25. **Selected conversation export.** In Utilities choose Export selected
    conversations / memories, select one synthetic conversation and choose a
    **new** local `.json` destination. Cancel confirmation first: expect no file.
    Repeat and approve: expect version 1 manifest, selected record only, count
    and SHA-256. An existing destination must be refused, never overwritten.
    Config, credentials, system/raw-provider records, notifications, logs,
    schedule labels and voice references must be absent.
26. **Selected memory export and stale confirmation.** Export one selected
    synthetic memory. Expect its whitelisted text/importance/timestamps only,
    no embeddings or unselected memories. Wait over 60 seconds before approving
    another export, or issue a newer explicit action first; expect no file and
    a safe failure. No restore/import/cloud upload control should exist.
27. **Settings and diagnostics.** Save/reopen Utilities location and retention
    settings; expect them preserved locally, weather result transient, active
    schedule labels visible only in the local schedule list. Inspect health and
    bounded poll delay/missed/presentation-failure counts. No raw paths,
    coordinates, purpose labels or provider payloads in diagnostics. Completed
    label retention must not erase active schedules or permit replay.
28. **Graceful pending-clarification Quit.** Open `Open a folder`, leave its picker
    pending, and use tray Quit. Expect the candidate process to exit normally,
    no Python/Qt crash dialog, hanging worker or stale picker after restart.
    Repeat during your real local voice or hosted session. Automated proof uses
    fresh default configuration; this owner check covers your configured runtime.

When every applicable item passes and any N/A has been explicitly resolved,
return your explicit confirmation. Phase 13 may then be closed only with the
automated/review/package evidence reconciled; no push is implied by acceptance.

## Owner acceptance and closure ? 2026-10-13

The owner confirmed the entire Phase 13 looks good, accepted the native UI
candidate, requested removal of chat message highlighting, and explicitly
authorized committing and pushing all reviewed changes since Phase 13C.
Phase 13A?13I is complete. No subsequent phase is activated by this record.
Owner testing is owner-reported; it is not relabeled as automated live-provider
evidence. Historical environment failures remain documented and do not override
the later passing gates. Generated builds, verification artifacts and private
data are excluded from the source checkpoint. The clean-build guard remains
mandatory; recurrence, restore/import and other explicit exclusions remain out
of scope.

## Owner acceptance and closure - 2026-10-13

The owner confirmed the entire Phase 13 looks good, accepted the native UI
candidate, requested removal of chat message highlighting, and explicitly
authorized committing and pushing all reviewed changes since Phase 13C.
Phase 13A through 13I is complete. No subsequent phase is activated here.
Owner testing is owner-reported, not automated live-provider evidence. Historical
environment failures remain documented alongside later passing gates. Generated
builds, verification artifacts and private data are excluded from the checkpoint.
The clean-build guard remains mandatory; recurrence, restore/import and all
other explicit exclusions remain out of scope.
