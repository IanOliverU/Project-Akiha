"""Qt workers for constrained LLM proposals and local media resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    DirectorySearchMatch,
    FileSearchMatch,
)
from project_akiha.core.actions.registry import (
    DIRECTORY_SEARCH_ACTION,
    FILE_SEARCH_ACTION,
)
from project_akiha.services.assistant_action_bridge import AssistantActionBridge
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolProposal,
    LLMAssistantToolGateway,
    build_media_search_queries,
    filter_directory_matches,
    filter_media_matches,
)


@dataclass(frozen=True, slots=True)
class MediaSearchOutcome:
    """Sanitized local matches collected from approved searchable roots."""

    matches: tuple[FileSearchMatch, ...]
    searched_roots: int


@dataclass(frozen=True, slots=True)
class DirectorySearchOutcome:
    """Sanitized directory matches collected from approved searchable roots."""

    matches: tuple[DirectorySearchMatch, ...]
    searched_roots: int


class AssistantToolProposalThread(QThread):
    """Ask the selected LLM for one validated, non-executable proposal."""

    proposal_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        gateway: LLMAssistantToolGateway,
        user_text: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._gateway = gateway
        self._user_text = user_text
        self._is_cancel_requested = False

    def run(self) -> None:
        """Generate one proposal away from the Qt event loop."""
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            proposal = asyncio.run(self._gateway.propose(self._user_text))
        except Exception as error:
            self.failed.emit(str(error))
            return
        if self._is_cancelled():
            self.cancelled.emit()
        else:
            self.proposal_ready.emit(proposal)

    def cancel(self) -> None:
        """Discard any eventual LLM result."""
        self._is_cancel_requested = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()


class AssistantMediaSearchThread(QThread):
    """Search approved roots and filter local results to passive media."""

    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        bridge: AssistantActionBridge,
        proposal: AssistantToolProposal,
        roots: tuple[str, ...],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._proposal = proposal
        self._roots = roots
        self._cancellation_token = ActionCancellationToken()

    def run(self) -> None:
        """Run bounded registered searches away from the Qt event loop."""
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            outcome = asyncio.run(self._search())
        except Exception as error:
            self.failed.emit(str(error))
            return
        if self._is_cancelled():
            self.cancelled.emit()
        else:
            self.result_ready.emit(outcome)

    def cancel(self) -> None:
        """Request cooperative cancellation for the current search."""
        self._cancellation_token.cancel()
        self.requestInterruption()

    async def _search(self) -> MediaSearchOutcome:
        collected: list[FileSearchMatch] = []
        searched_roots: set[str] = set()
        for query in build_media_search_queries(self._proposal):
            for root in self._roots:
                if self._is_cancelled():
                    break
                request = ActionRequest(
                    correlation_id=f"llm-media-{uuid4().hex}",
                    action_id=FILE_SEARCH_ACTION,
                    source="llm_proposal",
                    parameters={
                        "query": query,
                        "root": root,
                        "media_only": True,
                    },
                )
                dispatch = await self._bridge.dispatch(
                    request,
                    cancellation_token=self._cancellation_token,
                )
                searched_roots.add(root)
                matches = dispatch.result.metadata.get("matches")
                if not isinstance(matches, tuple):
                    continue
                collected.extend(
                    match for match in matches if isinstance(match, FileSearchMatch)
                )
            filtered = filter_media_matches(tuple(collected), self._proposal)
            if filtered or self._is_cancelled():
                return MediaSearchOutcome(
                    matches=filtered,
                    searched_roots=len(searched_roots),
                )

        return MediaSearchOutcome(
            matches=(),
            searched_roots=len(searched_roots),
        )

    def _is_cancelled(self) -> bool:
        return self._cancellation_token.is_cancelled or self.isInterruptionRequested()


class AssistantDirectorySearchThread(QThread):
    """Resolve one directory intent beneath approved searchable roots."""

    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        bridge: AssistantActionBridge,
        proposal: AssistantToolProposal,
        roots: tuple[str, ...],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._proposal = proposal
        self._roots = roots
        self._cancellation_token = ActionCancellationToken()

    def run(self) -> None:
        """Run bounded registered directory searches off the Qt event loop."""
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            outcome = asyncio.run(self._search())
        except Exception as error:
            self.failed.emit(str(error))
            return
        if self._is_cancelled():
            self.cancelled.emit()
        else:
            self.result_ready.emit(outcome)

    def cancel(self) -> None:
        """Request cooperative cancellation for directory discovery."""
        self._cancellation_token.cancel()
        self.requestInterruption()

    async def _search(self) -> DirectorySearchOutcome:
        collected: list[DirectorySearchMatch] = []
        searched_roots: set[str] = set()
        for match_all in (False, True):
            for root in self._roots:
                if self._is_cancelled():
                    break
                request = ActionRequest(
                    correlation_id=f"directory-navigation-{uuid4().hex}",
                    action_id=DIRECTORY_SEARCH_ACTION,
                    source="directory_navigation",
                    parameters={
                        "query": self._proposal.directory_name,
                        "root": root,
                        "match_all": match_all,
                    },
                )
                dispatch = await self._bridge.dispatch(
                    request,
                    cancellation_token=self._cancellation_token,
                )
                searched_roots.add(root)
                matches = dispatch.result.metadata.get("matches")
                if not isinstance(matches, tuple):
                    continue
                collected.extend(
                    match
                    for match in matches
                    if isinstance(match, DirectorySearchMatch)
                )
            filtered = filter_directory_matches(
                tuple(collected),
                self._proposal,
            )
            if filtered or self._is_cancelled():
                return DirectorySearchOutcome(
                    matches=filtered,
                    searched_roots=len(searched_roots),
                )
        return DirectorySearchOutcome(
            matches=(),
            searched_roots=len(searched_roots),
        )

    def _is_cancelled(self) -> bool:
        return self._cancellation_token.is_cancelled or self.isInterruptionRequested()
