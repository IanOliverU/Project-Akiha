"""Versioned, selected-only local exports with expiring opaque authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import monotonic
from uuid import uuid4

from project_akiha.core.actions import (
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
)
from project_akiha.core.actions.clarification import request_fingerprint
from project_akiha.core.actions.errors import ActionValidationError

EXPORT_ACTIONS = ("exports.conversations", "exports.memories")
MAX_EXPORT_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _ExportDraft:
    request: ActionRequest
    digest: str
    selected_ids: tuple[int, ...] = field(repr=False)
    destination: Path = field(repr=False)
    deadline: float
    owner_epoch: int | None = None
    confirmed: bool = False


class UserExportService:
    def __init__(
        self, database_path: Path, path_policy, *, clock=monotonic, commit_guard=None
    ):
        self.database_path = database_path
        self.path_policy = path_policy
        self.clock = clock
        self.commit_guard = commit_guard
        self._lock = RLock()
        self._drafts = {}

    def catalog(self, kind: str) -> tuple[tuple[int, str], ...]:
        with closing(sqlite3.connect(self.database_path)) as c:
            if kind == "conversations":
                rows = c.execute(
                    "SELECT id,substr(title,1,100) FROM conversations ORDER BY "
                    "updated_at DESC LIMIT 1000"
                ).fetchall()
            elif kind == "memories":
                rows = c.execute(
                    "SELECT id,substr(content,1,100) FROM memories WHERE "
                    "archived_at IS NULL ORDER BY updated_at DESC "
                    "LIMIT 1000"
                ).fetchall()
            else:
                raise ValueError("Invalid export category.")
        return tuple((row[0], row[1][:100]) for row in rows)

    def prepare(
        self, kind: str, selected_ids: tuple[int, ...], destination: Path
    ) -> ActionRequest:
        if kind not in {"conversations", "memories"}:
            raise ValueError("Invalid export category.")
        if (
            not isinstance(selected_ids, tuple)
            or not 1 <= len(selected_ids) <= 100
            or len(set(selected_ids)) != len(selected_ids)
            or any(type(i) is not int or i <= 0 for i in selected_ids)
        ):
            raise ValueError("Select 1 to 100 unique records.")
        destination = self._validate_destination(destination)
        token = uuid4().hex
        request = ActionRequest(
            "local-export-" + uuid4().hex,
            "exports." + kind,
            "ui.exports",
            {"service": "exports", "export_token": token},
        )
        draft = _ExportDraft(
            request,
            request_fingerprint(request),
            selected_ids,
            destination,
            self.clock() + 60,
        )
        with self._lock:
            self._drafts = {
                key: value
                for key, value in self._drafts.items()
                if self.clock() < value.deadline
            }
            if len(self._drafts) >= 10:
                raise ValueError("Too many pending exports.")
            self._drafts[token] = draft
        return request

    def confirmation_text(self, request: ActionRequest) -> str:
        with self._lock:
            draft = self._draft(request)
            category = request.action_id.split(".")[1]
            return (
                f"Write {len(draft.selected_ids)} selected {category} "
                f"to this new local file?\n\n{draft.destination}\n\n"
                "Exports contain selected private text. "
                "Existing files are never overwritten."
            )

    def bind_owner(self, request: ActionRequest, epoch: int):
        with self._lock:
            draft = self._draft(request)
            if (
                type(epoch) is not int
                or epoch < 0
                or (draft.owner_epoch is not None and draft.owner_epoch != epoch)
            ):
                raise ValueError("Export ownership changed.")
            self._drafts[request.parameters["export_token"]] = replace(
                draft, owner_epoch=epoch
            )

    def authorize_confirmed(self, request: ActionRequest, epoch: int):
        """Called only after the existing local confirmation lease was consumed."""
        with self._lock:
            draft = self._draft(request)
            if draft.owner_epoch != epoch:
                raise ValueError("Export confirmation owner changed.")
            self._drafts[request.parameters["export_token"]] = replace(
                draft, confirmed=True
            )

    def invalidate(self):
        with self._lock:
            self._drafts.clear()

    def _draft(self, request):
        draft = self._drafts.get(request.parameters.get("export_token"))
        if (
            draft is None
            or self.clock() >= draft.deadline
            or draft.digest != request_fingerprint(request)
            or draft.request != request
        ):
            raise ValueError("Export selection is stale or unavailable.")
        return draft

    def _validate_destination(self, destination: Path) -> Path:
        if (
            not isinstance(destination, Path)
            or not destination.is_absolute()
            or destination.suffix.casefold() != ".json"
        ):
            raise ValueError("Choose an absolute local JSON destination.")
        if str(destination).startswith(("\\\\", "//")):
            raise ValueError("Choose a local destination.")
        if ".." in destination.parts:
            raise ValueError("Export destinations cannot contain traversal.")
        if destination.exists() or not destination.parent.is_dir():
            raise ValueError("Choose a new file in an existing local folder.")
        for item in (destination, *destination.parents):
            try:
                stat = item.lstat()
            except FileNotFoundError:
                continue
            if item.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise ValueError("Export destinations cannot use reparse points.")
        try:
            return Path(self.path_policy.validate_path(str(destination)))
        except ActionValidationError as error:
            raise ValueError("Export destination is protected or invalid.") from error

    def _payload(self, draft: _ExportDraft) -> bytes:
        kind = draft.request.action_id.split(".")[1]
        records = []
        remaining = MAX_EXPORT_BYTES
        with closing(sqlite3.connect(self.database_path)) as c:
            c.execute("BEGIN")
            for identifier in draft.selected_ids:
                if kind == "conversations":
                    size = c.execute(
                        (
                            "SELECT coalesce(sum(length(CAST(content AS "
                            "BLOB))),0) FROM messages WHERE conversation_id=? "
                            "AND role IN ('user','assistant')"
                        ),
                        (identifier,),
                    ).fetchone()[0]
                    remaining -= size
                    if remaining < 0:
                        raise ValueError("Export exceeds 10 MiB.")
                    row = c.execute(
                        (
                            "SELECT id,title,created_at,closed_at FROM "
                            "conversations WHERE id=?"
                        ),
                        (identifier,),
                    ).fetchone()
                    if row is None:
                        raise ValueError("A selected conversation was removed.")
                    messages = c.execute(
                        (
                            "SELECT role,content,created_at FROM messages "
                            "WHERE conversation_id=? ORDER BY id LIMIT 10001"
                        ),
                        (identifier,),
                    ).fetchall()
                    if len(messages) > 10000:
                        raise ValueError(
                            "A selected conversation exceeds the export bound."
                        )
                    records.append(
                        {
                            "id": row[0],
                            "title": row[1],
                            "created_at": row[2],
                            "closed_at": row[3],
                            "messages": [
                                {"role": role, "text": text, "created_at": stamp}
                                for role, text, stamp in messages
                                if role in {"user", "assistant"}
                            ],
                        }
                    )
                else:
                    size = c.execute(
                        "SELECT length(CAST(content AS BLOB)) FROM memories WHERE id=?",
                        (identifier,),
                    ).fetchone()
                    remaining -= size[0] if size else 0
                    if remaining < 0:
                        raise ValueError("Export exceeds 10 MiB.")
                    row = c.execute(
                        (
                            "SELECT id,content,importance,created_at,updated_"
                            "at FROM memories WHERE id=? AND archived_at IS "
                            "NULL"
                        ),
                        (identifier,),
                    ).fetchone()
                    if row is None:
                        raise ValueError("A selected memory was removed or archived.")
                    records.append(
                        {
                            "id": row[0],
                            "text": row[1],
                            "importance": row[2],
                            "created_at": row[3],
                            "updated_at": row[4],
                        }
                    )
        section = json.dumps(
            records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(section) > MAX_EXPORT_BYTES:
            raise ValueError("Export exceeds 10 MiB.")
        document = {
            "format": "akiha.user-export",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "manifest": {
                "category": kind,
                "selected_ids": list(draft.selected_ids),
                "record_count": len(records),
                "records_sha256": hashlib.sha256(section).hexdigest(),
                "exclusions": [
                    "credentials",
                    "configuration",
                    "provider_payloads",
                    "logs",
                    "notification_receipts",
                    "voice_references",
                    "embeddings",
                    "schedule_labels",
                ],
            },
            "records": records,
        }
        result = json.dumps(
            document, ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")
        if len(result) > MAX_EXPORT_BYTES:
            raise ValueError("Export exceeds 10 MiB.")
        return result

    def write(self, request, cancellation_token) -> None:
        with self._lock:
            draft = self._draft(request)
            if not draft.confirmed:
                raise ValueError("Export requires fresh local confirmation.")
            self._drafts.pop(request.parameters["export_token"])
        if cancellation_token.is_cancelled:
            raise ValueError("Export cancelled.")
        destination = self._validate_destination(draft.destination)
        parent_identity = destination.parent.stat()
        payload = self._payload(draft)
        temporary = destination.parent / (".akiha-export-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())

            def commit():
                if cancellation_token.is_cancelled or self.clock() >= draft.deadline:
                    raise ValueError("Export cancelled or expired.")
                self._validate_destination(destination)
                current = destination.parent.stat()
                if (current.st_dev, current.st_ino) != (
                    parent_identity.st_dev,
                    parent_identity.st_ino,
                ):
                    raise ValueError("Export destination changed.")
                # Atomic publication of a complete file; a competing file wins.
                os.link(temporary, destination, follow_symlinks=False)

            if self.commit_guard is None or draft.owner_epoch is None:
                raise ValueError("Export ownership boundary is unavailable.")
            if not self.commit_guard(request, draft.owner_epoch, commit):
                raise ValueError("Export ownership was superseded.")
        finally:
            temporary.unlink(missing_ok=True)


class UserExportExecutor:
    def __init__(self, service, action_id):
        self.service = service
        self.action_id = action_id
        self.executor_id = action_id.replace(".", "_")

    async def execute(self, action, *, cancellation_token):
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(ActionStatus.CANCELLED, "Export cancelled.")
        try:
            await asyncio.to_thread(
                self.service.write, action.request, cancellation_token
            )
        except (OSError, ValueError, sqlite3.Error):
            return ActionExecutionResult(
                ActionStatus.FAILED,
                (
                    "Export was not completed. Check selection, "
                    "expiry and a new writable local JSON "
                    "destination. Existing files are preserved."
                ),
            )
        return ActionExecutionResult(
            ActionStatus.SUCCESS,
            "Selected records exported to the confirmed local destination.",
        )
