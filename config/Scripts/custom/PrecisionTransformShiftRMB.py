import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from pyfbsdk import FBInputModifier, FBInputType, FBMessageBox, FBSystem

try:
    import builtins
except ImportError:
    import __builtin__ as builtins


TOOL_NAME = "Precision Transform Shift RMB"
SERVICE_ATTR = "_codex_precision_transform_shift_rmb_service"
OLD_SERVICE_ATTR = "_codex_precision_transform_hold_shift_service"

VK_LBUTTON = 0x01
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

WH_MOUSE_LL = 14
HC_ACTION = 0

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

LLMHF_INJECTED = 0x00000001

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_KEYUP = 0x0002

POLL_INTERVAL_MS = 16

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_ssize_t


def _configure_user32():
    try:
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
    except Exception:
        pass


_configure_user32()


def _is_key_down(vk_code):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def _is_shift_down():
    return (
        _is_key_down(VK_SHIFT)
        or _is_key_down(VK_LSHIFT)
        or _is_key_down(VK_RSHIFT)
    )


def _is_left_down():
    return _is_key_down(VK_LBUTTON)


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", INPUT_UNION),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p)

_USER32 = ctypes.windll.user32
_KERNEL32 = ctypes.windll.kernel32


def _configure_hook_api():
    try:
        _USER32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            HOOKPROC,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        _USER32.SetWindowsHookExW.restype = ctypes.c_void_p
        _USER32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_void_p,
        ]
        _USER32.CallNextHookEx.restype = LRESULT
        _USER32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        _USER32.UnhookWindowsHookEx.restype = ctypes.c_int
        _USER32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        _USER32.SendInput.restype = ctypes.c_uint
        _USER32.GetForegroundWindow.argtypes = []
        _USER32.GetForegroundWindow.restype = ctypes.c_void_p
        _USER32.GetWindowThreadProcessId.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        _USER32.GetWindowThreadProcessId.restype = ctypes.c_ulong

        _KERNEL32.GetCurrentProcessId.argtypes = []
        _KERNEL32.GetCurrentProcessId.restype = ctypes.c_ulong
        _KERNEL32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        _KERNEL32.GetModuleHandleW.restype = ctypes.c_void_p
    except Exception:
        pass


_configure_hook_api()


def _make_mouse_input(flags):
    event = INPUT()
    event.type = INPUT_MOUSE
    event.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return event


def _make_key_input(vk_code, flags):
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.union.ki = KEYBDINPUT(vk_code, 0, flags, 0, 0)
    return event


def _send_inputs(events):
    if not events:
        return True

    array_type = INPUT * len(events)
    event_array = array_type(*events)
    sent = _USER32.SendInput(len(events), event_array, ctypes.sizeof(INPUT))
    return sent == len(events)


def _qt_mouse_button(name):
    if hasattr(QtCore.Qt, "MouseButton"):
        return getattr(QtCore.Qt.MouseButton, name)

    return getattr(QtCore.Qt, name)


def _qt_keyboard_modifier(name):
    if hasattr(QtCore.Qt, "KeyboardModifier"):
        return getattr(QtCore.Qt.KeyboardModifier, name)

    return getattr(QtCore.Qt, name)


def _qt_event_type(name):
    if hasattr(QtCore.QEvent, "Type"):
        return getattr(QtCore.QEvent.Type, name)

    return getattr(QtCore.QEvent, name)


def _enum_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    raw_value = getattr(value, "value", None)
    if raw_value is not None:
        return int(raw_value)

    return int(value)


def _same_enum_value(a, b):
    try:
        return _enum_int(a) == _enum_int(b)
    except Exception:
        return a == b


LEFT_BUTTON = _qt_mouse_button("LeftButton")
RIGHT_BUTTON = _qt_mouse_button("RightButton")
NO_BUTTON = _qt_mouse_button("NoButton")
NO_MODIFIER = _qt_keyboard_modifier("NoModifier")
RIGHT_BUTTON_KEY = _enum_int(RIGHT_BUTTON)

MOUSE_PRESS = _qt_event_type("MouseButtonPress")
MOUSE_RELEASE = _qt_event_type("MouseButtonRelease")
MOUSE_MOVE = _qt_event_type("MouseMove")
KEY_RELEASE = _qt_event_type("KeyRelease")


