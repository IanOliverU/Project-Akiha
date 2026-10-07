"""Real token/client history endpoint and central lease authority regressions."""

from __future__ import annotations

import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.config import SpotifyConfig
from project_akiha.core.actions import ActionRequest
from project_akiha.core.actions.clarification import (
    ActionClarificationReason,
    ActionClarificationSpec,
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.integrations.spotify.auth import SpotifyToken
from project_akiha.integrations.spotify.client import SpotifyAPIError, SpotifyClient
from project_akiha.integrations.spotify.history import (
    HISTORY_SCOPE,
    HistoryStatus,
    fetch_spotify_history,
    history_choices,
)
from project_akiha.integrations.spotify.session import SpotifySession
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.command_envelope import DeterministicCommandEnvelopeParser
from project_akiha.ui.assistant_action_worker import AssistantActionThread
from tests.unit.integrations.spotify.test_session import _SecretStore
from tests.unit.services.test_action_clarification import FakeClock


def play(identifier, *, title=None, playable=True):
    return {
        "track": {
            "id": identifier,
            "uri": "spotify:track:" + identifier,
            "name": title or "Track " + identifier,
            "artists": [{"name": "HISTORY_ARTIST_SENTINEL"}],
            "is_playable": playable,
        }
    }


class SpotifyHistoryTest(unittest.TestCase):
    def setUp(self):
        self.config = SpotifyConfig(enabled=True, client_id="a" * 32)
        self.store = _SecretStore("refresh")
        self.session = SpotifySession(
            self.config,
            self.store,
            token_refresher=lambda *_: SpotifyToken(
                "access", "refresh", 200, (HISTORY_SCOPE,)
            ),
            now=lambda: 100,
        )
        self.calls = []
        self.payload = {"items": [play(str(i)) for i in range(30)]}

        def transport(url, headers, timeout):
            self.calls.append(url)
            return self.payload

        self.client = SpotifyClient(self.config, self.session, transport=transport)
        self.request = ActionRequest(
            "history", "spotify.play_track", "chat", {"service": "spotify"}
        )

    def fetch(self):
        return fetch_spotify_history(self.client, self.session, self.session.generation)

    def test_fixed_history_endpoint_fetches_twenty_and_picker_takes_ten_newest(self):
        result = self.fetch()
        self.assertIs(result.status, HistoryStatus.READY)
        self.assertEqual(
            [t.spotify_id for t in result.tracks], [str(i) for i in range(10)]
        )
        self.assertEqual(len(self.calls), 1)
        url = urlparse(self.calls[0])
        self.assertEqual(url.path, "/v1/me/player/recently-played")
        self.assertEqual(parse_qs(url.query), {"limit": ["20"]})
        self.assertNotIn("search", self.calls[0])

    def test_repeated_track_ids_are_once_and_versions_remain_distinct(self):
        self.payload = {
            "items": [
                play("one", title="Avid"),
                play("one", title="older"),
                play("instrumental", title="Avid - instrumental"),
                play("another", title="Avid"),
            ]
        }
        result = self.fetch()
        self.assertEqual(
            [t.spotify_id for t in result.tracks], ["one", "instrumental", "another"]
        )
        self.assertEqual(result.tracks[0].name, "Avid")

    def test_twenty_repeats_produce_one_choice_without_fetching_older_pages(self):
        self.payload = {"items": [play("one")] * 20 + [play("older")] * 5}
        result = self.fetch()
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(len(self.calls), 1)

    def test_missing_scope_does_not_fetch_or_expand_authorization(self):
        self.session._token_refresher = lambda *_: SpotifyToken(
            "access", "refresh", 200, ()
        )
        result = self.fetch()
        self.assertIs(result.status, HistoryStatus.MISSING_SCOPE)
        self.assertIn("Reconnect", result.message)
        self.assertIn(HISTORY_SCOPE, result.message)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.values[("spotify", "refresh_token")], "refresh")

    def test_empty_history_does_not_fall_back_to_search(self):
        self.payload = {"items": []}
        result = self.fetch()
        self.assertIs(result.status, HistoryStatus.EMPTY)
        self.assertEqual(history_choices(self.request, result).requests, ())
        self.assertEqual(len(self.calls), 1)

    def test_api_failures_and_rate_limits_have_fixed_local_explanations(self):
        for status, expected in [
            (403, HistoryStatus.MISSING_SCOPE),
            (401, HistoryStatus.DISCONNECTED),
            (429, HistoryStatus.RATE_LIMITED),
            (500, HistoryStatus.FAILED),
        ]:
            with self.subTest(status=status):

                def fail(*_, status=status):
                    raise SpotifyAPIError("HISTORY_ERROR_SENTINEL", status_code=status)

                self.client._transport = fail
                result = self.fetch()
                self.assertIs(result.status, expected)
                self.assertNotIn("SENTINEL", result.message + repr(result))

    def test_unexpected_failure_never_echoes_private_exception(self):
        def fail(*_):
            raise RuntimeError("HISTORY_ERROR_SENTINEL")

        self.client._transport = fail
        self.assertIs(self.fetch().status, HistoryStatus.FAILED)

    def test_unavailable_tracks_remain_visible_but_disabled(self):
        self.payload = {"items": [play("one", playable=False), play("two")]}
        targets = history_choices(self.request, self.fetch())
        self.assertEqual(targets.enabled, (False, True))
        self.assertIn("unavailable", targets.labels[0])
        self.assertEqual(
            targets.requests[1].parameters["track_uri"], "spotify:track:two"
        )

    def test_disconnect_during_response_drops_account_history(self):
        def disconnect(*_):
            self.session.disconnect()
            return self.payload

        self.client._transport = disconnect
        self.assertIs(self.fetch().status, HistoryStatus.STALE)

    def test_account_switch_invalidates_captured_generation(self):
        generation = self.session.generation
        self.session.clear_access_token()
        self.store.values[("spotify", "refresh_token")] = "another-account"
        self.assertIs(
            fetch_spotify_history(self.client, self.session, generation).status,
            HistoryStatus.STALE,
        )
        self.assertEqual(self.calls, [])

    def test_disconnected_account_does_not_call_endpoint(self):
        self.session.disconnect()
        self.assertIs(self.fetch().status, HistoryStatus.DISCONNECTED)
        self.assertEqual(self.calls, [])

    def test_private_snapshot_and_choices_repr_exclude_track_names(self):
        self.payload = {"items": [play("one", title="HISTORY_TITLE_SENTINEL")]}
        snapshot = self.fetch()
        targets = history_choices(self.request, snapshot)
        self.assertNotIn("SENTINEL", repr(snapshot) + repr(targets))

    def test_missing_artist_does_not_create_invalid_empty_parameters(self):
        item = play("one")
        item["track"]["artists"] = []
        self.payload = {"items": [item]}
        targets = history_choices(self.request, self.fetch())
        self.assertNotIn("artist_query", targets.requests[0].parameters)
        leases = ActionClarificationService()
        ActionClarificationController(leases).prepare(self.request)
        captured = leases.start_spotify_history(leases.pending.identity, 0)
        self.assertTrue(
            leases.publish_spotify_history(
                captured, targets, account_guard=lambda: True
            )
        )


