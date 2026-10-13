# Consolidated outstanding owner checks - HEAD 88a7e6b

Phase 13 remains pending. Prior functional approval and unchanged automated
evidence are retained; this checklist covers the new exact-revision package and
affected UI/runtime flows. Do not repeat the two older checklists as additional
requirements. The previously supplied package predates the final chat correction.

Candidate: `dist/phase13-head-88a7e6b-candidate-20261013/Akiha/Akiha.exe`.
Keep the entire folder together. First use the tray **Quit** on older/source
Akiha instances. Keep a backup of your existing application data. Use synthetic
test messages, files and labels. Do not return credentials or private transcripts.

1. **Existing profile and final chat appearance.** Start the candidate, open
   Chat and type `Hello Akiha`. Expect your existing settings/records to remain,
   no startup error, no background highlight strips behind messages, readable
   speaker labels and secondary English subtitles. Backgrounds remain Akiha's
   dark blue/charcoal and blue-gray with lavender accents; sprite art is unchanged.
   Quit and reopen; expect existing records intact.
2. **Native Windows scaling and keyboard.** At each available Windows Display
   scaling setting (100%, 125%, 150%, 200%), open Chat and Settings, resize them
   compact/large, Tab/Shift+Tab through controls, and scroll long pages. Expect
   readable English/Japanese, visible focus, no overlaps and reachable Save,
   footer and menu commands. Record unavailable scaling levels explicitly;
   Qt scale-factor screenshots are not owner Windows DPI verification.
3. **Multiline and streaming.** In Chat type `first line`, press Shift+Enter,
   type `second line`, then Enter. Expect one multiline message, no early send
   and a cleared composer. While a reply streams, select earlier text and scroll
   upward; expect stable selection/reading position without duplicated response
   text. New/Clear/Export remain accessible under Conversation.
4. **Workspace and Settings drafts.** Click Memories, Music, Utilities,
   Notifications, Activity and Settings twice each. Expect existing managers
   reused, Music/Utilities opening their Settings pages and no duplicate pet.
   Change Pet FPS without saving, switch categories, then search `FPS`.
   Expect draft preserved and only static setting labels matched. Close with
   Cancel (draft stays), then Discard (saved value returns); on a new edit use
   Save Changes and reopen (new value persists). Restore your preferred setting.
5. **Local action choices and privacy surface.** Type `Open an app`, select an
   approved app; type `Open a folder`, select a configured approved root.
   Expect exact targets and existing permission checks. Repeat and Cancel,
   then supersede a pending picker with another explicit action; expect no old
   action. While folder clarification is pending, enter synthetic
   `I prefer Downloads/ UI_ONLY_SECRET.mp3` in the composer: expect safe local
   handling/rejection, no canonical chat/provider echo. `I prefer coffee` still
   works as chat. With synthetic text only, deliberately use Continue as normal
   chat: expect explicit normal-chat routing. Do not share actual private paths.
6. **Music and Spotify controls.** Settings > Music files: drop a supported
   synthetic song or album folder, filter it, use `Open a music file` and choose
   it; remove registration afterward. Expect no copying/deleting source files
   and the same permission/confirmation behavior. With Spotify connected, use
   `Play music on Spotify`: choose recently played, expect up to ten distinct
   available tracks newest-first from the latest twenty plays; choose a specific
   search instead and enter a known song/artist. Expect existing bounded search
   and playback checks, not an arbitrary selection. Disconnect while a picker
   is pending; expect its old selection to be unusable. Restore the connection.
7. **Timer and native reminder UI.** Workspace > Utilities > Timer: create a
   five-second timer and expect one receipt. Create another and use Cancel
   selected schedule now before due; expect no due receipt. On Reminder choose
   a time a few minutes ahead using the calendar/time controls, explicitly select
   `Asia/Taipei`, enter synthetic label `UI reminder`, and use Create one-shot
   reminder now. Expect the selected local time and timezone, one local schedule
   and generic notification. Create another, select it, Snooze selected reminder
   now, then Cancel selected schedule now; expect only that schedule affected.
8. **Weather settings/results.** Utilities > Weather: verify your intended
   coordinates and consent locally, enable read-only weather and Save Changes.
   Type `Weather` and `Weather forecast` in Chat. Expect results on the Weather
   tab with source/time/age, rather than raw weather/location payload in chat.
   With network temporarily unavailable, retry; expect bounded failure without
   hanging Settings/chat. Restore network/settings and explicitly retry.
9. **Context navigation and export review.** Open an approved synthetic folder
   containing a `Compressed` subfolder, then type `Open Compressed folder inside
   it`. Expect navigation within that root and local choices if ambiguous.
   Utilities > Data & export > Select conversations / memories to export?:
   check one synthetic conversation, choose a new `.json` file, cancel final
   confirmation (expect no file), then repeat and confirm (expect selected data
   only). Repeat for one synthetic memory. Existing destinations are refused;
   configuration, credentials, schedules and raw provider records are absent.
10. **Managers, sprite and tray menus.** Inspect Memories, Notifications,
    Activity, assistant-action history and Companion care/status/shop. Expect
    preserved records, filters and destructive confirmations. Right-click the
    sprite: test Chat, Settings, Walk/Sleep/Wake and show/hide via the tray.
    At large scaling, scroll or use arrow keys/End to reach the last menu command.
    Expect all commands usable and original sprite animation behavior unchanged.
11. **Actual configured voice paths.** With local microphone configured, say
    `Open a folder`; compare the recognized Heard text and picker to typed input.
    Test your configured TTS with a harmless reply. In configured Gemini Live,
    issue an incomplete local action, expect audio forwarding suspended before
    the question is actionable; resolve/Cancel through the current controls and
    explicitly resume/restart. Test cancel/end conversation. Expect normal
    recovery and no old session resuming a newer pending clarification. Record
    which voice/providers you actually tested; offline SDK checks do not cover this.
12. **Configured graceful Quit and draft cancellation.** Leave `Open a folder`
    pending, use tray Quit and check Task Manager: expect the candidate process
    to exit normally, with no crash dialog or hanging worker. Repeat during your
    configured local voice and hosted session. Separately edit an unsaved setting
    and Quit: choose Cancel and expect the app to remain running; then Discard
    or Save and Quit, expect normal exit. Restart and expect no stale picker.

Return results as `1 PASS`, `2 FAIL - steps`, etc. For unavailable accounts,
providers or scaling settings, use N/A with a reason; unresolved required checks
remain pending until explicitly settled. Your earlier utility approval remains
recorded; no new acceptance is inferred from this checklist or automated results.