def _event_button(event):
    try:
        return event.button()
    except Exception:
        return NO_BUTTON


def _event_buttons(event):
    try:
        return event.buttons()
    except Exception:
        return NO_BUTTON


def _event_local_pos(event):
    for attr_name in ("position", "localPos", "pos"):
        try:
            value = getattr(event, attr_name)()

            if hasattr(value, "toPointF"):
                return value.toPointF()

            return QtCore.QPointF(value)
        except Exception:
            pass

    return QtCore.QPointF(0.0, 0.0)


def _event_scene_pos(event, local_pos):
    for attr_name in ("scenePosition", "windowPos"):
        try:
            return getattr(event, attr_name)()
        except Exception:
            pass

    return local_pos


def _event_global_pos(event, local_pos):
    for attr_name in ("globalPosition", "screenPos", "globalPos"):
        try:
            value = getattr(event, attr_name)()

            if hasattr(value, "toPointF"):
                return value.toPointF()

            return QtCore.QPointF(value)
        except Exception:
            pass

    return local_pos


def _event_xy(event):
    local_pos = _event_local_pos(event)
    return int(round(local_pos.x())), int(round(local_pos.y()))


class PrecisionTransformShiftRMBService(QtCore.QObject):
    def __init__(self, app):
        QtCore.QObject.__init__(self, app)

        self.app = app
        self.active = False
        self.injecting = False
        self.suppress_until_left_up = False
        self.target = None
        self.last_source_event = None
        self.renderer = None
        self.press_count = 0
        self.move_count = 0
        self.release_count = 0
        self.error_text = None

    def start(self):
        self.app.installEventFilter(self)

    def stop(self):
        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass

        self.active = False
        self.suppress_until_left_up = False
        self.target = None

    def _send_mouse_event(self, target, event_type, source_event, button, buttons):
        x, y = _event_xy(source_event)

        if self.renderer is None:
            self.renderer = FBSystem().Renderer

        if event_type == MOUSE_PRESS:
            input_type = FBInputType.kFBButtonPress
        elif event_type == MOUSE_RELEASE:
            input_type = FBInputType.kFBButtonRelease
        else:
            input_type = FBInputType.kFBMotionNotify

        return bool(
            self.renderer.MouseInput(
                x,
                y,
                input_type,
                RIGHT_BUTTON_KEY,
                FBInputModifier.kFBKeyNone,
            )
        )

    def _start_rmb_drag(self, target, event):
        self.target = target
        self.last_source_event = event

        if not self._send_mouse_event(target, MOUSE_PRESS, event, RIGHT_BUTTON, RIGHT_BUTTON):
            return False

        self.active = True
        self.suppress_until_left_up = False
        self.press_count += 1
        return True

    def _send_rmb_move(self, event):
        if self.target is None:
            return False

        self.last_source_event = event

        if self._send_mouse_event(
            self.target,
            MOUSE_MOVE,
            event,
            NO_BUTTON,
            RIGHT_BUTTON,
        ):
            self.move_count += 1
            return True

        return False

    def _finish_rmb_drag(self, source_event=None, suppress_until_left_up=False):
        if not self.active or self.target is None:
            self.active = False
            self.suppress_until_left_up = suppress_until_left_up
            return False

        event = source_event or self.last_source_event

        if event is not None:
            self._send_mouse_event(
                self.target,
                MOUSE_RELEASE,
                event,
                RIGHT_BUTTON,
                NO_BUTTON,
            )
            self.release_count += 1

        self.active = False
        self.target = None
        self.suppress_until_left_up = suppress_until_left_up
        return True

    def _is_shift_key_release(self, event):
        try:
            return _enum_int(event.key()) in (0x01000020, 0x01000021)
        except Exception:
            return False

    def eventFilter(self, watched, event):
        if self.injecting:
            return False

        try:
            event_type = event.type()

            if event_type == KEY_RELEASE and self.active and self._is_shift_key_release(event):
                self._finish_rmb_drag(None, True)
                return False

            if event_type not in (MOUSE_PRESS, MOUSE_MOVE, MOUSE_RELEASE):
                return False

            if self.suppress_until_left_up:
                if event_type == MOUSE_RELEASE and _same_enum_value(_event_button(event), LEFT_BUTTON):
                    self.suppress_until_left_up = False

                return True

            if self.active:
                if event_type == MOUSE_MOVE:
                    self._send_rmb_move(event)
                    return True

                if event_type == MOUSE_RELEASE and _same_enum_value(_event_button(event), LEFT_BUTTON):
                    self._finish_rmb_drag(event, False)
                    return True

                return False

            if (
                event_type == MOUSE_PRESS
                and _same_enum_value(_event_button(event), LEFT_BUTTON)
                and _is_shift_down()
            ):
                return self._start_rmb_drag(watched, event)

            return False
        except Exception:
            self.error_text = traceback.format_exc()
            self.stop()
            FBMessageBox(TOOL_NAME + " Error", self.error_text[-1800:], "OK")
            return False


