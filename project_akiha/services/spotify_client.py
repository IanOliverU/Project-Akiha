"""Bounded Spotify catalog and personal-library Web API client."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_akiha.config import SpotifyConfig
from project_akiha.services.spotify_session import SpotifySession

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
_SEARCH_LIMIT_MAX = 10
_PAGE_LIMIT_MAX = 50
_LIBRARY_RESULT_MAX = 500
_QUERY_LENGTH_MAX = 256
_SEARCH_RESPONSE_KEYS = {
    "album": "albums",
    "artist": "artists",
    "playlist": "playlists",
    "track": "tracks",
}

JSONPayload = dict[str, Any]
SpotifyTransport = Callable[[str, Mapping[str, str], float], JSONPayload]


class SpotifyAPIError(RuntimeError):
    """Privacy-safe Spotify Web API failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SpotifyItemKind(StrEnum):
    """Supported Spotify item categories for the first music integration."""

    TRACK = "track"
    ARTIST = "artist"
    ALBUM = "album"
    PLAYLIST = "playlist"


@dataclass(frozen=True, slots=True)
class SpotifyDevice:
    """Minimal, short-lived metadata for one controllable Spotify device."""

    device_id: str
    name: str
    device_type: str
    is_active: bool
    is_restricted: bool
    volume_percent: int | None = None
    supports_volume: bool = False

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise ValueError("Spotify device ID cannot be empty.")
        if not self.name.strip():
            raise ValueError("Spotify device name cannot be empty.")
        if not self.device_type.strip():
            raise ValueError("Spotify device type cannot be empty.")
        if self.volume_percent is not None and not 0 <= self.volume_percent <= 100:
            raise ValueError("Spotify device volume must be between 0 and 100.")


@dataclass(frozen=True, slots=True)
class SpotifyCatalogItem:
    """Minimal Spotify metadata retained for local ranking and presentation."""

    kind: SpotifyItemKind
    spotify_id: str
    uri: str
    name: str
    artist_names: tuple[str, ...] = ()
    album_name: str = ""
    owner_name: str = ""
    duration_ms: int | None = None
    is_playable: bool = True

    @property
    def display_label(self) -> str:
        """Return a concise label without requiring provider-owned artwork."""
        if self.artist_names:
            return f"{self.name} - {', '.join(self.artist_names)}"
        if self.owner_name:
            return f"{self.name} - {self.owner_name}"
        return self.name


@dataclass(frozen=True, slots=True)
class SpotifySearchResult:
    """Typed, bounded catalog matches in provider response order."""

    query: str
    items: tuple[SpotifyCatalogItem, ...]


