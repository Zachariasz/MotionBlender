import ctypes
import os
import traceback

from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList, FBSystem, FBVector3d

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

try:
    import builtins
except ImportError:
    import __builtin__ as builtins


TOOL_NAME = "Precision Transform Hold Shift"

_SHIFT_RMB_REMAP_LOADED = True
try:
    try:
        _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        _SCRIPT_DIR = r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts"

    _SHIFT_RMB_SCRIPT = os.path.join(_SCRIPT_DIR, "PrecisionTransformShiftRMB.py")

    with open(_SHIFT_RMB_SCRIPT, "r", encoding="utf-8-sig") as _script_file:
        _shift_rmb_namespace = {
            "__file__": _SHIFT_RMB_SCRIPT,
            "__name__": "__precision_transform_shift_rmb_launcher__",
        }
        exec(
            compile(_script_file.read(), _SHIFT_RMB_SCRIPT, "exec"),
            _shift_rmb_namespace,
            _shift_rmb_namespace,
        )
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")

SERVICE_ATTR = "_codex_precision_transform_hold_shift_service"
POLL_INTERVAL_MS = 1
PRECISION_MULTIPLIER = 0.10
VECTOR_EPSILON = 0.000001

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

TRANSFORMS = [
    ("translation", "Translation", False),
    ("rotation", "Rotation", True),
    ("scaling", "Scaling", False),
]


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


def _is_precision_key_down():
    return (
        _is_key_down(VK_SHIFT)
        or _is_key_down(VK_LSHIFT)
        or _is_key_down(VK_RSHIFT)
    )


def _is_transform_mouse_down():
    return (
        _is_key_down(VK_LBUTTON)
        or _is_key_down(VK_RBUTTON)
        or _is_key_down(VK_MBUTTON)
    )


def _selected_transformable_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)

    return [
        model
        for model in selected_models
        if getattr(model, "Transformable", True)
    ]


def _model_key(model):
    try:
        value = model.UniqueName
        if value:
            return value
    except Exception:
        pass

    try:
        value = model.LongName
        if value:
            return value
    except Exception:
        pass

    try:
        value = model.Name
        if value:
            return value
    except Exception:
        return repr(model)

    return repr(model)


def _selection_signature(models):
    return tuple(_model_key(model) for model in models)


def _vector_to_list(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def _copy_vector(values):
    return FBVector3d(values[0], values[1], values[2])


def _read_vector(model, property_name):
    return _vector_to_list(getattr(model, property_name))


def _write_vector(model, property_name, values):
    setattr(model, property_name, _copy_vector(values))


def _wrapped_angle_delta(current, base):
    delta = current - base

    while delta > 180.0:
        delta -= 360.0

    while delta < -180.0:
        delta += 360.0

    return delta


def _scaled_values(base, current, is_rotation):
    scaled = []

    for index in range(3):
        if is_rotation:
            delta = _wrapped_angle_delta(current[index], base[index])
        else:
            delta = current[index] - base[index]

        scaled.append(base[index] + (delta * PRECISION_MULTIPLIER))

    return scaled


def _vectors_close(a, b, epsilon=VECTOR_EPSILON):
    return all(abs(a[index] - b[index]) <= epsilon for index in range(3))


def _transform_snapshot(model, transforms=TRANSFORMS):
    values = {}

    for name, property_name, _is_rotation in transforms:
        values[name] = _read_vector(model, property_name)

    return values


def _copy_snapshot(snapshot):
    return {
        name: list(values)
        for name, values in snapshot.items()
    }


class PrecisionTransformHoldShiftService(QtCore.QObject):
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)

        self.selection_signature = ()
        self.model_states = []
        self.transforms = tuple(TRANSFORMS)
        self.precision_active = False
        self.was_mouse_down = _is_transform_mouse_down()
        self.was_precision_down = _is_precision_key_down()
        self.error_reported = False

        self.timer = QtCore.QTimer(self)
        self._set_precise_timer()
        self.timer.timeout.connect(self._tick)

    def _set_precise_timer(self):
        try:
            if hasattr(QtCore.Qt, "TimerType"):
                self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
            else:
                self.timer.setTimerType(QtCore.Qt.PreciseTimer)
        except Exception:
            pass

    def start(self):
        self.timer.start(POLL_INTERVAL_MS)

    def stop(self):
        try:
            self.timer.stop()
        except Exception:
            pass

        self.precision_active = False

    def _capture_models(self, models):
        self.selection_signature = _selection_signature(models)
        self.model_states = []

        for model in models:
            snapshot = _transform_snapshot(model, self.transforms)
            self.model_states.append(
                {
                    "model": model,
                    "base": _copy_snapshot(snapshot),
                    "last_applied": _copy_snapshot(snapshot),
                }
            )

    def _begin_precision(self, models):
        self._capture_models(models)
        self.precision_active = True

    def _apply_precision(self):
        wrote_anything = False

        for state in self.model_states:
            model = state["model"]

            for name, property_name, is_rotation in self.transforms:
                current = _read_vector(model, property_name)
                last_applied = state["last_applied"].get(name)

                if last_applied is not None and _vectors_close(current, last_applied):
                    continue

                target = _scaled_values(state["base"][name], current, is_rotation)

                if not _vectors_close(target, current):
                    _write_vector(model, property_name, target)
                    wrote_anything = True

                state["last_applied"][name] = list(target)

        if wrote_anything:
            try:
                FBSystem().Scene.Evaluate()
            except Exception:
                pass

    def _refresh_normal_baseline(self, models):
        self._capture_models(models)
        self.precision_active = False

    def _finish_precision(self, models):
        if self.precision_active and models:
            self._apply_precision()

        self._refresh_normal_baseline(models)

    def _tick(self):
        try:
            models = _selected_transformable_models()
            mouse_down = _is_transform_mouse_down()
            precision_down = _is_precision_key_down()

            if not mouse_down or not models:
                self._finish_precision(models)
                self.was_mouse_down = mouse_down
                self.was_precision_down = precision_down
                return

            if not precision_down:
                self._finish_precision(models)
                self.was_mouse_down = mouse_down
                self.was_precision_down = False
                return

            selection_changed = (
                _selection_signature(models) != self.selection_signature
            )
            precision_just_pressed = precision_down and not self.was_precision_down
            mouse_just_pressed = mouse_down and not self.was_mouse_down

            if (
                selection_changed
                or not self.precision_active
                or precision_just_pressed
                or mouse_just_pressed
            ):
                self._begin_precision(models)
            else:
                self._apply_precision()

            self.was_mouse_down = mouse_down
            self.was_precision_down = precision_down
        except Exception:
            self._report_error(traceback.format_exc())

    def _report_error(self, details):
        if self.error_reported:
            return

        self.error_reported = True
        self.stop()
        FBMessageBox(TOOL_NAME + " Error", details[-1800:], "OK")


def start_precision_transform_hold_shift():
    app = QtWidgets.QApplication.instance()

    if app is None:
        FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
        return

    old_service = getattr(builtins, SERVICE_ATTR, None)

    if old_service is not None:
        try:
            old_service.stop()
        except Exception:
            pass

    service = PrecisionTransformHoldShiftService(app)
    setattr(builtins, SERVICE_ATTR, service)
    service.start()

    print("%s active: hold Shift while dragging transform gizmos for x0.1 precision." % TOOL_NAME)


if not globals().get("_SHIFT_RMB_REMAP_LOADED", False):
    try:
        start_precision_transform_hold_shift()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