class WindowsMouseHookPrecisionService(QtCore.QObject):
    def __init__(self, app):
        QtCore.QObject.__init__(self, app)

        self.app = app
        self.current_pid = _KERNEL32.GetCurrentProcessId()
        self.mouse_hook = None
        self.mouse_proc = HOOKPROC(self._mouse_proc)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._tick)

        self.active = False
        self.shift_hidden = False
        self.press_count = 0
        self.release_count = 0
        self.handoff_count = 0
        self.error_text = None

    def start(self):
        self.stop()

        module_handle = _KERNEL32.GetModuleHandleW(None)
        self.mouse_hook = _USER32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self.mouse_proc,
            module_handle,
            0,
        )

        if not self.mouse_hook:
            raise ctypes.WinError()

        self.timer.start()

    def stop(self):
        if self.active:
            self._finish_precision_drag(handoff_to_left=False)

        if self.mouse_hook:
            try:
                _USER32.UnhookWindowsHookEx(self.mouse_hook)
            except Exception:
                pass

        self.mouse_hook = None

        try:
            self.timer.stop()
        except Exception:
            pass

    def _call_next(self, code, w_param, l_param):
        return _USER32.CallNextHookEx(self.mouse_hook, code, w_param, l_param)

    def _foreground_is_motionbuilder(self):
        foreground_window = _USER32.GetForegroundWindow()

        if not foreground_window:
            return False

        process_id = ctypes.c_ulong()
        _USER32.GetWindowThreadProcessId(foreground_window, ctypes.byref(process_id))
        return process_id.value == self.current_pid

    def _hide_shift_for_motionbuilder(self):
        events = []

        if _is_key_down(VK_LSHIFT):
            events.append(_make_key_input(VK_LSHIFT, KEYEVENTF_KEYUP))

        if _is_key_down(VK_RSHIFT):
            events.append(_make_key_input(VK_RSHIFT, KEYEVENTF_KEYUP))

        if not events and _is_key_down(VK_SHIFT):
            events.append(_make_key_input(VK_SHIFT, KEYEVENTF_KEYUP))

        self.shift_hidden = bool(events) and _send_inputs(events)

    def _restore_shift_if_needed(self):
        if not self.shift_hidden:
            return

        events = []

        if _is_key_down(VK_LSHIFT):
            events.append(_make_key_input(VK_LSHIFT, 0))

        if _is_key_down(VK_RSHIFT):
            events.append(_make_key_input(VK_RSHIFT, 0))

        if not events and _is_key_down(VK_SHIFT):
            events.append(_make_key_input(VK_SHIFT, 0))

        _send_inputs(events)
        self.shift_hidden = False

    def _begin_precision_drag(self):
        if self.active:
            return True

        self._hide_shift_for_motionbuilder()

        if not _send_inputs([_make_mouse_input(MOUSEEVENTF_RIGHTDOWN)]):
            self._restore_shift_if_needed()
            return False

        self.active = True
        self.press_count += 1
        return True

    def _finish_precision_drag(self, handoff_to_left):
        if not self.active:
            self._restore_shift_if_needed()
            return True

        events = [_make_mouse_input(MOUSEEVENTF_RIGHTUP)]

        if handoff_to_left:
            events.append(_make_mouse_input(MOUSEEVENTF_LEFTDOWN))

        ok = _send_inputs(events)

        self.active = False
        self.release_count += 1

        if handoff_to_left:
            self.handoff_count += 1
            self.shift_hidden = False
        else:
            self._restore_shift_if_needed()

        return ok

    def _tick(self):
        try:
            if not self.active:
                return

            if not _is_left_down():
                self._finish_precision_drag(handoff_to_left=False)
                return

            if not _is_shift_down():
                self._finish_precision_drag(handoff_to_left=True)
        except Exception:
            self.error_text = traceback.format_exc()
            self.stop()
            FBMessageBox(TOOL_NAME + " Error", self.error_text[-1800:], "OK")

    def _mouse_proc(self, code, w_param, l_param):
        try:
            if code != HC_ACTION:
                return self._call_next(code, w_param, l_param)

            event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents

            if event.flags & LLMHF_INJECTED:
                return self._call_next(code, w_param, l_param)

            if not self._foreground_is_motionbuilder():
                return self._call_next(code, w_param, l_param)

            if w_param == WM_LBUTTONDOWN and _is_shift_down():
                if self._begin_precision_drag():
                    return 1

                return self._call_next(code, w_param, l_param)

            if w_param == WM_LBUTTONUP and self.active:
                self._finish_precision_drag(handoff_to_left=False)
                return 1

            return self._call_next(code, w_param, l_param)
        except Exception:
            self.error_text = traceback.format_exc()
            self.stop()
            return self._call_next(code, w_param, l_param)


