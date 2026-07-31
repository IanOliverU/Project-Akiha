"""Qt workers for constrained LLM proposals and local media resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    FileSearchMatch,
)
from project_akiha.core.actions.registry import FILE_SEARCH_ACTION
from project_akiha.services.assistant_action_bridge import AssistantActionBridge
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolProposal,
    LLMAssistantToolGateway,
    filter_media_matches,
)


@dataclass(frozen=True, slots=True)
class MediaSearchOutcome:
    """Sanitized local matches collected from approved searchable roots."""

    matches: tuple[FileSearchMatch, ...]
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
        searched_roots = 0
        for root in self._roots:
            if self._is_cancelled():
                break
            request = ActionRequest(
                correlation_id=f"llm-media-{uuid4().hex}",
                action_id=FILE_SEARCH_ACTION,
                source="llm_proposal",
                parameters={
                    "query": self._proposal.title,
                    "root": root,
                },
            )
            dispatch = await self._bridge.dispatch(
                request,
                cancellation_token=self._cancellation_token,
            )
            searched_roots += 1
            matches = dispatch.result.metadata.get("matches")
            if not isinstance(matches, tuple):
                continue
            collected.extend(
                match for match in matches if isinstance(match, FileSearchMatch)
            )

        return MediaSearchOutcome(
            matches=filter_media_matches(tuple(collected), self._proposal),
            searched_roots=searched_roots,
        )

    def _is_cancelled(self) -> bool:
        return self._cancellation_token.is_cancelled or self.isInterruptionRequested()
