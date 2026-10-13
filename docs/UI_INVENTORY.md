# Native UI inventory and preserved bindings

Generated from actual Qt presentation classes for the authorized 2026-10-12 overhaul. Static source identifiers and labels only; no owner data or credentials. The old-to-new screen map and controller/save semantics are in [UI_OVERHAUL.md](UI_OVERHAUL.md).

## ActionClarificationPanel

`project_akiha/ui/action_clarification_panel.py`

**Existing route signals:** `refresh_requested`, `normal_chat_requested`, `spotify_history_requested`.

**Presentation update methods:** `show_notice`, `show_privacy_notice`, `refresh`.

**Static controls:** `Cancel action`, `Continue as normal chat`, `Open any of these`, `Use this answer`.

## AssistantActionHistoryWindow

`project_akiha/ui/assistant_action_history_window.py`

**Existing route signals:** `refresh_requested`, `clear_requested`.

**Presentation update methods:** `update_search_results`, `update_audits`, `append_notice`.

**Static controls:** `Clear history`, `Refresh`.

## BehaviorHistoryWindow

`project_akiha/ui/behavior_history_window.py`

**Existing route signals:** `refresh_requested`, `clear_requested`, `clear_matching_requested`.

**Presentation update methods:** `update_events`, `append_notice`, `selected_event_id`, `selected_event`, `selected_event_type_filter`, `selected_kind_filter`.

**Static controls:** `Clear all`, `Clear matching`, `Copy`, `Refresh`.

## ChatWindow

`project_akiha/ui/chat_window.py`

**Existing route signals:** `message_submitted`, `cancel_requested`, `new_chat_requested`, `clear_chat_requested`, `export_chat_requested`, `voice_listen_requested`, `voice_listen_stop_requested`, `voice_listen_cancel_requested`, `voice_speak_stop_requested`, `voice_replay_requested`, `voice_conversation_start_requested`, `voice_conversation_end_requested`, `destination_requested`.

**Presentation update methods:** `add_clarification_panel`, `clear_history`, `append_message`, `begin_streaming_message`, `append_stream_delta`, `replace_streaming_message`, `finish_streaming_message`, `append_error`, `append_notice`, `append_proactive_suggestion`, `append_assistant_translation`, `append_translation_unavailable`, `set_status`, `set_provider_display`, `set_presence_text`, `set_voice_capabilities`, `set_voice_state`, `set_voice_conversation_active`, `set_voice_conversation_lane`, `set_voice_conversation_state`, `set_voice_replay_available`, `insert_voice_transcript`, `submit_voice_transcript`, `set_voice_input_status`, `show_voice_transcript_preview`, `show_live_voice_transcript`, `set_busy`.

**Static controls:** `Clear chat`, `Export`, `New chat`, `Send`, `Start conversation`, `Stop`, `Talk`.

## MemoryWindow

`project_akiha/ui/memory_window.py`

**Existing route signals:** `refresh_requested`, `edit_requested`, `archive_requested`, `restore_requested`, `delete_requested`, `clear_requested`, `reflect_requested`, `approve_requested`, `reject_requested`, `clear_pending_requested`.

**Presentation update methods:** `update_memories`, `update_archived_memories`, `update_pending_memories`, `append_notice`, `selected_memory_id`, `selected_memory`, `selected_archived_memory_id`, `selected_pending_memory_id`.

**Static controls:** `Approve`, `Archive`, `Clear all`, `Clear pending`, `Delete`, `Edit`, `Reflect`, `Refresh`, `Reject`, `Restore`.

## MemoryEditDialog

`project_akiha/ui/memory_window.py`

**Existing route signals:** native dialog accept/reject or controller/EventBus methods.

**Presentation update methods:** `values`.

## MusicFilesPanel

`project_akiha/ui/music_files_panel.py`

**Existing route signals:** `files_changed`, `registration_requested`, `open_requested`, `permissions_requested`.

**Presentation update methods:** `set_config`, `set_directories`, `set_status`, `register`, `refresh`.

**Static controls:** `Add files`, `Add folder`, `Folder permissions`, `Open selected`, `Refresh`, `Remove from list`.

## NotificationCenterWindow

`project_akiha/ui/notification_center_window.py`

**Existing route signals:** `refresh_requested`, `mark_read_requested`, `mark_all_read_requested`, `clear_requested`.

**Presentation update methods:** `update_records`, `append_notice`.

**Static controls:** `Clear all`, `Mark all read`, `Mark read`, `Refresh`.

## PetCareWindow

`project_akiha/ui/pet_care_window.py`

**Existing route signals:** `refresh_requested`, `care_action_requested`, `status_requested`, `shop_requested`.

**Presentation update methods:** `update_record`, `show_care_result`, `set_busy`, `set_notice`.

## PetStatusWindow

`project_akiha/ui/pet_status_window.py`

**Existing route signals:** `refresh_requested`, `care_requested`, `shop_requested`.

**Presentation update methods:** `update_snapshot`, `set_busy`, `set_notice`.

## PetWindow

`project_akiha/ui/pet_window.py`

**Existing route signals:** native dialog accept/reject or controller/EventBus methods.

**Presentation update methods:** `apply_config`, `set_animation_provider`, `staged_sleep_available`, `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`, `contextMenuEvent`, `paintEvent`.

