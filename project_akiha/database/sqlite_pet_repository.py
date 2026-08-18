"""SQLite persistence for Akiha's revisioned pet-state aggregate."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from project_akiha.core.pet import (
    PetBandTransition,
    PetDecayProgress,
    PetMutationKind,
    PetNeed,
    PetProgression,
    PetRewardGrant,
    PetRewardKind,
    PetState,
    PetStateConflictError,
    PetStateHistoryEntry,
    PetStateRecord,
    PetWellbeing,
    WellbeingBand,
    level_for_xp,
)
from project_akiha.database.migrator import DatabaseMigrator


class SQLitePetStateRepository:
    """Atomically persist the singleton pet state and typed transition history."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def load_or_create(
        self,
        initial_state: PetState,
        evaluated_at: datetime,
    ) -> PetStateRecord:
        """Return the singleton pet state, creating it when absent."""
        _require_state(initial_state, "initial_state")
        normalized_time = _normalize_datetime(evaluated_at, "evaluated_at")
        return await asyncio.to_thread(
            self._load_or_create,
            initial_state,
            normalized_time,
        )

    async def load(self) -> PetStateRecord | None:
        """Return the persisted pet state when it exists."""
        return await asyncio.to_thread(self._load)

    async def save_transition(
        self,
        *,
        expected_revision: int,
        previous_state: PetState,
        current_state: PetState,
        evaluated_at: datetime,
        mutation_kind: PetMutationKind,
        band_transitions: tuple[PetBandTransition, ...] = (),
        record_history: bool,
        reward_grant: PetRewardGrant | None = None,
    ) -> PetStateRecord:
        """Commit one compare-and-swap state transition and optional history."""
        if type(expected_revision) is not int:
            raise TypeError("expected_revision must be an integer.")
        if expected_revision < 0:
            raise ValueError("expected_revision cannot be negative.")
        _require_state(previous_state, "previous_state")
        _require_state(current_state, "current_state")
        normalized_time = _normalize_datetime(evaluated_at, "evaluated_at")
        if not isinstance(mutation_kind, PetMutationKind):
            raise TypeError("mutation_kind must be a PetMutationKind value.")
        if not isinstance(band_transitions, tuple) or any(
            not isinstance(transition, PetBandTransition)
            for transition in band_transitions
        ):
            raise TypeError(
                "band_transitions must be a tuple of PetBandTransition values."
            )
        if not isinstance(record_history, bool):
            raise TypeError("record_history must be a boolean.")
        if reward_grant is not None and not isinstance(
            reward_grant,
            PetRewardGrant,
        ):
            raise TypeError("reward_grant must be a PetRewardGrant or None.")
        _validate_progression_transition(
            previous_state,
            current_state,
            reward_grant,
        )

        return await asyncio.to_thread(
            self._save_transition,
            expected_revision,
            previous_state,
            current_state,
            normalized_time,
            mutation_kind,
            band_transitions,
            record_history,
            reward_grant,
        )

    async def get_recent_history(
        self,
        limit: int,
    ) -> tuple[PetStateHistoryEntry, ...]:
        """Return recent typed pet-state transitions newest first."""
        if type(limit) is not int:
            raise TypeError("pet-state history limit must be an integer.")
        if limit <= 0:
            raise ValueError("pet-state history limit must be greater than zero.")
        return await asyncio.to_thread(self._get_recent_history, limit)

    async def get_reward_grants(
        self,
        since: datetime,
    ) -> tuple[PetRewardGrant, ...]:
        """Return reward grants on or after one timezone-aware boundary."""
        normalized_time = _normalize_datetime(since, "since")
        return await asyncio.to_thread(self._get_reward_grants, normalized_time)

    async def find_reward_grant(
        self,
        event_id: UUID,
    ) -> PetRewardGrant | None:
        """Return the grant assigned to one structured event when present."""
        if not isinstance(event_id, UUID):
            raise TypeError("event_id must be a UUID.")
        return await asyncio.to_thread(self._find_reward_grant, event_id)

    async def reset(
        self,
        initial_state: PetState,
        evaluated_at: datetime,
    ) -> PetStateRecord:
        """Atomically restore defaults and clear pet-only history and rewards."""
        _require_state(initial_state, "initial_state")
        normalized_time = _normalize_datetime(evaluated_at, "evaluated_at")
        return await asyncio.to_thread(
            self._reset,
            initial_state,
            normalized_time,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _load_or_create(
        self,
        initial_state: PetState,
        evaluated_at: datetime,
    ) -> PetStateRecord:
        timestamp = _timestamp(evaluated_at)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = _select_state(connection)
            if row is None:
                connection.execute(
                    """
                    INSERT INTO pet_state(
                        id,
                        satiety,
                        energy,
                        attention,
                        affection,
                        xp,
                        level,
                        currency,
                        satiety_decay_seconds,
                        energy_decay_seconds,
                        attention_decay_seconds,
                        revision,
                        evaluated_at,
                        created_at,
                        updated_at
                    )
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    _state_columns(initial_state) + (timestamp, timestamp, timestamp),
                )
                _insert_history(
                    connection,
                    revision=0,
                    mutation_kind=PetMutationKind.INITIALIZED,
                    previous_state=None,
                    current_state=initial_state,
                    band_transitions=(),
                    created_at=timestamp,
                )
                row = _select_state(connection)
            connection.commit()
            return _record_from_row(_require_row(row))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _load(self) -> PetStateRecord | None:
        connection = self._connect()
        try:
            row = _select_state(connection)
        finally:
            connection.close()
        return _record_from_row(row) if row is not None else None

    def _save_transition(
        self,
        expected_revision: int,
        previous_state: PetState,
        current_state: PetState,
        evaluated_at: datetime,
        mutation_kind: PetMutationKind,
        band_transitions: tuple[PetBandTransition, ...],
        record_history: bool,
        reward_grant: PetRewardGrant | None,
    ) -> PetStateRecord:
        timestamp = _timestamp(evaluated_at)
        next_revision = expected_revision + 1
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = _select_state(connection)
            if existing_row is None:
                raise PetStateConflictError("The persisted pet state is missing.")
            existing_record = _record_from_row(existing_row)
            if existing_record.revision != expected_revision:
                raise PetStateConflictError(
                    "The persisted pet-state revision changed before commit."
                )
            if existing_record.state != previous_state:
                raise PetStateConflictError(
                    "The persisted pet state does not match the expected snapshot."
                )

            cursor = connection.execute(
                """
                UPDATE pet_state
                SET satiety = ?,
                    energy = ?,
                    attention = ?,
                    affection = ?,
                    xp = ?,
                    level = ?,
                    currency = ?,
                    satiety_decay_seconds = ?,
                    energy_decay_seconds = ?,
                    attention_decay_seconds = ?,
                    revision = ?,
                    evaluated_at = ?,
                    updated_at = ?
                WHERE id = 1 AND revision = ?
                """,
                _state_columns(current_state)
                + (next_revision, timestamp, timestamp, expected_revision),
            )
            if cursor.rowcount != 1:
                raise PetStateConflictError(
                    "The persisted pet-state revision changed before commit."
                )
            if record_history:
                _insert_history(
                    connection,
                    revision=next_revision,
                    mutation_kind=mutation_kind,
                    previous_state=previous_state,
                    current_state=current_state,
                    band_transitions=band_transitions,
                    created_at=timestamp,
                )
            if reward_grant is not None:
                _insert_reward_grant(connection, reward_grant)
            row = _select_state(connection)
            connection.commit()
            return _record_from_row(_require_row(row))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _get_recent_history(
        self,
        limit: int,
    ) -> tuple[PetStateHistoryEntry, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id,
                       revision,
                       mutation_kind,
                       previous_state_json,
                       current_state_json,
                       band_transitions_json,
                       created_at
                FROM pet_state_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_history_from_row(row) for row in rows)

    def _get_reward_grants(
        self,
        since: datetime,
    ) -> tuple[PetRewardGrant, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT reward_kind,
                       event_id,
                       xp_awarded,
                       currency_awarded,
                       granted_at
                FROM pet_reward_grants
                WHERE granted_at >= ?
                ORDER BY granted_at DESC, id DESC
                """,
                (_timestamp(since),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_reward_from_row(row) for row in rows)

    def _find_reward_grant(self, event_id: UUID) -> PetRewardGrant | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT reward_kind,
                       event_id,
                       xp_awarded,
                       currency_awarded,
                       granted_at
                FROM pet_reward_grants
                WHERE event_id = ?
                """,
                (str(event_id),),
            ).fetchone()
        finally:
            connection.close()
        return _reward_from_row(row) if row is not None else None

    def _reset(
        self,
        initial_state: PetState,
        evaluated_at: datetime,
    ) -> PetStateRecord:
        timestamp = _timestamp(evaluated_at)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM pet_reward_grants")
            connection.execute("DELETE FROM pet_state_history")
            connection.execute("DELETE FROM pet_state")
            connection.execute(
                """
                INSERT INTO pet_state(
                    id,
                    satiety,
                    energy,
                    attention,
                    affection,
                    xp,
                    level,
                    currency,
                    satiety_decay_seconds,
                    energy_decay_seconds,
                    attention_decay_seconds,
                    revision,
                    evaluated_at,
                    created_at,
                    updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                _state_columns(initial_state) + (timestamp, timestamp, timestamp),
            )
            _insert_history(
                connection,
                revision=0,
                mutation_kind=PetMutationKind.RESET,
                previous_state=None,
                current_state=initial_state,
                band_transitions=(),
                created_at=timestamp,
            )
            row = _select_state(connection)
            connection.commit()
            return _record_from_row(_require_row(row))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _select_state(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute("""
        SELECT satiety,
               energy,
               attention,
               affection,
               xp,
               level,
               currency,
               satiety_decay_seconds,
               energy_decay_seconds,
               attention_decay_seconds,
               revision,
               evaluated_at,
               created_at,
               updated_at
        FROM pet_state
        WHERE id = 1
        """).fetchone()


def _record_from_row(row: sqlite3.Row) -> PetStateRecord:
    return PetStateRecord(
        state=_state_from_columns(row),
        revision=int(row["revision"]),
        evaluated_at=_datetime_from_text(row["evaluated_at"]),
        created_at=_datetime_from_text(row["created_at"]),
        updated_at=_datetime_from_text(row["updated_at"]),
    )


def _history_from_row(row: sqlite3.Row) -> PetStateHistoryEntry:
    previous_json = row["previous_state_json"]
    return PetStateHistoryEntry(
        id=int(row["id"]),
        revision=int(row["revision"]),
        mutation_kind=PetMutationKind(str(row["mutation_kind"])),
        previous_state=(
            _state_from_json(str(previous_json)) if previous_json is not None else None
        ),
        current_state=_state_from_json(str(row["current_state_json"])),
        band_transitions=_transitions_from_json(str(row["band_transitions_json"])),
        created_at=_datetime_from_text(row["created_at"]),
    )


def _reward_from_row(row: sqlite3.Row) -> PetRewardGrant:
    event_id = row["event_id"]
    return PetRewardGrant(
        kind=PetRewardKind(str(row["reward_kind"])),
        event_id=UUID(str(event_id)) if event_id is not None else None,
        xp_awarded=int(row["xp_awarded"]),
        currency_awarded=int(row["currency_awarded"]),
        granted_at=_datetime_from_text(row["granted_at"]),
    )


def _insert_history(
    connection: sqlite3.Connection,
    *,
    revision: int,
    mutation_kind: PetMutationKind,
    previous_state: PetState | None,
    current_state: PetState,
    band_transitions: tuple[PetBandTransition, ...],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO pet_state_history(
            revision,
            mutation_kind,
            previous_state_json,
            current_state_json,
            band_transitions_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            revision,
            mutation_kind.value,
            _state_to_json(previous_state) if previous_state is not None else None,
            _state_to_json(current_state),
            _transitions_to_json(band_transitions),
            created_at,
        ),
    )


def _insert_reward_grant(
    connection: sqlite3.Connection,
    grant: PetRewardGrant,
) -> None:
    connection.execute(
        """
        INSERT INTO pet_reward_grants(
            reward_kind,
            event_id,
            xp_awarded,
            currency_awarded,
            granted_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            grant.kind.value,
            str(grant.event_id) if grant.event_id is not None else None,
            grant.xp_awarded,
            grant.currency_awarded,
            _timestamp(grant.granted_at.astimezone(UTC)),
        ),
    )


def _state_columns(state: PetState) -> tuple[int, ...]:
    return (
        state.wellbeing.satiety,
        state.wellbeing.energy,
        state.wellbeing.attention,
        state.wellbeing.affection,
        state.progression.xp,
        state.progression.level,
        state.progression.currency,
        state.decay_progress.satiety_seconds,
        state.decay_progress.energy_seconds,
        state.decay_progress.attention_seconds,
    )


def _state_from_columns(row: sqlite3.Row) -> PetState:
    return PetState(
        wellbeing=PetWellbeing(
            satiety=int(row["satiety"]),
            energy=int(row["energy"]),
            attention=int(row["attention"]),
            affection=int(row["affection"]),
        ),
        progression=PetProgression(
            xp=int(row["xp"]),
            level=int(row["level"]),
            currency=int(row["currency"]),
        ),
        decay_progress=PetDecayProgress(
            satiety_seconds=int(row["satiety_decay_seconds"]),
            energy_seconds=int(row["energy_decay_seconds"]),
            attention_seconds=int(row["attention_decay_seconds"]),
        ),
    )


def _state_to_json(state: PetState) -> str:
    payload = {
        "wellbeing": {
            "satiety": state.wellbeing.satiety,
            "energy": state.wellbeing.energy,
            "attention": state.wellbeing.attention,
            "affection": state.wellbeing.affection,
        },
        "progression": {
            "xp": state.progression.xp,
            "level": state.progression.level,
            "currency": state.progression.currency,
        },
        "decay_progress": {
            "satiety_seconds": state.decay_progress.satiety_seconds,
            "energy_seconds": state.decay_progress.energy_seconds,
            "attention_seconds": state.decay_progress.attention_seconds,
        },
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _state_from_json(value: str) -> PetState:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Persisted pet state must be a JSON object.")
    wellbeing = _require_mapping(payload.get("wellbeing"), "wellbeing")
    progression = _require_mapping(payload.get("progression"), "progression")
    decay_progress = _require_mapping(
        payload.get("decay_progress"),
        "decay_progress",
    )
    return PetState(
        wellbeing=PetWellbeing(
            satiety=_exact_json_int(wellbeing, "satiety"),
            energy=_exact_json_int(wellbeing, "energy"),
            attention=_exact_json_int(wellbeing, "attention"),
            affection=_exact_json_int(wellbeing, "affection"),
        ),
        progression=PetProgression(
            xp=_exact_json_int(progression, "xp"),
            level=_exact_json_int(progression, "level"),
            currency=_exact_json_int(progression, "currency"),
        ),
        decay_progress=PetDecayProgress(
            satiety_seconds=_exact_json_int(
                decay_progress,
                "satiety_seconds",
            ),
            energy_seconds=_exact_json_int(decay_progress, "energy_seconds"),
            attention_seconds=_exact_json_int(
                decay_progress,
                "attention_seconds",
            ),
        ),
    )


def _transitions_to_json(
    transitions: tuple[PetBandTransition, ...],
) -> str:
    payload = [
        {
            "need": transition.need.value,
            "previous_band": transition.previous_band.value,
            "current_band": transition.current_band.value,
        }
        for transition in transitions
    ]
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _transitions_from_json(value: str) -> tuple[PetBandTransition, ...]:
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Persisted pet-state transitions must be a JSON array.")
    transitions = []
    for item in payload:
        mapping = _require_mapping(item, "band transition")
        transitions.append(
            PetBandTransition(
                need=PetNeed(_exact_json_string(mapping, "need")),
                previous_band=WellbeingBand(
                    _exact_json_string(mapping, "previous_band")
                ),
                current_band=WellbeingBand(_exact_json_string(mapping, "current_band")),
            )
        )
    return tuple(transitions)


def _require_state(value: object, label: str) -> None:
    if not isinstance(value, PetState):
        raise TypeError(f"{label} must be a PetState value.")


def _validate_progression_transition(
    previous_state: PetState,
    current_state: PetState,
    reward_grant: PetRewardGrant | None,
) -> None:
    previous = previous_state.progression
    current = current_state.progression
    if reward_grant is None:
        if current != previous:
            raise ValueError("progression cannot change without a reward grant.")
        return

    expected_xp = previous.xp + reward_grant.xp_awarded
    expected = PetProgression(
        xp=expected_xp,
        level=level_for_xp(expected_xp),
        currency=previous.currency + reward_grant.currency_awarded,
    )
    if current != expected:
        raise ValueError("progression must match the attached reward grant.")


def _normalize_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _datetime_from_text(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Persisted pet-state timestamps must be timezone-aware.")
    return parsed.astimezone(UTC)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Persisted pet-state {label} must be a JSON object.")
    return value


def _exact_json_int(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if type(value) is not int:
        raise ValueError(f"Persisted pet-state {key} must be an integer.")
    return value


def _exact_json_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Persisted pet-state {key} must be a string.")
    return value


def _require_row(row: sqlite3.Row | None) -> sqlite3.Row:
    if row is None:
        raise RuntimeError("Pet-state write completed without a persisted row.")
    return row
