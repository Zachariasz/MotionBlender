import ctypes
import os
import subprocess
import threading
import time
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

import pyfbsdk
from pyfbsdk import FBCreateObject, FBFilterManager, FBMessageBox

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    import shiboken2 as shiboken


TOOL_NAME = "Key Reducing Precision Default"
SERVICE_ATTR = "_key_reducing_precision_default_service"
PRECISION = 0.7
FILTER_NAME = "Key Reducing"
FILTER_RESOURCE_PATHS = (
    "Filter/DataType/Number",
    "Filter/DataType/Vector",
)
TITLE_REFERENCE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "KeyReducingGeneralTitleReference.png",
)
INPUT_HELPER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "KeyReducingPrecisionInputHelper.vbs",
)
UI_POLL_INTERVAL_MS = 250
UI_STABILITY_SECONDS = 0.5
VK_CONTROL = 0x11
VK_A = 0x41
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1


if os.name == "nt":
    import ctypes.wintypes as wintypes

    ULONG_PTR = wintypes.WPARAM

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )


    class INPUT_UNION(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),)


    class INPUT(ctypes.Structure):
        _anonymous_ = ("data",)
        _fields_ = (
            ("type", wintypes.DWORD),
            ("data", INPUT_UNION),
        )


def set_key_reducing_precision(component):
    if component is None:
        return False

    try:
        precision = component.PropertyList.Find("Precision")
    except Exception:
        precision = None

    if precision is None:
        return False

    precision.Data = PRECISION
    return True


def _send_virtual_key(key_code, key_up=False):
    flags = KEYEVENTF_KEYUP if key_up else 0
    ctypes.windll.user32.keybd_event(key_code, 0, flags, 0)


def _send_unicode_character(character):
    down = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, ord(character), KEYEVENTF_UNICODE, 0, 0),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, ord(character), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0),
    )
    inputs = (INPUT * 2)(down, up)
    ctypes.windll.user32.SendInput(2, inputs, ctypes.sizeof(INPUT))


def _motionbuilder_is_foreground():
    if os.name != "nt":
        return False

    process_id = wintypes.DWORD()
    foreground = ctypes.windll.user32.GetForegroundWindow()
    if not foreground:
        return False
    ctypes.windll.user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
    return process_id.value == os.getpid()


def _images_match(reference, current):
    if reference.isNull() or current.isNull() or reference.size() != current.size():
        return False

    width = reference.width()
    height = reference.height()
    left_edge = 5
    right_edge = max(left_edge, width - 5)
    top_edge = 4
    bottom_edge = max(top_edge, height - 4)
    compared_pixels = max(1, (right_edge - left_edge) * (bottom_edge - top_edge))
    allowed_mismatches = max(12, int(compared_pixels * 0.03))
    mismatches = 0

    for y in range(top_edge, bottom_edge):
        for x in range(left_edge, right_edge):
            left = reference.pixelColor(x, y)
            right = current.pixelColor(x, y)
            delta = (
                abs(left.red() - right.red())
                + abs(left.green() - right.green())
                + abs(left.blue() - right.blue())
            )
            if delta > 24:
                mismatches += 1
                if mismatches > allowed_mismatches:
                    return False

    return True


def _qt_object_is_valid(value):
    try:
        if value is None:
            return False
        value.metaObject()
        return True
    except (RuntimeError, ReferenceError):
        return False


def _qt_object_pointer(value):
    try:
        if value is None:
            return None
        return int(shiboken.getCppPointer(value)[0])
    except Exception:
        return None


class FilterManagerProxy(object):
    def __init__(self, manager):
        self._manager = manager

    def CreateFilter(self, filter_type_name):
        filt = self._manager.CreateFilter(filter_type_name)
        if str(filter_type_name) == FILTER_NAME:
            set_key_reducing_precision(filt)
        return filt

    def __getattr__(self, name):
        return getattr(self._manager, name)


