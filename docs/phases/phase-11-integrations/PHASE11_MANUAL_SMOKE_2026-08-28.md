# Phase 11 Manual Smoke Checklist

**Candidate:** `dist/pyinstaller-phase11/Akiha/Akiha.exe`

**Artifact note:** This candidate predates the final real-account Discord and
Gmail corrections. It remains the validated Phase 11 packaging baseline, but the
next consolidated candidate must include those accepted source changes before it
is treated as the current distributable build.

**Automated status:** Passed on 2026-08-28. The candidate passed static privacy
validation, Windows GUI-subsystem validation, migration `0013`, and fresh- and
existing-data startup smoke. Real account checks below require owner-controlled
credentials and are intentionally not automated.

**Owner acceptance:** Passed on 2026-08-28. The owner accepted a real Discord
Bot Gateway connection and notification path, then completed real Gmail Desktop
OAuth, synchronization, and delivery of one new test-email notification. Phase
11 is formally closed. Unchecked items below are retained as optional extended
manual hardening checks; corresponding failure, deduplication, suppression,
credential-removal, and shutdown paths have deterministic automated coverage.

## Gmail

- [x] Create or select a Google OAuth **Desktop app** client and retain its
  generated Client ID and Client Secret.
- [x] Add the owner account as an OAuth test user when the consent screen is in
  testing mode.
- [x] In Akiha Settings > Integrations, enter the Client ID and Client Secret,
  keep `http://127.0.0.1:43822/callback`, enable Gmail, and select Connect.
- [x] Confirm the consent screen requests only Gmail metadata access.
- [x] Confirm the first synchronization creates a baseline without announcing
  old mail.
- [x] Send one test email and confirm one bounded notification appears.
- [ ] Restart Akiha and confirm the same message is not announced again.
- [ ] Confirm classification wording uses uncertainty for recruiter/interview
  candidates.
- [ ] Disable the relevant event toggle and confirm it suppresses delivery.
- [ ] Disconnect and confirm the local encrypted refresh token and OAuth client
  secret are removed.

## Discord

- [x] Create a Discord application and bot in the Developer Portal; do not use
  a normal user token.
- [x] Invite the bot only to an owner-controlled test server and grant only the
  channel access needed for the test.
- [x] In Akiha Settings > Integrations, paste the bot token into the masked
  credential field, enter the owner's numeric Discord user ID, optionally add
  an authorized channel ID, and Connect.
- [x] Direct-message the bot and confirm the Gateway event is received.
- [x] Mention the bot in an authorized server channel and confirm a desktop
  notification appears.
- [ ] Confirm a DM to the bot produces an English desktop notification and a
  short Japanese voice notice.
- [ ] Ask another user to mention the configured owner account and confirm
  Akiha reports the owner mention.
- [ ] Ask another user to reply to an owner message and confirm Akiha reports
  the structured reply.
- [ ] Send several unique mentions more than one second apart and confirm they
  are delivered; repeat one exact event and confirm it remains deduplicated.
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

Phase 11 closed after the owner-controlled provider checks recorded above. The
remaining unchecked checks are useful release-hardening exercises but do not
represent missing Phase 11 implementation.
