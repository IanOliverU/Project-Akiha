"""Grouped native menus shared by the sprite and tray."""

from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory, QWidgetAction

from project_akiha.ui.components import PageHeader
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.theme import native_surface_stylesheet


class _ScrollableMenuStyle(QProxyStyle):
    """Native overflow scrolling keeps commands reachable on scaled screens."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Menu_Scrollable:
            return 1
        return super().styleHint(hint, option, widget, returnData)


def polish_menu(menu):
    style = _ScrollableMenuStyle(QStyleFactory.create("Fusion"))
    style.setParent(menu)
    menu.setStyle(style)
    menu.setStyleSheet(native_surface_stylesheet())
    menu.setMinimumWidth(230)
    first = menu.actions()[0] if menu.actions() else None
    title = QWidgetAction(menu)
    heading = PageHeader("Akiha", "Desktop companion", menu)
    heading.setObjectName("contextMenuHeading")
    title.setDefaultWidget(heading)
    if first is not None:
        menu.insertAction(first, title)
    else:
        menu.addAction(title)
    icons = {
        "Chat": "chat",
        "Settings": "settings",
        "Care": "pet",
        "Status": "info",
        "Shop & appearance": "shop",
        "Behavior history": "history",
        "Notifications": "notification",
        "Hide": "pet",
        "Show": "pet",
        "Quit": "exit",
        "Walk": "pet",
        "Sleep": "pet",
        "Wake": "pet",
        "Stop walking": "pet",
    }
    for action in menu.actions():
        if action.text() in icons:
            action.setIcon(fluent_icon(icons[action.text()]))
    return menu
