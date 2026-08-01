"""Tests for ephemeral local Spotify preference ranking."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.services.spotify_client import SpotifyCatalogItem, SpotifyItemKind
from project_akiha.services.spotify_preferences import SpotifyPreferenceRanker


class SpotifyPreferenceRankerTest(unittest.TestCase):
    def test_liked_track_can_break_a_close_provider_order_tie(self) -> None:
        first = _track("first", "First", "Other Artist")
        second = _track("second", "Second", "Other Artist")
        liked = _track("liked", "Favorite", "Favorite Artist")
        client = _PreferenceClient(liked=(liked,))
        ranker = SpotifyPreferenceRanker(client)  # type: ignore[arg-type]

        ranked = asyncio.run(ranker.rank((first, second, liked)))

        self.assertEqual(ranked[0], liked)
        self.assertTrue(ranker.is_preferred_cached(liked))
        self.assertFalse(ranker.is_preferred_cached(first))

    def test_favorite_mix_deduplicates_and_prefers_liked_then_top_tracks(self) -> None:
        liked = _track("liked", "Liked", "Artist One")
        top = _track("top", "Top", "Artist Two")
        client = _PreferenceClient(
            liked=(liked,),
            top={"short_term": (top,), "medium_term": (liked,)},
            recent=(top,),
        )
        ranker = SpotifyPreferenceRanker(client)  # type: ignore[arg-type]

        queue = asyncio.run(ranker.favorite_tracks("mix"))

        self.assertEqual(queue, (liked, top))
        self.assertEqual(
            asyncio.run(ranker.favorite_tracks("liked")),
            (liked,),
        )

    def test_profile_is_cached_and_invalidation_forces_refresh(self) -> None:
        client = _PreferenceClient(liked=(_track("liked", "Liked", "Artist"),))
        ranker = SpotifyPreferenceRanker(client)  # type: ignore[arg-type]

        asyncio.run(ranker.favorite_tracks("mix"))
        asyncio.run(ranker.favorite_tracks("mix"))
        self.assertEqual(client.saved_calls, 1)

        ranker.invalidate()
        asyncio.run(ranker.favorite_tracks("mix"))
        self.assertEqual(client.saved_calls, 2)

    def test_optional_source_failure_does_not_discard_available_liked_songs(
        self,
    ) -> None:
        liked = _track("liked", "Liked", "Artist")
        client = _PreferenceClient(liked=(liked,), fail_top=True)
        ranker = SpotifyPreferenceRanker(client)  # type: ignore[arg-type]

        self.assertEqual(asyncio.run(ranker.favorite_tracks("mix")), (liked,))


class _PreferenceClient:
    def __init__(
        self,
        *,
        liked: tuple[SpotifyCatalogItem, ...] = (),
        top: dict[str, tuple[SpotifyCatalogItem, ...]] | None = None,
        recent: tuple[SpotifyCatalogItem, ...] = (),
        playlists: tuple[SpotifyCatalogItem, ...] = (),
        fail_top: bool = False,
    ) -> None:
        self.liked = liked
        self.top = top or {}
        self.recent = recent
        self.playlists = playlists
        self.fail_top = fail_top
        self.saved_calls = 0

    def get_saved_tracks(self, *, max_items: int) -> tuple[SpotifyCatalogItem, ...]:
        self.saved_calls += 1
        self.assert_bound(max_items, 50)
        return self.liked

    def get_top_items(
        self,
        _kind: SpotifyItemKind,
        *,
        time_range: str,
        limit: int,
    ) -> tuple[SpotifyCatalogItem, ...]:
        self.assert_bound(limit, 20)
        if self.fail_top:
            raise RuntimeError("optional source unavailable")
        return self.top.get(time_range, ())

    def get_recent_tracks(self, *, limit: int) -> tuple[SpotifyCatalogItem, ...]:
        self.assert_bound(limit, 20)
        return self.recent

    def get_playlists(self, *, max_items: int) -> tuple[SpotifyCatalogItem, ...]:
        self.assert_bound(max_items, 100)
        return self.playlists

    @staticmethod
    def assert_bound(actual: int, expected: int) -> None:
        if actual != expected:
            raise AssertionError(f"Expected bound {expected}, got {actual}.")


def _track(
    spotify_id: str,
    name: str,
    artist: str,
) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.TRACK,
        spotify_id=spotify_id,
        uri=f"spotify:track:{spotify_id}",
        name=name,
        artist_names=(artist,),
        album_name=f"{name} Album",
    )


if __name__ == "__main__":
    unittest.main()
