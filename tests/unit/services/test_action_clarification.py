"""Phase 13B lifecycle, authority, concurrency, and privacy regressions."""

from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.core.actions import ActionRequest, build_default_action_registry
from project_akiha.core.actions.clarification import (
    ActionClarificationReason,
    ActionClarificationSpec,
    ActionReadinessStatus,
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
    analyze_action_readiness,
    approved_directory_aliases,
)
from project_akiha.services.action_clarification import ActionClarificationService


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 10.0

    def monotonic_seconds(self) -> float:
        return self.seconds


class ActionClarificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.leases = ActionClarificationService(clock=self.clock)
        self.controller = ActionClarificationController(self.leases)
        self.request = ActionRequest("request-1", "applications.launch", "chat", {})

    def begin(self, *, cloud: bool = False):
        self.assertFalse(self.controller.prepare(self.request, cloud_origin=cloud))
        pending = self.leases.pending
        assert pending is not None
        return pending

    def answer(self, pending, value="spotify", **kwargs):
        return ClarificationAnswer(
            pending.identity, ClarificationAnswerSource.LOCAL_UI, value, **kwargs
        )

    def test_exact_ready_request_has_no_lease(self) -> None:
        request = replace(self.request, parameters={"application_id": "spotify"})
        self.assertTrue(self.controller.prepare(request))
        self.assertIsNone(self.leases.pending)

    def test_unknown_action_and_extra_or_invalid_parameters_fail_closed(self) -> None:
        for action, parameters in [
            ("system.run", {}),
            ("applications.launch", {"application_id": True}),
            ("applications.launch", {"shell": "cmd.exe"}),
            ("applications.launch", {"application_id": "powershell"}),
        ]:
            with self.subTest(action=action, parameters=parameters):
                request = replace(self.request, action_id=action, parameters=parameters)
                self.assertEqual(
                    analyze_action_readiness(request, self.leases.registry).status,
                    ActionReadinessStatus.INVALID,
                )
        self.assertIsNone(self.leases.pending)

    def test_missing_target_preserves_identity_and_operation(self) -> None:
        pending = self.begin()
        result = self.leases.resolve(self.answer(pending))
        self.assertEqual(result.outcome, ClarificationOutcome.RESOLVED)
        self.assertEqual(
            result.request,
            replace(self.request, parameters={"application_id": "spotify"}),
        )
        self.assertIsNone(self.leases.pending)

    def test_cancel_timeout_and_boundary(self) -> None:
        pending = self.begin()
        self.assertEqual(
            self.leases.resolve(self.answer(pending, cancel=True)).outcome,
            ClarificationOutcome.CANCELLED,
        )
        pending = self.begin()
        self.clock.seconds = pending.identity.deadline
        self.assertEqual(
            self.leases.resolve(self.answer(pending)).outcome,
            ClarificationOutcome.EXPIRED,
        )
        self.assertIsNone(self.leases.pending)

    def test_answer_replay_and_duplicate_are_stale(self) -> None:
        pending = self.begin()
        answer = self.answer(pending)
        self.assertEqual(
            self.leases.resolve(answer).outcome, ClarificationOutcome.RESOLVED
        )
        for _ in range(3):
            self.assertEqual(
                self.leases.resolve(answer).outcome, ClarificationOutcome.STALE
            )

    def test_wrong_nonce_request_digest_revision_epoch_or_id_is_stale(self) -> None:
        pending = self.begin()
        for identity in (
            replace(pending.identity, nonce="different"),
            replace(pending.identity, lease_id="other-lease"),
            replace(pending.identity, revision=1),
            replace(pending.identity, owner_epoch=99),
            replace(pending.identity, request_digest="0" * 64),
        ):
            with self.subTest(identity=identity):
                self.assertEqual(
                    self.leases.resolve(
                        replace(self.answer(pending), identity=identity)
                    ).outcome,
                    ClarificationOutcome.STALE,
                )
        self.assertIsNotNone(self.leases.pending)

    def test_superseded_answer_cannot_attach_to_another_request(self) -> None:
        old = self.begin()
        self.controller.prepare(replace(self.request, correlation_id="request-2"))
        self.assertEqual(
            self.leases.resolve(self.answer(old)).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(self.leases.pending.request.correlation_id, "request-2")

    def test_new_ready_action_supersedes_pending(self) -> None:
        old = self.begin()
        self.controller.prepare(
            replace(self.request, parameters={"application_id": "chrome"})
        )
        self.assertIsNone(self.leases.pending)
        self.assertEqual(
            self.leases.resolve(self.answer(old)).outcome, ClarificationOutcome.STALE
        )

    def test_unrelated_chat_does_not_consume_or_extend(self) -> None:
        pending = self.begin()
        self.clock.seconds += 30
        self.assertIsNone(self.controller.route_answer("How are you today?"))
        self.assertEqual(self.leases.pending, pending)

    def test_partial_answer_increments_revision_without_extending_deadline(
        self,
    ) -> None:
        request = ActionRequest("search-1", "files.search", "chat", {})
        self.controller.prepare(request)
        first = self.leases.pending
        self.clock.seconds += 100
        result = self.leases.resolve(self.answer(first, "Downloads"))
        self.assertEqual(result.outcome, ClarificationOutcome.PENDING)
        revised = self.leases.pending
        self.assertEqual(revised.identity.deadline, first.identity.deadline)
        self.assertEqual(revised.identity.created_at, first.identity.created_at)
        self.assertEqual(revised.identity.revision, 1)
        self.assertNotEqual(
            revised.identity.request_digest, first.identity.request_digest
        )
        self.assertEqual(
            self.leases.resolve(self.answer(first, "song")).outcome,
            ClarificationOutcome.STALE,
        )
        result = self.leases.resolve(self.answer(revised, "song"))
        self.assertEqual(
            result.request.parameters, {"root": "Downloads", "query": "song"}
        )

    def test_attempt_to_extend_or_shift_deadline_rejected(self) -> None:
        pending = self.begin()
        with self.assertRaises(ValueError):
            replace(pending.identity, deadline=pending.identity.deadline + 10)
        shifted = replace(pending.identity, created_at=20.0, deadline=140.0)
        self.assertEqual(
            self.leases.resolve(
                replace(self.answer(pending), identity=shifted)
            ).outcome,
            ClarificationOutcome.STALE,
        )

    def test_provider_cannot_answer_or_cancel_and_cloud_requires_local_ui(self) -> None:
        pending = self.begin(cloud=True)
        for source in (
            ClarificationAnswerSource.PROVIDER,
            ClarificationAnswerSource.LOCAL_TEXT,
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
        ):
            for cancel in (False, True):
                self.assertEqual(
                    self.leases.resolve(
                        replace(self.answer(pending, cancel=cancel), source=source)
                    ).outcome,
                    ClarificationOutcome.INVALID,
                )
        self.assertEqual(
            self.leases.resolve(self.answer(pending)).outcome,
            ClarificationOutcome.RESOLVED,
        )

    def test_zero_matches_can_retry_original_operation(self) -> None:
        request = ActionRequest("open-1", "files.open", "chat", {})
        pending = self.controller.choices(request, ())
        self.assertEqual(pending.spec.reason, ActionClarificationReason.NO_MATCH)
        result = self.leases.resolve(self.answer(pending, r"C:\Approved\song.mp3"))
        self.assertEqual(result.request.action_id, "files.open")
        self.assertEqual(result.request.correlation_id, "open-1")

    def test_multiple_matches_and_trusted_local_open_any(self) -> None:
        request = ActionRequest("open-1", "files.open", "chat", {})
        choices = tuple(
            replace(request, parameters={"path": f"C:/Approved/{i}.mp3"})
            for i in range(3)
        )
        pending = self.controller.choices(request, choices)
        self.assertEqual(
            pending.spec.reason, ActionClarificationReason.MULTIPLE_MATCHES
        )
        result = self.leases.resolve(self.answer(pending, "", choice_index=2))
        self.assertEqual(result.request, choices[1])
        request = replace(request, correlation_id="open-any-2")
        choices = tuple(
            replace(choice, correlation_id=request.correlation_id) for choice in choices
        )
        pending = self.controller.choices(request, choices)
        result = self.leases.resolve(self.answer(pending, "", open_any=True))
        self.assertEqual(result.request, choices[0])

    def test_free_text_and_provider_open_any_do_not_resolve(self) -> None:
        request = ActionRequest("open-1", "files.open", "chat", {})
        choice = replace(request, parameters={"path": "C:/Approved/a.mp3"})
        pending = self.controller.choices(request, (choice,))
        for source in ClarificationAnswerSource:
            self.assertEqual(
                self.leases.resolve(
                    ClarificationAnswer(pending.identity, source, "open any")
                ).outcome,
                ClarificationOutcome.INVALID,
            )
        for source in (
            ClarificationAnswerSource.PROVIDER,
            ClarificationAnswerSource.LOCAL_TEXT,
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
        ):
            self.assertEqual(
                self.leases.resolve(
                    ClarificationAnswer(pending.identity, source, open_any=True)
                ).outcome,
                ClarificationOutcome.INVALID,
            )

    def test_choice_bounds_and_operation_or_request_switch_rejected(self) -> None:
        request = ActionRequest("open-1", "files.open", "chat", {})
        choice = replace(request, parameters={"path": "C:/Approved/a.mp3"})
        spec = ActionClarificationSpec(
            ActionClarificationReason.MULTIPLE_MATCHES, choice_count=1
        )
        for changed in (
            replace(choice, action_id="files.open_directory"),
            replace(choice, correlation_id="wrong"),
            replace(choice, source="provider.gemini.live"),
        ):
            with self.assertRaises(ValueError):
                self.leases.begin(request, spec, (changed,))
        pending = self.controller.choices(request, (choice,) * 11)
        self.assertEqual(len(pending.choices), 10)
        for index in (0, 11, True):
            self.assertEqual(
                self.leases.resolve(
                    self.answer(pending, "", choice_index=index)
                ).outcome,
                ClarificationOutcome.INVALID,
            )

    def test_shell_or_compound_answer_rejected_without_consumption(self) -> None:
        pending = self.begin()
        for value in (
            "spotify; cmd.exe",
            "spotify and then open chrome",
            "powershell",
            "x\nsecret",
        ):
            self.assertEqual(
                self.leases.resolve(self.answer(pending, value)).outcome,
                ClarificationOutcome.INVALID,
            )
        self.assertEqual(self.leases.pending, pending)

    def test_atomic_resolution_allows_one_winner(self) -> None:
        pending = self.begin()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: self.leases.resolve(self.answer(pending)).outcome,
                    range(32),
                )
            )
        self.assertEqual(results.count(ClarificationOutcome.RESOLVED), 1)
        self.assertEqual(results.count(ClarificationOutcome.STALE), 31)

    def test_revocation_invalidates_pending_and_confirmation(self) -> None:
        pending = self.begin()
        request = replace(self.request, parameters={"application_id": "spotify"})
        confirmation = self.leases.issue_confirmation(request)
        self.controller.invalidate()
        self.assertEqual(
            self.leases.resolve(self.answer(pending)).outcome,
            ClarificationOutcome.STALE,
        )
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, request, approved=True)
        )

    def test_confirmation_expiry_mutation_replay_and_atomicity(self) -> None:
        request = replace(self.request, parameters={"application_id": "spotify"})
        confirmation = self.leases.issue_confirmation(request)
        self.clock.seconds += 60
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, request, approved=True)
        )
        confirmation = self.leases.issue_confirmation(request)
        self.assertFalse(
            self.leases.consume_confirmation(
                confirmation,
                replace(request, parameters={"application_id": "chrome"}),
                approved=True,
            )
        )
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, request, approved=True)
        )
        confirmation = self.leases.issue_confirmation(request)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: self.leases.consume_confirmation(
                        confirmation, request, approved=True
                    ),
                    range(32),
                )
            )
        self.assertEqual(results.count(True), 1)

    def test_confirmation_deadline_extension_and_decline(self) -> None:
        request = replace(self.request, parameters={"application_id": "spotify"})
        confirmation = self.leases.issue_confirmation(request)
        with self.assertRaises(ValueError):
            replace(confirmation, deadline=confirmation.deadline + 1)
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, request, approved=False)
        )
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, request, approved=True)
        )

    def test_sanitized_evidence_and_private_repr(self) -> None:
        request = ActionRequest("secret-request", "files.open", "chat", {})
        pending = self.controller.choices(
            request,
            (replace(request, parameters={"path": "C:/secret/credential.mp3"}),),
        )
        answer = self.answer(pending, "private answer", choice_index=1)
        result = self.leases.resolve(answer)
        for value in (pending, answer, result, self.leases.evidence):
            self.assertNotIn("credential", repr(value))
            self.assertNotIn("private answer", repr(value))
        for evidence in self.leases.evidence:
            self.assertEqual(
                set(asdict(evidence)),
                {"lease_id", "action_category", "reason_code", "timestamp", "outcome"},
            )

    def test_duplicate_aliases_fail_deterministically(self) -> None:
        for roots in (
            (r"C:\One\Music", r"D:\Two\music"),
            (r"D:\Two\music", r"C:\One\Music"),
        ):
            with self.assertRaises(ValueError):
                approved_directory_aliases(roots)

    def test_uncertain_time_is_contract_only_without_registered_utility(self) -> None:
        spec = ActionClarificationSpec(
            ActionClarificationReason.UNCERTAIN_TIME, ("time",)
        )
        self.assertEqual(spec.reason.value, "uncertain_time")
        registry = build_default_action_registry()
        for definition in registry.definitions:
            self.assertNotIn("timer", definition.action_id)
            self.assertNotIn("reminder", definition.action_id)
        with self.assertRaises(ValueError):
            self.leases.begin(
                ActionRequest("timer-1", "timers.create", "chat", {}), spec
            )

    def test_incomplete_command_envelope_rejects_negation_and_hypothetical(
        self,
    ) -> None:
        self.assertEqual(
            self.controller.incomplete_command("Please open app", "request-1"),
            self.request,
        )
        for text in (
            "don't open app",
            "if I asked you to open app",
            "open app and then delete files",
        ):
            self.assertIsNone(self.controller.incomplete_command(text, "request-1"))

    def test_repeated_preparation_cannot_extend_foreground_deadline(self) -> None:
        original = self.begin()
        self.clock.seconds += 100
        self.controller.prepare(self.request)
        self.assertEqual(self.leases.pending, original)
        self.assertEqual(
            self.leases.pending.identity.deadline, original.identity.deadline
        )

    def test_empty_required_target_is_missing_instead_of_execution_ready(self) -> None:
        self.assertFalse(
            self.controller.prepare(
                replace(self.request, parameters={"application_id": "   "})
            )
        )
        self.assertEqual(
            self.leases.pending.spec.missing_parameters, ("application_id",)
        )
        self.assertEqual(
            self.leases.resolve(self.answer(self.leases.pending)).outcome,
            ClarificationOutcome.RESOLVED,
        )

    def test_vague_spotify_music_is_bound_locally_without_inventing_content(self):
        for prefix in ("", "please ", "Akiha, ", "Akiha, please ", "please Akiha, "):
            for wording in (
                "Play Music on Spotify",
                "Play a song on Spotify.",
                "Play a track on Spotify",
            ):
                request = self.controller.incomplete_command(
                    prefix + wording, f"spotify-{len(prefix)}-{len(wording)}"
                )
                self.assertEqual(request.action_id, "spotify.play_track")
                self.assertEqual(request.parameters, {"service": "spotify"})
                self.assertFalse(self.controller.prepare(request))
                pending = self.leases.pending
                self.assertEqual(pending.spec.missing_parameters, ("track_query",))
                self.assertEqual(pending.choices, ())
                self.assertEqual(
                    self.leases.evidence[-1].action_category, "spotify.play_track"
                )

    def test_spotify_music_answer_keeps_operation_and_owner_and_rejects_replay(self):
        request = self.controller.incomplete_command(
            "Play Music on Spotify", "spotify-target"
        )
        self.controller.prepare(request)
        pending = self.leases.pending
        epoch = self.leases.owner_epoch
        answer = self.answer(pending, "Blinding Lights")
        result = self.controller.resolve(answer)
        self.assertIs(result.outcome, ClarificationOutcome.RESOLVED)
        self.assertEqual(
            result.request.parameters,
            {"service": "spotify", "track_query": "Blinding Lights"},
        )
        self.assertEqual(result.request.action_id, "spotify.play_track")
        self.assertEqual(result.request.correlation_id, request.correlation_id)
        self.assertEqual(self.leases.owner_epoch, epoch)
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )

    def test_spotify_recognition_does_not_rewrite_prose_negation_or_specific_tracks(
        self,
    ):
        from project_akiha.services.assistant_action_bridge import (
            AssistantActionRequestParser,
        )

        for wording in (
            "I would like to discuss Play Music on Spotify",
            "Don't play music on Spotify",
            "Akiha, do not play music on Spotify",
            "Play Music on Spotify and open a folder",
            "Akiha, Akiha, play music on Spotify",
        ):
            self.assertIsNone(
                self.controller.incomplete_command(wording, "not-command")
            )
        wording = "Play track Blinding Lights by The Weeknd on Spotify"
        self.assertIsNone(self.controller.incomplete_command(wording, "specific"))
        request = AssistantActionRequestParser().parse(wording)
        self.assertEqual(request.action_id, "spotify.play_track")
        self.assertEqual(
            request.parameters,
            {
                "service": "spotify",
                "track_query": "Blinding Lights",
                "artist_query": "The Weeknd",
            },
        )

    def test_typed_missing_parameters_resolve_without_time_interpretation_or_authority(
        self,
    ) -> None:
        for action, value, name, expected in (
            ("spotify.seek", "42", "position_seconds", 42),
            ("spotify.shuffle", "true", "enabled", True),
        ):
            with self.subTest(action=action):
                request = ActionRequest(
                    f"typed-{action}", action, "chat", {"service": "spotify"}
                )
                self.assertFalse(self.controller.prepare(request))
                pending = self.leases.pending
                self.assertEqual(
                    self.leases.resolve(self.answer(pending, "sometime later")).outcome,
                    ClarificationOutcome.INVALID,
                )
                result = self.leases.resolve(self.answer(pending, value))
                self.assertEqual(result.outcome, ClarificationOutcome.RESOLVED)
                self.assertEqual(result.request.parameters[name], expected)
                self.assertEqual(type(result.request.parameters[name]), type(expected))
                self.assertEqual(result.request.action_id, action)
