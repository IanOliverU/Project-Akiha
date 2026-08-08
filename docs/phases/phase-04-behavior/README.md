# Phase 4 Activity, Mood, And Proactive Behavior

Phase 4 makes Akiha aware of app-local user activity and gives her conservative
proactive behavior. The goal is not autonomy yet. The goal is a safe behavior
layer that can observe, decide, deliver, and record small companion moments.

## Completed

- Activity tracker for active, idle, and away states
- App activity controller that publishes user activity changes
- Behavior settings in the Settings window
- Notification policy with enabled flags, quiet hours, cooldowns, and away
  guardrails
- Proactive suggestion engine for idle check-ins
- Scheduled check-in engine and controller
- Delivery service for safe proactive chat and tray notifications
- Qt delivery surface for chat notices and tray messages
- Mood engine with calm, attentive, waiting, resting, checking-in, and sleepy
  states
- Mood controller that reacts to activity and proactive events
- Mood-to-animation mapping for sleep/wake animation requests
- Presence text mapping for chat/tray companion state
- Behavior event model and SQLite behavior history repository
- Behavior history recorder for activity, mood, proactive, scheduled, and
  delivery events
- Integration coverage for the full proactive behavior flow

## Key Modules

- `project_akiha/core/behavior/activity.py`
- `project_akiha/core/behavior/notification_policy.py`
- `project_akiha/core/behavior/proactive.py`
- `project_akiha/core/behavior/schedule.py`
- `project_akiha/core/behavior/delivery.py`
- `project_akiha/core/behavior/mood.py`
- `project_akiha/core/behavior/mood_animation.py`
- `project_akiha/core/behavior/presence.py`
- `project_akiha/app/activity_controller.py`
- `project_akiha/app/proactive_controller.py`
- `project_akiha/app/scheduled_check_in_controller.py`
- `project_akiha/app/proactive_delivery_controller.py`
- `project_akiha/app/mood_controller.py`
- `project_akiha/app/mood_animation_controller.py`

## Not In Phase 4

- Voice input or output
- Cloud provider integrations
- Local assistant command execution
- User permission gates for automation
- Plugin API
- Fully autonomous behavior
- Advanced animation/model backend

## Manual Smoke Test

```powershell
python -m project_akiha.app.main
```

Then check:

- Settings opens and saves behavior options.
- Quiet hours, cooldown, proactive, and scheduled check-in settings save without
  crashing.
- Chat and tray surfaces can receive proactive notices.
- Behavior History opens and shows recorded behavior events after activity or
  proactive events occur.
- Leaving the app open long enough for timers to tick does not crash.

## Verification

```powershell
python -m unittest discover tests
python -m compileall project_akiha tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
```