class QtSendInputPrecisionService(QtCore.QObject):
    def __init__(self, app):
        QtCore.QObject.__init__(self, app)

        self.app = app
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._tick)

        self.active = False
        self.shift_hidden = False
        self.ignore_next_left_release = False
        self.press_count = 0
        self.release_count = 0
        self.handoff_count = 0
        self.error_text = None

    def start(self):
        self.stop()
        self.app.installEventFilter(self)
        self.timer.start()

    def stop(self):
        if self.active:
            self._finish_precision_drag(handoff_to_left=False)

        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass

        try:
            self.timer.stop()
        except Exception:
            pass

    def _hide_shift_for_motionbuilder(self):
        events = []

        if _is_key_down(VK_LSHIFT):
            events.append(_make_key_input(VK_LSHIFT, KEYEVENTF_KEYUP))

        if _is_key_down(VK_RSHIFT):
            events.append(_make_key_input(VK_RSHIFT, KEYEVENTF_KEYUP))

        if not events and _is_key_down(VK_SHIFT):
            events.append(_make_key_input(VK_SHIFT, KEYEVENTF_KEYUP))

        self.shift_hidden = bool(events) and _send_inputs(events)

    def _restore_shift_if_needed(self):
        if not self.shift_hidden:
            return

        events = []

        if _is_key_down(VK_LSHIFT):
            events.append(_make_key_input(VK_LSHIFT, 0))

        if _is_key_down(VK_RSHIFT):
            events.append(_make_key_input(VK_RSHIFT, 0))

        if not events and _is_key_down(VK_SHIFT):
            events.append(_make_key_input(VK_SHIFT, 0))

        _send_inputs(events)
        self.shift_hidden = False

    def _begin_precision_drag(self):
        if self.active:
            return True

        self._hide_shift_for_motionbuilder()
        self.active = True
        self.ignore_next_left_release = True

        ok = _send_inputs(
            [
                _make_mouse_input(MOUSEEVENTF_LEFTUP),
                _make_mouse_input(MOUSEEVENTF_RIGHTDOWN),
            ]
        )

        if not ok:
            self.active = False
            self.ignore_next_left_release = False
            self._restore_shift_if_needed()
            return False

        self.press_count += 1
        return True

    def _finish_precision_drag(self, handoff_to_left):
        if not self.active:
            self._restore_shift_if_needed()
            return True

        events = [_make_mouse_input(MOUSEEVENTF_RIGHTUP)]

        if handoff_to_left:
            events.append(_make_mouse_input(MOUSEEVENTF_LEFTDOWN))

        ok = _send_inputs(events)

        self.active = False
        self.ignore_next_left_release = False
        self.release_count += 1

        if handoff_to_left:
            self.handoff_count += 1
            self.shift_hidden = False
        else:
            self._restore_shift_if_needed()

        return ok

    def _is_shift_key_release(self, event):
        try:
            return _enum_int(event.key()) in (0x01000020, 0x01000021)
        except Exception:
            return False

    def _tick(self):
        try:
            if self.active and not _is_shift_down():
                self._finish_precision_drag(handoff_to_left=True)
        except Exception:
            self.error_text = traceback.format_exc()
            self.stop()
            FBMessageBox(TOOL_NAME + " Error", self.error_text[-1800:], "OK")

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()

            if event_type == KEY_RELEASE and self.active and self._is_shift_key_release(event):
                self._finish_precision_drag(handoff_to_left=True)
                return False

            if event_type not in (MOUSE_PRESS, MOUSE_RELEASE):
                return False

            if self.active:
                if event_type == MOUSE_RELEASE and _same_enum_value(_event_button(event), LEFT_BUTTON):
                    if self.ignore_next_left_release:
                        self.ignore_next_left_release = False
                        return True

                    self._finish_precision_drag(handoff_to_left=False)
                    return True

                return False

            if (
                event_type == MOUSE_PRESS
                and _same_enum_value(_event_button(event), LEFT_BUTTON)
                and _is_shift_down()
            ):
                QtCore.QTimer.singleShot(0, self._begin_precision_drag)
                return True

            return False
        except Exception:
            self.error_text = traceback.format_exc()
            self.stop()
            FBMessageBox(TOOL_NAME + " Error", self.error_text[-1800:], "OK")
            return False


