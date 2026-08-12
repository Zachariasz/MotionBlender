"""Manager-native, context-sensitive Quick Favorites popup."""

from __future__ import absolute_import

import traceback

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from mobu_tools_manager import get_manager
from mobu_tools_manager.quick_favorites.settings import (
    CONTEXT_FCURVES,
    CONTEXT_OTHER,
    CONTEXT_TIMELINE,
    CONTEXT_VIEWER,
    context_for_ui_classification,
    favorite_key,
)


TOOL_NAME = "Quick Favorites"
CURSOR_MENU_X_FRACTION = 5.0 / 6.0
CONTEXT_TITLES = {
    CONTEXT_VIEWER: "3D Viewer Favorites",
    CONTEXT_FCURVES: "FCurves Favorites",
    CONTEXT_TIMELINE: "Timeline Favorites",
    CONTEXT_OTHER: "General Favorites",
}

_active_menu = None
_pending_popup = None


def _enum(container, nested_name, name):
    nested = getattr(container, nested_name, container)
    return getattr(nested, name)


def _event_position(event):
    try:
        return event.globalPosition().toPoint()
    except Exception:
        pass
    try:
        return event.globalPos()
    except Exception:
        return QtGui.QCursor.pos()


def _context_name(snapshot):
    classification = str(
        snapshot.get("hovered")
        or snapshot.get("active")
        or "other"
    ).lower()
    return context_for_ui_classification(classification)


def _source_widgets(snapshot):
    preferred = snapshot.get("hovered_widget") or snapshot.get(
        "active_widget"
    )
    surface = snapshot.get("surface") or snapshot.get("active_surface")
    if surface is None:
        surface = preferred
    return surface, preferred


def _show_error(details):
    try:
        from pyfbsdk import FBMessageBox

        FBMessageBox(TOOL_NAME, str(details), "OK")
    except Exception:
        print(details)


def _run_entry(manager, entry):
    try:
        if entry["kind"] == "feature":
            return manager.dispatch(entry["target"])
        if entry["kind"] == "native_action":
            return manager.dispatch_native_action(entry["target"])
        raise RuntimeError(
            "Unsupported Quick Favorite kind: " + entry["kind"]
        )
    except Exception:
        _show_error(traceback.format_exc())
        return None


class DeferredPopup(QtCore.QObject):
    """Wait for the launcher key-up without adding another event filter."""

    def __init__(
        self,
        context,
        global_position,
        snapshot,
        pressed_virtual_keys,
    ):
        QtCore.QObject.__init__(self, context.qt_application)
        self.context = context
        self.global_position = QtCore.QPoint(global_position)
        self.snapshot = dict(snapshot)
        self.pressed_virtual_keys = tuple(pressed_virtual_keys)
        self.cancelled = False
        self.opened = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._poll)

    def start(self):
        self.context.add_ui_event_observer(self._observe_event)
        self.timer.start()
        return self

    def cancel(self):
        global _pending_popup
        if self.cancelled:
            return
        self.cancelled = True
        self.timer.stop()
        try:
            self.context.remove_ui_event_observer(self._observe_event)
        except Exception:
            pass
        if _pending_popup is self:
            _pending_popup = None
        self.deleteLater()

    def _keys_are_down(self):
        return self.context.input.virtual_keys_are_down(
            self.pressed_virtual_keys
        )

    def _observe_event(self, _watched, event):
        key_release = _enum(QtCore.QEvent, "Type", "KeyRelease")
        if event.type() == key_release:
            # Never consume the release. The source editor must receive the
            # matching key-up before QMenu takes focus.
            QtCore.QTimer.singleShot(0, self._open_if_released)
        return False

    def _poll(self):
        if not self._keys_are_down():
            self.timer.stop()
            QtCore.QTimer.singleShot(30, self._open)

    def _open_if_released(self):
        if not self._keys_are_down():
            self._open()

    def _open(self):
        global _pending_popup
        if self.cancelled or self.opened:
            return
        self.opened = True
        self.timer.stop()
        try:
            self.context.remove_ui_event_observer(self._observe_event)
        except Exception:
            pass
        if _pending_popup is self:
            _pending_popup = None
        _show_now(self.context, self.global_position, self.snapshot)
        self.deleteLater()