**Static controls:** `Behavior history`, `Care`, `Chat`, `Hide`, `Quit`, `Settings`, `Shop & appearance`, `Sleep`, `Status`, `Stop walking`, `Wake`, `Walk`.

## PrivacyNoticeDialog

`project_akiha/ui/privacy_notice.py`

**Existing route signals:** native dialog accept/reject or controller/EventBus methods.

**Presentation update methods:** native widget lifecycle.

## HostedLivePrivacyNoticeDialog

`project_akiha/ui/privacy_notice.py`

**Existing route signals:** native dialog accept/reject or controller/EventBus methods.

**Presentation update methods:** native widget lifecycle.

## SettingsWindow

`project_akiha/ui/settings_window.py`

**Existing route signals:** `settings_saved`, `utility_action_requested`, `utility_export_requested`, `music_files_changed`, `music_registration_requested`, `music_file_open_requested`, `position_reset_requested`, `pet_diagnostics_requested`, `pet_reset_requested`, `memory_manager_requested`, `behavior_history_requested`, `assistant_action_history_requested`, `assistant_permissions_refresh_requested`, `assistant_directory_approval_requested`, `assistant_directory_remove_requested`, `assistant_application_grant_requested`, `assistant_application_revoke_requested`, `assistant_application_close_grant_requested`, `assistant_application_close_revoke_requested`, `spotify_playback_grant_requested`, `spotify_playback_revoke_requested`, `spotify_session_changed`, `gmail_session_changed`, `discord_session_changed`, `integration_refresh_requested`, `integration_test_notification_requested`, `integration_local_data_clear_requested`, `notification_center_requested`, `assistant_permissions_reset_requested`, `voice_health_check_requested`, `voice_microphone_test_requested`, `voice_output_test_requested`, `hosted_live_privacy_acknowledged`.

**Presentation update methods:** `update_config`, `mark_save_result`, `closeEvent`, `set_voice_health`, `set_voice_diagnostic_status`, `set_voice_test_active`, `set_pet_diagnostics`, `set_pet_system_diagnostics`, `set_pet_maintenance_status`, `set_pet_maintenance_busy`, `set_microphone_activity`, `set_voice_engine_status`, `show_weather`, `update_schedules`, `open_page`, `update_music_files`, `update_assistant_permissions`, `set_assistant_permission_status`, `cancel_spotify_authorization`, `set_integration_health`, `set_provider_health_summary`, `set_integration_last_event`, `cancel_gmail_authorization`, `cancel_ai_discovery`.

**Static controls:** `Add directory`, `Apply selected permissions`, `Assistant actions`, `Behavior history`, `Browse`, `Check Gemini Live setup`, `Check now`, `Check setup`, `Clear key`, `Clear local history`, `Connect Gmail`, `Connect Spotify`, `Connect and find models`, `Disable close`, `Disable launch`, `Disable playback`, `Disconnect`, `Enable close`, `Enable launch`, `Enable playback`, `Memories`, `Open data`, `Open logs`, `Open notifications`, `Reconnect`, `Refresh`, `Refresh diagnostics`, `Remove selected`, `Reset all assistant permissions`, `Reset pet progress`, `Reset position`, `Review cloud-audio notice`, `Save Changes`, `Save token and connect`, `Test microphone`, `Test notification`, `Test voice`.

## ShopWindow

`project_akiha/ui/shop_window.py`

**Existing route signals:** `refresh_requested`, `purchase_requested`, `appearance_select_requested`.

**Presentation update methods:** `current_query`, `update_result`, `update_snapshot`, `set_busy`, `set_notice`.

**Static controls:** `Purchase`, `Use appearance`.

## AkihaTrayIcon

`project_akiha/ui/tray.py`

**Existing route signals:** `behavior_history_requested`, `notification_center_requested`, `pet_care_requested`, `pet_status_requested`, `shop_requested`.

**Presentation update methods:** `show_companion_message`, `set_presence_text`.

**Static controls:** `Behavior history`, `Care`, `Chat`, `Hide`, `Notifications`, `Quit`, `Settings`, `Shop & appearance`, `Show`, `Status`.

## UserExportDialog

`project_akiha/ui/user_export_dialog.py`

**Existing route signals:** native dialog accept/reject or controller/EventBus methods.

**Presentation update methods:** `selection`.

## UtilitiesPanel

`project_akiha/ui/utilities_panel.py`

**Existing route signals:** `action_requested`, `export_requested`.

**Presentation update methods:** `set_config`, `config`, `show_weather`, `update_schedules`.

**Static controls:** `Cancel selected schedule now`, `Create one-shot reminder now`, `Create timer now`, `Select conversations / memories to export?`, `Snooze selected reminder now`.

## Native platform handoffs

File/directory/export destination pickers, permission and destructive confirmations, privacy consent, browser OAuth handoff and menu dispatch remain native. Provider/OAuth workers remain existing workers; managers emit requests instead of gaining repository/provider/executor authority. The export dialog now receives a selected local snapshot from composition instead of querying its service. Sprite context requests still publish the same EventBus events.

Spotify/Gmail Connect retain their existing explicit save-before-authorization semantics. Connection tests use current draft connection fields and existing credential handling. Permission revocation, file registration/removal, schedule operations and export selection remain immediate local operations, independent of the general configuration Save button.
