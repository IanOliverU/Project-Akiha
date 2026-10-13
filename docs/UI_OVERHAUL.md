# Native UI overhaul — 2026-10-12

**Current status (2026-10-13):** UI implementation included in pushed HEAD 88a7e6b.
Phase 13I and exact-revision UI acceptance are pending under the owner's latest
instruction. See [current reconciliation](phases/phase-13-assistant-utilities/CURRENT_HEAD_VERIFICATION.md)
and [one consolidated checklist](phases/phase-13-assistant-utilities/OWNER_CHECKLIST_CURRENT_HEAD.md).
Records below are chronological history; no new commit/push occurred.


Status: active presentation/interaction work, separate from Phase 13. Owner
Phase 13 testing is paused, not passed. Phase 13I and final UI acceptance remain
pending a fresh consolidated candidate and refreshed checklist. No commit/push.

## Design and architecture

Keep PySide6/Qt Widgets, existing artwork/animation contracts, controllers,
EventBus and singleton managers. Original dark blue/charcoal backgrounds, blue-gray surfaces and
lavender/purple accents, bundled vector icons, readable Japanese/English typography, shared
spacing/focus/disabled/error states. Native pickers and OAuth remain native.
Do not copy reference branding or invent unsupported features. No new dependency,
provider, scheduler, permission grant, storage or credential behavior is planned.

## Feature-to-screen map and preserved bindings

| Existing surface | Redesigned destination | Actual boundary / save semantics |
| --- | --- | --- |
| ChatWindow transcript/composer/history toolbar | Workspace Chat, contextual conversation controls | message_submitted, cancel/new/clear/export signals; ChatController canonical transcript/provider construction |
| ActionClarificationPanel | Local action card beside composer | same controller, opaque choice identity/epoch/expiry/replay, explicit local sharing control |
| Voice chat controls | Chat voice/session row | existing listen/stop/cancel/replay/start/end signals and runtime-fed state only |
| Settings Pet page | Settings → Pet | existing PetWindowConfig, diagnostics/reset operations; explicit Save |
| AI/personality/provider discovery/keys | Settings → AI | same masked key/keep-saved/clear logic; provider discovery worker; explicit Save |
| Memory settings | Settings → Memory; Workspace Memories | same MemoryConfig; manager emits approvals/edit/archive/restore/delete/clear/reflection requests |
| Behavior/quiet hours/channels | Settings → Behavior; Workspace Activity | same BehaviorConfig; history filters/detail/matching clear confirmations |
| App/root/Spotify grants | Settings → Actions | existing independent grant/revoke signals; immediate operations, never delayed until Save |
| Spotify | Settings → Spotify; Chat local search/recent picker | existing OAuth worker/session signals and playback permission boundaries |
| Gmail/Discord/Notification Center | Settings → Integrations; Workspace Notifications | existing auth/test/refresh/clear signals; read-only integrations, sanitized inbox |
| Voice configuration/advanced diagnostics | Settings → Voice | same VoiceConfig; privacy acknowledgment, microphone/output/health diagnostics |
| Registered music | Workspace Music / Settings → Music files | same MusicFilesPanel registration/open/remove/filter/drop signals; parent-folder effects explained; no file move/delete |
| Timers/reminders/weather | Workspace Utilities / Settings → Utilities | same utility_action_requested signals; one schedule owner, DST/lease validation; weather opt-in and transient results |
| Selected data export | Utilities export/review | existing opaque export selection/destination/confirmation service; no restore/import |
| Pet care/status/shop/appearance | Workspace Companion entry points | existing persistent managers/care/shop workers and typed requests, unchanged assets |
| Logs/data/provider health/tuning | Settings diagnostics / advanced sections | existing local reveal/health/test callbacks; no credentials in search/status |
| Sprite context menu and tray | Compact grouped native menus | existing show/hide/walk/sleep/wake/care/status/shop/chat/settings/history/quit commands |
| Privacy notices and confirmations | Shared native dialog styling | preserve consent/revocation and default-No destructive/consequential decisions |

Settings retain explicit Save. Draft-edit status and close protection are added;
search indexes static UI labels/descriptions, never field values, credentials,
transcripts, paths, registered filenames or account/history content. Immediate
operations remain independently labeled and routed through current callbacks.

## Verification plan

Capture actual composed Qt widgets with synthetic content before/after; test
multiline Enter/Shift+Enter, cursor insertion, streaming replacement/subtitle
privacy/stable scrolling, navigation focus/singleton ownership, settings search
and draft preservation, unchanged immediate revocation and local action routing,
native reminder inputs/DST, context commands, GUI-thread deferred destruction.
Run focused/regression/full single-process gates, source quality/static/privacy,
historical Qt pair and source/package lifecycle checks. Build only with verified
guarded paths. Old candidate evidence is not a redesigned UI pass. Simulated
Qt scale-factor captures are separate from owner Windows 100/125/150/200% checks.

## Owner palette correction — 2026-10-13

The reference applies to layout and interaction only. The original committed
Akiha palette is the source of truth: window #1A1D24, panel #22252E, control
#2C303C, border #3A3F52, text #E8E9EE and secondary text #9A9FB5. Lavender
accents and existing status colors are preserved. Shared theme tokens now also
own hover and disabled states; scoped manager surfaces use these same tokens.
Sprite artwork and animation assets are unchanged. Final verification and a
fresh candidate remain pending; earlier candidate evidence is superseded.

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
