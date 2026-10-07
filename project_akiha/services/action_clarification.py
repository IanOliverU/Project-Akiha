"""One bounded process-local clarification owner; no execution or persistence."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from uuid import uuid4

from project_akiha.core.actions.clarification import (
    ActionClarificationReason,
    ActionClarificationSpec,
    ActionReadinessStatus,
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationLeaseIdentity,
    ClarificationOutcome,
    ClarificationResolution,
    ConfirmationLease,
    LocalSearchIdentity,
    LocalSearchOutcome,
    LocalSearchResolution,
    LocalTargetChoices,
    SpotifyHistoryIdentity,
    analyze_action_readiness,
    request_fingerprint,
)
from project_akiha.core.actions.models import ActionRequest, ParameterKind
from project_akiha.core.actions.registry import (
    ActionRegistry,
    build_default_action_registry,
)
from project_akiha.core.utilities.clock import SystemUtilityClock, UtilityClock


@dataclass(frozen=True, slots=True)
class PendingClarification:
    identity: ClarificationLeaseIdentity
    spec: ActionClarificationSpec
    request: ActionRequest = field(repr=False)
    choices: tuple[ActionRequest, ...] = field(default=(), repr=False)
    local_targets: LocalTargetChoices | None = field(default=None, repr=False)
    choice_ids: tuple[str, ...] = field(default=(), repr=False)
    local_choice_guard: Callable[[], bool] | None = field(default=None, repr=False)
    local_execution_guard: Callable[[], bool] | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ClarificationEvidence:
    lease_id: str
    action_category: str
    reason_code: str
    timestamp: float
    outcome: str


class ActionClarificationService:
    """Serialize lease transitions, preserving exact operation and deadlines."""

    def __init__(
        self, registry: ActionRegistry | None = None, clock: UtilityClock | None = None
    ) -> None:
        self.registry = registry or build_default_action_registry()
        self.clock = clock or SystemUtilityClock()
        self._lock = threading.RLock()
        self._epoch = 0
        self._current_request: tuple[str, str] | None = None
        # Only identifiers/digests survive a request; private payloads do not.
        self._request_digests: dict[str, str] = {}
        self._pending: PendingClarification | None = None
        self._confirmations: OrderedDict[str, ConfirmationLease] = OrderedDict()
        self._search_generation = 0
        self._local_search: LocalSearchIdentity | None = None
        self._search_ready: tuple[LocalSearchIdentity, ActionRequest] | None = None
        self._spotify_history: SpotifyHistoryIdentity | None = None
        self._spotify_selected: tuple[int, str, str] | None = None
        self._spotify_selected_guard: Callable[[], bool] | None = None
        self._evidence: deque[ClarificationEvidence] = deque(maxlen=128)

    @property
    def pending(self) -> PendingClarification | None:
        with self._lock:
            self._expire()
            return self._pending

    @property
    def owner_epoch(self) -> int:
        with self._lock:
            return self._epoch

    @property
    def evidence(self) -> tuple[ClarificationEvidence, ...]:
        with self._lock:
            return tuple(self._evidence)

    def begin(
        self,
        request: ActionRequest,
        spec: ActionClarificationSpec,
        choices: tuple[ActionRequest, ...] = (),
        *,
        owner_epoch: int | None = None,
        local_targets: LocalTargetChoices | None = None,
    ) -> PendingClarification:
        with self._lock:
            self._expire()
            request_fingerprint(request)
            self.registry.resolve(request.action_id)
            if owner_epoch is not None and not self.owns(request, owner_epoch):
                raise ValueError("clarification result has stale ownership")
            self.claim(request)
            if (
                self._pending is not None
                and self._pending.request.correlation_id == request.correlation_id
            ):
                if self._pending.identity.request_digest != request_fingerprint(
                    request
                ):
                    raise ValueError(
                        "a repeated request cannot change its normalized fingerprint"
                    )
                return self._pending
            maximum = 5 if request.action_id.startswith("spotify.") else 10
            if spec.local_music_catalog and not (
                local_targets is not None
                and request.action_id == "files.open"
                and request.source == "chat.music"
            ):
                raise ValueError("full catalog requires trusted local music choices")
            if (
                local_targets is not None
                and request.action_id == "files.open"
                and request.source == "chat.music"
            ):
                maximum = local_targets.choice_limit
            if local_targets is not None and local_targets.requests != choices:
                raise ValueError("local choice snapshots must match the lease")
            if len(choices) > maximum or spec.choice_count != len(choices):
                raise ValueError("candidate count does not match bounded specification")
            for choice in choices:
                if (choice.action_id, choice.correlation_id, choice.source) != (
                    request.action_id,
                    request.correlation_id,
                    request.source,
                ):
                    raise ValueError("a clarification cannot change the operation")
                request_fingerprint(choice)
            if self._pending is not None:
                self._finish(ClarificationOutcome.SUPERSEDED)
            now = self.clock.monotonic_seconds()
            identity = ClarificationLeaseIdentity(
                f"clarification-{uuid4().hex}",
                uuid4().hex,
                self._epoch,
                0,
                request_fingerprint(request),
                now,
                now + 120.0,
            )
            self._pending = PendingClarification(
                identity,
                spec,
                request,
                choices,
                local_targets,
                tuple(uuid4().hex for _ in choices) if local_targets else (),
            )
            self._record(self._pending, ClarificationOutcome.PENDING)
            return self._pending

    def resolve(
        self,
        answer: ClarificationAnswer,
        *,
        validate_local_choice: Callable[[ActionRequest], bool] | None = None,
    ) -> ClarificationResolution:
        with self._lock:
            pending = self._pending
            if pending is None or answer.identity != pending.identity:
                return ClarificationResolution(ClarificationOutcome.STALE)
            if self.clock.monotonic_seconds() >= pending.identity.deadline:
                self._finish(ClarificationOutcome.EXPIRED)
                return ClarificationResolution(ClarificationOutcome.EXPIRED)
            if answer.source is ClarificationAnswerSource.PROVIDER or (
                pending.spec.cloud_origin
                and answer.source is not ClarificationAnswerSource.LOCAL_UI
            ):
                return ClarificationResolution(ClarificationOutcome.INVALID)
            if answer.source not in {
                ClarificationAnswerSource.LOCAL_UI,
                ClarificationAnswerSource.LOCAL_TEXT,
                ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
            }:
                return ClarificationResolution(ClarificationOutcome.INVALID)
            if answer.artist_query and not (
                answer.source is ClarificationAnswerSource.LOCAL_UI
                and pending.request.action_id == "spotify.play_track"
                and pending.spec.missing_parameters == ("track_query",)
                and pending.local_targets is None
                and not pending.choices
            ):
                return ClarificationResolution(ClarificationOutcome.INVALID)
            if answer.cancel:
                self._finish(ClarificationOutcome.CANCELLED)
                return ClarificationResolution(ClarificationOutcome.CANCELLED)
            if (
                answer.open_any
                and answer.source is not ClarificationAnswerSource.LOCAL_UI
            ):
                return ClarificationResolution(ClarificationOutcome.INVALID)
            if re.search(r"\b(?:open|play|choose)\s+any\b", answer.value, re.I):
                return ClarificationResolution(ClarificationOutcome.INVALID)
            if pending.local_targets is not None:
                if (
                    answer.source is not ClarificationAnswerSource.LOCAL_UI
                    or answer.choice_id not in pending.choice_ids
                    or answer.choice_index is not None
                    or answer.open_any
                    or answer.value
                ):
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                selected = pending.choices[pending.choice_ids.index(answer.choice_id)]
                if (
                    pending.local_targets.enabled
                    and not pending.local_targets.enabled[
                        pending.choice_ids.index(answer.choice_id)
                    ]
                ):
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                valid = (
                    pending.local_choice_guard()
                    if pending.local_choice_guard is not None
                    else (
                        validate_local_choice(selected)
                        if validate_local_choice is not None
                        else False
                    )
                )
                if self._pending is not pending:
                    return ClarificationResolution(ClarificationOutcome.STALE)
                if self.clock.monotonic_seconds() >= pending.identity.deadline:
                    self._finish(ClarificationOutcome.EXPIRED)
                    return ClarificationResolution(ClarificationOutcome.EXPIRED)
                if not valid:
                    self._finish(ClarificationOutcome.CANCELLED)
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                parameters = dict(selected.parameters)
            elif answer.choice_id is not None:
                return ClarificationResolution(ClarificationOutcome.INVALID)
            elif pending.choices:
                index = 1 if answer.open_any else answer.choice_index
                if type(index) is not int or not 1 <= index <= len(pending.choices):
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                parameters = dict(pending.choices[index - 1].parameters)
            else:
                if answer.open_any or answer.choice_index is not None:
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                if not pending.spec.missing_parameters:
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                value = answer.value.strip()
                if not value or len(value) > 256 or any(ord(c) < 32 for c in value):
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                if re.search(
                    r"(?:[;|`]|\b(?:and then|powershell|cmd\.exe)\b)", value, re.I
                ):
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                parameters = dict(pending.request.parameters)
                name = pending.spec.missing_parameters[0]
                definition = self.registry.resolve(pending.request.action_id)
                field_spec = next(
                    (spec for spec in definition.parameters if spec.name == name), None
                )
                if field_spec is None:
                    return ClarificationResolution(ClarificationOutcome.INVALID)
                if field_spec.kind is ParameterKind.INTEGER:
                    if re.fullmatch(r"-?[0-9]{1,9}", value) is None:
                        return ClarificationResolution(ClarificationOutcome.INVALID)
                    parameters[name] = int(value)
                elif field_spec.kind is ParameterKind.BOOLEAN:
                    if value.casefold() not in {"true", "false"}:
                        return ClarificationResolution(ClarificationOutcome.INVALID)
                    parameters[name] = value.casefold() == "true"
                else:
                    parameters[name] = next(
                        (
                            allowed
                            for allowed in field_spec.allowed_values
                            if allowed.casefold() == value.casefold()
                        ),
                        value,
                    )
                if answer.artist_query:
                    artist = answer.artist_query.strip()
                    if not artist or any(ord(c) < 32 for c in artist):
                        return ClarificationResolution(ClarificationOutcome.INVALID)
                    parameters["artist_query"] = artist
            request = ActionRequest(
                pending.request.correlation_id,
                pending.request.action_id,
                pending.request.source,
                parameters,
            )
            readiness = analyze_action_readiness(request, self.registry)
            if readiness.status is ActionReadinessStatus.INVALID:
                return ClarificationResolution(ClarificationOutcome.INVALID)
            # This is a trusted, identity-bound revision, never external ID reuse.
            digest = request_fingerprint(request)
            self._request_digests[request.correlation_id] = digest
            self._current_request = (request.correlation_id, digest)
            if (
                pending.local_targets is not None
                and pending.local_targets.spotify_history
            ):
                self._spotify_selected = (self._epoch, request.correlation_id, digest)
                self._spotify_selected_guard = pending.local_execution_guard
            if readiness.status is ActionReadinessStatus.CLARIFICATION_REQUIRED:
                identity = replace(
                    pending.identity,
                    revision=pending.identity.revision + 1,
                    request_digest=request_fingerprint(request),
                )
                assert readiness.spec is not None
                spec = replace(readiness.spec, cloud_origin=pending.spec.cloud_origin)
                self._pending = PendingClarification(identity, spec, request)
                return ClarificationResolution(ClarificationOutcome.PENDING, identity)
            self._finish(ClarificationOutcome.RESOLVED)
            return ClarificationResolution(
                ClarificationOutcome.RESOLVED, pending.identity, request
            )

    def start_spotify_history(
        self, identity: ClarificationLeaseIdentity, account_generation: int
    ) -> SpotifyHistoryIdentity | None:
        """Capture once; an old fetch cannot acquire new ownership."""
        with self._lock:
            self._expire()
            pending = self._pending
            if (
                pending is None
                or pending.identity != identity
                or pending.request.source != "chat"
                or pending.request.action_id != "spotify.play_track"
                or pending.spec.missing_parameters != ("track_query",)
                or "track_query" in pending.request.parameters
                or not self.owns(pending.request, identity.owner_epoch)
                or self._spotify_history is not None
            ):
                return None
            captured = SpotifyHistoryIdentity(
                identity, uuid4().hex, account_generation, pending.request
            )
            self._spotify_history = captured
            return captured

    def publish_spotify_history(
        self,
        captured: SpotifyHistoryIdentity,
        targets: LocalTargetChoices,
        *,
        account_guard: Callable[[], bool],
        execution_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Install at most ten local play entries under the original lease lock."""
        with self._lock:
            self._expire()
            pending = self._pending
            if (
                pending is None
                or pending.identity != captured.lease
                or self._spotify_history != captured
                or pending.request != captured.request
                or not self.owns(captured.request, captured.lease.owner_epoch)
            ):
                return False
            allowed = account_guard()
            if self._pending is not pending or self._spotify_history != captured:
                return False
            self._expire()
            if self._pending is not pending:
                return False
            if not allowed:
                self._finish(ClarificationOutcome.CANCELLED)
                return False
            if not targets.spotify_history or len(targets.requests) > 10:
                raise ValueError("history requires a bounded trusted local snapshot")
            for choice in targets.requests:
                if (choice.correlation_id, choice.action_id, choice.source) != (
                    captured.request.correlation_id,
                    "spotify.play_track",
                    "chat",
                ) or analyze_action_readiness(
                    choice, self.registry
                ).status is not ActionReadinessStatus.READY:
                    raise ValueError("invalid history continuation")
            self._spotify_history = None
            self._pending = replace(
                pending,
                identity=replace(
                    pending.identity, revision=pending.identity.revision + 1
                ),
                spec=replace(pending.spec, choice_count=len(targets.requests)),
                choices=targets.requests,
                local_targets=targets,
                choice_ids=tuple(uuid4().hex for _ in targets.requests),
                local_choice_guard=account_guard,
                local_execution_guard=execution_guard or account_guard,
            )
            return True

    def spotify_search_mode(self, identity: ClarificationLeaseIdentity) -> bool:
        """Deliberate local switch cancels a fetch/snapshot, retaining the deadline."""
        with self._lock:
            self._expire()
            pending = self._pending
            if (
                pending is None
                or pending.identity != identity
                or pending.request.source != "chat"
                or pending.request.action_id != "spotify.play_track"
                or "track_query" in pending.request.parameters
            ):
                return False
            self._spotify_history = None
            self._pending = replace(
                pending,
                identity=replace(identity, revision=identity.revision + 1),
                spec=replace(pending.spec, choice_count=0),
                choices=(),
                local_targets=None,
                choice_ids=(),
                local_choice_guard=None,
                local_execution_guard=None,
            )
            return True

    def capture_owner(self, request: ActionRequest) -> int | None:
        """Capture an exact request's ownership once, without adopting later owners."""
        with self._lock:
            return self._epoch if self.owns(request) else None

    def is_spotify_history_selection(self, request: ActionRequest, epoch: int) -> bool:
        """Only a digest survives selection, for privacy-safe result presentation."""
        with self._lock:
            return self._spotify_selected == (
                epoch,
                request.correlation_id,
                request_fingerprint(request),
            )

    def execution_owned(self, request: ActionRequest, epoch: int) -> bool:
        """Retain account binding through the executor's cancellation checkpoints."""
        with self._lock:
            if not self.owns(request, epoch):
                return False
            if self.is_spotify_history_selection(request, epoch):
                guard = self._spotify_selected_guard
                allowed = guard is not None and guard()
                return allowed and self.owns(request, epoch)
            return True

    def start_local_search(self, request: ActionRequest) -> LocalSearchIdentity:
        """Claim the complete local search intent once, before starting its worker.

        Search arguments bind discovery, not executable arguments. Only this
        trusted continuation may replace them with a validated local path.
        """
        with self._lock:
            if request.action_id not in {"files.open", "files.open_directory"}:
                raise ValueError("unsupported local search operation")
            epoch = self.claim(request)
            self._search_generation += 1
            now = self.clock.monotonic_seconds()
            identity = LocalSearchIdentity(
                epoch,
                request_fingerprint(request),
                request.correlation_id,
                request.action_id,
                request.source,
                request.action_id,
                self._search_generation,
                uuid4().hex,
                uuid4().hex,
                now,
                now + 120.0,
                request,
            )
            self._local_search = identity
            self._search_ready = None
            return identity

    def continue_local_search(
        self,
        identity: LocalSearchIdentity,
        paths: tuple[str, ...],
        *,
        complete: bool = True,
        limited: bool = False,
        before_publish: Callable[[], bool] | None = None,
    ) -> LocalSearchResolution:
        """Consume discovery exactly once and atomically publish or admit execution."""
        with self._lock:
            self._expire()
            if not self._owns_search(identity):
                return LocalSearchResolution(LocalSearchOutcome.STALE, identity)
            if (
                type(complete) is not bool
                or type(limited) is not bool
                or not isinstance(paths, tuple)
                or any(not isinstance(p, str) or not p.strip() for p in paths)
            ):
                self._local_search = None
                return LocalSearchResolution(LocalSearchOutcome.REJECTED, identity)
            limited = limited or len(paths) > 10
            paths = paths[:10]
            candidates = tuple(
                ActionRequest(
                    identity.request_id,
                    identity.operation,
                    identity.source,
                    {"path": path},
                )
                for path in paths
            )
            if any(
                analyze_action_readiness(candidate, self.registry).status
                is not ActionReadinessStatus.READY
                for candidate in candidates
            ):
                self._local_search = None
                return LocalSearchResolution(LocalSearchOutcome.REJECTED, identity)
            unique = len(paths) == 1 and complete and not limited
            cloud = False
            if not unique and before_publish is not None:
                cloud = before_publish()
                if not self._owns_search(identity):
                    return LocalSearchResolution(LocalSearchOutcome.STALE, identity)
            request = ActionRequest(
                identity.request_id,
                identity.operation,
                identity.source,
                {"path": paths[0]} if unique else {},
            )
            if (
                unique
                and analyze_action_readiness(request, self.registry).status
                is not ActionReadinessStatus.READY
            ):
                self._local_search = None
                return LocalSearchResolution(LocalSearchOutcome.REJECTED, identity)
            # Trusted revision of the SAME owner: no claim, epoch change or new ID.
            digest = request_fingerprint(request)
            self._current_request = (request.correlation_id, digest)
            self._request_digests[request.correlation_id] = digest
            self._local_search = None
            if unique:
                self._search_ready = (identity, request)
                return LocalSearchResolution(
                    LocalSearchOutcome.READY_TO_EXECUTE, identity, request
                )
            choices = candidates
            spec = ActionClarificationSpec(
                (
                    ActionClarificationReason.MULTIPLE_MATCHES
                    if paths
                    else ActionClarificationReason.NO_MATCH
                ),
                ("path",),
                len(choices),
                cloud,
                limited or not complete,
            )
            self.begin(request, spec, choices, owner_epoch=identity.owner_epoch)
            return LocalSearchResolution(
                LocalSearchOutcome.CLARIFICATION_REQUIRED, identity
            )

    def _owns_search(self, identity: LocalSearchIdentity) -> bool:
        return (
            self._local_search == identity
            and identity.request_digest == request_fingerprint(identity.request)
            and (
                identity.request_id,
                identity.action_id,
                identity.source,
                identity.operation,
            )
            == (
                identity.request.correlation_id,
                identity.request.action_id,
                identity.request.source,
                identity.request.action_id,
            )
            and self.owns(identity.request, identity.owner_epoch)
            and self.clock.monotonic_seconds() < identity.deadline
        )

    def enqueue_local_search(
        self,
        resolution: LocalSearchResolution,
        enqueue: Callable[[ActionRequest, int], None],
    ) -> bool:
        """Consume ready admission under the owner lock, without claiming."""
        with self._lock:
            self._expire()
            request = resolution.request
            if (
                resolution.outcome is not LocalSearchOutcome.READY_TO_EXECUTE
                or request is None
                or self._search_ready != (resolution.identity, request)
                or not self.owns(request, resolution.identity.owner_epoch)
            ):
                return False
            self._search_ready = None
            enqueue(request, resolution.identity.owner_epoch)
            return True

    def cancel_local_search(self, identity: LocalSearchIdentity) -> bool:
        with self._lock:
            self._expire()
            if not self._owns_search(identity):
                return False
            self.invalidate()
            return True

    def publish_result(
        self,
        owner_request: ActionRequest,
        owner_epoch: int,
        request: ActionRequest,
        spec: ActionClarificationSpec,
        choices: tuple[ActionRequest, ...] = (),
        *,
        before_publish: Callable[[], bool] | None = None,
    ) -> PendingClarification:
        """Validate the captured owner and publish its continuation atomically."""
        with self._lock:
            self._expire()
            if not self.owns(owner_request, owner_epoch):
                raise ValueError("clarification result has stale ownership")
            if before_publish is not None:
                hosted_active = before_publish()
                spec = replace(spec, cloud_origin=spec.cloud_origin or hosted_active)
                # Synchronous event delivery may reenter the owner on this RLock.
                if not self.owns(owner_request, owner_epoch):
                    raise ValueError("clarification result has stale ownership")
            # begin claims a new continuation identity only after this owner's
            # validation, without releasing the lock between these transitions.
            return self.begin(request, spec, choices)

    def confirmation_active(self, lease: ConfirmationLease) -> bool:
        with self._lock:
            self._expire()
            return (
                self._confirmations.get(lease.lease_id) == lease
                and lease.owner_epoch == self._epoch
            )

    def discard_confirmation(self, lease: ConfirmationLease) -> None:
        with self._lock:
            self._confirmations.pop(lease.lease_id, None)

    def supersede(self) -> None:
        with self._lock:
            self._epoch += 1
            self._current_request = None
            self._local_search = None
            self._search_ready = None
            self._spotify_selected = None
            self._spotify_selected_guard = None
            self._spotify_history = None
            self._confirmations.clear()
            if self._pending is not None:
                self._finish(ClarificationOutcome.SUPERSEDED)

    def invalidate(self) -> None:
        """Called synchronously on revocation, reset, Stop, or owner teardown."""
        with self._lock:
            if self._pending is not None:
                self._finish(ClarificationOutcome.CANCELLED)
            self._confirmations.clear()
            self._epoch += 1
            self._current_request = None
            self._local_search = None
            self._search_ready = None
            self._spotify_selected = None
            self._spotify_selected_guard = None
            self._spotify_history = None

    def claim(self, request: ActionRequest) -> int:
        """Accept an explicit request atomically, rejecting changed ID reuse."""
        with self._lock:
            digest = request_fingerprint(request)
            previous = self._request_digests.get(request.correlation_id)
            if previous is not None and previous != digest:
                self.invalidate()
                raise ValueError("request ID has a different normalized fingerprint")
            identity = (request.correlation_id, digest)
            if self._current_request != identity:
                self.supersede()
                self._request_digests[request.correlation_id] = digest
                self._current_request = identity
            return self._epoch

    def owns(self, request: ActionRequest, owner_epoch: int | None = None) -> bool:
        """Reject callbacks from a different operation, revision, or owner."""
        with self._lock:
            return (
                owner_epoch is None or owner_epoch == self._epoch
            ) and self._current_request == (
                request.correlation_id,
                request_fingerprint(request),
            )

    def issue_confirmation(
        self, request: ActionRequest, *, owner_epoch: int | None = None
    ) -> ConfirmationLease:
        """Caller must first obtain CONFIRMATION_REQUIRED from the action service."""
        with self._lock:
            self._expire()
            if owner_epoch is not None and not self.owns(request, owner_epoch):
                raise ValueError("confirmation result has stale ownership")
            digest = request_fingerprint(request)
            for existing in self._confirmations.values():
                if (
                    existing.owner_epoch == self._epoch
                    and existing.request_digest == digest
                ):
                    return existing
            now = self.clock.monotonic_seconds()
            lease = ConfirmationLease(
                f"confirmation-{uuid4().hex}",
                uuid4().hex,
                self._epoch,
                request_fingerprint(request),
                now,
                now + 60.0,
                request,
            )
            self._confirmations[lease.lease_id] = lease
            while len(self._confirmations) > 32:
                self._confirmations.popitem(last=False)
            return lease

    def consume_confirmation(
        self, lease: ConfirmationLease, request: ActionRequest, *, approved: bool
    ) -> bool:
        with self._lock:
            stored = self._confirmations.get(lease.lease_id)
            if stored != lease:
                return False
            self._confirmations.pop(lease.lease_id)
            try:
                digest = request_fingerprint(request)
            except (TypeError, ValueError):
                return False
            return (
                approved is True
                and lease.owner_epoch == self._epoch
                and self.clock.monotonic_seconds() < lease.deadline
                and digest == lease.request_digest
            )

    def _expire(self) -> None:
        search = self._local_search or (
            self._search_ready[0] if self._search_ready else None
        )
        if search is not None and self.clock.monotonic_seconds() >= search.deadline:
            self.invalidate()
        if (
            self._pending
            and self.clock.monotonic_seconds() >= self._pending.identity.deadline
        ):
            self._finish(ClarificationOutcome.EXPIRED)
        now = self.clock.monotonic_seconds()
        for key, lease in tuple(self._confirmations.items()):
            if now >= lease.deadline:
                del self._confirmations[key]

    def _finish(self, outcome: ClarificationOutcome) -> None:
        assert self._pending is not None
        self._record(self._pending, outcome)
        self._pending = None
        self._spotify_history = None
        if outcome in {ClarificationOutcome.CANCELLED, ClarificationOutcome.EXPIRED}:
            self._epoch += 1
            self._current_request = None
            self._confirmations.clear()

    def _record(
        self, pending: PendingClarification, outcome: ClarificationOutcome
    ) -> None:
        self._evidence.append(
            ClarificationEvidence(
                pending.identity.lease_id,
                pending.request.action_id,
                pending.spec.reason.value,
                self.clock.monotonic_seconds(),
                outcome.value,
            )
        )
