# Spotify Integration

**Status:** In progress - generic typed and spoken playback controls implemented

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
music`, `resume Spotify playback`, `next track`, and `previous song`, plus the
explicit `/spotify-*` command forms. Speech punctuation between a control and
its target is accepted, along with a small tested alias set for observed
`pause`/`Spotify` transcription errors. Track, album, playlist, and favorites
selection remain separate local resolution steps.

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
played with the same numbered artist follow-up.

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
  pause, resume, next, and previous action contracts and executors.
- [x] Deterministic typed/voice parsing for generic playback controls without
  sending the command through an AI provider.
- [x] Local artist search, guarded artist-context playback, and bounded
  ambiguity follow-ups for typed and voice requests.
- [x] Standalone artist search and bounded chat result presentation.
- [ ] Local preference ranking and ambiguity UI.
- [ ] Track, artist, album, playlist, and favorites voice/chat resolution with
  end-to-end tests.
- [ ] Packaged build and manual Spotify smoke test.
