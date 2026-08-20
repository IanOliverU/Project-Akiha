# Spotify Integration

**Status:** Source implementation complete - packaged verification pending

**Automated baseline:** 927 tests passed, 3 skipped. Spotify-focused service
coverage passed 120 tests. Ruff, Black, compilation, import, and diff checks
also passed.

**Independent release gate:** Spotify no longer waits for the Voice Intent and
Live Conversation architecture. The current Phase 8 package predates Spotify,
so one standalone rebuild and packaged Spotify smoke pass remain required.

Approved Post-Phase 8 architecture: `docs/roadmap/VOICE_INTELLIGENCE_V0_V8.md`

## Purpose

Project Akiha can optionally connect to the user's Spotify Premium account for
permission-gated music search, library discovery, and playback control. This is
an assistant-action extension, not direct AI access to Spotify.

## Fixed Decisions

- Authorization Code with PKCE; no Client Secret.
- Fixed callback: `http://127.0.0.1:43821/callback`.
- Spotify Premium is required for Web API playback control.
- Akiha launches Spotify when playback needs an available desktop device.
- Device IDs are fetched immediately before use and are never persisted.
- Current-playback queries retain only the item title, bounded creator names,
  album/show name, playing/paused state, and bounded progress for that request.
  Device metadata, Spotify IDs, and URIs are discarded before presentation.
- An active unrestricted device wins; otherwise Akiha selects one unambiguous
  computer or sole usable device and refuses to guess between peers.
- Ambiguous songs, albums, artists, or playlists require a user choice.
- Favorites combine Liked Songs, private playlists, top items, and recent
  listening when the corresponding data is available.
- Access tokens remain in memory. The refresh token is encrypted with Windows
  DPAPI for the current Windows user.

## Scopes

```text
playlist-read-private
user-library-read
user-modify-playback-state
user-read-playback-state
user-read-recently-played
user-top-read
```

No write-library or playlist-mutation scope is requested in the first version.

## Architecture

```text
Settings -> PKCE request -> system browser -> Spotify authorization
         -> 127.0.0.1 callback -> state validation -> token exchange
         -> DPAPI encrypted refresh token

typed/voice request -> constrained intent proposal
                    -> local Spotify resolver and ranking
                    -> ambiguity confirmation when needed
                    -> typed playback action
                    -> active-device selection
                    -> Spotify Web API
```

Generic playback commands use the deterministic local parser before any AI
provider. Supported typed or spoken forms include `play Spotify`, `pause the
music`, `resume Spotify playback`, `next track`, `previous song`, `enable
shuffle`, and `disable shuffle`, plus the explicit `/spotify-*` command forms.
Conversational variants are also accepted, including `I want to listen to
music`, `skip this song`, `I don't like this one`, `go back`, `continue
playing`, `turn the music down`, and `make the music louder`. Relative volume
defaults to a 10% step when no percentage is stated. Pronoun forms such as
`turn it up`, `make it quieter`, and `it's too loud` resolve only while recent
Spotify activity remains in ephemeral context. Shuffle is always assigned an
explicit boolean state through the fixed `spotify.shuffle` action rather than
exposed as an ambiguous toggle. Speech
commands also support `repeat this song`, `repeat this album`, and `turn repeat
off`. Repeat is restricted to Spotify's fixed `track`, `context`, and `off`
modes; the ambiguous phrase `enable repeat` is intentionally not interpreted.
Explicit Spotify volume commands accept only percentages from 0 through 100,
including spoken forms such as `set Spotify volume to seventy five percent`.
The selected device must report remote-volume support; generic system-volume
phrases are not intercepted. Absolute seeking accepts bounded clock positions
and spoken durations through commands such as `seek Spotify to 1 minute 30
seconds`, `go to 2:15 on Spotify`, and `restart current Spotify track`.
Positions are converted to milliseconds only after validation; relative seek
commands remain out of scope. Current playback retrieval is a separate
read-only action and does not infer seek deltas.
Speech punctuation between a control and its target is accepted, along with a
small tested alias set for observed `pause`/`Spotify` transcription errors.
Artist, track, album, playlist, and favorites selection use separate local
resolution steps.

Explicit questions such as `What song is currently playing?`, `What's playing
on Spotify?`, `Identify the current track`, and `/spotify-current` use the
typed `spotify.current_playback` action. The local Spotify client calls the
fixed current-item endpoint and returns only bounded display metadata. In a
provider-native tool session, Akiha receives a sanitized result that labels
catalog values as untrusted data rather than instructions. The provider never
receives device names or IDs, Spotify item IDs or URIs, OAuth data, or the raw
API response.

