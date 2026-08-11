"""Qt worker for permission-gated Ollama native tool turns."""

from __future__ import annotations

import asyncio
import threading
import time

from PySide6.QtCore import QThread, Signal

from project_akiha.app.chat_controller import ChatController
from project_akiha.core.actions import ProviderActionToolCatalog
from project_akiha.core.voice_session import SanitizedActionResult
from project_akiha.providers.ai import OllamaProvider, OllamaProviderError
from project_akiha.services.intent_arbitration import IntentArbiter
from project_akiha.services.modular_provider_turn_authority import (
    ModularProviderTurnAuthority,
)
from project_akiha.services.provider_action_dispatcher import (
    ProviderActionConfirmation,
    ProviderActionDispatcher,
    ProviderActionService,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
)

_CONFIRMATION_TIMEOUT_SECONDS = 300.0


class OllamaNativeToolThread(QThread):
    """Own one Ollama tool exchange without granting provider authority."""

    response_ready = Signal(object)
    action_result = Signal(object)
    confirmation_requested = Signal(object)
    native_tools_unavailable = Signal()
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        *,
        provider: OllamaProvider,
        chat_controller: ChatController,
        message: str,
        catalog: ProviderActionToolCatalog,
        action_service: ProviderActionService,
        intent_arbiter: IntentArbiter,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._chat_controller = chat_controller
        self._message = message
        self._catalog = catalog
        self._authority = ModularProviderTurnAuthority()
        self._gateway = ProviderActionProposalGateway(catalog, self._authority)
        self._dispatcher = ProviderActionDispatcher(
            action_service,
            self._authority,
            intent_arbiter,
        )
        self._lock = threading.RLock()
        self._confirmation_decisions: dict[tuple[str, str, str], bool] = {}
        self._pending_confirmation: tuple[str, str, str] | None = None
        self._cancel_requested = False

    def run(self) -> None:
        """Run the complete native-tool turn outside the Qt event loop."""
        try:
            asyncio.run(self._run_turn())
        except Exception as error:
            if self._is_cancelled():
                self.cancelled.emit()
            else:
                self.failed.emit(_safe_error(error))
        finally:
            self._gateway.clear()
            self._dispatcher.clear()
            self._authority.close_turn()
            with self._lock:
                self._confirmation_decisions.clear()
                self._pending_confirmation = None

    def cancel(self) -> None:
        """Invalidate ownership and discard any eventual provider response."""
        with self._lock:
            self._cancel_requested = True
        self._authority.close_turn()
        self.requestInterruption()

    def resolve_confirmation(
        self,
        confirmation: ProviderActionConfirmation,
        *,
        approved: bool,
    ) -> bool:
        """Accept one boolean decision from Akiha's trusted local dialog."""
        key = (
            confirmation.session_id,
            confirmation.turn_id,
            confirmation.proposal_id,
        )
        with self._lock:
            if self._pending_confirmation != key or self._is_cancelled_locked():
                return False
            self._confirmation_decisions[key] = approved
            return True

    async def _run_turn(self) -> None:
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            supports_native_tools = await self._provider.supports_native_tools()
        except OllamaProviderError:
            if self._is_cancelled():
                self.cancelled.emit()
            else:
                self.native_tools_unavailable.emit()
            return
        if self._is_cancelled():
            self.cancelled.emit()
            return
        if not supports_native_tools:
            self.native_tools_unavailable.emit()
            return

        identity = self._authority.open_turn()
        messages = await self._chat_controller.build_provider_messages(self._message)
        turn = await self._provider.request_native_tool_turn(
            messages,
            self._catalog.schemas,
            session_id=identity.session_id,
            turn_id=identity.turn_id,
        )
        if self._is_cancelled():
            self.cancelled.emit()
            return

        if not turn.proposals:
            commit = await self._chat_controller.commit_canonical_live_turn(
                self._message,
                turn.initial_text,
            )
            self.response_ready.emit(commit)
            return

        self._dispatcher.complete_local_routing(identity.session_id, identity.turn_id)
        results: list[SanitizedActionResult] = []
        for proposal in turn.proposals:
            conversion = self._gateway.convert(proposal)
            if not conversion.decision.accepted:
                result = SanitizedActionResult(
                    session_id=proposal.session_id,
                    turn_id=proposal.turn_id,
                    proposal_id=proposal.proposal_id,
                    status="denied",
                    message="The action proposal was rejected safely.",
                )
            else:
                result = await self._dispatcher.dispatch(conversion)
            if result.status == "confirmation_required":
                confirmation = self._dispatcher.pending_confirmation(
                    session_id=result.session_id,
                    turn_id=result.turn_id,
                    proposal_id=result.proposal_id,
                )
                if confirmation is not None:
                    result = await self._resolve_confirmation(confirmation)
            results.append(result)
            self.action_result.emit(result)
            if self._is_cancelled():
                self.cancelled.emit()
                return

        final_text = await self._provider.complete_native_tool_turn(turn, results)
        if self._is_cancelled():
            self.cancelled.emit()
            return
        commit = await self._chat_controller.commit_canonical_live_turn(
            self._message,
            final_text,
        )
        self.response_ready.emit(commit)

    async def _resolve_confirmation(
        self,
        confirmation: ProviderActionConfirmation,
    ) -> SanitizedActionResult:
        key = (
            confirmation.session_id,
            confirmation.turn_id,
            confirmation.proposal_id,
        )
        with self._lock:
            self._pending_confirmation = key
        self.confirmation_requested.emit(confirmation)
        deadline = time.monotonic() + _CONFIRMATION_TIMEOUT_SECONDS
        approved: bool | None = None
        while time.monotonic() < deadline and not self._is_cancelled():
            with self._lock:
                approved = self._confirmation_decisions.pop(key, None)
            if approved is not None:
                break
            await asyncio.sleep(0.05)
        with self._lock:
            if self._pending_confirmation == key:
                self._pending_confirmation = None
        if approved is None:
            approved = False
        return await self._dispatcher.resolve_confirmation(
            session_id=confirmation.session_id,
            turn_id=confirmation.turn_id,
            proposal_id=confirmation.proposal_id,
            approved=approved,
        )

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled_locked()

    def _is_cancelled_locked(self) -> bool:
        return self._cancel_requested or self.isInterruptionRequested()


def _safe_error(error: Exception) -> str:
    return (str(error).strip() or type(error).__name__)[:4_096]
