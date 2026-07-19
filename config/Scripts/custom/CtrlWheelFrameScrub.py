import ctypes
import os
import sys
import time
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import FBMessageBox, FBPlayerControl, FBSystem

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Ctrl Wheel Frame Scrub"
ACTIVE_CONTROLLER_ATTR = "_ctrl_wheel_frame_scrub_controller"
ACTIVE_STATE_MODULE = "_ctrl_wheel_frame_scrub_state"
LEGACY_CONTROLLER_ATTRS = (
    "_alt_wheel_frame_scrub_controller",
)
LEGACY_STATE_MODULES = (
    "_alt_wheel_frame_scrub_state",
)
SCRIPT_VERSION = 7

POLL_INTERVAL_MS = 15
OVERLAY_HOLD_SECONDS = 0.8
OVERLAY_BOTTOM_MARGIN = 24
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
VK_LCONTROL = 0xA2
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
HC_ACTION = 0

# Wheel up moves forward, wheel down moves backward. Change this if you prefer
# the opposite direction.
INVERT_WHEEL_DIRECTION = False
FRAMES_PER_WHEEL_STEP = 1
STOP_PLAYBACK_WHEN_SCRUBBING = True
SHOW_INFORMATION_BOX = False


def _is_key_down(vk_code):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def _is_any_mouse_button_down():
    return (
        _is_key_down(VK_LBUTTON)
        or _is_key_down(VK_RBUTTON)
        or _is_key_down(VK_MBUTTON)
        or _is_key_down(VK_XBUTTON1)
        or _is_key_down(VK_XBUTTON2)
    )


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


def _active_controller_state_module():
    module = sys.modules.get(ACTIVE_STATE_MODULE)
    if module is None:
        import types
        module = types.ModuleType(ACTIVE_STATE_MODULE)
        sys.modules[ACTIVE_STATE_MODULE] = module
    return module


def _active_controller_holders(app=None):
    holders = [_active_controller_state_module(), builtins]

    if app is None:
        try:
            app = QtWidgets.QApplication.instance()
        except Exception:
            app = None

    if app is not None:
        holders.append(app)

    return holders


def _iter_controller_holders(include_legacy=False):
    for holder in _active_controller_holders():
        yield holder

    if include_legacy:
        for module_name in LEGACY_STATE_MODULES:
            module = sys.modules.get(module_name)
            if module is not None:
                yield module


def _get_active_controller():
    for holder in _iter_controller_holders():
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
    for holder in _iter_controller_holders(include_legacy=True):
        for attr_name in (ACTIVE_CONTROLLER_ATTR,) + LEGACY_CONTROLLER_ATTRS:
            try:
                if getattr(holder, attr_name, None) is controller:
                    setattr(holder, attr_name, None)
            except Exception:
                pass

    try:
        controller.setParent(None)
    except Exception:
        pass


def _stop_legacy_frame_scrub_controllers():
    stopped = []

    for holder in _iter_controller_holders(include_legacy=True):
        for attr_name in LEGACY_CONTROLLER_ATTRS:
            try:
                controller = getattr(holder, attr_name, None)
            except Exception:
                continue

            if controller is None:
                continue

            try:
                if getattr(controller, "running", False):
                    controller.stop()
                    stopped.append(attr_name)
            except Exception:
                stopped.append(attr_name + " stop failed")

            try:
                setattr(holder, attr_name, None)
            except Exception:
                pass

    return stopped


class FrameScrubOverlay(QtWidgets.QLabel):
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
            "background-color: rgba(18, 18, 18, 210);"
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
                and self.controller.should_handle_wheel()
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


