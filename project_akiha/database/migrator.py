"""SQLite migration runner."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Migration:
    """One versioned SQL migration file."""

    version: int
    name: str
    path: Path


class DatabaseMigrator:
    """Apply versioned SQL migrations to a SQLite database."""

    def __init__(
        self,
        database_path: Path,
        migrations_dir: Path | None = None,
    ) -> None:
        self._database_path = database_path
        self._migrations_dir = migrations_dir or Path(__file__).with_name("migrations")

    def apply_pending(self) -> None:
        """Create or update the database schema."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            _ensure_schema_version_table(connection)

            applied_versions = _applied_versions(connection)
            for migration in self._load_migrations():
                if migration.version in applied_versions:
                    continue
                sql = migration.path.read_text(encoding="utf-8")
                connection.executescript(sql)
                connection.execute(
                    """
                    INSERT INTO schema_version(version, name)
                    VALUES (?, ?)
                    """,
                    (migration.version, migration.name),
                )
            connection.commit()
        finally:
            connection.close()

    def _load_migrations(self) -> tuple[Migration, ...]:
        migrations: list[Migration] = []
        for path in sorted(self._migrations_dir.glob("*.sql")):
            version_text, _, name = path.stem.partition("_")
            if not version_text.isdigit():
                message = f"Migration filename must start with a version: {path.name}"
                raise ValueError(message)
            migrations.append(
                Migration(
                    version=int(version_text),
                    name=name,
                    path=path,
                )
            )

        return tuple(migrations)


def _ensure_schema_version_table(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute("SELECT version FROM schema_version").fetchall()
    return {int(row[0]) for row in rows}
