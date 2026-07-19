"""Keep bare Alt and Tab from moving MotionBuilder's keyboard focus.

The guard only intercepts Qt's ShortcutOverride handshake used by QMenuBar to
enter keyboard-navigation mode. It also consumes only an unmodified Tab
key-down, which is the event Qt uses for focus traversal. Tab key-up and all
modified Tab events remain available to MotionBuilder's keyboard map.
"""

import builtins


try:
    from PySide6 import QtCore, QtWidgets

    SHORTCUT_OVERRIDE = QtCore.QEvent.Type.ShortcutOverride
    KEY_PRESS = QtCore.QEvent.Type.KeyPress
    KEY_ALT = QtCore.Qt.Key.Key_Alt
    KEY_TAB = QtCore.Qt.Key.Key_Tab
    ALT_MODIFIER = QtCore.Qt.KeyboardModifier.AltModifier
    NO_MODIFIER = QtCore.Qt.KeyboardModifier.NoModifier
except ImportError:
    from PySide2 import QtCore, QtWidgets

    SHORTCUT_OVERRIDE = QtCore.QEvent.ShortcutOverride
    KEY_PRESS = QtCore.QEvent.KeyPress
    KEY_ALT = QtCore.Qt.Key_Alt
    KEY_TAB = QtCore.Qt.Key_Tab
    ALT_MODIFIER = QtCore.Qt.AltModifier
    NO_MODIFIER = QtCore.Qt.NoModifier


SCRIPT_VERSION = 2
CONTROLLER_KEY = "_motionbuilder_block_alt_menu_focus_controller"


class BlockAltMenuFocusController(QtCore.QObject):
    """Blocks Qt's bare-Alt menu mode and plain-Tab focus traversal."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.script_version = SCRIPT_VERSION
        self.blocked_count = 0
        self.blocked_alt_count = 0
        self.blocked_tab_count = 0
        self.installed = False

    def install(self):
        if self.installed:
            return
        self.app.installEventFilter(self)
        self.installed = True

    def uninstall(self):
        if not self.installed:
            return
        try:
            self.app.removeEventFilter(self)
        finally:
            self.installed = False

    def eventFilter(self, watched, event):
        try:
            if (
                event.type() == SHORTCUT_OVERRIDE
                and event.key() == KEY_ALT
                and event.modifiers() == ALT_MODIFIER
            ):
                # Leave the event unaccepted so Qt shortcuts can still match.
                # Returning True prevents QMenuBar's own filter from arming its
                # focus-taking keyboard-navigation state.
                event.ignore()
                self.blocked_count += 1
                self.blocked_alt_count += 1
                return True

            if (
                event.type() == KEY_PRESS
                and event.key() == KEY_TAB
                and event.modifiers() == NO_MODIFIER
            ):
                # Qt performs focus traversal on the plain Tab key-down. The
                # Blender map's plain-Tab action is bound to TAB*UP, which is
                # deliberately left untouched. Modified Tab events (including
                # the mapped Shift+Tab action) are also passed through.
                event.accept()
                self.blocked_count += 1
                self.blocked_tab_count += 1
                return True
        except (AttributeError, RuntimeError):
            pass

        return False


def stop_existing_controller():
    old_controller = getattr(builtins, CONTROLLER_KEY, None)
    if old_controller is None:
        return

    try:
        old_controller.uninstall()
    except Exception:
        pass

    try:
        old_controller.deleteLater()
    except Exception:
        pass


def start_block_alt_menu_focus():
    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("MotionBuilder QApplication is not available")

    stop_existing_controller()
    controller = BlockAltMenuFocusController(app)
    controller.install()
    setattr(builtins, CONTROLLER_KEY, controller)
    return controller


def get_block_alt_menu_focus_controller():
    return getattr(builtins, CONTROLLER_KEY, None)


controller = start_block_alt_menu_focus()