class QuickFavoritesMenu(QtWidgets.QMenu):
    def __init__(
        self,
        context,
        manager,
        context_name,
        entries,
        source_surface,
        source_widget,
        parent=None,
    ):
        QtWidgets.QMenu.__init__(self, parent)
        self.context = context
        self.manager = manager
        self.context_name = context_name
        self.entries = tuple(dict(entry) for entry in entries)
        self.source_surface = source_surface
        self.source_widget = source_widget
        self._favorite_actions = {}
        self._popup_anchor = None
        self._outside_button = _enum(
            QtCore.Qt,
            "MouseButton",
            "NoButton",
        )
        self._observing = False
        self._launching = False
        self.setObjectName("motionbuilder_quick_favorites_menu")
        self.setWindowTitle(TOOL_NAME)
        self.setTearOffEnabled(False)

        title = self.addAction(CONTEXT_TITLES[context_name])
        title.setEnabled(False)
        self.addSeparator()
        for entry in self.entries:
            if entry["kind"] == "separator":
                self.addSeparator()
                continue
            action = self.addAction(entry["label"])
            available, reason = self._availability(entry)
            action.setEnabled(available)
            if reason:
                action.setToolTip(reason)
            self._favorite_actions[favorite_key(entry)] = action
            action.triggered.connect(
                lambda _checked=False, selected=entry: self._run(selected)
            )
        if not self.entries:
            empty = self.addAction("No favorites configured")
            empty.setEnabled(False)

        self.aboutToShow.connect(self._start_observing)
        self.aboutToHide.connect(self._finish_hide)

    def _availability(self, entry):
        if entry["kind"] == "native_action":
            if self.manager.native_action_exists(entry["target"]):
                return True, ""
            return False, "Action is not present in the active keyboard map."
        try:
            feature = self.manager.feature(entry["target"])
        except Exception:
            return False, "Managed feature ID was not found."
        if not self.manager.is_enabled(feature.id):
            return False, "Managed feature is disabled."
        return True, ""

    def _start_observing(self):
        if not self._observing:
            self.context.add_ui_event_observer(self._observe_event)
            self._observing = True

    def _stop_observing(self):
        if self._observing:
            try:
                self.context.remove_ui_event_observer(self._observe_event)
            except Exception:
                pass
            self._observing = False

    def _finish_hide(self):
        global _active_menu
        self._stop_observing()
        if _active_menu is self:
            _active_menu = None
        menu = self

        def finish():
            if not menu._launching:
                try:
                    menu.context.restore_editor_focus(
                        menu.source_surface,
                        menu.source_widget,
                    )
                except Exception:
                    pass
            try:
                menu.deleteLater()
            except Exception:
                pass

        QtCore.QTimer.singleShot(0, finish)

    def close_safely(self):
        self._stop_observing()
        try:
            self.close()
        except RuntimeError:
            pass

    def _last_action(self):
        key = self.manager.last_quick_favorite(self.context_name)
        return self._favorite_actions.get(key)

    def _position_for_anchor(self, anchor):
        anchor = QtCore.QPoint(anchor)
        target = self._last_action()
        if target is None:
            return anchor
        self.ensurePolished()
        self.adjustSize()
        size = self.sizeHint().expandedTo(self.size())
        row = self.actionGeometry(target)
        if row.height() <= 0 or size.width() <= 0:
            return anchor
        return QtCore.QPoint(
            int(round(anchor.x() - size.width() * CURSOR_MENU_X_FRACTION)),
            int(round(anchor.y() - row.center().y())),
        )

    def _constrain_position(self, position, anchor):
        screen = QtGui.QGuiApplication.screenAt(anchor)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return QtCore.QPoint(position)
        available = screen.availableGeometry()
        size = self.sizeHint().expandedTo(self.size())
        maximum_x = max(
            available.left(),
            available.right() - size.width() + 1,
        )
        maximum_y = max(
            available.top(),
            available.bottom() - size.height() + 1,
        )
        return QtCore.QPoint(
            max(available.left(), min(position.x(), maximum_x)),
            max(available.top(), min(position.y(), maximum_y)),
        )

    def popup_anchored(self, anchor):
        self._popup_anchor = QtCore.QPoint(anchor)
        self.popup(
            self._constrain_position(
                self._position_for_anchor(self._popup_anchor),
                self._popup_anchor,
            )
        )
        QtCore.QTimer.singleShot(0, self._realign)

    def _realign(self):
        if not self.isVisible() or self._popup_anchor is None:
            return
        position = self._constrain_position(
            self._position_for_anchor(self._popup_anchor),
            self._popup_anchor,
        )
        if self.pos() != position:
            self.move(position)

    def _is_outside(self, event):
        return not self.frameGeometry().contains(_event_position(event))

    def _observe_event(self, _watched, event):
        event_type = event.type()
        press_types = (
            _enum(QtCore.QEvent, "Type", "MouseButtonPress"),
            _enum(QtCore.QEvent, "Type", "MouseButtonDblClick"),
            _enum(QtCore.QEvent, "Type", "NonClientAreaMouseButtonPress"),
        )
        release_type = _enum(
            QtCore.QEvent,
            "Type",
            "MouseButtonRelease",
        )
        no_button = _enum(QtCore.Qt, "MouseButton", "NoButton")
        if event_type in press_types and self.isVisible():
            if self._is_outside(event):
                self._outside_button = event.button()
                event.accept()
                return True
        elif event_type == release_type and self._outside_button != no_button:
            button = event.button()
            event.accept()
            if button == self._outside_button:
                self._outside_button = no_button
                self.close()
            return True
        return False

    def _run(self, entry):
        self._launching = True
        self.manager.remember_quick_favorite(
            self.context_name,
            favorite_key(entry),
        )
        try:
            self.context.restore_editor_focus(
                self.source_surface,
                self.source_widget,
            )
        except Exception:
            pass
        self.close()
        manager = self.manager
        favorite = dict(entry)
        QtCore.QTimer.singleShot(
            0,
            lambda: _run_entry(manager, favorite),
        )