Successful playback also creates a five-minute, memory-only context containing
only the last Spotify action and coarse `playing` / `paused` state. This lets
the contextual resolver recover strong speech-recognition variants such as
`Paue MIZIK` or `Continua la música` without changing the displayed transcript
or stored conversation. Weak or competing interpretations ask a fixed local
clarification instead of executing. When optional AI-assisted actions are
enabled, the selected hosted or local model may receive the current request
and those coarse labels, but never library data, device IDs, Spotify URIs, or
conversation history; its typed proposal still uses the existing permission
and audit path.

Artist-catalog playback is resolved locally through Spotify search and the
fixed playback-context endpoint. Explicit forms include `play songs by
Megurine Luka`, `play Megurine Luka's catalog on Spotify`, and
`/spotify-artist Megurine Luka`. One exact or clearly dominant artist match is
played immediately. Ambiguous results are bounded to five local choices and
require an explicit follow-up such as `play artist result 1`; Akiha never asks
an AI provider to choose between Spotify artists.

Standalone artist discovery uses the same bounded local result path without
starting playback. Supported forms include `search Spotify artists for
Megurine Luka`, `find artist Megurine Luka on Spotify`, and
`/spotify-search-artists Megurine Luka`. Results are shown in chat and may be
played or opened with explicit numbered artist follow-ups.

Artist-page opening resolves the artist locally and prefers the installed
Spotify desktop client through the fixed `spotify:artist:<validated-id>`
protocol. If Windows cannot launch that protocol, Akiha falls back to the fixed
official `https://open.spotify.com/artist/<validated-id>` page. Supported forms
include `open artist ADO on Spotify`, `go to ADO's Spotify page`, and
`/spotify-open-artist ADO`. Ambiguous direct-open requests retain their intent
and accept only an `open artist result 1` follow-up; they never start playback.

Specific-track playback uses bounded local Spotify search and starts only one
validated `spotify:track:<id>` URI. Explicit forms include `play Spotify track
Usseewa by ADO`, `play Usseewa by ADO on Spotify`, and `/spotify-track Usseewa
| ADO`. Conversational play and listen requests such as `Play Kagakushu`,
`Can you play Hurtful & Painful?`, and `I want to listen to Somniomancer` also
route to Spotify track resolution. Standalone forms such as `search Spotify
tracks for Usseewa by ADO` or `Look for Kagakushu` show up to five playable
results in chat. Duplicate releases or uncertain matches require
`play track result 1`; no AI provider chooses the track.
If a strict title-and-artist search returns nothing, Akiha performs one bounded
relaxed catalog search before local scoring. A transient missing-device response
causes one fresh device lookup and one retry, never an unbounded loop.
Local-file playback remains available through the approved-directory media
workflow when the optional tool gateway proposes `play_media`, or when the user
asks for local music explicitly. Ordinary conversational `play` / `listen to`
requests prefer Spotify.

Album discovery, desktop-first opening, and playback use validated
`spotify:album:<id>` URIs. Supported forms include `search Spotify albums for
Kyougen by ADO`, `open album Kyougen by ADO on Spotify`, `play Spotify album
Kyougen by ADO`, and the corresponding `/spotify-search-albums`,
`/spotify-open-album`, and `/spotify-album` forms. Ambiguous editions are shown
as at most five local choices and accept only explicit `play album result 1` or
`open album result 1` follow-ups allowed by the originating request.
Numbered Spotify results are ephemeral interaction state rather than durable
companion memory. They refer only to the latest visible list, are cleared after
successful selection or chat reset, and accept only indexes inside that list.
Stale or out-of-range references receive a correction and never become a new
catalog search query. After a successful validated album action, Akiha retains
only that album's name, artist, and Spotify URI as short-lived interaction
context. Explicit `play that album` and `open the same album` follow-ups reuse
that exact URI without another catalog search or AI interpretation. New chat,
Clear chat, and presentation of a new album result list discard this context;
it is never written to durable companion memory.

Playlist discovery combines a bounded local snapshot of the authenticated
user's playlists with Spotify catalog search results. Personal matches are
ranked first, duplicate URIs are removed, and at most five validated
`spotify:playlist:<id>` choices are retained. Supported forms include `search
Spotify playlists for Night Drive`, `play my playlist called Night Drive on
Spotify`, `/spotify-search-playlists Night Drive`, and `/spotify-playlist Night
Drive`. Ambiguous names require `play playlist result 1`; successful playback
also permits the short-lived `play that playlist` follow-up. Playlist metadata
never becomes durable companion memory or hosted-provider prompt context.

