# Phase 11 Manual Smoke Checklist

**Candidate:** `dist/pyinstaller-phase11/Akiha/Akiha.exe`

**Automated status:** Passed on 2026-08-28. The candidate passed static privacy
validation, Windows GUI-subsystem validation, migration `0013`, and fresh- and
existing-data startup smoke. Real account checks below require owner-controlled
credentials and are intentionally not automated.

## Gmail

- [ ] Create or select a Google OAuth **Desktop app** client. Do not create or
  enter a client secret.
- [ ] Add the owner account as an OAuth test user when the consent screen is in
  testing mode.
- [ ] In Akiha Settings > Integrations, enter the client ID, keep
  `http://127.0.0.1:43822/callback`, enable Gmail, and select Connect.
- [ ] Confirm the consent screen requests only Gmail metadata access.
- [ ] Confirm the first synchronization creates a baseline without announcing
  old mail.
- [ ] Send one test email and confirm one bounded notification appears.
- [ ] Restart Akiha and confirm the same message is not announced again.
- [ ] Confirm classification wording uses uncertainty for recruiter/interview
  candidates.
- [ ] Disable the relevant event toggle and confirm it suppresses delivery.
- [ ] Disconnect and confirm the local encrypted refresh token is removed.

## Discord

- [ ] Create a Discord application and bot in the Developer Portal; do not use
  a normal user token.
- [ ] Invite the bot only to an owner-controlled test server and grant only the
  channel access needed for the test.
- [ ] In Akiha Settings > Integrations, paste the bot token into the masked
  credential field, optionally add an authorized channel ID, and Connect.
- [ ] Direct-message the bot and confirm one notification appears.
- [ ] Mention the bot in an authorized server channel and confirm one
  notification appears.
- [ ] Confirm an unapproved channel is ignored.
- [ ] Restart Akiha and confirm the same Gateway event is not announced again.
- [ ] Confirm Settings clearly states that personal user DMs, friend lists, and
  friend requests are unsupported.
- [ ] Disconnect and confirm the encrypted bot token is removed.

## Shared Delivery And Shutdown

- [ ] Confirm visual notifications follow global quiet-hours and cooldown
  policy.
- [ ] Confirm voice notifications use the existing GPT-SoVITS path and do not
  interrupt active user speech.
- [ ] Confirm synthetic Test notification uses no real sender or message data.
- [ ] Quit from Akiha's menu and confirm the providers stop without Task
  Manager.
- [ ] Reopen Akiha with both integrations disabled or offline and confirm local
  chat, pet state, voice, memory, and assistant actions remain available.

Phase 11 closes only after these owner-controlled checks are recorded.
