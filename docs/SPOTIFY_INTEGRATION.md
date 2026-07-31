# Spotify Integration

**Status:** In progress - authentication, lookup, and device resolution implemented

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
- [ ] Typed playback action contracts and executors.
- [ ] Local preference ranking and ambiguity UI.
- [ ] Voice/chat intent integration and end-to-end tests.
- [ ] Packaged build and manual Spotify smoke test.
