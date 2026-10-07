"""Shared preparation for chat, modular speech, JSON and native tool proposals."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from project_akiha.core.actions.clarification import (
    ActionClarificationReason,
    ActionClarificationSpec,
    ActionReadinessDecision,
    ActionReadinessStatus,
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
    ClarificationResolution,
    LocalTargetChoices,
    analyze_action_readiness,
)
from project_akiha.core.actions.models import ActionRequest, ActionResult
from project_akiha.core.actions.path_input import looks_like_private_path
from project_akiha.services.action_clarification import (
    ActionClarificationService,
    PendingClarification,
)
from project_akiha.services.command_envelope import DeterministicCommandEnvelopeParser


class ActionClarificationController:
    """Never executes or confirms; completed requests return to existing callers."""

    def __init__(
        self,
        leases: ActionClarificationService,
        on_pending: Callable[[], None] | None = None,
    ) -> None:
        self.leases = leases
        self.on_pending = on_pending
        self.before_pending: Callable[[], bool] | None = None
        self.local_target_choices: (
            Callable[[ActionRequest], LocalTargetChoices] | None
        ) = None
        self.validate_local_choice: Callable[[ActionRequest], bool] | None = None

    def allows_normal_chat(self, identity) -> bool:
        """Validate the foreground identity for a deliberate local panel action."""
        pending = self.leases.pending
        return (
            pending is not None
            and pending.identity == identity
            and pending.request.action_id.startswith(("files.", "directories."))
        )

    def _suspend_cloud(self, cloud_origin: bool) -> bool:
        """Suspend shared hosted ownership synchronously before publishing a lease."""
        hosted_active = (
            self.before_pending() if self.before_pending is not None else False
        )
        return cloud_origin or hosted_active

    def readiness(self, request: ActionRequest) -> ActionReadinessDecision:
        decision = analyze_action_readiness(request, self.leases.registry)
        if (
            decision.status is ActionReadinessStatus.READY
            and request.source.startswith("provider.")
        ):
            target_field = {
                "files.open": "path",
                "files.open_directory": "path",
                "files.search": "root",
                "directories.search": "root",
            }.get(request.action_id)
            value = request.parameters.get(target_field) if target_field else None
            if isinstance(value, str) and not (
                Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
            ):
                return ActionReadinessDecision(
                    ActionReadinessStatus.CLARIFICATION_REQUIRED,
                    request,
                    ActionClarificationSpec(
                        ActionClarificationReason.MISSING_TARGET, (target_field,)
                    ),
                )
        return decision

    def prepare(self, request: ActionRequest, *, cloud_origin: bool = False) -> bool:
        decision = self.readiness(request)
        try:
            owner_epoch = self.leases.claim(request)
        except (TypeError, ValueError):
            self._notify()
            return False
        if decision.status is ActionReadinessStatus.CLARIFICATION_REQUIRED:
            assert decision.spec is not None
            try:
                local_targets = (
                    self.local_target_choices(request)
                    if self.local_target_choices is not None
                    and request.source in {"chat", "chat.music"}
                    and (request.action_id, decision.spec.missing_parameters)
                    in {
                        ("applications.launch", ("application_id",)),
                        ("files.open_directory", ("path",)),
                        ("files.open", ("path",)),
                    }
                    and (
                        request.action_id != "files.open"
                        or request.source == "chat.music"
                    )
                    else None
                )
                self.leases.begin(
                    request,
                    replace(
                        decision.spec,
                        cloud_origin=self._suspend_cloud(cloud_origin),
                        choice_count=(
                            len(local_targets.requests) if local_targets else 0
                        ),
                        truncated=local_targets.truncated if local_targets else False,
                        local_music_catalog=local_targets is not None
                        and request.source == "chat.music",
                    ),
                    local_targets.requests if local_targets else (),
                    owner_epoch=owner_epoch,
                    local_targets=local_targets,
                )
            except ValueError:
                return False
            self._notify()
            return False
        if decision.status is ActionReadinessStatus.READY:
            self._notify()
            return True
        self.leases.supersede()
        self._notify()
        return False

    def choices(
        self,
        request: ActionRequest,
        choices: tuple[ActionRequest, ...],
        *,
        cloud_origin: bool = False,
        missing_parameter: str | None = None,
        limited: bool = False,
        owner_epoch: int | None = None,
        owner_request: ActionRequest | None = None,
    ) -> PendingClarification:
        maximum = 5 if request.action_id.startswith("spotify.") else 10
        truncated = limited or len(choices) > maximum
        choices = choices[:maximum]
        spec = ActionClarificationSpec(
            (
                ActionClarificationReason.MULTIPLE_MATCHES
                if choices
                else ActionClarificationReason.NO_MATCH
            ),
            (
                missing_parameter
                or self.leases.registry.resolve(request.action_id).target_parameter,
            ),
            len(choices),
            (
                cloud_origin
                if owner_request is not None
                else self._suspend_cloud(cloud_origin)
            ),
            truncated,
        )
        if owner_request is not None:
            if owner_epoch is None:
                raise ValueError("result publication requires captured ownership")
            pending = self.leases.publish_result(
                owner_request,
                owner_epoch,
                request,
                spec,
                choices,
                before_publish=lambda: self._suspend_cloud(cloud_origin),
            )
        else:
            pending = self.leases.begin(request, spec, choices, owner_epoch=owner_epoch)
        self._notify()
        return pending

    def resolve(self, answer: ClarificationAnswer) -> ClarificationResolution:
        result = self.leases.resolve(
            answer, validate_local_choice=self.validate_local_choice
        )
        self._notify()
        return result

    def handle_local_result(
        self,
        request: ActionRequest,
        result: ActionResult,
        *,
        cloud_origin: bool = False,
        owner_epoch: int | None = None,
    ) -> bool:
        """Keep ambiguous Spotify targets local and retain the exact operation."""
        from project_akiha.integrations.spotify.client import SpotifyCatalogItem

        owner_epoch = result.metadata.get("_clarification_epoch", owner_epoch)
        if owner_epoch is None:
            owner_epoch = self.leases.capture_owner(request)
        if owner_epoch is None or not self.leases.owns(request, owner_epoch):
            return True
        pending = self.leases.pending
        if (
            pending is not None
            and pending.request.correlation_id == request.correlation_id
        ):
            return True
        if (
            request.action_id == "files.search"
            and request.parameters.get("result_mode") == "open_unique"
        ):
            from project_akiha.core.actions.models import FileSearchMatch

            matches = result.metadata.get("matches")
            if isinstance(matches, tuple):
                intended = ActionRequest(
                    f"clarified-open-{uuid4().hex}", "files.open", request.source, {}
                )
                choices = tuple(
                    ActionRequest(
                        intended.correlation_id,
                        intended.action_id,
                        intended.source,
                        {"path": match.path},
                    )
                    for match in matches[:10]
                    if isinstance(match, FileSearchMatch)
                )
                try:
                    self.choices(
                        intended,
                        choices,
                        cloud_origin=cloud_origin,
                        limited=result.metadata.get("limited") is True,
                        owner_epoch=owner_epoch,
                        owner_request=request,
                    )
                except ValueError:
                    # A newer explicit action won while candidates were assembled.
                    return True
                return True
        for kind in ("track", "playlist", "album", "artist"):
            candidates = result.metadata.get(f"{kind}_candidates")
            if not isinstance(candidates, tuple) or not request.action_id.startswith(
                "spotify."
            ):
                continue
            if "search" in request.action_id:
                # Read-only catalog browsing remains an ordinary bounded result.
                return False
            choices = []
            for candidate in candidates[:5]:
                if not isinstance(candidate, SpotifyCatalogItem):
                    return False
                parameters = dict(request.parameters)
                parameters.update(
                    {
                        f"{kind}_query": candidate.name,
                        f"{kind}_name": candidate.name,
                        f"{kind}_uri": candidate.uri,
                    }
                )
                if kind in {"track", "album"} and candidate.artist_names:
                    parameters[f"{kind}_artist"] = candidate.artist_names[0]
                    parameters["artist_query"] = candidate.artist_names[0]
                if kind == "playlist":
                    parameters["playlist_owner"] = candidate.owner_name
                choices.append(
                    ActionRequest(
                        request.correlation_id,
                        request.action_id,
                        request.source,
                        parameters,
                    )
                )
            try:
                self.choices(
                    request,
                    tuple(choices),
                    cloud_origin=cloud_origin,
                    missing_parameter=f"{kind}_query",
                    owner_epoch=owner_epoch,
                    owner_request=request,
                )
            except ValueError:
                return True
            return True
        return False

    def route_answer(
        self, text: str, *, local_voice: bool = False
    ) -> ClarificationResolution | None:
        """Only exact cancel/choice/catalog replies attach to a foreground lease."""
        pending = self.leases.pending
        value = text.strip()
        match = re.fullmatch(
            r"(?:(?:open|play)\s+)?(?:(?:track|playlist|album|artist)\s+)?(?:result\s+)?([1-9]|10)",
            value,
            re.I,
        )
        cancel = value.casefold() in {"cancel", "never mind", "nevermind"}
        explicit_any = re.search(r"\b(?:open|play|choose)\s+any\b", value, re.I)
        private_path_reply = looks_like_private_path(
            value,
            embedded=pending is not None
            and pending.request.action_id.startswith(("files.", "directories.")),
        )
        if pending is None:
            stale_catalog = bool(
                self.leases.evidence
                and self.leases.evidence[-1].action_category.startswith("applications.")
                and value.casefold()
                in {"chrome", "discord", "spotify", "vlc", "vscode"}
            )
            if self.leases.evidence and (
                match or cancel or explicit_any or stale_catalog or private_path_reply
            ):
                return ClarificationResolution(ClarificationOutcome.STALE)
            return None
        if private_path_reply:
            # Only the dedicated panel accepts private free-text parameters.
            return ClarificationResolution(ClarificationOutcome.INVALID)
        catalog_reply = pending.spec.missing_parameters == (
            "application_id",
        ) and value.casefold() in {"chrome", "discord", "spotify", "vlc", "vscode"}
        if not (match or cancel or explicit_any or catalog_reply or private_path_reply):
            return None
        # Cloud-origin leases can only be answered using the dedicated local UI.
        source = (
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT
            if local_voice
            else ClarificationAnswerSource.LOCAL_TEXT
        )
        return self.resolve(
            ClarificationAnswer(
                pending.identity,
                source,
                value.casefold() if catalog_reply else value,
                int(match.group(1)) if match else None,
                cancel,
            )
        )

    def incomplete_command(
        self, text: str, correlation_id: str
    ) -> ActionRequest | None:
        if len(text) > 2000:
            return None
        # One anchored local name prefix; the existing envelope handles courtesy
        # and negation. No provider topic or arbitrary prose is rewritten.
        text = re.sub(
            r"^please\s+(?=akiha(?:\s*[,!:]|\s))",
            "",
            text.strip(),
            count=1,
            flags=re.I,
        )
        text = re.sub(
            r"^akiha(?:\s*[,!:]\s*|\s+)", "", text.strip(), count=1, flags=re.I
        )
        envelope = DeterministicCommandEnvelopeParser().parse(text)
        if envelope is None:
            return None
        command = envelope.command_text.strip().casefold().rstrip(".!?")
        actions = {
            "open app": "applications.launch",
            "open an app": "applications.launch",
            "launch app": "applications.launch",
            "close app": "applications.close",
            "close the app": "applications.close",
            "open folder": "files.open_directory",
            "open a folder": "files.open_directory",
            "open file": "files.open",
            "open a file": "files.open",
        }
        action = actions.get(command)
        if command in {"open music file", "open a music file"}:
            return ActionRequest(correlation_id, "files.open", "chat.music", {})
        if command in {
            "play music on spotify",
            "play a song on spotify",
            "play a track on spotify",
        }:
            return ActionRequest(
                correlation_id, "spotify.play_track", "chat", {"service": "spotify"}
            )
        return ActionRequest(correlation_id, action, "chat", {}) if action else None

    def supersede(self) -> None:
        self.leases.supersede()
        self._notify()

    def invalidate(self) -> None:
        self.leases.invalidate()
        self._notify()

    def _notify(self) -> None:
        if self.on_pending is not None:
            self.on_pending()
