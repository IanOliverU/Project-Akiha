"""Structured presentation helpers for Akiha's manager windows."""

from __future__ import annotations

import re

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from project_akiha.ui.theme import AKIHA_PALETTE

ITEM_TITLE_ROLE = Qt.ItemDataRole.UserRole + 10
ITEM_META_ROLE = Qt.ItemDataRole.UserRole + 11
ITEM_ACCENT_ROLE = Qt.ItemDataRole.UserRole + 12
ITEM_TIMESTAMP_ROLE = Qt.ItemDataRole.UserRole + 13
ITEM_TAGS_ROLE = Qt.ItemDataRole.UserRole + 14
ITEM_STATUS_ROLE = Qt.ItemDataRole.UserRole + 15

_CARD = QColor("#1A1D24")
_CARD_HOVER = QColor("#22252E")
_CARD_SELECTED = QColor("#2C303C")
_CHIP = QColor("#292D3B")
_TEXT = QColor(AKIHA_PALETTE.text)
_MUTED = QColor(AKIHA_PALETTE.muted_text)
_PRIMARY = QColor("#BFC2FF")


class ManagerItemDelegate(QStyledItemDelegate):
    """Base painter for manager records with deterministic selection contrast."""

    def _card_rect(self, option: QStyleOptionViewItem) -> QRect:
        return option.rect.adjusted(8, 4, -8, -4)

    def _paint_card(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
    ) -> tuple[QRect, bool]:
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        card = self._card_rect(option)
        background = _CARD_SELECTED if selected else _CARD_HOVER if hovered else _CARD
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(card, 3, 3)
        if selected:
            painter.setBrush(QColor(AKIHA_PALETTE.highlight))
            painter.drawRect(QRect(card.left(), card.top(), 2, card.height()))
        return card, selected

    @staticmethod
    def _font(
        family: str,
        pixels: int,
        *,
        weight: QFont.Weight = QFont.Weight.Normal,
    ) -> QFont:
        font = QFont(family)
        font.setPixelSize(pixels)
        font.setWeight(weight)
        return font

    @staticmethod
    def _draw_text(
        painter: QPainter,
        rect: QRect,
        text: str,
        color: QColor,
        *,
        font: QFont,
        alignment: Qt.AlignmentFlag = (
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        ),
    ) -> None:
        painter.setFont(font)
        painter.setPen(color)
        rendered = painter.fontMetrics().elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            max(0, rect.width()),
        )
        painter.drawText(rect, alignment, rendered)

    @staticmethod
    def _draw_chip(
        painter: QPainter,
        rect: QRect,
        text: str,
        *,
        foreground: QColor,
        background: QColor = _CHIP,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 2, 2)
        painter.setFont(ManagerItemDelegate._font("Cascadia Mono", 11))
        painter.setPen(foreground)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    @staticmethod
    def _tags(index: QModelIndex) -> tuple[str, ...]:
        value = index.data(ITEM_TAGS_ROLE)
        if isinstance(value, tuple):
            return tuple(str(tag) for tag in value)
        if isinstance(value, list):
            return tuple(str(tag) for tag in value)
        return ()


