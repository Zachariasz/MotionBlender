"""Backtick menu for MotionBuilder transport frame-replay behavior."""

from __future__ import absolute_import


FEATURE_ID = "animation.playback_frame_mode_menu"
MENU_TITLE = "Playback Frame Mode"
MODE_OPTIONS = (
    ("no_snap", "No Snap", "kFBTransportSnapModeNoSnap"),
    ("snap_on_frames", "Snap on Frames", "kFBTransportSnapModeSnapOnFrames"),
    ("play_on_frames", "Play on Frames", "kFBTransportSnapModePlayOnFrames"),
    (
        "snap_and_play_on_frames",
        "Snap & Play on Frames",
        "kFBTransportSnapModeSnapAndPlayOnFrames",
    ),
)
_MODE_BY_ID = dict((mode_id, (label, enum_name)) for mode_id, label, enum_name in MODE_OPTIONS)
_ACTIVE_MENU = None
_SERVICE = None


def _qt_modules():
    try:
        from PySide6 import QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtGui, QtWidgets
    return QtGui, QtWidgets


def _sdk():
    import pyfbsdk

    return pyfbsdk


def _enum_value(sdk, enum_name):
    value = getattr(sdk, enum_name, None)
    if value is not None:
        return value
    enum_type = getattr(sdk, "FBTransportSnapMode", None)
    return getattr(enum_type, enum_name)


def _player_control(context, sdk=None):
    player = getattr(context, "player_control", None)
    if player is not None:
        return player
    return (sdk or _sdk()).FBPlayerControl()


def current_mode_id(context, sdk=None):
    """Return the stable ID for the current transport snap mode, if known."""
    sdk = sdk or _sdk()
    current = _player_control(context, sdk).SnapMode
    for mode_id, _label, enum_name in MODE_OPTIONS:
        if current == _enum_value(sdk, enum_name):
            return mode_id
    return None


def set_mode(context, mode_id, sdk=None):
    """Set MotionBuilder's transport snap/play behavior and report the change."""
    if mode_id not in _MODE_BY_ID:
        raise ValueError("Unknown playback frame mode: " + str(mode_id))
    sdk = sdk or _sdk()
    label, enum_name = _MODE_BY_ID[mode_id]
    player = _player_control(context, sdk)
    previous_mode = current_mode_id(context, sdk)
    player.SnapMode = _enum_value(sdk, enum_name)

    diagnostics = getattr(context, "diagnostics", None)
    record = getattr(diagnostics, "record", None)
    if callable(record):
        record(
            "playback_frame_mode_changed",
            FEATURE_ID,
            previous_mode=previous_mode,
            mode=mode_id,
            label=label,
        )
    return {
        "previous_mode": previous_mode,
        "mode": mode_id,
        "label": label,
    }


class PlaybackFrameModeMenu(object):
    """Small transient Qt menu; the service owns no persistent widget."""

    def __init__(self, context, parent=None):
        QtGui, QtWidgets = _qt_modules()
        self.context = context
        self.QtGui = QtGui
        self.menu = QtWidgets.QMenu(parent)
        self.menu.setObjectName("motionbuilder_playback_frame_mode_menu")
        self.menu.setWindowTitle(MENU_TITLE)
        self._actions = {}
        group = QtGui.QActionGroup(self.menu)
        group.setExclusive(True)
        active_mode = current_mode_id(context)
        for mode_id, label, _enum_name in MODE_OPTIONS:
            action = self.menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode_id == active_mode)
            group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, selected=mode_id: set_mode(
                    self.context, selected
                )
            )
            self._actions[mode_id] = action
        self.menu.aboutToHide.connect(self._finish_hide)

    def popup(self):
        self.menu.popup(self.QtGui.QCursor.pos())
        return self

    def close_safely(self):
        try:
            self.menu.close()
        except RuntimeError:
            pass

    def _finish_hide(self):
        global _ACTIVE_MENU
        if _ACTIVE_MENU is self:
            _ACTIVE_MENU = None
        try:
            self.menu.deleteLater()
        except RuntimeError:
            pass


def show(context):
    """Open the checked frame-replay menu at the current cursor position."""
    global _ACTIVE_MENU
    close()
    _QtGui, QtWidgets = _qt_modules()
    application = getattr(context, "qt_application", None)
    parent = None
    if application is not None:
        try:
            parent = application.activeWindow()
        except Exception:
            pass
    if parent is None:
        try:
            parent = QtWidgets.QApplication.activeWindow()
        except Exception:
            pass
    _ACTIVE_MENU = PlaybackFrameModeMenu(context, parent)
    return _ACTIVE_MENU.popup()


def close():
    """Close the one transient menu, if it exists."""
    global _ACTIVE_MENU
    menu, _ACTIVE_MENU = _ACTIVE_MENU, None
    if menu is not None:
        menu.close_safely()


class PlaybackFrameModeHotkeyService(object):
    """Own the backtick binding through the shared manager input router."""

    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_error = None
        self._show_token = 0

    def start(self):
        if self.running:
            return self
        self.context.input.configure_playback_frame_mode_launcher(
            self._callback
        )
        self.running = True
        return self

    def stop(self):
        self._show_token += 1
        if self.context is not None:
            try:
                self.context.input.clear_playback_frame_mode_launcher(
                    self._callback
                )
            except Exception:
                pass
        close()
        self.running = False

    def handle_key(self, _payload=None):
        if not self.running:
            return False
        self._show_token += 1
        token = self._show_token
        try:
            QtCore = getattr(self.context.input, "QtCore")
            QtCore.QTimer.singleShot(0, lambda: self._show_after_key(token))
        except Exception as error:
            self.last_error = str(error)
            return False
        return True

    def _show_after_key(self, token):
        if not self.running or token != self._show_token:
            return
        try:
            show(self.context)
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)

    def status(self):
        return {
            "running": self.running,
            "binding": "`",
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = PlaybackFrameModeHotkeyService(context)
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