class ExternalPrecisionHelperService(QtCore.QObject):
    def __init__(self, app):
        QtCore.QObject.__init__(self, app)

        self.app = app
        self.process = None
        self.error_text = None
        self.script_dir = self._script_dir()
        self.helper_path = os.path.join(self.script_dir, "PrecisionTransformShiftRMBHelper.py")
        self.status_path = os.path.join(self.script_dir, ".precision_shift_rmb_helper_status.json")
        self.stop_path = os.path.join(self.script_dir, ".precision_shift_rmb_helper_stop")
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll_status)
        self.last_status = None

    def _script_dir(self):
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts"

    def _python_command(self):
        candidates = []

        for name in ("pythonw.exe", "python.exe", "py.exe"):
            path = shutil.which(name)

            if path:
                candidates.append(path)

        for path in candidates:
            base_name = os.path.basename(path).lower()

            if base_name == "py.exe":
                return [path, "-3"]

            return [path]

        return None

    def _read_status(self):
        try:
            with open(self.status_path, "r", encoding="utf-8") as status_file:
                return json.load(status_file)
        except Exception:
            return None

    def _request_helper_stop(self):
        try:
            with open(self.stop_path, "w", encoding="utf-8") as stop_file:
                stop_file.write(str(time.time()))
        except Exception:
            pass

        for _index in range(20):
            status = self._read_status()

            if status and status.get("state") == "stopped":
                break

            time.sleep(0.05)

    def start(self):
        self.stop()
        self._request_helper_stop()

        if not os.path.isfile(self.helper_path):
            raise RuntimeError("Helper script does not exist: %s" % self.helper_path)

        python_command = self._python_command()

        if not python_command:
            raise RuntimeError("Could not find pythonw.exe, python.exe, or py.exe on PATH.")

        try:
            if os.path.exists(self.stop_path):
                os.remove(self.stop_path)
        except Exception:
            pass

        target_pid = int(_KERNEL32.GetCurrentProcessId())
        command = python_command + [self.helper_path, str(target_pid)]
        startupinfo = None
        creationflags = 0

        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            command,
            cwd=self.script_dir,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        self.timer.start()

    def stop(self):
        try:
            self.timer.stop()
        except Exception:
            pass

        self._request_helper_stop()

        if self.process is not None:
            try:
                if self.process.poll() is None:
                    self.process.wait(1.0)
            except Exception:
                pass

        self.process = None

    def _poll_status(self):
        status = self._read_status()

        if status is not None:
            self.last_status = status
            self.error_text = status.get("error_text")


def start_precision_transform_shift_rmb():
    app = QtWidgets.QApplication.instance()

    if app is None:
        FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
        return

    old_transform_service = getattr(builtins, OLD_SERVICE_ATTR, None)

    if old_transform_service is not None:
        try:
            old_transform_service.stop()
        except Exception:
            pass

    old_service = getattr(builtins, SERVICE_ATTR, None)

    if old_service is not None:
        try:
            old_service.stop()
        except Exception:
            pass

    service = ExternalPrecisionHelperService(app)
    setattr(builtins, SERVICE_ATTR, service)
    service.start()

    print("%s active: external Shift+LMB to RMB helper is running." % TOOL_NAME)


try:
    start_precision_transform_shift_rmb()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