def _show_now(context, global_position=None, snapshot=None):
    global _active_menu
    app = context.qt_application
    if app is None:
        raise RuntimeError("MotionBuilder's Qt application is not available.")
    if global_position is None:
        global_position = QtGui.QCursor.pos()
    if snapshot is None:
        snapshot = context.ui_context

    if _active_menu is not None:
        _active_menu.close_safely()

    manager = get_manager()
    context_name = _context_name(snapshot)
    settings = manager.quick_favorites_settings()
    entries = settings["contexts"].get(context_name, ())
    source_surface, source_widget = _source_widgets(snapshot)
    parent = None
    if source_widget is not None:
        try:
            parent = source_widget.window()
        except Exception:
            pass
    if parent is None:
        parent = app.activeWindow()

    menu = QuickFavoritesMenu(
        context,
        manager,
        context_name,
        entries,
        source_surface,
        source_widget,
        parent,
    )
    _active_menu = menu
    menu.popup_anchored(global_position)
    return menu


def show(context):
    """Show favorites for the manager-owned UI context under the cursor."""
    global _pending_popup
    close()
    position_values = context.input.cursor_position()
    position = QtCore.QPoint(
        int(round(position_values[0])),
        int(round(position_values[1])),
    )
    snapshot = context.ui_context
    pressed = context.input.pressed_virtual_keys()
    if pressed:
        pending = DeferredPopup(context, position, snapshot, pressed)
        _pending_popup = pending
        return pending.start()
    return _show_now(context, position, snapshot)


def close():
    """Release all manager-owned Quick Favorites UI resources."""
    global _active_menu, _pending_popup
    pending, _pending_popup = _pending_popup, None
    if pending is not None:
        try:
            pending.cancel()
        except Exception:
            pass
    menu, _active_menu = _active_menu, None
    if menu is not None:
        try:
            menu.close_safely()
        except Exception:
            pass