class SpotifyClient:
    """Query Spotify without exposing tokens, responses, or library data to AI."""

    def __init__(
        self,
        config: SpotifyConfig,
        session: SpotifySession,
        *,
        transport: SpotifyTransport | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._transport = transport or _get_json

    def apply_config(self, config: SpotifyConfig) -> None:
        """Apply public request settings to future Spotify calls."""
        self._config = config
        self._session.apply_config(config)

    def search(
        self,
        query: str,
        *,
        kinds: Iterable[SpotifyItemKind | str] = (SpotifyItemKind.TRACK,),
        limit_per_kind: int = 5,
    ) -> SpotifySearchResult:
        """Search selected catalog kinds with Spotify's current per-kind bound."""
        normalized_query = _validate_query(query)
        normalized_kinds = _normalize_kinds(kinds)
        if not 1 <= limit_per_kind <= _SEARCH_LIMIT_MAX:
            raise ValueError(
                f"limit_per_kind must be between 1 and {_SEARCH_LIMIT_MAX}."
            )
        payload = self._request_json(
            "/search",
            {
                "q": normalized_query,
                "type": ",".join(kind.value for kind in normalized_kinds),
                "limit": str(limit_per_kind),
                "offset": "0",
            },
        )
        items: list[SpotifyCatalogItem] = []
        for kind in normalized_kinds:
            page = payload.get(_SEARCH_RESPONSE_KEYS[kind.value])
            items.extend(_parse_page_items(page, kind))
        return SpotifySearchResult(
            query=normalized_query,
            items=_deduplicate_items(items),
        )

    def get_saved_tracks(
        self, *, max_items: int = 200
    ) -> tuple[SpotifyCatalogItem, ...]:
        """Return a bounded portion of Liked Songs using local offset pagination."""
        return self._get_offset_items(
            "/me/tracks",
            kind=SpotifyItemKind.TRACK,
            max_items=max_items,
            unwrap_key="track",
        )

    def get_playlists(self, *, max_items: int = 200) -> tuple[SpotifyCatalogItem, ...]:
        """Return a bounded portion of the current user's playlists."""
        return self._get_offset_items(
            "/me/playlists",
            kind=SpotifyItemKind.PLAYLIST,
            max_items=max_items,
        )

    def get_top_items(
        self,
        kind: SpotifyItemKind | str,
        *,
        time_range: str = "medium_term",
        limit: int = 20,
    ) -> tuple[SpotifyCatalogItem, ...]:
        """Return top tracks or artists for one of Spotify's fixed time ranges."""
        normalized_kind = SpotifyItemKind(str(kind))
        if normalized_kind not in {SpotifyItemKind.TRACK, SpotifyItemKind.ARTIST}:
            raise ValueError("Spotify top items support only tracks or artists.")
        if time_range not in {"short_term", "medium_term", "long_term"}:
            raise ValueError("Unsupported Spotify top-item time range.")
        _validate_page_limit(limit)
        payload = self._request_json(
            f"/me/top/{normalized_kind.value}s",
            {
                "time_range": time_range,
                "limit": str(limit),
                "offset": "0",
            },
        )
        return _parse_page_items(payload, normalized_kind)

    def get_recent_tracks(self, *, limit: int = 20) -> tuple[SpotifyCatalogItem, ...]:
        """Return a bounded recent-track snapshot without retaining timestamps."""
        _validate_page_limit(limit)
        payload = self._request_json(
            "/me/player/recently-played",
            {"limit": str(limit)},
        )
        return _parse_page_items(
            payload,
            SpotifyItemKind.TRACK,
            unwrap_key="track",
        )

    def get_available_devices(self) -> tuple[SpotifyDevice, ...]:
        """Return a fresh minimal snapshot of usable Spotify device metadata."""
        payload = self._request_json("/me/player/devices", {})
        raw_devices = payload.get("devices")
        if not isinstance(raw_devices, list):
            raise SpotifyAPIError("Spotify returned an invalid device collection.")
        devices: list[SpotifyDevice] = []
        for raw_device in raw_devices:
            device = _parse_device(raw_device)
            if device is not None:
                devices.append(device)
        return tuple(devices)

    def _get_offset_items(
        self,
        path: str,
        *,
        kind: SpotifyItemKind,
        max_items: int,
        unwrap_key: str | None = None,
    ) -> tuple[SpotifyCatalogItem, ...]:
        _validate_max_items(max_items)
        items: list[SpotifyCatalogItem] = []
        offset = 0
        page_count = 0
        max_pages = ceil(max_items / _PAGE_LIMIT_MAX) + 1
        while len(items) < max_items and page_count < max_pages:
            page_limit = min(_PAGE_LIMIT_MAX, max_items - len(items))
            payload = self._request_json(
                path,
                {"limit": str(page_limit), "offset": str(offset)},
            )
            raw_items = _require_item_list(payload)
            items.extend(_parse_raw_items(raw_items, kind, unwrap_key=unwrap_key))
            returned = len(raw_items)
            page_count += 1
            if payload.get("next") is None:
                break
            offset += returned
            if returned == 0:
                break
        return _deduplicate_items(items)[:max_items]

    def _request_json(self, path: str, query: Mapping[str, str]) -> JSONPayload:
        if not path.startswith("/") or "://" in path:
            raise ValueError(
                "Spotify API paths must be relative to the fixed API host."
            )
        encoded_query = urlencode(dict(query))
        url = f"{SPOTIFY_API_BASE_URL}{path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        timeout = min(max(float(self._config.request_timeout_seconds), 1.0), 60.0)
        for attempt in range(2):
            access_token = self._session.get_access_token()
            try:
                return self._transport(
                    url,
                    {
                        "Accept": "application/json",
                        "Authorization": f"Bearer {access_token}",
                    },
                    timeout,
                )
            except SpotifyAPIError as error:
                if error.status_code != 401 or attempt > 0:
                    raise
                self._session.clear_access_token()
        raise SpotifyAPIError("Spotify authorization could not be refreshed.")


def _get_json(url: str, headers: Mapping[str, str], timeout: float) -> JSONPayload:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise _http_error(error.code) from error
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpotifyAPIError("Spotify could not be reached.") from error
    if not isinstance(payload, dict):
        raise SpotifyAPIError("Spotify returned an invalid response.")
    return payload


def _http_error(status_code: int) -> SpotifyAPIError:
    if status_code == 401:
        detail = "Spotify authorization expired or was revoked."
    elif status_code == 403:
        detail = "Spotify denied this request. Check account access and permissions."
    elif status_code == 404:
        detail = "The requested Spotify resource is unavailable."
    elif status_code == 429:
        detail = "Spotify temporarily rate-limited requests."
    else:
        detail = f"Spotify returned HTTP {status_code}."
    return SpotifyAPIError(detail, status_code=status_code)


def _validate_query(query: str) -> str:
    normalized = " ".join(query.split())
    if not normalized:
        raise ValueError("Spotify search query cannot be empty.")
    if len(normalized) > _QUERY_LENGTH_MAX:
        raise ValueError(
            f"Spotify search query cannot exceed {_QUERY_LENGTH_MAX} characters."
        )
    return normalized


def _normalize_kinds(
    kinds: Iterable[SpotifyItemKind | str],
) -> tuple[SpotifyItemKind, ...]:
    normalized: list[SpotifyItemKind] = []
    for kind in kinds:
        parsed = SpotifyItemKind(str(kind))
        if parsed not in normalized:
            normalized.append(parsed)
    if not normalized:
        raise ValueError("At least one Spotify search kind is required.")
    return tuple(normalized)


def _validate_page_limit(limit: int) -> None:
    if not 1 <= limit <= _PAGE_LIMIT_MAX:
        raise ValueError(f"limit must be between 1 and {_PAGE_LIMIT_MAX}.")


def _validate_max_items(max_items: int) -> None:
    if not 1 <= max_items <= _LIBRARY_RESULT_MAX:
        raise ValueError(f"max_items must be between 1 and {_LIBRARY_RESULT_MAX}.")


def _parse_page_items(
    page: object,
    kind: SpotifyItemKind,
    *,
    unwrap_key: str | None = None,
) -> tuple[SpotifyCatalogItem, ...]:
    return _parse_raw_items(_require_item_list(page), kind, unwrap_key=unwrap_key)


def _require_item_list(page: object) -> list[object]:
    if not isinstance(page, dict) or not isinstance(page.get("items"), list):
        raise SpotifyAPIError("Spotify returned an invalid item collection.")
    return page["items"]


def _parse_raw_items(
    raw_items: Iterable[object],
    kind: SpotifyItemKind,
    *,
    unwrap_key: str | None = None,
) -> tuple[SpotifyCatalogItem, ...]:
    parsed: list[SpotifyCatalogItem] = []
    for raw_item in raw_items:
        candidate = raw_item
        if unwrap_key is not None:
            if not isinstance(raw_item, dict):
                continue
            candidate = raw_item.get(unwrap_key)
        item = _parse_item(candidate, kind)
        if item is not None:
            parsed.append(item)
    return tuple(parsed)


def _parse_item(raw_item: object, kind: SpotifyItemKind) -> SpotifyCatalogItem | None:
    if not isinstance(raw_item, dict):
        return None
    spotify_id = _nonempty_string(raw_item.get("id"))
    uri = _nonempty_string(raw_item.get("uri"))
    name = _nonempty_string(raw_item.get("name"))
    if spotify_id is None or uri is None or name is None:
        return None
    if raw_item.get("type") not in {None, kind.value}:
        return None

    artist_names = _artist_names(raw_item.get("artists"))
    album_name = ""
    owner_name = ""
    if kind == SpotifyItemKind.TRACK:
        album = raw_item.get("album")
        if isinstance(album, dict):
            album_name = _nonempty_string(album.get("name")) or ""
    elif kind == SpotifyItemKind.PLAYLIST:
        owner = raw_item.get("owner")
        if isinstance(owner, dict):
            owner_name = (
                _nonempty_string(owner.get("display_name"))
                or _nonempty_string(owner.get("id"))
                or ""
            )

    duration = raw_item.get("duration_ms")
    duration_ms = duration if isinstance(duration, int) and duration >= 0 else None
    is_playable = raw_item.get("is_playable", True)
    return SpotifyCatalogItem(
        kind=kind,
        spotify_id=spotify_id,
        uri=uri,
        name=name,
        artist_names=artist_names,
        album_name=album_name,
        owner_name=owner_name,
        duration_ms=duration_ms,
        is_playable=is_playable if isinstance(is_playable, bool) else True,
    )


def _parse_device(raw_device: object) -> SpotifyDevice | None:
    if not isinstance(raw_device, dict):
        return None
    device_id = _nonempty_string(raw_device.get("id"))
    name = _nonempty_string(raw_device.get("name"))
    device_type = _nonempty_string(raw_device.get("type"))
    if device_id is None or name is None or device_type is None:
        return None

    volume = raw_device.get("volume_percent")
    volume_percent = (
        volume
        if isinstance(volume, int)
        and not isinstance(volume, bool)
        and 0 <= volume <= 100
        else None
    )
    supports_volume = raw_device.get("supports_volume", False)
    is_active = raw_device.get("is_active", False)
    is_restricted = raw_device.get("is_restricted", False)
    return SpotifyDevice(
        device_id=device_id,
        name=name,
        device_type=device_type.casefold(),
        is_active=is_active if isinstance(is_active, bool) else False,
        is_restricted=is_restricted if isinstance(is_restricted, bool) else True,
        volume_percent=volume_percent,
        supports_volume=(
            supports_volume if isinstance(supports_volume, bool) else False
        ),
    )


def _artist_names(raw_artists: object) -> tuple[str, ...]:
    if not isinstance(raw_artists, list):
        return ()
    return tuple(
        name
        for artist in raw_artists
        if isinstance(artist, dict)
        and (name := _nonempty_string(artist.get("name"))) is not None
    )


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _deduplicate_items(
    items: Iterable[SpotifyCatalogItem],
) -> tuple[SpotifyCatalogItem, ...]:
    unique: list[SpotifyCatalogItem] = []
    seen_uris: set[str] = set()
    for item in items:
        if item.uri in seen_uris:
            continue
        seen_uris.add(item.uri)
        unique.append(item)
    return tuple(unique)
