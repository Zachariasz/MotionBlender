import ctypes
import json
import os
import sys
import time
import traceback


TOOL_NAME = "Precision Transform Shift RMB Helper"

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

LLKHF_INJECTED = 0x00000010
LLMHF_INJECTED = 0x00000001

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_KEYUP = 0x0002

VK_LBUTTON = 0x01
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_ssize_t

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(SCRIPT_DIR, ".precision_shift_rmb_helper_status.json")
STOP_PATH = os.path.join(SCRIPT_DIR, ".precision_shift_rmb_helper_stop")


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_ulong),
        ("pt", POINT),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
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

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    ctypes.c_void_p,
    ctypes.c_ulong,
]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_size_t,
    ctypes.c_void_p,
]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.c_int
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
user32.PeekMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = ctypes.c_int
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetCurrentProcessId.argtypes = []
kernel32.GetCurrentProcessId.restype = ctypes.c_ulong
kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_int


def _write_status(data):
    data = dict(data)
    data["helper_pid"] = int(kernel32.GetCurrentProcessId())
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    temp_path = STATUS_PATH + ".tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2, sort_keys=True)

        os.replace(temp_path, STATUS_PATH)
    except Exception:
        pass


def _key_down(vk_code):
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


def _shift_down():
    return _key_down(VK_SHIFT) or _key_down(VK_LSHIFT) or _key_down(VK_RSHIFT)


def _target_foreground(target_pid):
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return False

    process_id = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return process_id.value == target_pid


def _process_exists(process_id):
    handle = kernel32.OpenProcess(0x1000, 0, process_id)

    if not handle:
        return False

    kernel32.CloseHandle(handle)
    return True


def _mouse_input(flags):
    event = INPUT()
    event.type = INPUT_MOUSE
    event.union.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return event


def _key_input(vk_code, flags):
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.union.ki = KEYBDINPUT(vk_code, 0, flags, 0, 0)
    return event


def _send_inputs(events):
    if not events:
        return True

    array_type = INPUT * len(events)
    event_array = array_type(*events)
    sent = user32.SendInput(len(events), event_array, ctypes.sizeof(INPUT))
    return sent == len(events)