class KeyReducingPrecisionDefaultService(QtCore.QObject):
    def __init__(self):
        app = QtWidgets.QApplication.instance()
        QtCore.QObject.__init__(self, app)
        self.original_filter_manager_factory = getattr(pyfbsdk, "FBFilterManager", FBFilterManager)
        self.original_create_object = getattr(pyfbsdk, "FBCreateObject", FBCreateObject)
        self.resource_filters = []
        self.app = app
        self.ui_timer = None
        self.title_reference = QtGui.QImage(TITLE_REFERENCE_PATH)
        self.ui_input_running = False
        self.ui_applied = False
        self.ui_last_error = None
        self.ui_candidate_pointer = None
        self.ui_candidate_since = 0.0
        self.ui_window_handle = None
        self.installed = False

    def start(self):
        if self.installed:
            return

        service = self

        def patched_filter_manager(*args, **kwargs):
            manager = service.original_filter_manager_factory(*args, **kwargs)
            return FilterManagerProxy(manager)

        def patched_create_object(group_name, entry_name, object_name, nth=0):
            obj = service.original_create_object(group_name, entry_name, object_name, nth)
            if str(entry_name) == FILTER_NAME and str(group_name) in FILTER_RESOURCE_PATHS:
                set_key_reducing_precision(obj)
            return obj

        pyfbsdk.FBFilterManager = patched_filter_manager
        pyfbsdk.FBCreateObject = patched_create_object
        self.resource_filters = self.create_resource_filters()
        self.start_ui_watcher()
        self.installed = True

    def stop(self):
        if not self.installed:
            return

        pyfbsdk.FBFilterManager = self.original_filter_manager_factory
        pyfbsdk.FBCreateObject = self.original_create_object
        if self.ui_timer is not None:
            try:
                self.ui_timer.stop()
            except Exception:
                pass
            self.ui_timer = None
        for filt in self.resource_filters:
            try:
                filt.FBDelete()
            except Exception:
                pass
        self.resource_filters = []
        self.installed = False

    def start_ui_watcher(self):
        if (
            self.app is None
            or os.name != "nt"
            or self.title_reference.isNull()
            or not os.path.isfile(INPUT_HELPER_PATH)
        ):
            return

        self.ui_timer = QtCore.QTimer(self)
        self.ui_timer.setInterval(UI_POLL_INTERVAL_MS)
        self.ui_timer.timeout.connect(self.poll_key_reducing_ui)
        self.ui_timer.start()

    def find_key_reducing_ui(self):
        if self.app is None:
            return None

        for dock in self.app.allWidgets():
            if not _qt_object_is_valid(dock):
                continue
            try:
                if not isinstance(dock, QtWidgets.QDockWidget) or dock.windowTitle() != "Resources":
                    continue
            except RuntimeError:
                continue

            title = None
            value = None
            try:
                children = dock.findChildren(QtWidgets.QWidget)
            except RuntimeError:
                continue

            for widget in children:
                if not _qt_object_is_valid(widget):
                    continue
                try:
                    accessible_name = widget.accessibleName()
                    if accessible_name == "GeneralTitle" and widget.isVisible():
                        title = widget
                    elif accessible_name == "Value0" and widget.isVisible():
                        value = widget
                except RuntimeError:
                    continue

            if not _qt_object_is_valid(title) or not _qt_object_is_valid(value):
                continue

            try:
                current_title = title.grab().toImage()
            except RuntimeError:
                continue
            if _images_match(self.title_reference, current_title):
                return value

        return None

    def arm_key_reducing_ui_input(self):
        if self.app is None:
            return False

        for dock in self.app.allWidgets():
            try:
                if not isinstance(dock, QtWidgets.QDockWidget) or dock.windowTitle() != "Resources":
                    continue

                title = None
                value = None
                children = dock.findChildren(QtWidgets.QWidget)
                for widget in children:
                    try:
                        accessible_name = widget.accessibleName()
                        if accessible_name == "GeneralTitle" and widget.isVisible():
                            title = widget
                        elif accessible_name == "Value0" and widget.isVisible():
                            value = widget
                    except RuntimeError:
                        continue

                if title is None or value is None:
                    continue
                if not _images_match(self.title_reference, title.grab().toImage()):
                    continue

                pointer = _qt_object_pointer(value)
                if pointer is None:
                    continue

                now = time.time()
                if pointer != self.ui_candidate_pointer:
                    self.ui_candidate_pointer = pointer
                    self.ui_candidate_since = now
                    return False
                if (now - self.ui_candidate_since) < UI_STABILITY_SECONDS:
                    return False

                window = value.window()
                self.ui_window_handle = int(window.winId())
                window.activateWindow()
                value.setFocus(QtCore.Qt.OtherFocusReason)
                return True
            except (RuntimeError, ReferenceError):
                self.ui_candidate_pointer = None
                self.ui_candidate_since = 0.0
                continue

        self.ui_candidate_pointer = None
        self.ui_candidate_since = 0.0
        return False

    def poll_key_reducing_ui(self):
        if self.ui_applied:
            if self.ui_timer is not None:
                self.ui_timer.stop()
            return
        if self.ui_input_running:
            return

        try:
            if not self.arm_key_reducing_ui_input():
                return
            self.ui_input_running = True
            self.ui_last_error = None
            worker = threading.Thread(target=self._type_ui_precision)
            worker.daemon = True
            worker.start()
        except RuntimeError:
            self.ui_candidate_pointer = None
            self.ui_candidate_since = 0.0
        except Exception:
            self.ui_last_error = traceback.format_exc()[-1200:]
            self.ui_input_running = False

    def _type_ui_precision(self):
        try:
            command = [
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "wscript.exe"),
                "//B",
                "//Nologo",
                INPUT_HELPER_PATH,
                str(os.getpid()),
            ]
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(command, creationflags=creation_flags)
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError("Precision input helper exited with code %s" % return_code)
            self.ui_applied = True
        except Exception:
            self.ui_last_error = traceback.format_exc()[-1200:]
        finally:
            self.ui_input_running = False

    def create_resource_filters(self):
        filters = []
        for path in FILTER_RESOURCE_PATHS:
            try:
                filt = self.original_create_object(path, FILTER_NAME, FILTER_NAME)
                if set_key_reducing_precision(filt):
                    filters.append(filt)
            except Exception:
                pass
        return filters

    def status(self):
        manager_filter_precision = None
        resource_precisions = []

        try:
            manager = pyfbsdk.FBFilterManager()
            filt = manager.CreateFilter(FILTER_NAME)
            prop = filt.PropertyList.Find("Precision") if filt else None
            if prop:
                manager_filter_precision = prop.Data
            if filt:
                filt.FBDelete()
        except Exception:
            manager_filter_precision = "ERROR"

        for filt in self.resource_filters:
            try:
                prop = filt.PropertyList.Find("Precision")
                resource_precisions.append(prop.Data if prop else None)
            except Exception:
                resource_precisions.append("ERROR")

        return {
            "installed": self.installed,
            "manager_filter_precision": manager_filter_precision,
            "resource_filter_precisions": resource_precisions,
            "ui_reference_loaded": not self.title_reference.isNull(),
            "ui_helper_available": os.path.isfile(INPUT_HELPER_PATH),
            "ui_input_running": self.ui_input_running,
            "ui_applied": self.ui_applied,
            "ui_last_error": self.ui_last_error,
        }


def install_key_reducing_precision_default():
    old_service = getattr(builtins, SERVICE_ATTR, None)
    if old_service is not None:
        try:
            old_service.stop()
        except Exception:
            pass

    service = KeyReducingPrecisionDefaultService()
    setattr(builtins, SERVICE_ATTR, service)
    service.start()
    return service


try:
    install_key_reducing_precision_default()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