class MemoryItemDelegate(ManagerItemDelegate):
    """Render memory records as the approved full-width cards."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        card, selected = self._paint_card(painter, option)
        memory_id = str(index.data(Qt.ItemDataRole.UserRole) or "")
        title = str(index.data(ITEM_TITLE_ROLE) or index.data() or "")
        meta = str(index.data(ITEM_META_ROLE) or "")
        accent = QColor(str(index.data(ITEM_ACCENT_ROLE) or "#BFC2FF"))

        id_rect = QRect(card.left() + 14, card.top() + 13, 34, 24)
        self._draw_chip(
            painter,
            id_rect,
            f"#{memory_id}",
            foreground=_TEXT if selected else _PRIMARY,
        )

        content_left = id_rect.right() + 18
        content_width = card.right() - content_left - 14
        self._draw_text(
            painter,
            QRect(content_left, card.top() + 8, content_width, 27),
            title,
            _TEXT,
            font=self._font("Segoe UI", 13, weight=QFont.Weight.DemiBold),
        )

        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRect(content_left + 1, card.top() + 45, 10, 10))
        meta_rect = QRect(content_left + 17, card.top() + 39, 72, 22)
        self._draw_text(
            painter,
            meta_rect,
            meta,
            _TEXT if selected else _MUTED,
            font=self._font("Cascadia Mono", 11),
        )

        tag_left = meta_rect.right() + 5
        for tag in self._tags(index):
            painter.setFont(self._font("Cascadia Mono", 10))
            tag_width = min(110, painter.fontMetrics().horizontalAdvance(tag) + 12)
            if tag_left + tag_width > card.right() - 12:
                break
            tag_color = QColor("#E0C561") if _is_priority_tag(tag) else _PRIMARY
            tag_background = QColor(tag_color)
            tag_background.setAlpha(28)
            self._draw_chip(
                painter,
                QRect(tag_left, card.top() + 40, tag_width, 20),
                tag,
                foreground=tag_color,
                background=tag_background,
            )
            tag_left += tag_width + 5
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        del option, index
        return QSize(520, 78)


class BehaviorEventDelegate(ManagerItemDelegate):
    """Render behavior records with ID, time, title, and category badges."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        card, selected = self._paint_card(painter, option)
        event_id = str(index.data(Qt.ItemDataRole.UserRole) or "")
        title = str(index.data(ITEM_TITLE_ROLE) or index.data() or "")
        timestamp = str(index.data(ITEM_TIMESTAMP_ROLE) or "")
        accent = QColor(str(index.data(ITEM_ACCENT_ROLE) or "#BFC2FF"))

        self._draw_text(
            painter,
            QRect(card.left() + 14, card.top() + 8, 72, 19),
            f"#{event_id}",
            _TEXT if selected else _PRIMARY,
            font=self._font("Cascadia Mono", 11),
        )
        self._draw_text(
            painter,
            QRect(card.left() + 88, card.top() + 8, card.width() - 102, 19),
            timestamp,
            _TEXT if selected else _MUTED,
            font=self._font("Cascadia Mono", 10),
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self._draw_text(
            painter,
            QRect(card.left() + 14, card.top() + 29, card.width() - 28, 24),
            title,
            _TEXT,
            font=self._font("Segoe UI", 12, weight=QFont.Weight.DemiBold),
        )

        tag_left = card.left() + 14
        for tag in self._tags(index)[:3]:
            painter.setFont(self._font("Cascadia Mono", 9))
            tag_width = min(95, painter.fontMetrics().horizontalAdvance(tag) + 12)
            tag_color = accent if tag_left == card.left() + 14 else _MUTED
            tag_background = QColor(tag_color)
            tag_background.setAlpha(30)
            self._draw_chip(
                painter,
                QRect(tag_left, card.top() + 59, tag_width, 17),
                tag.upper(),
                foreground=tag_color,
                background=tag_background,
            )
            tag_left += tag_width + 5
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        del option, index
        return QSize(300, 88)


class ActionItemDelegate(ManagerItemDelegate):
    """Render compact action identifiers with semantic result status."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        card, selected = self._paint_card(painter, option)
        item_id = str(index.data(Qt.ItemDataRole.UserRole) or "")
        title = str(index.data(ITEM_TITLE_ROLE) or index.data() or "")
        item_kind = str(index.data(ITEM_META_ROLE) or "")
        accent = QColor(str(index.data(ITEM_ACCENT_ROLE) or "#BFC2FF"))
        status = str(index.data(ITEM_STATUS_ROLE) or "")

        self._draw_chip(
            painter,
            QRect(card.left() + 14, card.top() + 14, 42, 24),
            f"#{item_id}" if item_id.isdigit() else item_kind[:4].upper() or "FILE",
            foreground=_TEXT if selected else accent,
        )
        self._draw_text(
            painter,
            QRect(card.left() + 67, card.top() + 10, card.width() - 104, 32),
            title,
            _TEXT if status not in {"denied", "failed", "unavailable"} else accent,
            font=self._font("Cascadia Mono", 11, weight=QFont.Weight.DemiBold),
        )
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRect(card.right() - 26, card.top() + 18, 12, 12))
        if status == "success":
            painter.drawLine(
                card.right() - 23,
                card.top() + 24,
                card.right() - 20,
                card.top() + 27,
            )
            painter.drawLine(
                card.right() - 20,
                card.top() + 27,
                card.right() - 16,
                card.top() + 21,
            )
        elif status:
            painter.drawLine(
                card.right() - 20,
                card.top() + 21,
                card.right() - 20,
                card.top() + 25,
            )
            painter.drawPoint(card.right() - 20, card.top() + 28)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        del option, index
        return QSize(290, 58)


class TechnicalDetailsHighlighter(QSyntaxHighlighter):
    """Apply restrained semantic color to structured detail text."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._label = _format(AKIHA_PALETTE.highlight, bold=True)
        self._key = _format("#BFC2FF")
        self._value = _format("#E0C561")
        self._success = _format(AKIHA_PALETTE.success, bold=True)
        self._error = _format("#FFB4AB", bold=True)
        self._number = _format("#9CC7DF")

    def highlightBlock(self, text: str) -> None:
        self._apply(r"^[A-Za-z][A-Za-z ]+(?=:)", text, self._label)
        self._apply(r'"[^"\\]*(?:\\.[^"\\]*)*"(?=\s*:)', text, self._key)
        self._apply(r'(?<=:\s)"[^"\\]*(?:\\.[^"\\]*)*"', text, self._value)
        self._apply(r"\b(?:success|granted|available|true)\b", text, self._success)
        self._apply(
            r"\b(?:denied|failed|missing|unavailable|timed_out|false)\b",
            text,
            self._error,
        )
        self._apply(r"(?<![A-Za-z_])#?\d+(?:\.\d+)?(?:\s*ms)?\b", text, self._number)

    def _apply(self, pattern: str, text: str, text_format: QTextCharFormat) -> None:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            self.setFormat(match.start(), match.end() - match.start(), text_format)


def _is_priority_tag(tag: str) -> bool:
    normalized = tag.casefold()
    return normalized in {"identity", "preference", "preferences", "critical"}


def _format(color: str, *, bold: bool = False) -> QTextCharFormat:
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Weight.DemiBold)
    return text_format
