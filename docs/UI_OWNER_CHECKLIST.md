# Native UI candidate owner checklist

Historical checklist. Current owner checks are consolidated in [phases/phase-13-assistant-utilities/OWNER_CHECKLIST_CURRENT_HEAD.md](phases/phase-13-assistant-utilities/OWNER_CHECKLIST_CURRENT_HEAD.md).
Do not repeat this historical list as an additional acceptance requirement.


UI acceptance and Phase 13I acceptance remain pending. Use the new candidate
listed in UI_OVERHAUL_VERIFICATION.md, rather than an earlier packaged build.
Test your existing profile first; do not delete or overwrite your private data.

1. **Visual identity:** open Chat, Settings and the feature managers. Expect
   Akiha's original dark blue/charcoal, blue-gray and lavender palette. The sprite
   artwork and animations must look unchanged.
2. **Scaling and keyboard:** test Windows scaling at 100%, 125%, 150% and 200%,
   compact and enlarged windows, Tab/Shift+Tab and visible focus. Expect readable
   English/Japanese, scrollable long pages/menus and accessible Save/footer controls.
3. **Workspace:** open Memories, Music, Utilities, Notifications and Activity
   repeatedly from Chat. Expect the existing manager to be reused, with the
   same records and operations. Settings opens its corresponding existing page.
4. **Composer:** Shift+Enter inserts a newline; Enter sends. Select older chat
   text and scroll upward during a response; selection and reading position
   should remain stable. Translation subtitles stay visually secondary.
5. **Voice:** test real local microphone, your configured TTS and hosted voice.
   Expect the same listening/speaking controls, cancellation and privacy notice.
   Automated synthetic tests do not establish live microphone/provider success.
6. **Clarification:** use `Open an app`, `Open a folder`, `Open a music file`
   and `Play music on Spotify`. Expect the existing local choices and permission
   checks. Cancel and supersede a pending choice; stale choices must not execute.
   Private answers remain local unless you deliberately choose normal chat.
7. **Settings drafts:** edit a setting, switch categories and search its static
   label. Expect the draft to survive. Close with Cancel, then Discard, then Save
   on separate attempts; expect each choice to do exactly what it says. Search
   must not reveal keys, paths, messages, account history or other dynamic values.
8. **Permissions/music/Spotify:** independently grant/revoke an app/root, drop
   an album folder, filter/remove/open registered music, and test Spotify recent
   history versus a specific search. Expect the existing bounded choices and
   unavailable/revoked states; immediate operations do not wait for Settings Save.
9. **Utilities:** create/cancel a short timer; create a one-shot reminder using
   the calendar, time and explicit timezone; snooze/cancel it. Check weather with
   explicit configuration/consent. Results appear on the Weather tab. Labels stay
   private, and timers/reminders remain distinct.
10. **Export/managers:** review selected export categories and destination before
    confirming. Check memories, notifications, history, pet care/status and shop.
    Expect the same approvals, filters and destructive-action confirmations.
11. **Sprite/tray:** right-click Akiha and use the grouped menu, including scrolling
    or keyboard navigation at large scaling. Test show/hide, walk/sleep/wake,
    Chat, Settings, care/status/shop and Quit. No command should disappear.
12. **Shutdown/data:** quit while clarification is pending and while Settings has
    an unsaved draft. Cancel must preserve the running app; an approved quit must
    finish normally. Restart and verify existing configuration and records remain.

Return each item as PASS, FAIL (with steps), or N/A (with reason). Repeat the
retained Phase 13 owner checklist separately; neither checklist is accepted here.

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
