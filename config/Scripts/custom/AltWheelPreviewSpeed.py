import ctypes
import os
import sys
import time
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import FBMessageBox, FBPlayerControl

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Alt Wheel Preview Speed"
ACTIVE_CONTROLLER_ATTR = "_alt_wheel_preview_speed_controller"
ACTIVE_STATE_MODULE = "_alt_wheel_preview_speed_state"
SCRIPT_VERSION = 2

POLL_INTERVAL_MS = 30
OVERLAY_HOLD_SECONDS = 1.1
OVERLAY_BOTTOM_MARGIN = 24
VK_LMENU = 0xA4
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
HC_ACTION = 0

# Change this to True if you want wheel scrolling to use custom smooth values
# instead of MotionBuilder's predefined transport speed steps.
USE_SMOOTH_SPEED = False
SMOOTH_SPEED_STEP = 0.10
SMOOTH_MIN_SPEED = 0.10
SMOOTH_MAX_SPEED = 4.00

SPEEDS = (
    (0.10, "0.1x"),
    (0.20, "0.2x"),
    (0.25, "0.25x"),
    (0.33, "0.33x"),
    (0.50, "0.5x"),
    (1.00, "1x"),
    (1.50, "1.5x"),
    (2.00, "2x"),
    (2.50, "2.5x"),
    (3.00, "3x"),
    (3.50, "3.5x"),
    (4.00, "4x"),
)


def _is_key_down(vk_code):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def _set_precise_timer(timer):
    try:
        if hasattr(QtCore.Qt, "TimerType"):
            timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        else:
            timer.setTimerType(QtCore.Qt.PreciseTimer)
    except Exception:
        pass


def _qt_event_type(name):
    try:
        if hasattr(QtCore.QEvent, "Type"):
            return getattr(QtCore.QEvent.Type, name)
        return getattr(QtCore.QEvent, name)
    except Exception:
        return None


def _qt_window_flag(name):
    if hasattr(QtCore.Qt, "WindowType"):
        return getattr(QtCore.Qt.WindowType, name)
    return getattr(QtCore.Qt, name)


def _qt_widget_attribute(name):
    if hasattr(QtCore.Qt, "WidgetAttribute"):
        return getattr(QtCore.Qt.WidgetAttribute, name)
    return getattr(QtCore.Qt, name)


def _set_widget_attribute(widget, name, enabled=True):
    try:
        widget.setAttribute(_qt_widget_attribute(name), enabled)
    except Exception:
        pass


def _cursor_qpoint():
    return QtGui.QCursor.pos()


def _qt_widget_rect(widget):
    top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
    return top_left.x(), top_left.y(), int(widget.width()), int(widget.height())


def _rect_contains_point(rect, point):
    x, y, width, height = rect
    return x <= point.x() <= x + width and y <= point.y() <= y + height


def _clamp(value, minimum, maximum):
    if maximum < minimum:
        return minimum
    return max(minimum, min(maximum, value))


def _speed_label(speed):
    for candidate, label in SPEEDS:
        if abs(candidate - float(speed)) < 0.005:
            return label
    return ("%.2f" % float(speed)).rstrip("0").rstrip(".") + "x"


def _active_controller_state_module():
    module = sys.modules.get(ACTIVE_STATE_MODULE)
    if module is None:
        import types
        module = types.ModuleType(ACTIVE_STATE_MODULE)
        sys.modules[ACTIVE_STATE_MODULE] = module
    return module


def _active_controller_holders():
    holders = [_active_controller_state_module(), builtins]

    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None

    if app is not None:
        holders.append(app)

    return holders


def _get_active_controller():
    for holder in _active_controller_holders():
        try:
            controller = getattr(holder, ACTIVE_CONTROLLER_ATTR, None)
        except Exception:
            continue

        if controller is not None and getattr(controller, "running", False):
            return controller

    return None


def _set_active_controller(controller):
    try:
        controller.setObjectName(ACTIVE_CONTROLLER_ATTR)
    except Exception:
        pass

    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            controller.setParent(app)
    except Exception:
        pass

    for holder in _active_controller_holders():
        try:
            setattr(holder, ACTIVE_CONTROLLER_ATTR, controller)
        except Exception:
            pass


