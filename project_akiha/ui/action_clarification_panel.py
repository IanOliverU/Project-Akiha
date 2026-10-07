"""Transient local questions and answers, deliberately outside the transcript."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PureWindowsPath

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.actions.models import ActionRequest


class ActionClarificationPanel(QWidget):
    """Marshal lease changes to Qt; never append, publish, persist, or speak text."""

    refresh_requested = Signal()
    normal_chat_requested = Signal(object)
    spotify_history_requested = Signal(object)

    def __init__(
        self,
        controller: ActionClarificationController,
        on_resolved: Callable[[ActionRequest], None],
        parent: QWidget | None = None,
        *,
        on_owned_resolved: Callable[[ActionRequest, int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_resolved = on_resolved
        self._on_owned_resolved = on_owned_resolved
        self._identity = None
        self._spotify_lease = None
        self._spotify_mode = QComboBox()
        self._spotify_mode.addItems(
            ["Recently played (up to 10 distinct tracks)", "Search by song and artist"]
        )
        self._spotify_mode.hide()
        self._spotify_mode.currentIndexChanged.connect(self._switch_spotify_mode)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._choices = QComboBox()
        self._answer = QLineEdit()
        self._artist = QLineEdit()
        self._artist.setPlaceholderText("Artist (optional; stays local)")
        self._artist.hide()
        self._answer.setPlaceholderText(
            "Local answer (not saved or sent to a provider)"
        )
        self._submit = QPushButton("Use this answer")
        self._any = QPushButton("Open any of these")
        self._normal_chat = QPushButton("Continue as normal chat")
        self._normal_chat.hide()
        self._normal_chat.clicked.connect(self._allow_normal_chat)
        cancel = QPushButton("Cancel action")
        row = QHBoxLayout()
        for widget in (self._submit, self._any, cancel):
            row.addWidget(widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._spotify_mode)
        layout.addWidget(self._choices)
        layout.addWidget(self._answer)
        layout.addWidget(self._artist)
        layout.addLayout(row)
        layout.addWidget(self._normal_chat)
        self._submit.clicked.connect(lambda: self._resolve())
        self._answer.returnPressed.connect(lambda: self._resolve())
        self._any.clicked.connect(lambda: self._resolve(open_any=True))
        cancel.clicked.connect(lambda: self._resolve(cancel=True))
        self.refresh_requested.connect(self.refresh)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.hide()

    def show_notice(self, text: str) -> None:
        """Display a fixed local notice where no exact operation can be bound."""
        self._identity = None
        self._normal_chat.hide()
        self._label.setText(text)
        self._answer.clear()
        self._artist.clear()
        self._choices.clear()
        for widget in (
            self._choices,
            self._answer,
            self._artist,
            self._spotify_mode,
            self._submit,
            self._any,
        ):
            widget.hide()
        self.show()

    def show_privacy_notice(self) -> None:
        """Reject composer material without retaining it or replacing the lease."""
        self._answer.clear()
        pending = self._controller.leases.pending
        instruction = (
            "Select an offered local choice"
            if pending is not None
            and pending.local_targets is not None
            and pending.choices
            else (
                "Configure an eligible app or approved folder in Settings"
                if pending is not None and pending.local_targets is not None
                else "Use the local answer field"
            )
        )
        self._label.setText(
            "Path-like text stayed local and was not saved or sent. "
            + instruction
            + ", or type your message again in the "
            "composer and click Continue as normal chat."
        )
        self._normal_chat.setVisible(
            pending is not None
            and pending.request.action_id.startswith(("files.", "directories."))
        )
        self.show()

    def _allow_normal_chat(self) -> None:
        if self._controller.allows_normal_chat(self._identity):
            self.normal_chat_requested.emit(self._identity)

    def refresh(self) -> None:
        pending = self._controller.leases.pending
        if pending is None:
            if self._identity is not None:
                self._identity = None
                self._answer.clear()
                self._artist.clear()
                self._artist.hide()
                self._spotify_mode.hide()
                self._spotify_lease = None
                self._choices.clear()
                self._label.clear()
                self._normal_chat.hide()
                self.hide()
            return
        if self._identity == pending.identity:
            return
        self._identity = pending.identity
        spotify = (
            pending.request.action_id == "spotify.play_track"
            and pending.request.source == "chat"
            and "track_query" not in pending.request.parameters
            and pending.spec.missing_parameters == ("track_query",)
        )
        if spotify and self._spotify_lease != pending.identity.lease_id:
            self._spotify_lease = pending.identity.lease_id
            self._spotify_mode.blockSignals(True)
            self._spotify_mode.setCurrentIndex(0)
            self._spotify_mode.blockSignals(False)
        self._spotify_mode.setVisible(spotify)
        search_mode = spotify and self._spotify_mode.currentIndex() == 1
        history_mode = spotify and not search_mode
        self._normal_chat.setVisible(
            pending.request.action_id.startswith(("files.", "directories."))
        )
        self._normal_chat.setToolTip(
            "Send the current composer text as ordinary chat: "
            "it will be saved and sent to the selected provider."
        )
        self._answer.clear()
        self._artist.clear()
        self._choices.clear()
        operation = pending.request.action_id.rsplit(".", 1)[-1].replace("_", " ")
        field_name = (
            pending.spec.missing_parameters[0]
            if pending.spec.missing_parameters
            else "target"
        )
        questions = {
            "application_id": "Which allowlisted application?",
            "path": "Which approved local file or directory?",
            "root": "Which approved local search root?",
            "query": "What should I search for?",
            "track_query": (
                "Which song would you like to play on Spotify? Enter its title."
            ),
            "position_seconds": "What position in seconds (a whole number)?",
            "enabled": "Should shuffle be enabled? Enter true or false.",
        }
        self._label.setText(
            "Choose the exact target for this action. "
            "This question expires after 120 seconds."
            if pending.choices
            else questions.get(field_name, "Supply the missing target or parameter.")
        )
        self._label.setText(operation.capitalize() + ": " + self._label.text())
        if pending.local_targets is not None and (
            not pending.choices
            or (
                pending.local_targets.enabled and not any(pending.local_targets.enabled)
            )
        ):
            self._label.setText(pending.local_targets.empty_message)
        if pending.spec.truncated:
            self._label.setText(
                self._label.text() + " This is a bounded or incomplete set of matches."
            )
        if pending.spec.cloud_origin:
            self._label.setText(
                self._label.text()
                + " Cloud audio is paused; answer here, then restart voice explicitly."
            )
        if history_mode:
            self._label.setText(
                "Spotify recently played — up to 10 distinct tracks "
                "from the latest 20 plays. "
                + (
                    pending.local_targets.empty_message
                    if pending.local_targets is not None
                    and not any(pending.local_targets.enabled)
                    else "Choose an entry; nothing plays until you select it."
                )
                + (" Cloud audio remains paused." if pending.spec.cloud_origin else "")
            )
        for index, request in enumerate(pending.choices, 1):
            if pending.local_targets is not None:
                self._choices.addItem(
                    pending.local_targets.labels[index - 1],
                    pending.choice_ids[index - 1],
                )
                if pending.spec.local_music_catalog:
                    self._choices.setItemData(
                        index - 1,
                        request.parameters["path"],
                        Qt.ItemDataRole.ToolTipRole,
                    )
                if pending.local_targets.enabled:
                    item = self._choices.model().item(index - 1)
                    item.setEnabled(pending.local_targets.enabled[index - 1])
                continue
            parameters = request.parameters
            label = next(
                (
                    str(parameters[key])
                    for key in (
                        "track_name",
                        "playlist_name",
                        "album_name",
                        "artist_name",
                        "path",
                    )
                    if key in parameters
                ),
                f"Choice {index}",
            )
            if "path" in parameters:
                label = PureWindowsPath(label).name
            self._choices.addItem(f"{index}. {label}")
        self._choices.setVisible(bool(pending.choices))
        self._answer.setVisible(not pending.choices and pending.local_targets is None)
        self._artist.setVisible(search_mode)
        if search_mode:
            self._answer.setPlaceholderText("Song title (stays local)")
        else:
            self._answer.setPlaceholderText(
                "Local answer (not saved or sent to a provider)"
            )
        if history_mode:
            self._answer.hide()
        self._submit.setVisible(bool(pending.choices) or pending.local_targets is None)
        self._submit.setEnabled(True)
        self._submit.setText(
            "Play selected entry" if history_mode else "Use this answer"
        )
        if history_mode and not pending.choices:
            self._submit.hide()
        if pending.local_targets is not None and pending.local_targets.enabled:
            first_enabled = next(
                (
                    i
                    for i, enabled in enumerate(pending.local_targets.enabled)
                    if enabled
                ),
                -1,
            )
            self._choices.setCurrentIndex(first_enabled)
            self._submit.setEnabled(first_enabled >= 0)
        self._any.setVisible(
            bool(pending.choices)
            and pending.local_targets is None
            and pending.request.action_id in {"files.open", "files.open_directory"}
        )
        self.show()
        if history_mode and pending.local_targets is None:
            self._label.setText(
                "Loading Spotify recently played locally… "
                "You can also search by song and artist."
            )
            self.spotify_history_requested.emit(pending.identity)

    def _switch_spotify_mode(self) -> None:
        if self._identity is not None and self._controller.leases.spotify_search_mode(
            self._identity
        ):
            self.refresh()

    def _resolve(self, *, cancel: bool = False, open_any: bool = False) -> None:
        if self._identity is None:
            self.hide()
            return
        pending = self._controller.leases.pending
        local_catalog = pending is not None and pending.local_targets is not None
        answer = ClarificationAnswer(
            self._identity,
            ClarificationAnswerSource.LOCAL_UI,
            "" if local_catalog else self._answer.text(),
            (
                self._choices.currentIndex() + 1
                if self._choices.count() and not local_catalog
                else None
            ),
            cancel=cancel,
            open_any=open_any,
            choice_id=self._choices.currentData() if local_catalog else None,
            artist_query=self._artist.text() if not self._artist.isHidden() else "",
        )
        self._answer.clear()
        self._artist.clear()
        result = self._controller.resolve(answer)
        self.refresh()
        if result.outcome is ClarificationOutcome.INVALID and local_catalog:
            self._label.setText(
                "This local choice is unavailable. "
                "Check permissions and issue the action again."
            )
            self.show()
        if (
            result.outcome is ClarificationOutcome.RESOLVED
            and result.request is not None
        ):
            if self._on_owned_resolved is not None:
                assert result.identity is not None
                self._on_owned_resolved(result.request, result.identity.owner_epoch)
            else:
                self._on_resolved(result.request)