class ShiftRMBHelper(object):
    def __init__(self, target_pid):
        self.target_pid = target_pid
        self.mouse_hook = None
        self.keyboard_hook = None
        self.mouse_proc = HOOKPROC(self._mouse_proc)
        self.keyboard_proc = HOOKPROC(self._keyboard_proc)
        self.active = False
        self.running = True
        self.hidden_shift_keys = []
        self.press_count = 0
        self.release_count = 0
        self.handoff_count = 0
        self.error_text = None
        self.last_status_time = 0.0

    def start(self):
        module_handle = kernel32.GetModuleHandleW(None)
        self.mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self.mouse_proc, module_handle, 0)
        self.keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.keyboard_proc, module_handle, 0)

        if not self.mouse_hook or not self.keyboard_hook:
            raise ctypes.WinError()

        self._update_status("running")

    def stop(self):
        self.running = False

        if self.active:
            self._finish_precision(handoff_to_left=False)

        if self.mouse_hook:
            user32.UnhookWindowsHookEx(self.mouse_hook)
            self.mouse_hook = None

        if self.keyboard_hook:
            user32.UnhookWindowsHookEx(self.keyboard_hook)
            self.keyboard_hook = None

        self._update_status("stopped")

    def _update_status(self, state):
        _write_status(
            {
                "active": self.active,
                "error_text": self.error_text,
                "handoff_count": self.handoff_count,
                "hidden_shift_keys": list(self.hidden_shift_keys),
                "press_count": self.press_count,
                "release_count": self.release_count,
                "state": state,
                "target_pid": self.target_pid,
            }
        )
        self.last_status_time = time.time()

    def _call_next_mouse(self, code, w_param, l_param):
        return user32.CallNextHookEx(self.mouse_hook, code, w_param, l_param)

    def _call_next_keyboard(self, code, w_param, l_param):
        return user32.CallNextHookEx(self.keyboard_hook, code, w_param, l_param)

    def _hide_shift(self):
        self.hidden_shift_keys = []
        events = []

        for vk_code in (VK_LSHIFT, VK_RSHIFT):
            if _key_down(vk_code):
                self.hidden_shift_keys.append(vk_code)
                events.append(_key_input(vk_code, KEYEVENTF_KEYUP))

        if not self.hidden_shift_keys and _key_down(VK_SHIFT):
            self.hidden_shift_keys.append(VK_SHIFT)
            events.append(_key_input(VK_SHIFT, KEYEVENTF_KEYUP))

        return _send_inputs(events)

    def _restore_shift(self):
        events = []

        for vk_code in self.hidden_shift_keys:
            if _key_down(vk_code):
                events.append(_key_input(vk_code, 0))

        self.hidden_shift_keys = []
        return _send_inputs(events)

    def _begin_precision(self):
        if self.active:
            return True

        self._hide_shift()

        if not _send_inputs([_mouse_input(MOUSEEVENTF_RIGHTDOWN)]):
            self._restore_shift()
            return False

        self.active = True
        self.press_count += 1
        self._update_status("running")
        return True

    def _finish_precision(self, handoff_to_left):
        if not self.active:
            self._restore_shift()
            return True

        events = [_mouse_input(MOUSEEVENTF_RIGHTUP)]

        if handoff_to_left:
            events.append(_mouse_input(MOUSEEVENTF_LEFTDOWN))

        ok = _send_inputs(events)

        self.active = False
        self.release_count += 1

        if handoff_to_left:
            self.handoff_count += 1
            self.hidden_shift_keys = []
        else:
            self._restore_shift()

        self._update_status("running")
        return ok

    def _mouse_proc(self, code, w_param, l_param):
        try:
            if code != HC_ACTION:
                return self._call_next_mouse(code, w_param, l_param)

            event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents

            if event.flags & LLMHF_INJECTED:
                return self._call_next_mouse(code, w_param, l_param)

            if not _target_foreground(self.target_pid):
                return self._call_next_mouse(code, w_param, l_param)

            if w_param == WM_LBUTTONDOWN and _shift_down():
                if self._begin_precision():
                    return 1

                return self._call_next_mouse(code, w_param, l_param)

            if w_param == WM_LBUTTONUP and self.active:
                self._finish_precision(handoff_to_left=False)
                return 1

            return self._call_next_mouse(code, w_param, l_param)
        except Exception:
            self.error_text = traceback.format_exc()
            self._update_status("error")
            return self._call_next_mouse(code, w_param, l_param)

    def _keyboard_proc(self, code, w_param, l_param):
        try:
            if code != HC_ACTION:
                return self._call_next_keyboard(code, w_param, l_param)

            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

            if event.flags & LLKHF_INJECTED:
                return self._call_next_keyboard(code, w_param, l_param)

            if not self.active:
                return self._call_next_keyboard(code, w_param, l_param)

            if event.vkCode not in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                return self._call_next_keyboard(code, w_param, l_param)

            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                return 1

            if w_param in (WM_KEYUP, WM_SYSKEYUP):
                self._finish_precision(handoff_to_left=_key_down(VK_LBUTTON))
                return 1

            return self._call_next_keyboard(code, w_param, l_param)
        except Exception:
            self.error_text = traceback.format_exc()
            self._update_status("error")
            return self._call_next_keyboard(code, w_param, l_param)

    def run(self):
        message = MSG()

        while self.running:
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))

            if os.path.exists(STOP_PATH):
                break

            if not _process_exists(self.target_pid):
                break

            if self.active and not _key_down(VK_LBUTTON):
                self._finish_precision(handoff_to_left=False)

            if time.time() - self.last_status_time >= 0.5:
                self._update_status("running")

            time.sleep(0.005)


def main():
    if len(sys.argv) < 2:
        raise RuntimeError("Target MotionBuilder process id was not provided.")

    target_pid = int(sys.argv[1])

    if os.path.exists(STOP_PATH):
        os.remove(STOP_PATH)

    helper = ShiftRMBHelper(target_pid)

    try:
        helper.start()
        helper.run()
    except Exception:
        helper.error_text = traceback.format_exc()
        helper._update_status("error")
    finally:
        helper.stop()


if __name__ == "__main__":
    main()