def _clear_active_controller(controller):
    for holder in _active_controller_holders():
        try:
            if getattr(holder, ACTIVE_CONTROLLER_ATTR, None) is controller:
                setattr(holder, ACTIVE_CONTROLLER_ATTR, None)
        except Exception:
            pass

    try:
        controller.setParent(None)
    except Exception:
        pass


class SpeedOverlay(QtWidgets.QLabel):
    def __init__(self):
        flags = (
            _qt_window_flag("Tool")
            | _qt_window_flag("FramelessWindowHint")
            | _qt_window_flag("WindowStaysOnTopHint")
        )

        QtWidgets.QLabel.__init__(self, None, flags)
        _set_widget_attribute(self, "WA_TransparentForMouseEvents", True)
        _set_widget_attribute(self, "WA_ShowWithoutActivating", True)

        try:
            self.setFocusPolicy(QtCore.Qt.NoFocus)
        except Exception:
            pass

        self.setStyleSheet(
            "QLabel {"
            "background-color: rgba(18, 18, 18, 205);"
            "color: white;"
            "border: 1px solid rgba(255, 255, 255, 95);"
            "border-radius: 4px;"
            "padding: 6px 10px;"
            "font-size: 13px;"
            "}"
        )

    def show_text(self, text, viewport_rect=None):
        self.setText(text)
        self.adjustSize()
        self._move_to_bottom_center(viewport_rect)
        self.show()
        try:
            self.raise_()
        except Exception:
            pass

    def _move_to_bottom_center(self, viewport_rect=None):
        app = QtWidgets.QApplication.instance()
        target_rect = viewport_rect

        if target_rect is None:
            try:
                active_window = app.activeWindow()
                if active_window is not None and active_window.isVisible():
                    geometry = active_window.frameGeometry()
                    target_rect = (
                        geometry.x(),
                        geometry.y(),
                        geometry.width(),
                        geometry.height(),
                    )
            except Exception:
                target_rect = None

        if target_rect is None:
            try:
                screen = app.primaryScreen()
                geometry = screen.availableGeometry()
                target_rect = (
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                )
            except Exception:
                target_rect = (0, 0, 1280, 720)

        rect_x, rect_y, rect_width, rect_height = target_rect
        min_x = rect_x
        max_x = rect_x + rect_width - self.width()
        min_y = rect_y
        max_y = rect_y + rect_height - self.height()
        x = rect_x + int((rect_width - self.width()) * 0.5)
        y = rect_y + rect_height - self.height() - OVERLAY_BOTTOM_MARGIN
        self.move(_clamp(x, min_x, max_x), _clamp(y, min_y, max_y))


class _WindowsMouseHook(object):
    def __init__(self, controller):
        self.controller = controller
        self.user32 = None
        self.hook = None
        self.callback = None
        self.error = None

    def install(self):
        if os.name != "nt":
            self.error = "not Windows"
            return False

        try:
            from ctypes import wintypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("pt", POINT),
                    ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            self.MSLLHOOKSTRUCT = MSLLHOOKSTRUCT
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            lresult_type = ctypes.c_ssize_t
            hook_proc_type = ctypes.WINFUNCTYPE(
                lresult_type,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )
            self.callback = hook_proc_type(self._mouse_proc)

            self.user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                hook_proc_type,
                wintypes.HINSTANCE,
                wintypes.DWORD,
            ]
            self.user32.SetWindowsHookExW.restype = wintypes.HANDLE
            self.user32.CallNextHookEx.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            self.user32.CallNextHookEx.restype = lresult_type
            self.user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
            self.user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            self.user32.GetForegroundWindow.restype = wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD

            self.hook = self.user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                self.callback,
                None,
                0,
            )

            if not self.hook:
                self.error = "SetWindowsHookExW failed: %s" % ctypes.get_last_error()
                return False

            return True
        except Exception:
            self.error = traceback.format_exc()
            self.uninstall()
            return False

    def uninstall(self):
        if self.user32 is not None and self.hook:
            try:
                self.user32.UnhookWindowsHookEx(self.hook)
            except Exception:
                pass

        self.hook = None

    def _foreground_is_this_process(self):
        try:
            hwnd = self.user32.GetForegroundWindow()
            if not hwnd:
                return False

            from ctypes import wintypes
            process_id = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            return int(process_id.value) == int(os.getpid())
        except Exception:
            return True

    def _mouse_proc(self, n_code, w_param, l_param):
        try:
            if (
                n_code == HC_ACTION
                and int(w_param) == WM_MOUSEWHEEL
                and self.controller.running
                and self.controller.is_left_alt_down()
                and self._foreground_is_this_process()
            ):
                event = ctypes.cast(
                    l_param,
                    ctypes.POINTER(self.MSLLHOOKSTRUCT),
                ).contents
                delta = ctypes.c_short((int(event.mouseData) >> 16) & 0xFFFF).value
                self.controller.queue_wheel_delta(delta, "hook")
                return 1
        except Exception:
            pass

        return self.user32.CallNextHookEx(self.hook, n_code, w_param, l_param)


