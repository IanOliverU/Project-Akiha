"""Create and verify synthetic historical databases in a new isolated profile."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.database.migrator import DatabaseMigrator

FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures/upgrades"
STAMP = "2026-10-13T00:00:00+00:00"


def schema(connection: sqlite3.Connection) -> list[tuple]:
    """Compare every user table, index, trigger and view, including constraints."""
    return connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()


def verify_schema(database: Path) -> None:
    if not database.is_file():
        raise ValueError("Database must already exist")
    with tempfile.TemporaryDirectory() as temporary:
        reference = Path(temporary) / "reference.sqlite3"
        DatabaseMigrator(reference).apply_pending()
        with closing(sqlite3.connect(reference)) as expected:
            expected_schema = schema(expected)
            versions = expected.execute(
                "SELECT version,name FROM schema_version ORDER BY version"
            ).fetchall()
        with closing(
            sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        ) as actual:
            if schema(actual) != expected_schema:
                raise AssertionError(
                    "Complete target schema differs from bundled migrations"
                )
            if (
                actual.execute(
                    "SELECT version,name FROM schema_version ORDER BY version"
                ).fetchall()
                != versions
            ):
                raise AssertionError("Ordered migration receipts differ")
            if actual.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise AssertionError("Integrity check failed")
            if actual.execute("PRAGMA foreign_key_check").fetchall():
                raise AssertionError("Foreign key check failed")


def create_fixture(profile: Path, version: int) -> None:
    """Never accept an existing profile or read the owner's application data."""
    if version not in (14, 15):
        raise ValueError("Only historical schema 14 and 15 are supported")
    profile.mkdir(parents=True, exist_ok=False)
    database = profile / "akiha.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            (FIXTURES / "phase12-v14.sql").read_text(encoding="utf-8")
        )
        if version == 15:
            connection.executescript(
                (FIXTURES / "phase13c-v15-delta.sql").read_text(encoding="utf-8")
            )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO conversations(id,title,created_at,updated_at,closed_a"
            "t,summary) VALUES (101,'synthetic prior conversation',?,?,?,'synt"
            "hetic summary')",
            (STAMP, STAMP, STAMP),
        )
        connection.execute(
            "INSERT INTO messages(id,conversation_id,role,content,created_at,e"
            "nglish_translation) VALUES (102,101,'user','synthetic prior messa"
            "ge',?,'synthetic translation')",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO memories(id,content,source_conversation_id,created_at"
            ",updated_at,embedding_json) VALUES (103,'synthetic prior memory',"
            "101,?,?,'[0.1,0.2]')",
            (STAMP, STAMP),
        )
        connection.execute(
            "INSERT INTO assistant_action_permissions(id,capability,target,cre"
            "ated_at,revoked_at) VALUES (104,'applications.launch','notepad',?"
            ",NULL),(105,'applications.launch','vlc',?,?)",
            (STAMP, STAMP, STAMP),
        )
        connection.execute(
            "INSERT INTO assistant_action_audit(id,correlation_id,action_id,so"
            "urce,permission_decision,result_status,duration_ms,created_at) VA"
            "LUES (106,'synthetic-prior','open_directory','local','allowed','s"
            "uccess',1,?)",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO behavior_events(id,event_type,payload_json,created_at"
            ") VALUES (107,'synthetic','{}',?)",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO pet_reward_grants(id,reward_kind,event_id,xp_awarded,"
            "currency_awarded,granted_at) VALUES (108,'conversation_completed'"
            ",'synthetic-reward',1,0,?)",
            (STAMP,),
        )
        now = datetime.now(UTC).isoformat()
        connection.execute(
            "INSERT INTO pet_state VALUES (1,100,100,100,10,1,1,8,0,0,0,1,?,?,?)",
            (now, STAMP, now),
        )
        connection.execute(
            "INSERT INTO pet_state_history(id,revision,mutation_kind,current_s"
            "tate_json,created_at) VALUES (110,1,'synthetic','{}',?)",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO shop_transactions VALUES ('synthetic-purchase','synth"
            "etic-item',1,2,10,8,?)",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO shop_inventory VALUES ('synthetic-item',?,'purchase',"
            "'synthetic-purchase')",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO shop_equipment VALUES ('head','synthetic-item',?)", (STAMP,)
        )
        connection.execute(
            "UPDATE pet_appearance_selection SET appearance_id='seifuku',selected_at=?",
            (STAMP,),
        )
        connection.execute(
            "INSERT INTO external_event_receipts VALUES ('gmail',?,'synthetic'"
            ",?,'personal','normal','delivered',?,?)",
            ("a" * 64, STAMP, STAMP, STAMP),
        )
        connection.execute(
            "INSERT INTO integration_sync_state VALUES ('gmail',?,'synthetic-c"
            "ursor',?,?)",
            ("b" * 64, STAMP, STAMP),
        )
        connection.execute(
            "INSERT INTO notification_inbox(id,service,event_kind,priority,dis"
            "play_text,occurred_at,created_at,delivery_status) VALUES (109,'gm"
            "ail','synthetic','normal','synthetic prior receipt',?,?,'delivere"
            "d')",
            (STAMP, STAMP),
        )
        connection.execute(
            "UPDATE sqlite_sequence SET seq=500 WHERE name='notification_inbox'"
        )
        if version == 15:
            connection.execute(
                "INSERT INTO utility_timers VALUES ('synthetic-timer','synthetic-r"
                "equest',?,'synthetic label',60,?,?,'cancelled',?,NULL)",
                ("c" * 64, STAMP, STAMP, STAMP),
            )
        connection.commit()
        preserved = {}
        for (table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LI"
            "KE 'sqlite_%' AND name!='schema_version'"
        ):
            columns = [
                row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
            ]
            if table == "pet_state":
                # Needs/decay/revision are intentionally settled by normal startup.
                columns = ["id", "xp", "level", "currency", "created_at"]
            selected = ",".join(f'"{name}"' for name in columns)
            rows = connection.execute(
                f'SELECT {selected} FROM "{table}" ORDER BY 1'
            ).fetchall()
            if rows:
                preserved[table] = {"columns": columns, "rows": rows}
        manifest = {
            "prior_version": version,
            "preserved": preserved,
            "inbox_high_water": 500,
        }
    (profile / "upgrade-fixture.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (profile / "user_config.toml").write_text(
        '[ai]\nprovider = "mock"\n', encoding="utf-8"
    )


def verify_fixture(profile: Path) -> None:
    database = profile / "akiha.sqlite3"
    manifest = json.loads(
        (profile / "upgrade-fixture.json").read_text(encoding="utf-8")
    )
    verify_schema(database)
    with closing(
        sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    ) as connection:
        for table, expected in manifest["preserved"].items():
            columns = ",".join(f'"{name}"' for name in expected["columns"])
            for row in expected["rows"]:
                current = connection.execute(
                    f'SELECT {columns} FROM "{table}" '
                    f'WHERE "{expected["columns"][0]}"=?',
                    (row[0],),
                ).fetchone()
                if current is None or list(current) != row:
                    raise AssertionError(f"Prior records changed: {table}")
        high_water = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='notification_inbox'"
        ).fetchone()[0]
        if high_water < manifest["inbox_high_water"]:
            raise AssertionError("Inbox issued identifiers regressed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "verify", "schema"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--prior-version", type=int, choices=(14, 15), default=14)
    args = parser.parse_args()
    if args.operation == "create":
        create_fixture(args.path, args.prior_version)
    elif args.operation == "verify":
        verify_fixture(args.path)
    else:
        verify_schema(args.path)
    print(f"Upgrade fixture {args.operation}: PASS")


if __name__ == "__main__":
    main()
