import ctypes
import os
import traceback

from pyfbsdk import (
    FBGetSelectedModels,
    FBMessageBox,
    FBModelList,
    FBModelTransformationType,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


TOOL_NAME = "Precision Transform Gizmo"

_PRECISION_TRANSFORM_HOLD_LOADED = True
try:
    try:
        _OLD_PRECISION_WINDOW = globals().get("_PRECISION_TRANSFORM_GIZMO")
        if _OLD_PRECISION_WINDOW is not None:
            _OLD_PRECISION_WINDOW.close()
    except Exception:
        pass

    try:
        _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        _SCRIPT_DIR = r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts"

    _HOLD_SHIFT_SCRIPT = os.path.join(_SCRIPT_DIR, "PrecisionTransformShiftRMB.py")

    with open(_HOLD_SHIFT_SCRIPT, "r", encoding="utf-8-sig") as _script_file:
        _hold_shift_namespace = {
            "__file__": _HOLD_SHIFT_SCRIPT,
            "__name__": "__precision_transform_hold_shift_launcher__",
        }
        exec(
            compile(_script_file.read(), _HOLD_SHIFT_SCRIPT, "exec"),
            _hold_shift_namespace,
            _hold_shift_namespace,
        )
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")

POLL_INTERVAL_MS = 16
DEFAULT_MULTIPLIER = 0.10
VECTOR_EPSILON = 0.000001

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04

TRANSFORMS = [
    (
        "translation",
        "T",
        FBModelTransformationType.kModelTranslation,
        False,
    ),
    (
        "rotation",
        "R",
        FBModelTransformationType.kModelRotation,
        True,
    ),
    (
        "scaling",
        "S",
        FBModelTransformationType.kModelScaling,
        False,
    ),
]

_PRECISION_TRANSFORM_GIZMO = None


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
        return model.UniqueName
    except Exception:
        pass

    try:
        return model.LongName
    except Exception:
        pass

    try:
        return model.Name
    except Exception:
        return repr(model)


def _selection_signature(models):
    return tuple(_model_key(model) for model in models)


def _vector_to_list(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def _copy_vector(values):
    return FBVector3d(values[0], values[1], values[2])


def _read_vector(model, transform_type):
    vector = FBVector3d()
    model.GetVector(vector, transform_type, False)
    return _vector_to_list(vector)


def _write_vector(model, transform_type, values):
    model.SetVector(_copy_vector(values), transform_type, False)


def _wrapped_angle_delta(current, base):
    delta = current - base

    while delta > 180.0:
        delta -= 360.0

    while delta < -180.0:
        delta += 360.0

    return delta


def _scaled_values(base, current, multiplier, is_rotation):
    scaled = []

    for index in range(3):
        if is_rotation:
            delta = _wrapped_angle_delta(current[index], base[index])
        else:
            delta = current[index] - base[index]

        scaled.append(base[index] + (delta * multiplier))

    return scaled


def _vectors_close(a, b, epsilon=VECTOR_EPSILON):
    return all(abs(a[index] - b[index]) <= epsilon for index in range(3))


def _transform_snapshot(model):
    values = {}

    for name, _label, transform_type, _is_rotation in TRANSFORMS:
        values[name] = _read_vector(model, transform_type)

    return values


def _copy_snapshot(snapshot):
    return {
        name: list(values)
        for name, values in snapshot.items()
    }


def _button_role(name):
    if hasattr(QtWidgets.QDialogButtonBox, "ButtonRole"):
        return getattr(QtWidgets.QDialogButtonBox.ButtonRole, name)

    return getattr(QtWidgets.QDialogButtonBox, name)


def _standard_button(name):
    if hasattr(QtWidgets.QDialogButtonBox, "StandardButton"):
        return getattr(QtWidgets.QDialogButtonBox.StandardButton, name)

    return getattr(QtWidgets.QDialogButtonBox, name)


class PrecisionTransformGizmoWindow(QtWidgets.QDialog):
    def __init__(self):
        QtWidgets.QDialog.__init__(self)

        self.setWindowTitle(TOOL_NAME)
        self.setMinimumWidth(300)
        self.setModal(False)

        self.model_states = []
        self.selection_signature = ()
        self.drag_active = False
        self.was_mouse_down = _is_transform_mouse_down()
        self.error_reported = False

        self.enabled_check = QtWidgets.QCheckBox("Precision enabled")
        self.enabled_check.setChecked(True)

        self.multiplier_spin = QtWidgets.QDoubleSpinBox()
        self.multiplier_spin.setRange(0.01, 1.00)
        self.multiplier_spin.setDecimals(2)
        self.multiplier_spin.setSingleStep(0.01)
        self.multiplier_spin.setValue(DEFAULT_MULTIPLIER)

        self.transform_checks = {}
        transform_row = QtWidgets.QHBoxLayout()

        for name, label, _transform_type, _is_rotation in TRANSFORMS:
            check = QtWidgets.QCheckBox(label)
            check.setChecked(True)
            self.transform_checks[name] = check
            transform_row.addWidget(check)

        transform_row.addStretch(1)

        self.capture_button = QtWidgets.QPushButton("Capture")
        self.capture_button.clicked.connect(self.capture_current_selection)

        self.status_label = QtWidgets.QLabel("")

        buttons = QtWidgets.QDialogButtonBox()
        buttons.addButton(self.capture_button, _button_role("ActionRole"))
        buttons.addButton(_standard_button("Close"))
        buttons.rejected.connect(self.close)

        form = QtWidgets.QFormLayout()
        form.addRow("Multiplier", self.multiplier_spin)
        form.addRow("Transforms", transform_row)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.enabled_check)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)

        self.timer = QtCore.QTimer(self)
        self._set_precise_timer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)

        self.capture_current_selection()

    def _set_precise_timer(self):
        try:
            if hasattr(QtCore.Qt, "TimerType"):
                self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
            else:
                self.timer.setTimerType(QtCore.Qt.PreciseTimer)
        except Exception:
            pass

    def _enabled_transform_specs(self):
        enabled = []

        for name, label, transform_type, is_rotation in TRANSFORMS:
            check = self.transform_checks.get(name)

            if check is not None and check.isChecked():
                enabled.append((name, label, transform_type, is_rotation))

        return enabled

    def _multiplier(self):
        try:
            return float(self.multiplier_spin.value())
        except Exception:
            return DEFAULT_MULTIPLIER

    def _set_status(self, text):
        self.status_label.setText(text)

    def capture_current_selection(self):
        models = _selected_transformable_models()
        self._capture_models(models)

    def _capture_models(self, models):
        self.selection_signature = _selection_signature(models)
        self.model_states = []

        for model in models:
            snapshot = _transform_snapshot(model)
            self.model_states.append(
                {
                    "model": model,
                    "base": _copy_snapshot(snapshot),
                    "last_applied": _copy_snapshot(snapshot),
                }
            )

        self.drag_active = False
        self._set_status("%d selected, x%.2f" % (len(models), self._multiplier()))

    def _refresh_idle_baseline(self, models):
        if _selection_signature(models) != self.selection_signature:
            self._capture_models(models)
            return

        for state in self.model_states:
            snapshot = _transform_snapshot(state["model"])
            state["base"] = _copy_snapshot(snapshot)
            state["last_applied"] = _copy_snapshot(snapshot)

        self._set_status("%d selected, x%.2f" % (len(models), self._multiplier()))

    def _begin_drag_if_needed(self, models):
        if self.drag_active:
            return

        if _selection_signature(models) != self.selection_signature:
            self._capture_models(models)

        self.drag_active = True

    def _end_drag(self, models):
        if not self.drag_active:
            return

        self._capture_models(models)
        self.drag_active = False

    def _apply_precision(self):
        multiplier = self._multiplier()
        enabled_specs = self._enabled_transform_specs()

        if not enabled_specs or multiplier >= 0.999999:
            return

        for state in self.model_states:
            model = state["model"]

            for name, _label, transform_type, is_rotation in enabled_specs:
                current = _read_vector(model, transform_type)
                last_applied = state["last_applied"].get(name)

                if last_applied is not None and _vectors_close(current, last_applied):
                    continue

                base = state["base"][name]
                target = _scaled_values(base, current, multiplier, is_rotation)

                if not _vectors_close(target, current):
                    _write_vector(model, transform_type, target)

                state["last_applied"][name] = list(target)

    def _tick(self):
        try:
            models = _selected_transformable_models()
            mouse_down = _is_transform_mouse_down()

            if not self.enabled_check.isChecked():
                if not mouse_down:
                    self._refresh_idle_baseline(models)
                self.was_mouse_down = mouse_down
                return

            if not mouse_down:
                self._end_drag(models)
                self._refresh_idle_baseline(models)
                self.was_mouse_down = False
                return

            if mouse_down and not self.was_mouse_down:
                self._begin_drag_if_needed(models)

            if self.drag_active:
                self._apply_precision()

            self.was_mouse_down = mouse_down
        except Exception:
            self._report_error(traceback.format_exc())

    def _report_error(self, details):
        if self.error_reported:
            return

        self.error_reported = True

        try:
            self.timer.stop()
        except Exception:
            pass

        FBMessageBox(TOOL_NAME + " Error", details[-1800:], "OK")

    def closeEvent(self, event):
        global _PRECISION_TRANSFORM_GIZMO

        try:
            self.timer.stop()
        except Exception:
            pass

        if _PRECISION_TRANSFORM_GIZMO is self:
            _PRECISION_TRANSFORM_GIZMO = None

        event.accept()


def show_precision_transform_gizmo():
    app = QtWidgets.QApplication.instance()

    if app is None:
        FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
        return

    global _PRECISION_TRANSFORM_GIZMO

    try:
        if _PRECISION_TRANSFORM_GIZMO is not None:
            _PRECISION_TRANSFORM_GIZMO.close()
    except Exception:
        pass

    _PRECISION_TRANSFORM_GIZMO = PrecisionTransformGizmoWindow()
    _PRECISION_TRANSFORM_GIZMO.show()
    _PRECISION_TRANSFORM_GIZMO.raise_()
    _PRECISION_TRANSFORM_GIZMO.activateWindow()

    print("%s opened." % TOOL_NAME)


if not globals().get("_PRECISION_TRANSFORM_HOLD_LOADED", False):
    try:
        show_precision_transform_gizmo()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