Liked and favorite-music playback use the typed `spotify.play_favorites`
action. `Play my liked songs` builds a queue from at most 50 validated saved
track URIs. `Play my favorite music`, `Play something I like on Spotify`, and
`/spotify-favorites` build a bounded local mix from Liked Songs, short-,
medium-, and long-term top tracks, and recent listening. Duplicate or
unplayable tracks are removed before playback. The queue uses the same fresh
device, permission, cancellation, audit, and one-retry boundaries as other
Spotify playback actions.

Spotify preference metadata is cached in memory for ten minutes and discarded
when the Spotify session changes or Akiha exits. Named track, artist, album,
and playlist searches may use this profile as a small tie-break boost when
ordering otherwise close results. Visible favored results are labeled `local
favorite`. Preference scoring never replaces textual relevance checks, never
turns an ambiguous result into an automatic selection, and never allows an
unvalidated Spotify URI to reach playback. If optional top or recent endpoints
are unavailable, ranking degrades to the account data that remains available.

The AI provider receives only text the user explicitly supplied for constrained
intent interpretation. Akiha does not append Spotify library contents,
listening history, search results, device identifiers, OAuth data, or local
preference exports to hosted-provider prompts.

## Historical Personal Preference Export

The private `assets/animations/akiha/Spotify.txt` ranking export was removed
after the Spotify API preference path was completed. Its historical path
remains denylisted as defense in depth:

- ignored by Git
- explicitly excluded by the Nuitka build
- rejected by packaged-artifact validation if present
- absent from the current workspace

There is no planned runtime import from that path. Tests use synthetic track
and artist names rather than the user's data.

## Implementation Checklist

- [x] Typed Spotify config with strict Client ID and callback validation.
- [x] Settings tab for enablement, Client ID, connect, disconnect, and status.
- [x] Browser PKCE flow with a bounded local callback listener.
- [x] State validation and privacy-safe authorization errors.
- [x] Separate DPAPI namespace for the refresh token.
- [x] Access token excluded from persistent storage.
- [x] Personal export excluded from source control and packages.
- [x] Authenticated session and automatic access-token refresh.
- [x] Bounded Spotify catalog/library client for tracks, artists, albums,
  playlists, Liked Songs, top items, and recent tracks.
- [x] Fresh active-device selection with restricted-device refusal and bounded
  desktop-app activation through the existing permission/audit boundary.
- [x] Separate local `spotify.playback` permission and audited typed play,
  pause, resume, next, previous, explicit shuffle-state, and allowlisted repeat
  mode action contracts and executors, plus bounded device-aware volume and
  absolute seek controls.
- [x] Deterministic typed/voice parsing for generic playback controls without
  sending the command through an AI provider.
- [x] Permission-gated current-playback identification with bounded local
  metadata and an explicitly sanitized Gemini/Ollama tool result.
- [x] Local artist search, guarded artist-context playback, and bounded
  ambiguity follow-ups for typed and voice requests.
- [x] Standalone artist search and bounded chat result presentation.
- [x] Safe official artist-page opening with intent-preserving ambiguity
  follow-ups.
- [x] Specific-track search, exact title/artist resolution, bounded ambiguity
  presentation, and one-track playback.
- [x] Album search, local title/artist resolution, bounded result presentation,
  desktop-first opening, and guarded album-context playback.
- [x] Personal-plus-catalog playlist search, local ranking, bounded ambiguity
  presentation, validated playback, and contextual follow-ups.
- [x] Local ephemeral preference ranking and favored-result ambiguity labels.
- [x] Liked Songs and favorites-mix voice/chat playback with bounded queues.

## Closure Decision

The Spotify feature scope is closed at the source and automated-verification
level. New Spotify capabilities should not be added while the voice
architecture is being designed unless a regression or security defect is
found. Deterministic parsing, typed requests, permission checks, local
resolution, and audited execution remain the compatibility boundary for the
next voice system.

The following independent release verification remains open:

- manual Spotify command roundup through the current source voice path
- standalone rebuild containing the complete Spotify implementation
- packaged Spotify authentication, playback, and failure-mode smoke test
- removal of the previous package only after the new candidate is confirmed

This release gate should run independently before implementation of the new
voice architecture. Future voice work retains its own Spotify regression tests.