class AltWheelPreviewSpeedController(QtCore.QObject):
    def __init__(self, app):
        QtCore.QObject.__init__(self, app)
        self.app = app
        self.script_version = SCRIPT_VERSION
        self.player = FBPlayerControl()
        self.running = False
        self.pending_steps = 0
        self.last_change_time = 0.0
        self.last_hook_wheel_time = 0.0
        self.viewport_rect = None
        self.overlay = SpeedOverlay()
        self.hook = _WindowsMouseHook(self)
        self.hook_installed = False

        self.timer = QtCore.QTimer(self)
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)

    def start(self):
        if self.running:
            return

        self.running = True
        self.app.installEventFilter(self)
        self.hook_installed = self.hook.install()

        try:
            self.app.aboutToQuit.connect(self.stop)
        except Exception:
            pass

        self.set_speed(1.0)
        self.timer.start(POLL_INTERVAL_MS)
        print(
            "%s active. Hold Left Alt and use the mouse wheel to change playback speed."
            % TOOL_NAME
        )
        if not self.hook_installed:
            print("%s: Windows mouse hook unavailable; using Qt wheel events. %s" % (
                TOOL_NAME,
                self.hook.error or "",
            ))

    def stop(self):
        if not self.running:
            return

        self.running = False
        try:
            self.timer.stop()
        except Exception:
            pass

        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass

        self.hook.uninstall()

        try:
            self.overlay.hide()
            self.overlay.deleteLater()
        except Exception:
            pass

        _clear_active_controller(self)

    def reset_default(self):
        self.set_speed(1.0)

    def is_left_alt_down(self):
        return _is_key_down(VK_LMENU)

    def eventFilter(self, obj, event):
        try:
            if self.is_left_alt_down():
                wheel_event_type = _qt_event_type("Wheel")
                if wheel_event_type is not None and event.type() == wheel_event_type:
                    delta = self._qt_wheel_delta(event)
                    if delta:
                        if time.time() - self.last_hook_wheel_time > 0.08:
                            self.queue_wheel_delta(delta, "qt")
                        try:
                            event.accept()
                        except Exception:
                            pass
                        return True
        except Exception:
            pass

        return QtCore.QObject.eventFilter(self, obj, event)

    def queue_wheel_delta(self, delta, source=None):
        if delta == 0:
            return

        if source == "hook":
            self.last_hook_wheel_time = time.time()

        self._capture_viewport_rect_from_cursor()

        steps = int(abs(delta) / 120)
        if steps < 1:
            steps = 1

        if delta > 0:
            self.pending_steps += steps
        else:
            self.pending_steps -= steps

        self.last_change_time = time.time()

    def _capture_viewport_rect_from_cursor(self):
        cursor = _cursor_qpoint()

        try:
            widget = self.app.widgetAt(cursor)
        except Exception:
            widget = None

        candidates = []
        while widget is not None:
            if widget is self.overlay:
                widget = widget.parentWidget()
                continue

            try:
                if (
                    widget.isVisible()
                    and widget.width() >= 180
                    and widget.height() >= 120
                ):
                    rect = _qt_widget_rect(widget)
                    if _rect_contains_point(rect, cursor):
                        area = rect[2] * rect[3]
                        candidates.append((area, rect))
            except Exception:
                pass

            try:
                widget = widget.parentWidget()
            except Exception:
                widget = None

        if candidates:
            self.viewport_rect = sorted(candidates, key=lambda item: item[0])[0][1]

        return self.viewport_rect

    def _qt_wheel_delta(self, event):
        try:
            delta = event.angleDelta().y()
            if delta:
                return int(delta)
        except Exception:
            pass

        try:
            delta = event.delta()
            if delta:
                return int(delta)
        except Exception:
            pass

        try:
            delta = event.pixelDelta().y()
            if delta:
                return int(delta)
        except Exception:
            pass

        return 0

    def _current_speed(self):
        try:
            return float(self.player.GetPlaySpeed())
        except Exception:
            return 1.0

    def _next_speed(self, direction):
        current_speed = self._current_speed()

        if direction > 0:
            for speed, _label in SPEEDS:
                if speed > current_speed + 0.005:
                    return speed
            return SPEEDS[-1][0]

        for speed, _label in reversed(SPEEDS):
            if speed < current_speed - 0.005:
                return speed

        return SPEEDS[0][0]

    def _next_smooth_speed(self, direction):
        current_speed = self._current_speed()
        next_speed = current_speed + (SMOOTH_SPEED_STEP * direction)
        next_speed = _clamp(next_speed, SMOOTH_MIN_SPEED, SMOOTH_MAX_SPEED)
        return round(next_speed, 2)

    def _speed_for_wheel_direction(self, direction):
        if USE_SMOOTH_SPEED:
            return self._next_smooth_speed(direction)
        return self._next_speed(direction)

    def set_speed(self, speed):
        self.player.SetPlaySpeed(float(speed))
        applied_speed = self._current_speed()
        self.last_change_time = time.time()
        self._show_status(applied_speed)
        return applied_speed

    def _show_status(self, speed=None):
        if speed is None:
            speed = self._current_speed()
        if self.is_left_alt_down():
            self._capture_viewport_rect_from_cursor()
        self.overlay.show_text("Preview speed %s" % _speed_label(speed), self.viewport_rect)

    def _tick(self):
        if not self.running:
            return

        try:
            steps = self.pending_steps
            self.pending_steps = 0

            while steps > 0:
                self.set_speed(self._speed_for_wheel_direction(1))
                steps -= 1

            while steps < 0:
                self.set_speed(self._speed_for_wheel_direction(-1))
                steps += 1

            if self.is_left_alt_down():
                self._show_status()
            elif time.time() - self.last_change_time > OVERLAY_HOLD_SECONDS:
                try:
                    self.overlay.hide()
                except Exception:
                    pass
        except Exception:
            print("%s error:\n%s" % (TOOL_NAME, traceback.format_exc()))

    def status_payload(self):
        return {
            "running": bool(self.running),
            "hook_installed": bool(self.hook_installed),
            "hook_error": self.hook.error,
            "current_speed": self._current_speed(),
            "left_alt_down": self.is_left_alt_down(),
            "use_smooth_speed": bool(USE_SMOOTH_SPEED),
            "viewport_rect": self.viewport_rect,
        }


def start_alt_wheel_preview_speed():
    app = QtWidgets.QApplication.instance()
    if app is None:
        FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
        return None

    controller = _get_active_controller()
    if controller is not None:
        if getattr(controller, "script_version", None) == SCRIPT_VERSION:
            controller.reset_default()
            return controller

        try:
            controller.stop()
        except Exception:
            pass

    controller = AltWheelPreviewSpeedController(app)
    _set_active_controller(controller)
    controller.start()
    return controller


def run_with_error_dialog():
    try:
        return start_alt_wheel_preview_speed()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
        return None


run_with_error_dialog()
