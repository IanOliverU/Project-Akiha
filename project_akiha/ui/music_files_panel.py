"""Local reference registration by file picker or trusted Qt file drops."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from project_akiha.config import MusicFilesConfig
from project_akiha.core.actions import ApprovedDirectory
from project_akiha.services.music_file_catalog import MAX_MUSIC_DROP, MusicFileCatalog


class _MusicDropList(QListWidget):
    files_dropped = Signal(object)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    @staticmethod
    def local_paths(event: QDragEnterEvent | QDropEvent) -> tuple[str, ...] | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        urls = mime.urls()
        if not 1 <= len(urls) <= MAX_MUSIC_DROP or any(
            not url.isLocalFile() or url.host() or not url.isValid() for url in urls
        ):
            return None
        # Qt decodes its local-file transport once. Never decode the filesystem
        # value again or treat provider text / ordinary text drops as file paths.
        return tuple(url.toLocalFile() for url in urls)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.local_paths(event) is None:
            event.ignore()
        else:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self.local_paths(event)
        if paths is None:
            event.ignore()
            return
        self.files_dropped.emit(paths)
        # Registration copies references; never accept a move of the source files.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()


class MusicFilesPanel(QWidget):
    files_changed = Signal(object)
    registration_requested = Signal(object, object)
    open_requested = Signal(str)
    permissions_requested = Signal()

    def __init__(
        self,
        config: MusicFilesConfig,
        catalog: MusicFileCatalog,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._catalog = catalog
        self._directories: tuple[ApprovedDirectory, ...] = ()
        instruction = QLabel(
            "Drop music files or album folders into the list below. "
            "Folder scans include subfolders, up to 200 songs per drop. "
            "Their existing locations are saved locally; "
            "the files stay where they are.\n"
            "Say ‘Open a music file’ to choose from your registered list."
        )
        instruction.setWordWrap(True)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search registered music filenames")
        self._search.textChanged.connect(lambda _: self.refresh())
        self._list = _MusicDropList(self)
        self._list.setMinimumHeight(260)
        self._list.setObjectName("musicFileDropList")
        self._list.files_dropped.connect(self.register)
        self._list.itemSelectionChanged.connect(self._update_buttons)
        self._add = QPushButton("Add files")
        self._add.clicked.connect(self._browse)
        self._add_folder = QPushButton("Add folder")
        self._add_folder.clicked.connect(self._browse_folder)
        self._remove = QPushButton("Remove from list")
        self._remove.setToolTip(
            "Files and folder permissions are left in place. "
            "Revoke folder permissions in Actions settings."
        )
        self._remove.clicked.connect(self._remove_selected)
        self._open = QPushButton("Open selected")
        self._open.clicked.connect(self._open_selected)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        for button in (self._add, self._add_folder, self._remove, self._open, refresh):
            row.addWidget(button)
        permission_row = QHBoxLayout()
        permission_note = QLabel(
            "Adding music approves its containing folder for opening; adding an "
            "album folder approves that folder, including subfolders. "
            "File opening still requires confirmation. Revoke approval in Actions."
        )
        permission_note.setWordWrap(True)
        permissions = QPushButton("Folder permissions")
        permissions.clicked.connect(self.permissions_requested.emit)
        permission_row.addWidget(permission_note, 1)
        permission_row.addWidget(permissions)
        self._status = QLabel(
            "MP3, WAV, FLAC, OGG and M4A • up to 1,000 registered files."
        )
        self._status.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(instruction)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)
        layout.addLayout(row)
        layout.addLayout(permission_row)
        layout.addWidget(self._status)
        self.refresh()

    def set_config(self, config: MusicFilesConfig) -> None:
        self._config = config
        self.refresh()

    def set_directories(self, directories: tuple[ApprovedDirectory, ...]) -> None:
        self._directories = directories
        self.refresh()

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def register(self, paths: tuple[str, ...]) -> None:
        try:
            result = self._catalog.register(self._config, paths)
        except ValueError:
            self.set_status("Add at most 200 local files or folders at a time.")
            return
        self.set_status(
            f"Added {result.added}; already registered {result.duplicates}; "
            f"unsupported, unavailable or over the limit {result.rejected}."
            + (
                " Folder scan limited; add remaining files or subfolders separately."
                if result.limited
                else ""
            )
        )
        if result.added:
            self.set_config(result.config)
        if result.approval_roots:
            self.registration_requested.emit(result.config, paths)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Register music files",
            "",
            "Music files (*.mp3 *.wav *.flac *.ogg *.m4a)",
        )
        if paths:
            self.register(tuple(paths))

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Register an album folder")
        if folder:
            self.register((folder,))

    def refresh(self) -> None:
        selected = {
            item.data(Qt.ItemDataRole.UserRole) for item in self._list.selectedItems()
        }
        query = self._search.text().strip().casefold()
        self._list.clear()
        for path in self._config.paths:
            filename = Path(path).name
            if query and query not in filename.casefold():
                continue
            status = self._catalog.status(path, self._directories)
            item = QListWidgetItem(f"{filename} — {Path(path).parent.name} — {status}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._list.addItem(item)
            item.setSelected(path in selected)
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self._list.selectedItems()
        self._remove.setEnabled(bool(selected))
        self._open.setEnabled(
            len(selected) == 1
            and self._catalog.status(
                selected[0].data(Qt.ItemDataRole.UserRole), self._directories
            )
            == "Ready"
        )

    def _remove_selected(self) -> None:
        selected = {
            item.data(Qt.ItemDataRole.UserRole) for item in self._list.selectedItems()
        }
        if selected:
            config = MusicFilesConfig(
                tuple(p for p in self._config.paths if p not in selected)
            )
            self.set_config(config)
            self.set_status(
                "Removed from the registered list. Files were left in place."
            )
            self.files_changed.emit(config)

    def _open_selected(self) -> None:
        selected = self._list.selectedItems()
        if len(selected) == 1:
            path = selected[0].data(Qt.ItemDataRole.UserRole)
            if self._catalog.status(path, self._directories) == "Ready":
                self.open_requested.emit(path)
