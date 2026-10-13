"""Keep bare Alt and Tab from moving MotionBuilder's keyboard focus.

Replaces the legacy ``custom/BlockAltMenuFocus.py`` controller, which installed
its own ``QApplication`` event filter and a builtins singleton. This service
observes events through the manager's single shared Qt event filter.
"""

from __future__ import absolute_import


FEATURE_ID = "input.block_alt_menu_focus"
_SERVICE = None


def _qt_modules():
    """Return (QtCore, QtWidgets) for PySide6 or PySide2."""
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


def _event_value(QtCore, name):
    """Get QEvent type value by name."""
    group = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    value = getattr(group, name, None)
    return value if value is not None else getattr(QtCore.QEvent, name, None)


def _qt_enum(QtCore, group, name):
    """Get Qt enum value by group and name."""
    container = getattr(QtCore.Qt, group, None)
    if container is not None and hasattr(container, name):
        return getattr(container, name)
    return getattr(QtCore.Qt, name, None)


class BlockAltMenuFocusService(object):
    def __init__(self, context):
        self.context = context
        self.running = False
        self.blocked_alt_count = 0
        self.blocked_tab_count = 0
        self.last_error = None

        QtCore, _ = _qt_modules()
        self._shortcut_override = _event_value(QtCore, "ShortcutOverride")
        self._key_press = _event_value(QtCore, "KeyPress")
        self._key_alt = _qt_enum(QtCore, "Key", "Key_Alt")
        self._key_tab = _qt_enum(QtCore, "Key", "Key_Tab")
        self._alt_modifier = _qt_enum(QtCore, "KeyboardModifier", "AltModifier")
        self._no_modifier = _qt_enum(QtCore, "KeyboardModifier", "NoModifier")

    def _record(self, event, **data):
        try:
            self.context.diagnostics.record(event, FEATURE_ID, **data)
        except Exception:
            pass

    def start(self):
        if self.running:
            return self
        try:
            self.context.add_ui_event_observer(self._observe_ui_event)
        except Exception as error:
            self.last_error = str(error)
            self._record("block_alt_menu_focus_start_error", error=self.last_error)
            return self
        self.running = True
        self._record("block_alt_menu_focus_started")
        return self

    def stop(self):
        try:
            self.context.remove_ui_event_observer(self._observe_ui_event)
        except Exception:
            pass
        self.running = False
        self._record("block_alt_menu_focus_stopped")

    def _observe_ui_event(self, watched, event):
        if not self.running:
            return False
        try:
            if (
                event.type() == self._shortcut_override
                and event.key() == self._key_alt
                and event.modifiers() == self._alt_modifier
            ):
                # Leave the event unaccepted so Qt shortcuts can still match.
                # Consuming it prevents QMenuBar's own filter from arming its
                # focus-taking keyboard-navigation state.
                event.ignore()
                self.blocked_alt_count += 1
                return True

            if (
                event.type() == self._key_press
                and event.key() == self._key_tab
                and event.modifiers() == self._no_modifier
            ):
                # Qt traverses focus on the plain Tab key-down. The Blender
                # map binds plain Tab to TAB*UP, which is left untouched;
                # key-up and modified Tab (including Shift+Tab) pass through.
                event.accept()
                self.blocked_tab_count += 1
                return True
        except (AttributeError, RuntimeError, TypeError):
            return False
        return False

    def status(self):
        return {
            "running": self.running,
            "blocked_alt_count": self.blocked_alt_count,
            "blocked_tab_count": self.blocked_tab_count,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = BlockAltMenuFocusService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.stop()
    _SERVICE = None


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
