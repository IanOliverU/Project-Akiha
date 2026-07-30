"""Tests for versioned privacy notice acknowledgement."""

from __future__ import annotations

import unittest

from project_akiha.config import PrivacyConfig
from project_akiha.services.privacy_notice import (
    CURRENT_PRIVACY_NOTICE_VERSION,
    acknowledge_current_privacy_notice,
    privacy_notice_required,
)


class PrivacyNoticePolicyTest(unittest.TestCase):
    """Verify first-run and versioned acknowledgement behavior."""

    def test_default_config_requires_current_notice(self) -> None:
        self.assertTrue(privacy_notice_required(PrivacyConfig()))

    def test_acknowledgement_satisfies_current_notice(self) -> None:
        acknowledged = acknowledge_current_privacy_notice(PrivacyConfig())

        self.assertEqual(
            acknowledged.notice_version_acknowledged,
            CURRENT_PRIVACY_NOTICE_VERSION,
        )
        self.assertFalse(privacy_notice_required(acknowledged))

    def test_older_acknowledgement_requires_newer_notice(self) -> None:
        previous_version = max(0, CURRENT_PRIVACY_NOTICE_VERSION - 1)

        self.assertTrue(
            privacy_notice_required(
                PrivacyConfig(notice_version_acknowledged=previous_version)
            )
        )


if __name__ == "__main__":
    unittest.main()
