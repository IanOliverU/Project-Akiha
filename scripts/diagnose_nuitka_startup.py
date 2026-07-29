"""Small diagnostic entry point for frozen startup crashes."""

from __future__ import annotations


def main() -> int:
    """Import startup modules one-by-one and print progress markers."""
    print("diagnostic start", flush=True)
    print("importing PySide6.QtCore", flush=True)
    import PySide6.QtCore as qt_core

    print(f"imported {qt_core.__name__}", flush=True)
    print("importing PySide6.QtWidgets", flush=True)
    import PySide6.QtWidgets as qt_widgets

    print(f"imported {qt_widgets.__name__}", flush=True)
    print("importing project_akiha.config", flush=True)
    import project_akiha.config as akiha_config

    print(f"imported {akiha_config.__name__}", flush=True)
    print("importing project_akiha.services.app_paths", flush=True)
    import project_akiha.services.app_paths as app_paths

    print(f"imported {app_paths.__name__}", flush=True)
    print("importing project_akiha.services.logging", flush=True)
    import project_akiha.services.logging as logging_service

    print(f"imported {logging_service.__name__}", flush=True)
    print("importing project_akiha.database", flush=True)
    import project_akiha.database as database

    print(f"imported {database.__name__}", flush=True)
    print("importing project_akiha.ui.pet_window", flush=True)
    import project_akiha.ui.pet_window as pet_window

    print(f"imported {pet_window.__name__}", flush=True)
    print("importing project_akiha.ui.tray", flush=True)
    import project_akiha.ui.tray as tray

    print(f"imported {tray.__name__}", flush=True)
    print("importing project_akiha.app.main", flush=True)
    import project_akiha.app.main as app_main

    print(f"imported {app_main.__name__}", flush=True)
    print("diagnostic complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
