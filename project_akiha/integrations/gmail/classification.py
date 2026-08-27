"""Deterministic local Gmail metadata classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEventKind,
    ExternalEventPriority,
)
from project_akiha.integrations.gmail.client import GmailMessageMetadata

_INTERVIEW = re.compile(
    r"(?i)(?:\b(interview|screening call|technical interview|assessment)\b|"
    r"\u9762\u63a5)"
)
_RECRUITER = re.compile(
    r"(?i)(?:\b(recruiter|recruitment|talent acquisition|hiring team)\b|\u63a1\u7528)"
)
_WORK = re.compile(r"(?i)\b(project|client|meeting|deadline|invoice|proposal|work)\b")
_NEWSLETTER = re.compile(r"(?i)\b(newsletter|digest|weekly update)\b")
_PROMOTIONAL = re.compile(r"(?i)\b(sale|discount|offer|deal|promo|coupon)\b")


@dataclass(frozen=True, slots=True)
class GmailClassificationResult:
    """Bounded deterministic classification and notification priority."""

    classification: ExternalClassification
    kind: ExternalEventKind
    priority: ExternalEventPriority


def classify_gmail_metadata(
    metadata: GmailMessageMetadata,
) -> GmailClassificationResult:
    """Classify only sender, subject, and Gmail labels."""
    text = " ".join(value for value in (metadata.sender, metadata.subject) if value)
    labels = set(metadata.label_ids)
    if _INTERVIEW.search(text):
        return GmailClassificationResult(
            ExternalClassification.INTERVIEW,
            ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
            ExternalEventPriority.IMPORTANT,
        )
    if _RECRUITER.search(text):
        return GmailClassificationResult(
            ExternalClassification.RECRUITER,
            ExternalEventKind.GMAIL_RECRUITER_CANDIDATE,
            ExternalEventPriority.IMPORTANT,
        )
    if "IMPORTANT" in labels:
        return GmailClassificationResult(
            ExternalClassification.IMPORTANT,
            ExternalEventKind.GMAIL_IMPORTANT_MESSAGE,
            ExternalEventPriority.IMPORTANT,
        )
    if _WORK.search(text):
        return GmailClassificationResult(
            ExternalClassification.WORK,
            ExternalEventKind.GMAIL_WORK_CANDIDATE,
            ExternalEventPriority.IMPORTANT,
        )
    if "CATEGORY_PROMOTIONS" in labels or _PROMOTIONAL.search(text):
        return GmailClassificationResult(
            ExternalClassification.PROMOTIONAL,
            ExternalEventKind.GMAIL_PROMOTIONAL_CANDIDATE,
            ExternalEventPriority.SILENT,
        )
    if _NEWSLETTER.search(text):
        return GmailClassificationResult(
            ExternalClassification.NEWSLETTER,
            ExternalEventKind.GMAIL_NEWSLETTER_CANDIDATE,
            ExternalEventPriority.LOW,
        )
    if "CATEGORY_PERSONAL" in labels:
        return GmailClassificationResult(
            ExternalClassification.PERSONAL,
            ExternalEventKind.GMAIL_PERSONAL_CANDIDATE,
            ExternalEventPriority.NORMAL,
        )
    return GmailClassificationResult(
        ExternalClassification.GENERAL,
        ExternalEventKind.GMAIL_NEW_MESSAGE,
        ExternalEventPriority.NORMAL,
    )
