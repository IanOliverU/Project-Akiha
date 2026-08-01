# Spotify Integration

**Status:** In progress - playback, artist, track, and album flows implemented

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
Shuffle is always assigned an explicit boolean state through the fixed
`spotify.shuffle` action rather than exposed as an ambiguous toggle. Speech
punctuation between a control and its target is accepted, along with a small
tested alias set for observed `pause`/`Spotify` transcription errors. Artist,
track, and album selection use separate local resolution steps; playlist and
favorites resolution remain.

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
| ADO`. Standalone forms such as `search Spotify tracks for Usseewa by ADO`
show up to five playable results in chat. Duplicate releases or uncertain
matches require `play track result 1`; no AI provider chooses the track.
If a strict title-and-artist search returns nothing, Akiha performs one bounded
relaxed catalog search before local scoring. A transient missing-device response
causes one fresh device lookup and one retry, never an unbounded loop.
Unqualified local-media requests such as `play Elis by Megurine Luka` remain
available to the approved-directory media workflow unless Spotify is named or
the request explicitly says `Spotify track` or `Spotify song`.

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

The AI provider receives only text the user explicitly supplied for constrained
intent interpretation. Akiha does not append Spotify library contents,
listening history, search results, device identifiers, OAuth data, or local
preference exports to hosted-provider prompts.

## Personal Preference Export

`assets/animations/akiha/Spotify.txt` is a private local export supplied for
ranking experiments. It is not an application asset:

- ignored by Git
- explicitly excluded by the Nuitka build
- rejected by packaged-artifact validation if present
- never logged or sent to an AI or Spotify endpoint by the current code

A later import action will copy parsed rankings into local application data so
the source export can live outside the repository. Tests must use synthetic
track and artist names rather than the user's data.

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
  pause, resume, next, previous, and explicit shuffle-state action contracts
  and executors.
- [x] Deterministic typed/voice parsing for generic playback controls without
  sending the command through an AI provider.
- [x] Local artist search, guarded artist-context playback, and bounded
  ambiguity follow-ups for typed and voice requests.
- [x] Standalone artist search and bounded chat result presentation.
- [x] Safe official artist-page opening with intent-preserving ambiguity
  follow-ups.
- [x] Specific-track search, exact title/artist resolution, bounded ambiguity
  presentation, and one-track playback.
- [x] Album search, local title/artist resolution, bounded result presentation,
  desktop-first opening, and guarded album-context playback.
- [ ] Local preference ranking and ambiguity UI.
- [ ] Track, artist, album, playlist, and favorites voice/chat resolution with
  end-to-end tests.
- [ ] Packaged build and manual Spotify smoke test.
