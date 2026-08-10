"""Versioned first-run privacy notice policy."""

from __future__ import annotations

from dataclasses import replace

from project_akiha.config import PrivacyConfig

CURRENT_PRIVACY_NOTICE_VERSION = 5
CURRENT_HOSTED_LIVE_PRIVACY_NOTICE_VERSION = 1


def privacy_notice_required(config: PrivacyConfig) -> bool:
    """Return whether the current privacy notice still needs acknowledgement."""
    return config.notice_version_acknowledged < CURRENT_PRIVACY_NOTICE_VERSION


def acknowledge_current_privacy_notice(config: PrivacyConfig) -> PrivacyConfig:
    """Return acknowledgement state for the current notice version."""
    return replace(
        config,
        notice_version_acknowledged=CURRENT_PRIVACY_NOTICE_VERSION,
    )


def hosted_live_privacy_notice_required(config: PrivacyConfig) -> bool:
    """Return whether hosted microphone audio still needs acknowledgement."""
    return (
        config.hosted_live_notice_version_acknowledged
        < CURRENT_HOSTED_LIVE_PRIVACY_NOTICE_VERSION
    )


def acknowledge_current_hosted_live_privacy_notice(
    config: PrivacyConfig,
) -> PrivacyConfig:
    """Return acknowledgement state for the current hosted-audio notice."""
    return replace(
        config,
        hosted_live_notice_version_acknowledged=(
            CURRENT_HOSTED_LIVE_PRIVACY_NOTICE_VERSION
        ),
    )
