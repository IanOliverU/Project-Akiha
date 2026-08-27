"""Official metadata-only Gmail integration."""

from project_akiha.integrations.gmail.auth import (
    GMAIL_METADATA_SCOPE,
    GmailOAuthError,
    GmailToken,
)
from project_akiha.integrations.gmail.client import GmailApiClient, GmailApiError
from project_akiha.integrations.gmail.provider import GmailIntegrationProvider

__all__ = [
    "GMAIL_METADATA_SCOPE",
    "GmailApiClient",
    "GmailApiError",
    "GmailIntegrationProvider",
    "GmailOAuthError",
    "GmailToken",
]