class CtrlWheelFrameScrubController(QtCore.QObject):
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
        self.overlay = FrameScrubOverlay() if SHOW_INFORMATION_BOX else None
        self.hook = _WindowsMouseHook(self)
        self.hook_installed = False

        self.timer = QtCore.QTimer(self)
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)

    def start(self):
        if self.running:
            return

        self.running = True
        self.hook_installed = self.hook.install()

        try:
            self.app.aboutToQuit.connect(self.stop)
        except Exception:
            pass

        self.timer.start(POLL_INTERVAL_MS)
        print(
            "%s active. Hold Left Ctrl and use the mouse wheel to scrub frames."
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

        self.hook.uninstall()

        try:
            if self.overlay is not None:
                self.overlay.hide()
                self.overlay.deleteLater()
        except Exception:
            pass

        _clear_active_controller(self)

    def is_left_control_down(self):
        return _is_key_down(VK_LCONTROL)

    def should_handle_wheel(self):
        return (
            self.running
            and self.is_left_control_down()
            and not _is_any_mouse_button_down()
        )

    def _is_wheel_event(self, event):
        wheel_event_type = _qt_event_type("Wheel")
        return wheel_event_type is not None and event.type() == wheel_event_type

    def eventFilter(self, obj, event):
        try:
            if not self._is_wheel_event(event):
                return QtCore.QObject.eventFilter(self, obj, event)

            if not self.should_handle_wheel():
                return QtCore.QObject.eventFilter(self, obj, event)

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

        direction = 1 if delta > 0 else -1
        if INVERT_WHEEL_DIRECTION:
            direction *= -1

        self.pending_steps += direction * steps * max(1, int(FRAMES_PER_WHEEL_STEP))
        self.last_change_time = time.time()

    def _capture_viewport_rect_from_cursor(self):
        cursor = _cursor_qpoint()

        try:
            widget = self.app.widgetAt(cursor)
        except Exception:
            widget = None

        candidates = []
        while widget is not None:
            if self.overlay is not None and widget is self.overlay:
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

    def _stop_playback_if_needed(self):
        if not STOP_PLAYBACK_WHEN_SCRUBBING:
            return

        try:
            if self.player.IsPlaying:
                self.player.Stop()
        except Exception:
            try:
                self.player.Stop()
            except Exception:
                pass

    def _scrub_frame_steps(self, frame_steps):
        if frame_steps == 0:
            return 0

        self._stop_playback_if_needed()

        direction = 1 if frame_steps > 0 else -1
        remaining = abs(int(frame_steps))
        moved = 0

        while remaining > 0:
            if direction > 0:
                ok = self.player.StepForward()
            else:
                ok = self.player.StepBackward()

            if ok is False:
                break

            moved += direction
            remaining -= 1

        self.last_change_time = time.time()
        self._show_status(moved)
        return moved

    def _current_time(self):
        try:
            return self.player.GetEditCurrentTime()
        except Exception:
            try:
                return FBSystem().LocalTime
            except Exception:
                return None

    def _current_frame(self):
        current_time = self._current_time()
        if current_time is None:
            return None

        try:
            return int(current_time.GetFrame(self.player.GetTransportFps()))
        except Exception:
            try:
                return int(current_time.GetFrame())
            except Exception:
                return None

    def _current_time_string(self):
        current_time = self._current_time()
        if current_time is None:
            return ""

        try:
            return str(current_time.GetTimeString())
        except Exception:
            return ""

    def _show_status(self, moved=0):
        if not SHOW_INFORMATION_BOX or self.overlay is None:
            return

        frame = self._current_frame()
        if self.is_left_control_down():
            self._capture_viewport_rect_from_cursor()

        if frame is None:
            text = "Frame scrub"
        else:
            text = "Frame %s" % frame

        if moved:
            if moved > 0:
                text += "  +%s" % moved
            else:
                text += "  %s" % moved

        self.overlay.show_text(text, self.viewport_rect)

    def _tick(self):
        if not self.running:
            return

        try:
            steps = self.pending_steps
            self.pending_steps = 0

            if steps:
                self._scrub_frame_steps(steps)
            elif SHOW_INFORMATION_BOX and self.is_left_control_down():
                self._show_status()
            elif time.time() - self.last_change_time > OVERLAY_HOLD_SECONDS:
                try:
                    if self.overlay is not None:
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
            "current_frame": self._current_frame(),
            "current_time": self._current_time_string(),
            "left_control_down": self.is_left_control_down(),
            "frames_per_wheel_step": int(FRAMES_PER_WHEEL_STEP),
            "invert_wheel_direction": bool(INVERT_WHEEL_DIRECTION),
            "show_information_box": bool(SHOW_INFORMATION_BOX),
            "viewport_rect": self.viewport_rect,
        }


def start_ctrl_wheel_frame_scrub():
    app = QtWidgets.QApplication.instance()
    if app is None:
        FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
        return None

    stopped_legacy = _stop_legacy_frame_scrub_controllers()
    if stopped_legacy:
        print("%s stopped old frame scrub controller(s): %s" % (
            TOOL_NAME,
            ", ".join(stopped_legacy),
        ))

    controller = _get_active_controller()
    if controller is not None:
        if getattr(controller, "script_version", None) == SCRIPT_VERSION:
            controller._show_status()
            return controller

        try:
            controller.stop()
        except Exception:
            pass

    controller = CtrlWheelFrameScrubController(app)
    _set_active_controller(controller)
    controller.start()
    return controller


def stop_ctrl_wheel_frame_scrub():
    controller = _get_active_controller()
    if controller is not None:
        controller.stop()
    return controller


def run_with_error_dialog():
    try:
        return start_ctrl_wheel_frame_scrub()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
        return None


run_with_error_dialog()
