"""Versioned first-run privacy notice policy."""

from __future__ import annotations

from dataclasses import replace

from project_akiha.config import PrivacyConfig

CURRENT_PRIVACY_NOTICE_VERSION = 2


def privacy_notice_required(config: PrivacyConfig) -> bool:
    """Return whether the current privacy notice still needs acknowledgement."""
    return config.notice_version_acknowledged < CURRENT_PRIVACY_NOTICE_VERSION


def acknowledge_current_privacy_notice(config: PrivacyConfig) -> PrivacyConfig:
    """Return acknowledgement state for the current notice version."""
    return replace(
        config,
        notice_version_acknowledged=CURRENT_PRIVACY_NOTICE_VERSION,
    )