class SpotifyHistoryLeaseTest(unittest.TestCase):
    fetch = SpotifyHistoryTest.fetch

    def setUp(self):
        SpotifyHistoryTest.setUp(self)
        self.clock = FakeClock()
        self.leases = ActionClarificationService(clock=self.clock)
        self.controller = ActionClarificationController(self.leases)
        self.assertFalse(self.controller.prepare(self.request))
        self.original = self.leases.pending
        self.captured = self.leases.start_spotify_history(
            self.original.identity, self.session.generation
        )
        self.targets = history_choices(self.request, self.fetch())

        def guard():
            return (
                self.session.generation == self.captured.account_generation
                and self.session.is_connected
            )

        self.guard = guard

    def publish(self):
        return self.leases.publish_spotify_history(
            self.captured, self.targets, account_guard=self.guard
        )

    def answer(self, **kwargs):
        p = self.leases.pending
        return ClarificationAnswer(
            p.identity,
            ClarificationAnswerSource.LOCAL_UI,
            choice_id=p.choice_ids[0],
            **kwargs,
        )

    def test_atomic_publication_preserves_owner_request_and_deadline(self):
        self.assertTrue(self.publish())
        p = self.leases.pending
        self.assertEqual(p.request, self.request)
        self.assertEqual(p.identity.owner_epoch, self.original.identity.owner_epoch)
        self.assertEqual(p.identity.deadline, self.original.identity.deadline)
        self.assertEqual(
            p.identity.request_digest, self.original.identity.request_digest
        )
        self.assertEqual(len(set(p.choice_ids)), 10)
        answer = self.answer()
        result = self.controller.resolve(answer)
        self.assertIs(result.outcome, ClarificationOutcome.RESOLVED)
        self.assertEqual(result.request.parameters["track_uri"], "spotify:track:0")
        self.assertTrue(self.leases.owns(result.request, result.identity.owner_epoch))
        self.assertTrue(
            self.leases.is_spotify_history_selection(
                result.request, result.identity.owner_epoch
            )
        )
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )

    def test_search_five_cap_is_unchanged_and_history_ten_is_separate(self):
        self.assertTrue(self.publish())
        self.assertEqual(len(self.leases.pending.choices), 10)
        other = ActionClarificationService()
        with self.assertRaises(ValueError):
            other.begin(
                self.request,
                ActionClarificationSpec(
                    ActionClarificationReason.MULTIPLE_MATCHES, ("track_query",), 10
                ),
                self.targets.requests,
            )
        pending = ActionClarificationController(other).choices(
            self.request, self.targets.requests
        )
        self.assertEqual(len(pending.choices), 5)
        self.assertTrue(pending.spec.truncated)

    def test_supersession_cancellation_revocation_expiration_and_replay_drop_fetch(
        self,
    ):
        for transition in ("supersede", "cancel", "revoke", "expire", "fingerprint"):
            with self.subTest(transition=transition):
                self.setUp()
                if transition == "supersede":
                    self.controller.prepare(
                        ActionRequest("new", "files.open_directory", "chat", {})
                    )
                elif transition == "cancel":
                    self.controller.resolve(
                        ClarificationAnswer(
                            self.original.identity,
                            ClarificationAnswerSource.LOCAL_UI,
                            cancel=True,
                        )
                    )
                elif transition == "revoke":
                    self.leases.invalidate()
                elif transition == "expire":
                    self.clock.seconds = self.original.identity.deadline
                else:
                    self.assertFalse(
                        self.controller.prepare(
                            replace(
                                self.request,
                                parameters={
                                    "service": "spotify",
                                    "track_query": "changed",
                                },
                            )
                        )
                    )
                newest = self.leases.pending
                self.assertFalse(self.publish())
                self.assertEqual(self.leases.pending, newest)
        self.setUp()
        self.assertTrue(self.publish())
        newest = self.leases.pending
        self.assertFalse(self.publish())
        self.assertEqual(self.leases.pending, newest)

    def test_exact_expiry_and_stale_selection_are_closed(self):
        self.assertTrue(self.publish())
        answer = self.answer()
        self.clock.seconds = answer.identity.deadline
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.EXPIRED
        )
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )

    def test_account_disconnect_switch_and_revoked_guard_reject_selection(self):
        for transition in ("disconnect", "switch", "revoke"):
            with self.subTest(transition=transition):
                self.setUp()
                self.assertTrue(self.publish())
                answer = self.answer()
                if transition == "disconnect":
                    self.session.disconnect()
                elif transition == "switch":
                    self.session.clear_access_token()
                else:
                    self.leases.invalidate()
                self.assertIn(
                    self.controller.resolve(answer).outcome,
                    (ClarificationOutcome.INVALID, ClarificationOutcome.STALE),
                )

    def test_provider_indices_free_text_and_unknown_ids_cannot_select_history(self):
        self.assertTrue(self.publish())
        answer = self.answer()
        for forged in (
            replace(answer, source=ClarificationAnswerSource.PROVIDER),
            replace(answer, choice_index=1),
            replace(answer, value="one"),
            replace(answer, choice_id="unknown"),
            replace(answer, open_any=True),
        ):
            self.assertIs(
                self.controller.resolve(forged).outcome, ClarificationOutcome.INVALID
            )

    def test_disabled_history_entry_cannot_execute(self):
        self.targets = replace(self.targets, enabled=(False,) * 10)
        self.assertTrue(self.publish())
        self.assertIs(
            self.controller.resolve(self.answer()).outcome, ClarificationOutcome.INVALID
        )

    def test_switch_to_search_discards_snapshot_and_late_callback(self):
        self.assertTrue(self.leases.spotify_search_mode(self.original.identity))
        identity = self.leases.pending.identity
        self.assertFalse(self.publish())
        self.assertEqual(self.leases.pending.identity, identity)
        result = self.controller.resolve(
            ClarificationAnswer(
                identity,
                ClarificationAnswerSource.LOCAL_UI,
                "Blinding Lights",
                artist_query="The Weeknd",
            )
        )
        self.assertEqual(
            result.request.parameters,
            {
                "service": "spotify",
                "track_query": "Blinding Lights",
                "artist_query": "The Weeknd",
            },
        )

    def test_reentrant_new_action_during_account_guard_wins(self):
        def guard():
            self.controller.prepare(
                ActionRequest("new", "applications.launch", "chat", {})
            )
            return True

        self.assertFalse(
            self.leases.publish_spotify_history(
                self.captured, self.targets, account_guard=guard
            )
        )
        self.assertEqual(self.leases.pending.request.correlation_id, "new")

    def test_expiry_during_account_guard_drops_publication(self):
        def guard():
            self.clock.seconds = self.original.identity.deadline
            return True

        self.assertFalse(
            self.leases.publish_spotify_history(
                self.captured, self.targets, account_guard=guard
            )
        )
        self.assertIsNone(self.leases.pending)

    def test_private_titles_do_not_enter_lease_evidence_or_surviving_repr(self):
        self.assertTrue(self.publish())
        self.assertNotIn(
            "SENTINEL", repr(self.leases.pending) + repr(self.leases.evidence)
        )
        self.controller.resolve(self.answer())
        self.assertNotIn(
            "SENTINEL",
            repr(self.leases._request_digests) + repr(self.leases._spotify_selected),
        )

    def test_specific_requests_and_provider_operations_do_not_fetch_history(self):
        self.leases.invalidate()
        for text in (
            "Play track Blinding Lights by The Weeknd on Spotify",
            "Play album The Dark Side of the Moon on Spotify",
            "Play playlist Chill on Spotify",
            "Play artist Ado on Spotify",
        ):
            # Actual deterministic parser is shared by typed and local voice routes.
            envelope = DeterministicCommandEnvelopeParser().parse(text)
            self.assertIsNotNone(envelope)
            self.assertIsNone(self.controller.incomplete_command(text, "specific"))
        provider = ActionRequest(
            "provider", "spotify.play_track", "provider.native", {"service": "spotify"}
        )
        self.controller.prepare(provider)
        self.assertIsNone(
            self.leases.start_spotify_history(self.leases.pending.identity, 0)
        )

    def test_account_switch_after_selection_invalidates_executor_token(self):
        self.assertTrue(self.publish())
        resolved = self.controller.resolve(self.answer())
        worker = AssistantActionThread(
            None,
            resolved.request,
            ownership_guard=lambda: self.leases.execution_owned(
                resolved.request, resolved.identity.owner_epoch
            ),
        )
        self.assertFalse(worker._cancellation_token.is_cancelled)
        self.session.clear_access_token()
        self.assertTrue(worker._cancellation_token.is_cancelled)

        def unavailable_guard():
            raise OSError("HISTORY_ERROR_SENTINEL")

        failed = AssistantActionThread(
            None, resolved.request, ownership_guard=unavailable_guard
        )
        self.assertTrue(failed._cancellation_token.is_cancelled)

    def test_artist_is_local_bound_and_invalid_values_do_not_execute(self):
        self.leases.spotify_search_mode(self.original.identity)
        identity = self.leases.pending.identity
        for artist in ("x" * 161, "bad\nartist"):
            answer = ClarificationAnswer(
                identity,
                ClarificationAnswerSource.LOCAL_UI,
                "song",
                artist_query=artist,
            )
            self.assertIs(
                self.controller.resolve(answer).outcome, ClarificationOutcome.INVALID
            )
            self.assertEqual(self.leases.pending.identity, identity)
        answer = ClarificationAnswer(
            identity, ClarificationAnswerSource.PROVIDER, "song", artist_query="artist"
        )
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.INVALID
        )
