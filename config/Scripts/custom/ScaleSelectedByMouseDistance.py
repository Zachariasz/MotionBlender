import ctypes
import math
import os
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import (
    FBCameraSwitcher,
    FBCameraMatrixType,
    FBCameraType,
    FBFCurve,
    FBFCurveEditorUtility,
    FBGetSelectedModels,
    FBMatrix,
    FBMessageBox,
    FBModelTransformationType,
    FBModelList,
    FBSystem,
    FBTangentMode,
    FBTangentWeightMode,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Scale Selected By Mouse Distance"
ACTIVE_CONTROLLER_ATTR = "_scale_selected_by_mouse_distance_active_controller"

POLL_INTERVAL_MS = 16
MOUSE_FINISH_RELEASE_DELAY_MS = 60
MIN_CURSOR_RADIUS = 8.0
MIN_MOUSE_SCALE_FACTOR = 0.001
PREVIEW_SCALE_EPSILON = 0.0005
SCALE_EPSILON = 0.000001
PRECISION_MULTIPLIER = 0.1
SNAP_INCREMENT = 0.1
OVERLAY_TEXT_MARGIN = 18
OVERLAY_TEXT_PADDING_X = 10
OVERLAY_TEXT_PADDING_Y = 5
AXIS_LINE_MIN_SCREEN_LENGTH = 4.0
SCALE_CURSOR_ICON = os.path.join("icons", "2arrow_2.png")
IDC_ARROW = 32512
CURSOR_RESTORE_LIMIT = 12
FCURVE_MARKER_WINDOW_RADIUS = 5
FCURVE_MARKER_MIN_DENSITY = 20.0
FCURVE_MIN_TANGENT_WEIGHT = 0.0001
FCURVE_MAX_TANGENT_WEIGHT = 0.99
FCURVE_MANUAL_DERIVATIVE_LIMIT = 1000000.0

AXIS_LOCK_X = "x"
AXIS_LOCK_Y = "y"
AXIS_LOCK_Z = "z"
AXIS_SPACE_GLOBAL = "global"
AXIS_SPACE_LOCAL = "local"

GLOBAL_AXIS_DIRECTIONS = {
    AXIS_LOCK_X: [1.0, 0.0, 0.0],
    AXIS_LOCK_Y: [0.0, 1.0, 0.0],
    AXIS_LOCK_Z: [0.0, 0.0, 1.0],
}

AXIS_GUIDE_COLORS = {
    AXIS_LOCK_X: (235, 55, 55, 230),
    AXIS_LOCK_Y: (70, 210, 85, 230),
    AXIS_LOCK_Z: (70, 135, 255, 230),
}

AXIS_INDEX = {
    AXIS_LOCK_X: 0,
    AXIS_LOCK_Y: 1,
    AXIS_LOCK_Z: 2,
}

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_BACKSPACE = 0x08
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_X = 0x58
VK_Y = 0x59
VK_Z = 0x5A
VK_0 = 0x30
VK_1 = 0x31
VK_2 = 0x32
VK_3 = 0x33
VK_4 = 0x34
VK_5 = 0x35
VK_6 = 0x36
VK_7 = 0x37
VK_8 = 0x38
VK_9 = 0x39
VK_NUMPAD0 = 0x60
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
VK_NUMPAD3 = 0x63
VK_NUMPAD4 = 0x64
VK_NUMPAD5 = 0x65
VK_NUMPAD6 = 0x66
VK_NUMPAD7 = 0x67
VK_NUMPAD8 = 0x68
VK_NUMPAD9 = 0x69
VK_DECIMAL = 0x6E
VK_SUBTRACT = 0x6D
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE

NUMERIC_INPUT_KEYS = (
    (VK_0, "0"),
    (VK_1, "1"),
    (VK_2, "2"),
    (VK_3, "3"),
    (VK_4, "4"),
    (VK_5, "5"),
    (VK_6, "6"),
    (VK_7, "7"),
    (VK_8, "8"),
    (VK_9, "9"),
    (VK_NUMPAD0, "0"),
    (VK_NUMPAD1, "1"),
    (VK_NUMPAD2, "2"),
    (VK_NUMPAD3, "3"),
    (VK_NUMPAD4, "4"),
    (VK_NUMPAD5, "5"),
    (VK_NUMPAD6, "6"),
    (VK_NUMPAD7, "7"),
    (VK_NUMPAD8, "8"),
    (VK_NUMPAD9, "9"),
    (VK_DECIMAL, "."),
    (VK_OEM_PERIOD, "."),
    (VK_SUBTRACT, "-"),
    (VK_OEM_MINUS, "-"),
    (VK_BACKSPACE, "backspace"),
)


def _configure_user32():
    try:
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.SetCursor.argtypes = [ctypes.c_void_p]
        user32.SetCursor.restype = ctypes.c_void_p
        user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.LoadCursorW.restype = ctypes.c_void_p
    except Exception:
        pass


_configure_user32()


def _script_directory():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        try:
            return os.getcwd()
        except Exception:
            return r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts\custom"


def _cursor_icon_path(relative_icon_path):
    script_directory = _script_directory()
    candidates = [
        os.path.join(script_directory, relative_icon_path),
        os.path.join(script_directory, "custom", relative_icon_path),
        os.path.join(os.getcwd(), "custom", relative_icon_path),
    ]

    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                return candidate
        except Exception:
            pass

    return candidates[0]


def _load_cursor_pixmap(relative_icon_path):
    try:
        pixmap = QtGui.QPixmap(_cursor_icon_path(relative_icon_path))
        if not pixmap.isNull():
            return pixmap
    except Exception:
        pass

    return None


def _hide_windows_cursor_once():
    try:
        ctypes.windll.user32.SetCursor(None)
    except Exception:
        pass


def _restore_windows_arrow_cursor():
    try:
        user32 = ctypes.windll.user32
        arrow_cursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
        if arrow_cursor:
            user32.SetCursor(arrow_cursor)
    except Exception:
        pass


def _qt_override_cursor(app):
    try:
        return app.overrideCursor()
    except Exception:
        try:
            return QtWidgets.QApplication.overrideCursor()
        except Exception:
            return None


def _rotated_cursor_pixmap(pixmap, angle_degrees):
    if pixmap is None:
        return None

    try:
        transform = QtGui.QTransform()
        transform.rotate(angle_degrees)
        rotated_pixmap = pixmap.transformed(
            transform,
            _qt_transformation_mode("SmoothTransformation"),
        )

        if rotated_pixmap.isNull():
            return None

        return rotated_pixmap
    except Exception:
        return None


def _scaled_pixmap(pixmap, scale):
    if pixmap is None or scale is None or abs(float(scale) - 1.0) <= 0.0001:
        return pixmap

    try:
        width = max(1, int(round(pixmap.width() * float(scale))))
        height = max(1, int(round(pixmap.height() * float(scale))))
        return pixmap.scaled(
            width,
            height,
            _qt_aspect_ratio_mode("KeepAspectRatio"),
            _qt_transformation_mode("SmoothTransformation"),
        )
    except Exception:
        return pixmap


def _cursor_from_pixmap(pixmap, angle_degrees, scale=1.0):
    rotated_pixmap = _rotated_cursor_pixmap(pixmap, angle_degrees)
    rotated_pixmap = _scaled_pixmap(rotated_pixmap, scale)

    if rotated_pixmap is None:
        return None

    try:
        return QtGui.QCursor(
            rotated_pixmap,
            int(rotated_pixmap.width() * 0.5),
            int(rotated_pixmap.height() * 0.5),
        )
    except Exception:
        return None


def _cursor_position():
    position = QtGui.QCursor.pos()
    return position.x(), position.y()


def _cursor_qpoint():
    return QtGui.QCursor.pos()


def _is_key_down(vk_code):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def _key_state(vk_code):
    try:
        value = ctypes.windll.user32.GetAsyncKeyState(vk_code)
        return bool(value & 0x8000), bool(value & 0x0001)
    except Exception:
        return False, False


def _qt_mouse_button(button_name):
    try:
        if hasattr(QtCore.Qt, "MouseButton"):
            button = getattr(QtCore.Qt.MouseButton, button_name)
        else:
            button = getattr(QtCore.Qt, button_name)
    except Exception:
        return False

    try:
        return bool(QtWidgets.QApplication.mouseButtons() & button)
    except Exception:
        pass

    try:
        return bool(QtGui.QGuiApplication.mouseButtons() & button)
    except Exception:
        return False


def _mouse_button_state(vk_code, button_name):
    windows_down, windows_pressed = _key_state(vk_code)
    qt_down = _qt_mouse_button(button_name)
    return windows_down or qt_down, windows_pressed


def _set_precise_timer(timer):
    try:
        if hasattr(QtCore.Qt, "TimerType"):
            timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        else:
            timer.setTimerType(QtCore.Qt.PreciseTimer)
    except Exception:
        pass


def _qt_window_flag(name):
    if hasattr(QtCore.Qt, "WindowType"):
        return getattr(QtCore.Qt.WindowType, name)

    return getattr(QtCore.Qt, name)


def _qt_widget_attribute(name):
    if hasattr(QtCore.Qt, "WidgetAttribute"):
        return getattr(QtCore.Qt.WidgetAttribute, name)

    return getattr(QtCore.Qt, name)


def _qt_pen_style(name):
    if hasattr(QtCore.Qt, "PenStyle"):
        return getattr(QtCore.Qt.PenStyle, name)

    return getattr(QtCore.Qt, name)


def _qt_alignment_flag(name):
    if hasattr(QtCore.Qt, "AlignmentFlag"):
        return getattr(QtCore.Qt.AlignmentFlag, name)

    return getattr(QtCore.Qt, name)


def _qt_text_elide_mode(name):
    if hasattr(QtCore.Qt, "TextElideMode"):
        return getattr(QtCore.Qt.TextElideMode, name)

    return getattr(QtCore.Qt, name)


def _qt_aspect_ratio_mode(name):
    if hasattr(QtCore.Qt, "AspectRatioMode"):
        return getattr(QtCore.Qt.AspectRatioMode, name)

    return getattr(QtCore.Qt, name)


def _qt_cursor_shape(name):
    if hasattr(QtCore.Qt, "CursorShape"):
        return getattr(QtCore.Qt.CursorShape, name)

    return getattr(QtCore.Qt, name)


def _qt_transformation_mode(name):
    if hasattr(QtCore.Qt, "TransformationMode"):
        return getattr(QtCore.Qt.TransformationMode, name)

    return getattr(QtCore.Qt, name)


def _set_widget_attribute(widget, attribute_name, enabled=True):
    try:
        widget.setAttribute(_qt_widget_attribute(attribute_name), enabled)
    except Exception:
        pass


def _active_controller_holders():
    holders = [builtins]

    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None

    if app is not None:
        holders.append(app)

    return holders


def _qt_active_controllers():
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None

    if app is None:
        return []

    try:
        return list(app.findChildren(QtCore.QObject, ACTIVE_CONTROLLER_ATTR))
    except Exception:
        return []


def _is_live_controller(controller):
    return (
        controller is not None
        and hasattr(controller, "request_restart_from_cursor")
        and not getattr(controller, "finished", True)
    )


def _get_active_controller():
    stale_controllers = []

    for holder in _active_controller_holders():
        try:
            controller = getattr(holder, ACTIVE_CONTROLLER_ATTR, None)
        except Exception:
            continue

        if controller is None:
            continue

        if _is_live_controller(controller):
            return controller

        stale_controllers.append((holder, controller))

    for controller in reversed(_qt_active_controllers()):
        if _is_live_controller(controller):
            return controller

    for holder, _controller in stale_controllers:
        try:
            setattr(holder, ACTIVE_CONTROLLER_ATTR, None)
        except Exception:
            pass

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


def _vector_to_list(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def _copy_vector3d(values):
    return FBVector3d(values[0], values[1], values[2])


def _length(values):
    return math.sqrt(sum(component * component for component in values))


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _mul(values, scalar):
    return [values[0] * scalar, values[1] * scalar, values[2] * scalar]


def _dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _normalize(values, fallback):
    length = _length(values)
    if length <= 0.000001:
        return list(fallback)
    return [component / length for component in values]


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _numeric_value(value, fallback):
    try:
        return float(value)
    except Exception:
        pass

    try:
        return float(value.Data)
    except Exception:
        return fallback


def _model_vector(model, transform_type, global_space):
    vector = FBVector3d()
    model.GetVector(vector, transform_type, global_space)
    return _vector_to_list(vector)


def _world_translation(model):
    try:
        return _model_vector(model, FBModelTransformationType.kModelTranslation, True)
    except Exception:
        pass

    try:
        return _vector_to_list(model.Translation)
    except Exception:
        return [0.0, 0.0, 0.0]


def _world_rotation(model):
    try:
        return _model_vector(model, FBModelTransformationType.kModelRotation, True)
    except Exception:
        pass

    try:
        return _vector_to_list(model.Rotation)
    except Exception:
        return [0.0, 0.0, 0.0]


def _local_scaling(model):
    try:
        return _vector_to_list(model.Scaling)
    except Exception:
        pass

    try:
        return _model_vector(model, FBModelTransformationType.kModelScaling, False)
    except Exception:
        return [1.0, 1.0, 1.0]


def _set_local_scaling(model, values):
    vector = _copy_vector3d(values)

    try:
        model.Scaling = vector
    except Exception:
        model.SetVector(vector, FBModelTransformationType.kModelScaling, False)


def _model_visible_for_center(model):
    try:
        return bool(model.IsVisible())
    except Exception:
        pass

    try:
        return bool(model.Show) and bool(model.Visibility)
    except Exception:
        return True


def _selected_transformable_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)
    return [
        model
        for model in selected_models
        if getattr(model, "Transformable", True)
    ]


def _rotate_xyz(values, rotation_degrees):
    x, y, z = values
    rx, ry, rz = [math.radians(value) for value in rotation_degrees]

    cos_x, sin_x = math.cos(rx), math.sin(rx)
    cos_y, sin_y = math.cos(ry), math.sin(ry)
    cos_z, sin_z = math.cos(rz), math.sin(rz)

    y, z = (y * cos_x) - (z * sin_x), (y * sin_x) + (z * cos_x)
    x, z = (x * cos_y) + (z * sin_y), (-x * sin_y) + (z * cos_x)
    x, y = (x * cos_z) - (y * sin_z), (x * sin_z) + (y * cos_z)

    return [x, y, z]


def _local_axis_directions(model):
    try:
        rotation = _world_rotation(model)
        return {
            AXIS_LOCK_X: _normalize(
                _rotate_xyz(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_X], rotation),
                GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_X],
            ),
            AXIS_LOCK_Y: _normalize(
                _rotate_xyz(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Y], rotation),
                GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Y],
            ),
            AXIS_LOCK_Z: _normalize(
                _rotate_xyz(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Z], rotation),
                GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Z],
            ),
        }
    except Exception:
        return {
            AXIS_LOCK_X: list(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_X]),
            AXIS_LOCK_Y: list(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Y]),
            AXIS_LOCK_Z: list(GLOBAL_AXIS_DIRECTIONS[AXIS_LOCK_Z]),
        }


def _current_camera():
    try:
        camera = FBSystem().Scene.Renderer.GetCameraInPane(0)
        if camera is not None:
            return camera
    except Exception:
        pass

    try:
        return FBCameraSwitcher().CurrentCamera
    except Exception:
        return None


def _camera_view_context():
    camera = _current_camera()
    if camera is None:
        print("%s: could not read current camera; using world Z view axis." % TOOL_NAME)
        return None, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]

    try:
        rotation = _world_rotation(camera)
        view_right = _normalize(_rotate_xyz([0.0, 0.0, 1.0], rotation), [0.0, 0.0, 1.0])
        view_up = _normalize(_rotate_xyz([0.0, 1.0, 0.0], rotation), [0.0, 1.0, 0.0])
        view_depth = _normalize(_rotate_xyz([1.0, 0.0, 0.0], rotation), [1.0, 0.0, 0.0])
        return camera, view_right, view_up, view_depth
    except Exception:
        print("%s: could not read camera rotation; using world Z view axis." % TOOL_NAME)
        return camera, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]


def _selection_center(model_states):
    center = [0.0, 0.0, 0.0]
    center_states = [
        state
        for state in model_states
        if state.get("center_visible", True)
    ]

    if not center_states:
        center_states = model_states

    for state in center_states:
        center = _add(center, state["original_translation"])

    return _mul(center, 1.0 / float(len(center_states)))


def _qt_widget_rect(widget):
    top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
    return top_left.x(), top_left.y(), int(widget.width()), int(widget.height())


def _rect_contains_point(rect, point):
    x, y, width, height = rect
    return x <= point.x() <= x + width and y <= point.y() <= y + height


def _font_metric_width(metrics, text):
    try:
        return metrics.horizontalAdvance(text)
    except Exception:
        return metrics.width(text)


def _widget_contains_global_point(widget, global_point):
    try:
        rect = _qt_widget_rect(widget)
        return _rect_contains_point(rect, global_point)
    except Exception:
        return False


def _fcurve_graph_widget_for_cursor():
    app = QtWidgets.QApplication.instance()

    if app is None:
        return None

    cursor = _cursor_qpoint()

    try:
        widget_at_cursor = app.widgetAt(cursor)
    except Exception:
        widget_at_cursor = None

    current = widget_at_cursor
    while current is not None:
        try:
            accessible_name = str(current.accessibleName() or "").lower()
            if accessible_name == "fcurve" and _widget_contains_global_point(current, cursor):
                return current
            current = current.parentWidget()
        except Exception:
            current = None

    graph_widgets = []

    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []

    for widget in widgets:
        try:
            if not widget.isVisible() or widget.width() <= 20 or widget.height() <= 20:
                continue

            accessible_name = str(widget.accessibleName() or "").lower()
            if (
                accessible_name == "fcurve"
                and _widget_contains_global_point(widget, cursor)
            ):
                graph_widgets.append(widget)
        except Exception:
            pass

    if not graph_widgets:
        return None

    graph_widgets.sort(
        key=lambda widget: (
            int(widget.width()) * int(widget.height()),
        )
    )
    return graph_widgets[0]


def _add_fcurve(curves, fcurve):
    if fcurve is None:
        return

    try:
        if len(fcurve.Keys) <= 0:
            return
    except Exception:
        return

    try:
        curves.add(fcurve)
    except Exception:
        if all(existing is not fcurve for existing in curves):
            curves.append(fcurve)


def _scan_animation_node_fcurves(animation_node, layer_index, curves):
    if animation_node is None:
        return

    try:
        _add_fcurve(curves, animation_node.GetFCurve(layer_index))
    except Exception:
        pass

    try:
        _add_fcurve(curves, animation_node.FCurve)
    except Exception:
        pass

    try:
        child_nodes = list(animation_node.Nodes)
    except Exception:
        child_nodes = []

    for child_node in child_nodes:
        _scan_animation_node_fcurves(child_node, layer_index, curves)


def _displayed_fcurves():
    curves = set()
    properties = []
    system = FBSystem()

    try:
        FBFCurveEditorUtility().GetProperties(properties, False)
    except Exception:
        properties = []

    try:
        layer_index = int(system.CurrentTake.GetCurrentLayer())
    except Exception:
        layer_index = 0

    for prop in properties:
        try:
            if prop.IsAnimated():
                _scan_animation_node_fcurves(prop.GetAnimationNode(), layer_index, curves)
        except Exception:
            pass

    if curves:
        return list(curves)

    try:
        components = list(system.Scene.Components)
    except Exception:
        components = []

    for component in components:
        if isinstance(component, FBFCurve):
            _add_fcurve(curves, component)

        try:
            component_properties = list(component.PropertyList)
        except Exception:
            component_properties = []

        for prop in component_properties:
            try:
                if prop.IsAnimatable():
                    _scan_animation_node_fcurves(prop.GetAnimationNode(), layer_index, curves)
            except Exception:
                pass

    return list(curves)


def _fcurve_key_is_selected(fcurve, index):
    try:
        if bool(fcurve.KeyGetSelected(index)):
            return True
    except Exception:
        pass

    try:
        if bool(fcurve.Keys[index].Selected):
            return True
    except Exception:
        pass

    try:
        if bool(fcurve.KeyGetMarkedForManipulation(index)):
            return True
    except Exception:
        pass

    try:
        return bool(fcurve.Keys[index].MarkedForManipulation)
    except Exception:
        return False


def _fcurve_key_time_ticks(fcurve, index):
    try:
        return int(fcurve.Keys[index].Time.Get())
    except Exception:
        return 0


def _fcurve_key_value(fcurve, index):
    try:
        return float(fcurve.Keys[index].Value)
    except Exception:
        try:
            return float(fcurve.KeyGetValue(index))
        except Exception:
            return 0.0


def _selected_fcurve_weight_states():
    states = []

    for fcurve in _displayed_fcurves():
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            if not _fcurve_key_is_selected(fcurve, index):
                continue

            try:
                states.append(
                    {
                        "curve": fcurve,
                        "index": index,
                        "time_ticks": _fcurve_key_time_ticks(fcurve, index),
                        "value": _fcurve_key_value(fcurve, index),
                        "original_left_derivative": float(fcurve.KeyGetLeftDerivative(index)),
                        "original_right_derivative": float(fcurve.KeyGetRightDerivative(index)),
                        "original_left_weight": float(fcurve.KeyGetLeftTangentWeight(index)),
                        "original_right_weight": float(fcurve.KeyGetRightTangentWeight(index)),
                        "original_tangent_mode": fcurve.KeyGetTangentMode(index),
                        "original_tangent_break": bool(fcurve.KeyGetTangentBreak(index)),
                        "original_weight_mode": fcurve.KeyGetTangentWeightMode(index),
                        "base_left_weight": float(fcurve.KeyGetLeftTangentWeight(index)),
                        "base_right_weight": float(fcurve.KeyGetRightTangentWeight(index)),
                        "base_left_derivative": float(fcurve.KeyGetLeftDerivative(index)),
                        "base_right_derivative": float(fcurve.KeyGetRightDerivative(index)),
                        "manual_prepared": False,
                        "independent_tangent_edit": False,
                    }
                )
            except Exception:
                continue

    return states


def _fcurve_pixel_score(color):
    red = int(color.red())
    green = int(color.green())
    blue = int(color.blue())
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    saturation = maximum - minimum

    if minimum >= 185:
        return 4.0

    if red >= 170 and green >= 140 and blue <= 150:
        return 4.0

    if maximum >= 145 and saturation >= 45:
        return 1.0

    if maximum >= 185 and (red + green + blue) >= 475:
        return 1.0

    return 0.0


def _fcurve_snapshot_key_center(
    graph_widget,
    cursor_local_x,
    cursor_local_y,
    details=None,
):
    if details is None:
        details = {}

    try:
        pixmap = graph_widget.grab()
        if pixmap.isNull():
            details["reason"] = "null_graph_snapshot"
            return None
        image = pixmap.toImage()
        if image.isNull():
            details["reason"] = "null_graph_image"
            return None
    except Exception as error:
        details["reason"] = "graph_snapshot_exception"
        details["snapshot_error"] = repr(error)
        return None

    widget_width = max(1.0, float(graph_widget.width()))
    widget_height = max(1.0, float(graph_widget.height()))
    image_width = int(image.width())
    image_height = int(image.height())

    if image_width <= 1 or image_height <= 1:
        details["reason"] = "invalid_graph_image_size"
        return None

    scale_x = float(image_width) / widget_width
    scale_y = float(image_height) / widget_height
    bin_width = max(4, int(round((FCURVE_MARKER_WINDOW_RADIUS + 1) * scale_x)))
    bin_height = max(4, int(round((FCURVE_MARKER_WINDOW_RADIUS + 1) * scale_y)))
    border_x = max(bin_width, int(round(7.0 * scale_x)))
    border_y = max(bin_height, int(round(7.0 * scale_y)))
    timeline_height = max(
        int(round(34.0 * scale_y)),
        int(round(image_height * 0.15)),
    )
    graph_image_bottom = max(border_y + 1, image_height - timeline_height)
    cursor_image_x = float(cursor_local_x) * scale_x
    cursor_image_y = float(cursor_local_y) * scale_y
    density_bins = {}

    for image_y in range(graph_image_bottom):
        for image_x in range(image_width):
            try:
                score = _fcurve_pixel_score(image.pixelColor(image_x, image_y))
            except Exception:
                score = 0.0

            if score <= 0.0:
                continue

            bin_key = (image_x // bin_width, image_y // bin_height)
            density, weighted_x, weighted_y = density_bins.get(
                bin_key,
                (0.0, 0.0, 0.0),
            )
            density_bins[bin_key] = (
                density + score,
                weighted_x + (float(image_x) * score),
                weighted_y + (float(image_y) * score),
            )

    candidates = []

    for bin_x, bin_y in density_bins:
        density = 0.0
        weighted_x = 0.0
        weighted_y = 0.0

        for offset_y in (-1, 0, 1):
            for offset_x in (-1, 0, 1):
                values = density_bins.get((bin_x + offset_x, bin_y + offset_y))
                if values is None:
                    continue
                density += values[0]
                weighted_x += values[1]
                weighted_y += values[2]

        if density < FCURVE_MARKER_MIN_DENSITY:
            continue

        image_x = weighted_x / density
        image_y = weighted_y / density

        if (
            image_x < border_x
            or image_x > image_width - border_x
            or image_y < border_y
            or image_y > graph_image_bottom
        ):
            continue

        distance = math.sqrt(
            ((image_x - cursor_image_x) ** 2)
            + ((image_y - cursor_image_y) ** 2)
        )
        candidates.append((density, distance, image_x, image_y))

    if not candidates:
        details["reason"] = "no_marker_candidates"
        return None

    maximum_density = max(candidate[0] for candidate in candidates)
    strong_threshold = max(
        FCURVE_MARKER_MIN_DENSITY,
        maximum_density * 0.72,
    )
    strong_candidates = [
        candidate
        for candidate in candidates
        if candidate[0] >= strong_threshold
    ]
    _density, _distance, best_x, best_y = min(
        strong_candidates,
        key=lambda candidate: (candidate[1], -candidate[0]),
    )
    return float(best_x) / scale_x, float(best_y) / scale_y


def _fcurve_tangent_pixel(color):
    red = int(color.red())
    green = int(color.green())
    blue = int(color.blue())
    return (
        red >= 150
        and green >= 90
        and blue >= 90
        and red - max(green, blue) >= 20
        and abs(green - blue) <= 20
    )


def _fcurve_selected_key_graph_data(graph_widget, tangent_states):
    if len(tangent_states) != 1:
        return None

    state = tangent_states[0]

    try:
        keys = list(state["curve"].Keys)
        selected_index = int(state["index"])
        selected_time = float(keys[selected_index].Time.GetSecondDouble())
        selected_value = float(keys[selected_index].Value)
    except Exception:
        return None

    if len(keys) < 3:
        return None

    try:
        pixmap = graph_widget.grab()
        image = pixmap.toImage()
        if pixmap.isNull() or image.isNull():
            return None
    except Exception:
        return None

    pixels = set()
    image_width = int(image.width())
    image_height = int(image.height())

    for image_y in range(image_height):
        for image_x in range(image_width):
            try:
                if _fcurve_tangent_pixel(image.pixelColor(image_x, image_y)):
                    pixels.add((image_x, image_y))
            except Exception:
                pass

    markers = []
    while pixels:
        start = pixels.pop()
        pending = [start]
        component = [start]

        while pending:
            pixel_x, pixel_y = pending.pop()
            for neighbor_y in range(pixel_y - 1, pixel_y + 2):
                for neighbor_x in range(pixel_x - 1, pixel_x + 2):
                    neighbor = (neighbor_x, neighbor_y)
                    if neighbor in pixels:
                        pixels.remove(neighbor)
                        pending.append(neighbor)
                        component.append(neighbor)

        if len(component) < 16:
            continue

        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        if max(xs) - min(xs) + 1 > 9 or max(ys) - min(ys) + 1 > 9:
            continue

        markers.append(
            (
                (min(xs) + max(xs)) * 0.5,
                (min(ys) + max(ys)) * 0.5,
            )
        )

    remaining_keys = [
        key
        for key_index, key in enumerate(keys)
        if key_index != selected_index
    ]

    if len(markers) != len(remaining_keys):
        return None

    remaining_keys.sort(key=lambda key: float(key.Time.GetSecondDouble()))
    markers.sort(key=lambda marker: marker[0])
    times = [float(key.Time.GetSecondDouble()) for key in remaining_keys]
    values = [float(key.Value) for key in remaining_keys]
    marker_xs = [marker[0] for marker in markers]
    marker_ys = [marker[1] for marker in markers]
    time_average = sum(times) / float(len(times))
    x_average = sum(marker_xs) / float(len(marker_xs))
    time_denominator = sum((value - time_average) ** 2 for value in times)

    if time_denominator <= 0.000001:
        return None

    pixels_per_second = sum(
        (time_value - time_average) * (x_value - x_average)
        for time_value, x_value in zip(times, marker_xs)
    ) / time_denominator

    if pixels_per_second <= 0.000001:
        return None

    value_average = sum(values) / float(len(values))
    y_average = sum(marker_ys) / float(len(marker_ys))
    value_denominator = sum((value - value_average) ** 2 for value in values)

    if value_denominator <= 0.000001:
        return None

    pixels_per_value = sum(
        (value - value_average) * (y_value - y_average)
        for value, y_value in zip(values, marker_ys)
    ) / value_denominator

    if abs(pixels_per_value) <= 0.000001:
        return None

    selected_x = x_average + ((selected_time - time_average) * pixels_per_second)
    selected_y = y_average + ((selected_value - value_average) * pixels_per_value)
    if (
        selected_x < 0.0
        or selected_x > float(image_width)
        or selected_y < 0.0
        or selected_y > float(image_height)
    ):
        return None

    image_scale_x = float(image_width) / max(1.0, float(graph_widget.width()))
    image_scale_y = float(image_height) / max(1.0, float(graph_widget.height()))
    pixels_per_second = pixels_per_second / image_scale_x
    pixels_per_value = pixels_per_value / image_scale_y
    derivative_scale = abs(pixels_per_second / pixels_per_value)
    return (
        selected_x / image_scale_x,
        selected_y / image_scale_y,
        derivative_scale,
    )


def _fcurve_scale_center(graph_widget, tangent_states):
    rect_x, rect_y, rect_width, rect_height = _qt_widget_rect(graph_widget)
    cursor = _cursor_qpoint()
    cursor_local_x = _clamp(float(cursor.x() - rect_x), 0.0, float(rect_width))
    cursor_local_y = _clamp(float(cursor.y() - rect_y), 0.0, float(rect_height))
    key_graph_data = _fcurve_selected_key_graph_data(
        graph_widget,
        tangent_states,
    )

    derivative_scale = None

    if key_graph_data is not None:
        local_x, local_y, derivative_scale = key_graph_data
    else:
        detected_center = _fcurve_snapshot_key_center(
            graph_widget,
            cursor_local_x,
            cursor_local_y,
            {},
        )

        if detected_center is None:
            local_x = cursor_local_x
            local_y = cursor_local_y
        else:
            local_x, local_y = detected_center

    local_x = _clamp(float(local_x), 0.0, float(rect_width))
    local_y = _clamp(float(local_y), 0.0, float(rect_height))
    return (rect_x + local_x, rect_y + local_y), derivative_scale


def _prepare_fcurve_weight_state(state, break_tangents=False):
    fcurve = state["curve"]
    index = state["index"]

    if not state.get("manual_prepared"):
        fcurve.KeySetTangentWeightMode(
            index,
            FBTangentWeightMode.kFBTangentWeightModeBoth,
        )
        state["manual_prepared"] = True

    if not break_tangents or state.get("independent_tangent_edit"):
        return

    # Preserve the original linked state until a single tangent is edited.
    fcurve.KeySetTangentMode(index, FBTangentMode.kFBTangentModeBreak)
    fcurve.KeySetTangentBreak(index, True)
    fcurve.KeySetLeftDerivative(index, state["original_left_derivative"])
    fcurve.KeySetRightDerivative(index, state["original_right_derivative"])
    fcurve.KeySetTangentWeightMode(
        index,
        FBTangentWeightMode.kFBTangentWeightModeBoth,
    )
    state["independent_tangent_edit"] = True


def _set_fcurve_weight_state_values(
    state,
    left_weight,
    right_weight,
    break_tangents=False,
):
    _prepare_fcurve_weight_state(state, break_tangents)
    fcurve = state["curve"]
    index = state["index"]
    fcurve.KeySetLeftTangentWeight(index, left_weight)
    fcurve.KeySetRightTangentWeight(index, right_weight)


def _set_fcurve_tangent_state_values(
    state,
    left_weight,
    right_weight,
    left_derivative,
    right_derivative,
    break_tangents=False,
):
    _set_fcurve_weight_state_values(
        state,
        left_weight,
        right_weight,
        break_tangents,
    )
    fcurve = state["curve"]
    index = state["index"]
    fcurve.KeySetLeftDerivative(index, left_derivative)
    fcurve.KeySetRightDerivative(index, right_derivative)


def _restore_fcurve_weight_states(tangent_states):
    for state in tangent_states:
        fcurve = state["curve"]
        index = state["index"]
        fcurve.KeySetTangentMode(index, FBTangentMode.kFBTangentModeBreak)
        fcurve.KeySetTangentBreak(index, True)
        fcurve.KeySetTangentWeightMode(
            index,
            FBTangentWeightMode.kFBTangentWeightModeBoth,
        )
        fcurve.KeySetLeftDerivative(index, state["original_left_derivative"])
        fcurve.KeySetRightDerivative(index, state["original_right_derivative"])
        fcurve.KeySetLeftTangentWeight(index, state["original_left_weight"])
        fcurve.KeySetRightTangentWeight(index, state["original_right_weight"])
        fcurve.KeySetTangentWeightMode(index, state["original_weight_mode"])
        fcurve.KeySetTangentMode(index, state["original_tangent_mode"])
        fcurve.KeySetTangentBreak(index, state["original_tangent_break"])
        state["manual_prepared"] = False
        state["independent_tangent_edit"] = False


def _refresh_fcurve_widget(graph_widget):
    try:
        graph_widget.update()
    except Exception:
        pass

    try:
        graph_widget.repaint()
    except Exception:
        pass


class ScaleOverlayWidget(QtWidgets.QWidget):
    def __init__(self, viewport_rect):
        flags = (
            _qt_window_flag("Tool")
            | _qt_window_flag("FramelessWindowHint")
            | _qt_window_flag("WindowStaysOnTopHint")
        )

        try:
            flags = flags | _qt_window_flag("WindowTransparentForInput")
        except Exception:
            pass

        QtWidgets.QWidget.__init__(self, None, flags)

        self.viewport_rect = None
        self.center_global = None
        self.cursor_global = None
        self.axis_lines_global = []
        self.axis_line_color = None
        self.cursor_icon_pixmap = None
        self.cursor_icon_angle = 0.0
        self.cursor_icon_scale = 1.0
        self.status_text = ""

        _set_widget_attribute(self, "WA_TransparentForMouseEvents", True)
        _set_widget_attribute(self, "WA_TranslucentBackground", True)
        _set_widget_attribute(self, "WA_ShowWithoutActivating", True)

        try:
            self.setFocusPolicy(QtCore.Qt.NoFocus)
        except Exception:
            try:
                self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            except Exception:
                pass

        try:
            self.setCursor(QtGui.QCursor(_qt_cursor_shape("BlankCursor")))
        except Exception:
            pass

        self.set_viewport_rect(viewport_rect)

    def set_viewport_rect(self, viewport_rect):
        if viewport_rect is None:
            return

        self.viewport_rect = viewport_rect
        x, y, width, height = viewport_rect
        self.setGeometry(int(x), int(y), int(width), int(height))

    def set_overlay_data(
        self,
        center_global,
        cursor_global,
        status_text,
        axis_lines_global=None,
        axis_line_color=None,
        cursor_icon_pixmap=None,
        cursor_icon_angle=0.0,
        cursor_icon_scale=1.0,
    ):
        self.center_global = center_global
        self.cursor_global = cursor_global
        self.axis_lines_global = axis_lines_global or []
        self.axis_line_color = axis_line_color
        self.cursor_icon_pixmap = cursor_icon_pixmap
        self.cursor_icon_angle = cursor_icon_angle
        self.cursor_icon_scale = cursor_icon_scale
        self.status_text = status_text or ""

        if not self.isVisible():
            self.show()

        try:
            self.raise_()
        except Exception:
            pass

        self.update()

    def _local_point(self, global_point):
        if global_point is None or self.viewport_rect is None:
            return None

        rect_x, rect_y, _width, _height = self.viewport_rect
        return QtCore.QPointF(
            float(global_point[0]) - float(rect_x),
            float(global_point[1]) - float(rect_y),
        )

    def paintEvent(self, event):
        if self.viewport_rect is None:
            return

        painter = QtGui.QPainter(self)

        try:
            if hasattr(QtGui.QPainter, "RenderHint"):
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            else:
                painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        except Exception:
            pass

        if self.axis_lines_global and self.axis_line_color is not None:
            axis_color = self.axis_line_color
            axis_pen = QtGui.QPen(
                QtGui.QColor(
                    int(axis_color[0]),
                    int(axis_color[1]),
                    int(axis_color[2]),
                    int(axis_color[3]),
                )
            )
            axis_pen.setWidth(3)
            painter.setPen(axis_pen)

            for axis_line in self.axis_lines_global:
                axis_center = self._local_point(axis_line[0])
                axis_point = self._local_point(axis_line[1])

                if axis_center is None or axis_point is None:
                    continue

                dx = axis_point.x() - axis_center.x()
                dy = axis_point.y() - axis_center.y()
                length = math.sqrt((dx * dx) + (dy * dy))

                if length <= 0.000001:
                    continue

                scale = max(self.width(), self.height()) * 1.5
                dx = (dx / length) * scale
                dy = (dy / length) * scale

                painter.drawLine(
                    QtCore.QPointF(axis_center.x() - dx, axis_center.y() - dy),
                    QtCore.QPointF(axis_center.x() + dx, axis_center.y() + dy),
                )

        center = self._local_point(self.center_global)
        cursor = self._local_point(self.cursor_global)

        if center is not None and cursor is not None:
            line_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 230))
            line_pen.setWidth(2)
            line_pen.setStyle(_qt_pen_style("DashLine"))
            painter.setPen(line_pen)
            painter.drawLine(center, cursor)

        if cursor is not None and self.cursor_icon_pixmap is not None:
            try:
                scale = float(self.cursor_icon_scale or 1.0)
                target_width = max(1.0, float(self.cursor_icon_pixmap.width()) * scale)
                target_height = max(1.0, float(self.cursor_icon_pixmap.height()) * scale)
                target_rect = QtCore.QRectF(
                    target_width * -0.5,
                    target_height * -0.5,
                    target_width,
                    target_height,
                )
                source_rect = QtCore.QRectF(
                    0.0,
                    0.0,
                    float(self.cursor_icon_pixmap.width()),
                    float(self.cursor_icon_pixmap.height()),
                )
                painter.save()
                painter.translate(cursor)
                painter.rotate(float(self.cursor_icon_angle or 0.0))
                painter.drawPixmap(
                    target_rect,
                    self.cursor_icon_pixmap,
                    source_rect,
                )
                painter.restore()
            except Exception:
                try:
                    painter.restore()
                except Exception:
                    pass

        if self.status_text:
            font = painter.font()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)

            metrics = QtGui.QFontMetrics(font)
            max_text_width = max(40, self.width() - 60)
            text = metrics.elidedText(
                self.status_text,
                _qt_text_elide_mode("ElideRight"),
                max_text_width,
            )
            text_width = _font_metric_width(metrics, text)
            text_height = metrics.height()
            box_width = text_width + (OVERLAY_TEXT_PADDING_X * 2)
            box_height = text_height + (OVERLAY_TEXT_PADDING_Y * 2)
            box_x = (self.width() - box_width) * 0.5
            box_y = self.height() - box_height - OVERLAY_TEXT_MARGIN
            box_rect = QtCore.QRectF(box_x, box_y, box_width, box_height)

            painter.fillRect(box_rect, QtGui.QColor(0, 0, 0, 165))
            painter.setPen(QtGui.QColor(255, 255, 255, 245))
            painter.drawText(
                box_rect,
                _qt_alignment_flag("AlignCenter"),
                text,
            )

        painter.end()


def _camera_int(camera, attribute_name, fallback):
    try:
        value = int(getattr(camera, attribute_name, fallback) or fallback)
        if value > 0:
            return value
    except Exception:
        pass

    return fallback


def _viewport_global_rect(camera):
    app = QtWidgets.QApplication.instance()

    if app is None or camera is None:
        return None

    cursor = _cursor_qpoint()
    widget = app.widgetAt(cursor)

    if widget is None:
        return None

    viewport_width = _camera_int(camera, "CameraViewportWidth", 0)
    viewport_height = _camera_int(camera, "CameraViewportHeight", 0)
    viewport_x = _camera_int(camera, "CameraViewportX", 0)
    viewport_y = _camera_int(camera, "CameraViewportY", 0)
    window_width = _camera_int(camera, "WindowWidth", 0)
    window_height = _camera_int(camera, "WindowHeight", 0)

    candidates = []

    while widget is not None:
        try:
            if widget.isVisible() and widget.width() > 50 and widget.height() > 50:
                rect = _qt_widget_rect(widget)
                _x, _y, width, height = rect

                if viewport_width > 0 and viewport_height > 0:
                    viewport_score = abs(width - viewport_width) + abs(height - viewport_height)
                    candidates.append((viewport_score, "viewport", rect))

                if window_width > 0 and window_height > 0:
                    window_score = abs(width - window_width) + abs(height - window_height) + 25
                    candidates.append((window_score, "window", rect))

                if not candidates:
                    containing_penalty = 0 if _rect_contains_point(rect, cursor) else 100000
                    candidates.append((containing_penalty + width + height, "viewport", rect))
        except Exception:
            pass

        widget = widget.parentWidget()

    if not candidates:
        return None

    _score, rect_type, rect = sorted(candidates, key=lambda item: item[0])[0]

    if (
        rect_type == "window"
        and viewport_width > 0
        and viewport_height > 0
    ):
        x, y, _width, _height = rect
        return x + viewport_x, y + viewport_y, viewport_width, viewport_height

    return rect


def _fbmatrix_values(matrix):
    return [float(matrix[index]) for index in range(16)]


def _project_point_with_matrix_values(point, matrix_values, row_major):
    x, y, z = point

    if row_major:
        clip_x = (matrix_values[0] * x) + (matrix_values[1] * y) + (matrix_values[2] * z) + matrix_values[3]
        clip_y = (matrix_values[4] * x) + (matrix_values[5] * y) + (matrix_values[6] * z) + matrix_values[7]
        clip_w = (matrix_values[12] * x) + (matrix_values[13] * y) + (matrix_values[14] * z) + matrix_values[15]
    else:
        clip_x = (matrix_values[0] * x) + (matrix_values[4] * y) + (matrix_values[8] * z) + matrix_values[12]
        clip_y = (matrix_values[1] * x) + (matrix_values[5] * y) + (matrix_values[9] * z) + matrix_values[13]
        clip_w = (matrix_values[3] * x) + (matrix_values[7] * y) + (matrix_values[11] * z) + matrix_values[15]

    if abs(clip_w) <= 0.000001:
        return None

    return clip_x / clip_w, clip_y / clip_w


def _matrix_projection_candidate(point, rect, matrix_values, row_major):
    ndc = _project_point_with_matrix_values(point, matrix_values, row_major)

    if ndc is None:
        return None

    ndc_x, ndc_y = ndc

    if not all(math.isfinite(value) for value in (ndc_x, ndc_y)):
        return None

    rect_x, rect_y, rect_width, rect_height = rect
    screen_x = rect_x + ((ndc_x + 1.0) * 0.5 * rect_width)
    screen_y = rect_y + ((1.0 - ndc_y) * 0.5 * rect_height)
    return screen_x, screen_y


def _camera_project_point_matrix(camera, point, rect):
    if camera is None or rect is None:
        return None

    try:
        matrix = FBMatrix()
        try:
            camera.GetCameraMatrix(matrix, FBCameraMatrixType.kFBModelViewProj, None)
        except TypeError:
            camera.GetCameraMatrix(matrix, FBCameraMatrixType.kFBModelViewProj)
        matrix_values = _fbmatrix_values(matrix)
    except Exception:
        return None

    return _matrix_projection_candidate(point, rect, matrix_values, False)


def _camera_project_center(camera, model_states, view_right, view_up, view_depth):
    rect = _viewport_global_rect(camera)

    if rect is None:
        return None

    rect_x, rect_y, rect_width, rect_height = rect

    if rect_width <= 1 or rect_height <= 1:
        return None

    try:
        center = _selection_center(model_states)
        matrix_center = _camera_project_point_matrix(camera, center, rect)

        if matrix_center is not None:
            return matrix_center

        camera_position = _world_translation(camera)
        to_center = _sub(center, camera_position)
        x_world = _dot(to_center, view_right)
        y_world = _dot(to_center, view_up)
        depth = abs(_dot(to_center, view_depth))

        if getattr(camera, "Type", None) == FBCameraType.kFBCameraTypeOrthogonal:
            ortho_zoom = _numeric_value(getattr(camera, "OrthoZoom", None), 0.0)
            if ortho_zoom <= 0.000001:
                return None

            pixels_per_unit = float(rect_height) / (2.0 * ortho_zoom)
            screen_x = rect_x + (rect_width * 0.5) + (x_world * pixels_per_unit)
            screen_y = rect_y + (rect_height * 0.5) - (y_world * pixels_per_unit)
            return screen_x, screen_y

        if depth <= 0.000001:
            return None

        aspect = float(rect_width) / float(rect_height)
        field_of_view_y = _numeric_value(getattr(camera, "FieldOfViewY", None), 0.0)

        if field_of_view_y <= 0.000001:
            field_of_view_y = _numeric_value(getattr(camera, "FieldOfView", None), 40.0)

        field_of_view_x = _numeric_value(getattr(camera, "FieldOfViewX", None), 0.0)

        if field_of_view_x <= 0.000001:
            half_fov_y = math.radians(field_of_view_y) * 0.5
            field_of_view_x = math.degrees(2.0 * math.atan(math.tan(half_fov_y) * aspect))

        half_width = depth * math.tan(math.radians(field_of_view_x) * 0.5)
        half_height = depth * math.tan(math.radians(field_of_view_y) * 0.5)

        if half_width <= 0.000001 or half_height <= 0.000001:
            return None

        screen_x = rect_x + (rect_width * 0.5) + ((x_world / half_width) * rect_width * 0.5)
        screen_y = rect_y + (rect_height * 0.5) - ((y_world / half_height) * rect_height * 0.5)
        return screen_x, screen_y
    except Exception:
        return None


def _scale_center_cursor(camera, model_states, view_right, view_up, view_depth):
    center = _camera_project_center(
        camera,
        model_states,
        view_right,
        view_up,
        view_depth,
    )

    if center is not None:
        return center

    print("%s: could not project selected center to the viewport; using cursor start as scale center." % TOOL_NAME)
    return _cursor_position()


def _axis_line_from_world(camera, viewport_rect, center_world, axis_direction, axis_name):
    if camera is None or viewport_rect is None or center_world is None or axis_direction is None:
        return None

    try:
        axis_direction = _normalize(
            axis_direction,
            GLOBAL_AXIS_DIRECTIONS.get(axis_name, [1.0, 0.0, 0.0]),
        )
        center_screen = _camera_project_point_matrix(camera, center_world, viewport_rect)

        if center_screen is None:
            return None

        camera_position = _world_translation(camera)
        camera_distance = _length(_sub(center_world, camera_position))
        base_scale = max(camera_distance * 0.25, 1.0)

        for scale_factor in (0.25, 1.0, 4.0, 16.0, 64.0, 256.0):
            scale = base_scale * scale_factor

            for direction in (1.0, -1.0):
                endpoint_world = _add(center_world, _mul(axis_direction, scale * direction))
                endpoint_screen = _camera_project_point_matrix(
                    camera,
                    endpoint_world,
                    viewport_rect,
                )

                if endpoint_screen is None:
                    continue

                screen_delta = _sub(
                    [endpoint_screen[0], endpoint_screen[1], 0.0],
                    [center_screen[0], center_screen[1], 0.0],
                )

                if _length(screen_delta) >= AXIS_LINE_MIN_SCREEN_LENGTH:
                    return center_screen, endpoint_screen
    except Exception:
        pass

    return None


def _axis_lock_overlay_lines(
    camera,
    viewport_rect,
    model_states,
    axis_lock,
    axis_space,
):
    if camera is None or viewport_rect is None or axis_lock is None:
        return [], None

    try:
        axis_lines = []

        if axis_space == AXIS_SPACE_LOCAL:
            for state in model_states:
                axis_line = _axis_line_from_world(
                    camera,
                    viewport_rect,
                    state["original_translation"],
                    state["local_axes"].get(axis_lock),
                    axis_lock,
                )
                if axis_line is not None:
                    axis_lines.append(axis_line)
        else:
            axis_line = _axis_line_from_world(
                camera,
                viewport_rect,
                _selection_center(model_states),
                GLOBAL_AXIS_DIRECTIONS.get(axis_lock),
                axis_lock,
            )
            if axis_line is not None:
                axis_lines.append(axis_line)

        return axis_lines, AXIS_GUIDE_COLORS.get(axis_lock, (255, 255, 255, 230))
    except Exception:
        return [], None


def _cursor_radius(center_cursor, cursor_position):
    center_x, center_y = center_cursor
    cursor_x, cursor_y = cursor_position
    delta_x = float(cursor_x - center_x)
    delta_y = float(cursor_y - center_y)
    return math.sqrt((delta_x * delta_x) + (delta_y * delta_y))


def _snap_scale_factor(scale_factor):
    if SNAP_INCREMENT <= 0.0:
        return scale_factor

    snapped = round(scale_factor / SNAP_INCREMENT) * SNAP_INCREMENT
    return max(MIN_MOUSE_SCALE_FACTOR, snapped)


def _scale_component(original_value, scale_factor):
    if abs(original_value) <= SCALE_EPSILON:
        return scale_factor

    return original_value * scale_factor


def _target_scale_vectors(model_states, scale_factor, axis_lock, numeric_value):
    target_vectors = []

    for state in model_states:
        original = list(state.get("base_scaling", state["original_scaling"]))

        if numeric_value is not None:
            if axis_lock is None:
                target = [numeric_value, numeric_value, numeric_value]
            else:
                target = list(original)
                target[AXIS_INDEX[axis_lock]] = numeric_value
        elif axis_lock is None:
            target = [
                _scale_component(original[0], scale_factor),
                _scale_component(original[1], scale_factor),
                _scale_component(original[2], scale_factor),
            ]
        else:
            target = list(original)
            axis_index = AXIS_INDEX[axis_lock]
            target[axis_index] = _scale_component(original[axis_index], scale_factor)

        target_vectors.append(target)

    return target_vectors


def _average_scale(scale_vectors):
    if not scale_vectors:
        return [0.0, 0.0, 0.0]

    total = [0.0, 0.0, 0.0]

    for values in scale_vectors:
        total[0] += values[0]
        total[1] += values[1]
        total[2] += values[2]

    count = float(len(scale_vectors))
    return [total[0] / count, total[1] / count, total[2] / count]


def _format_scale(value):
    if abs(value) < 0.0005:
        value = 0.0

    return "%.3f" % value


def _scales_close(a, b):
    if len(a) != len(b):
        return False

    for index, values in enumerate(a):
        other = b[index]
        for component_index in range(3):
            if abs(values[component_index] - other[component_index]) > PREVIEW_SCALE_EPSILON:
                return False

    return True


def _scale_fcurve_weight(weight, scale_factor):
    scaled = float(weight) * float(scale_factor)
    return _clamp(scaled, FCURVE_MIN_TANGENT_WEIGHT, FCURVE_MAX_TANGENT_WEIGHT)


def _average_fcurve_weights(tangent_states):
    if not tangent_states:
        return 0.0, 0.0

    left_total = 0.0
    right_total = 0.0

    for state in tangent_states:
        left_total += float(state.get("last_left_weight", state["base_left_weight"]))
        right_total += float(state.get("last_right_weight", state["base_right_weight"]))

    count = float(len(tangent_states))
    return left_total / count, right_total / count


def _fcurve_tangent_angle_degrees(derivative, derivative_scale):
    scale = abs(float(derivative_scale or 1.0))
    if scale <= SCALE_EPSILON:
        scale = 1.0

    return math.degrees(math.atan(float(derivative) / scale))


def _scale_fcurve_tangent_angle(derivative, scale_factor, derivative_scale):
    scale = abs(float(derivative_scale or 1.0))
    if scale <= SCALE_EPSILON:
        scale = 1.0

    angle = math.atan(float(derivative) / scale) * float(scale_factor)
    angle_limit = (math.pi * 0.5) - 0.0001
    angle = _clamp(angle, -angle_limit, angle_limit)
    return _clamp(
        math.tan(angle) * scale,
        -FCURVE_MANUAL_DERIVATIVE_LIMIT,
        FCURVE_MANUAL_DERIVATIVE_LIMIT,
    )


def _average_fcurve_tangent_angles(tangent_states, derivative_scale):
    if not tangent_states:
        return 0.0, 0.0

    left_total = 0.0
    right_total = 0.0

    for state in tangent_states:
        left_total -= _fcurve_tangent_angle_degrees(
            state.get("last_left_derivative", state["base_left_derivative"]),
            derivative_scale,
        )
        right_total += _fcurve_tangent_angle_degrees(
            state.get("last_right_derivative", state["base_right_derivative"]),
            derivative_scale,
        )

    count = float(len(tangent_states))
    return left_total / count, right_total / count


class FCurveTangentWeightScaleController(QtCore.QObject):
    def __init__(
        self,
        tangent_states,
        graph_widget,
        center_cursor,
        graph_rect,
        derivative_scale=None,
    ):
        QtCore.QObject.__init__(self)
        self.tangent_states = tangent_states
        self.graph_widget = graph_widget
        self.center_cursor = center_cursor
        self.graph_rect = graph_rect
        self.derivative_scale = derivative_scale
        self.overlay = None
        self.cursor_pixmap = _load_cursor_pixmap(SCALE_CURSOR_ICON)
        self.custom_cursor_active = False
        self.last_cursor_rotation_angle = None
        self.start_cursor = _cursor_position()
        self.start_radius = max(
            _cursor_radius(self.center_cursor, self.start_cursor),
            MIN_CURSOR_RADIUS,
        )
        self.last_preview_signature = None
        self.last_applied_factor = 1.0
        self.last_side_mode = "both"
        self.axis_lock = None
        self.timer = None
        self.armed = False
        self.accepted = False
        self.finished = False
        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False
        self.event_filter_installed = False
        self.error_text = None
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_return_down = _is_key_down(VK_RETURN)
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)

    def start(self):
        app = QtWidgets.QApplication.instance()

        if app is None or self.timer is not None:
            return app is not None

        self.timer = QtCore.QTimer(self)
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)
        app.installEventFilter(self)
        self.event_filter_installed = True
        self._show_overlay()
        self._update_custom_cursor(_cursor_position(), force=True)
        return True

    def run(self):
        return self.start()

    def request_restart_from_cursor(self):
        if self.finished:
            return False

        try:
            self._capture_current_tangents_as_base()
            self.start_cursor = _cursor_position()
            self.start_radius = max(
                _cursor_radius(self.center_cursor, self.start_cursor),
                MIN_CURSOR_RADIUS,
            )
            self.last_preview_signature = None
            self._preview_current_weights(force=True)
            return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)
            return False

    def _show_overlay(self):
        try:
            cursor_position = _cursor_position()
            self.overlay = ScaleOverlayWidget(self.graph_rect)
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(1.0),
                [],
                None,
                self.cursor_pixmap,
                self._cursor_angle(cursor_position),
                1.0,
            )
        except Exception:
            self.overlay = None

    def _hide_overlay(self):
        if self.overlay is None:
            return

        try:
            self.overlay.hide()
            self.overlay.deleteLater()
        except Exception:
            pass

        self.overlay = None

    def _cursor_rotation_angle(self, cursor_position):
        try:
            dx = float(cursor_position[0]) - float(self.center_cursor[0])
            dy = float(cursor_position[1]) - float(self.center_cursor[1])

            if math.sqrt((dx * dx) + (dy * dy)) <= 0.000001:
                return self.last_cursor_rotation_angle or 0.0

            return math.degrees(math.atan2(dy, dx))
        except Exception:
            return self.last_cursor_rotation_angle or 0.0

    def _cursor_angle(self, cursor_position):
        return self._cursor_rotation_angle(cursor_position) + 90.0

    def _update_custom_cursor(self, cursor_position=None, force=False):
        app = QtWidgets.QApplication.instance()

        if app is None:
            return

        if cursor_position is None:
            cursor_position = _cursor_position()

        angle = self._cursor_rotation_angle(cursor_position)

        try:
            _hide_windows_cursor_once()
            cursor = QtGui.QCursor(_qt_cursor_shape("BlankCursor"))
            override_cursor = _qt_override_cursor(app)

            if force or not self.custom_cursor_active or override_cursor is None:
                if self.custom_cursor_active and override_cursor is not None:
                    app.changeOverrideCursor(cursor)
                else:
                    app.setOverrideCursor(cursor)
                    self.custom_cursor_active = True

            self.last_cursor_rotation_angle = angle
        except Exception:
            pass

    def _restore_custom_cursor(self):
        app = QtWidgets.QApplication.instance()

        if app is not None:
            for _index in range(CURSOR_RESTORE_LIMIT):
                if _qt_override_cursor(app) is None:
                    break
                try:
                    app.restoreOverrideCursor()
                except Exception:
                    break

        self.custom_cursor_active = False
        self.last_cursor_rotation_angle = None
        _restore_windows_arrow_cursor()

    def _stop_interaction(self):
        app = QtWidgets.QApplication.instance()
        self._restore_custom_cursor()
        self._hide_overlay()

        if self.timer is not None:
            try:
                self.timer.stop()
                self.timer.deleteLater()
            except Exception:
                pass
            self.timer = None

        # Keep the filter active while Qt drains the release/context-menu
        # events belonging to the click that completed this interaction.
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass

        if self.event_filter_installed and app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
            self.event_filter_installed = False

        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()
            mouse_press_type = (
                QtCore.QEvent.Type.MouseButtonPress
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonPress
            )
            mouse_double_click_type = (
                QtCore.QEvent.Type.MouseButtonDblClick
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonDblClick
            )
            mouse_release_type = (
                QtCore.QEvent.Type.MouseButtonRelease
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonRelease
            )
            context_menu_type = (
                QtCore.QEvent.Type.ContextMenu
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.ContextMenu
            )

            if (
                event_type == context_menu_type
                and self.pending_finish_vk_code == VK_RBUTTON
            ):
                return True

            if not self.armed or self.finished:
                return False

            if event_type not in (
                mouse_press_type,
                mouse_double_click_type,
                mouse_release_type,
            ):
                return False

            button = event.button()

            if hasattr(QtCore.Qt, "MouseButton"):
                left_button = QtCore.Qt.MouseButton.LeftButton
                right_button = QtCore.Qt.MouseButton.RightButton
            else:
                left_button = QtCore.Qt.LeftButton
                right_button = QtCore.Qt.RightButton

            if event_type in (mouse_press_type, mouse_double_click_type):
                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON)
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON)
                    return True

            if (
                event_type == mouse_release_type
                and self.pending_finish is not None
                and (
                    (button == left_button and self.pending_finish_vk_code == VK_LBUTTON)
                    or (button == right_button and self.pending_finish_vk_code == VK_RBUTTON)
                )
            ):
                self._schedule_mouse_finish()
                return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._begin_mouse_finish(False, VK_RBUTTON)

        return False

    def _begin_mouse_finish(self, accepted, vk_code, cursor_position=None):
        if self.pending_finish is not None or self.finished:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = cursor_position or _cursor_position()
        self.pending_finish_scheduled = False

    def _schedule_mouse_finish(self):
        if (
            self.pending_finish is None
            or self.pending_finish_scheduled
            or self.finished
        ):
            return

        self.pending_finish_scheduled = True
        QtCore.QTimer.singleShot(
            MOUSE_FINISH_RELEASE_DELAY_MS,
            self._complete_pending_mouse_finish,
        )

    def _complete_pending_mouse_finish(self):
        if self.pending_finish is None or self.finished:
            return

        self._finish(self.pending_finish, self.pending_finish_cursor)

    def _capture_current_tangents_as_base(self):
        for state in self.tangent_states:
            fcurve = state["curve"]
            index = state["index"]
            state["base_left_weight"] = float(fcurve.KeyGetLeftTangentWeight(index))
            state["base_right_weight"] = float(fcurve.KeyGetRightTangentWeight(index))
            state["base_left_derivative"] = float(fcurve.KeyGetLeftDerivative(index))
            state["base_right_derivative"] = float(fcurve.KeyGetRightDerivative(index))
            state["last_left_weight"] = state["base_left_weight"]
            state["last_right_weight"] = state["base_right_weight"]
            state["last_left_derivative"] = state["base_left_derivative"]
            state["last_right_derivative"] = state["base_right_derivative"]

    def _mouse_scale_factor(self, cursor_position):
        current_radius = max(
            _cursor_radius(self.center_cursor, cursor_position),
            MIN_CURSOR_RADIUS,
        )
        start_radius = max(self.start_radius, MIN_CURSOR_RADIUS)
        return max(MIN_MOUSE_SCALE_FACTOR, current_radius / start_radius)

    def _side_mode(self, shift_down, ctrl_down):
        if shift_down and not ctrl_down:
            return "right"

        if ctrl_down and not shift_down:
            return "left"

        return "both"

    def _set_axis_lock(self, axis_lock):
        if self.axis_lock == axis_lock:
            self.axis_lock = None
        else:
            self.axis_lock = axis_lock

        self.last_preview_signature = None
        self._preview_current_weights(force=True)

    def _target_tangents_for_state(self, state, scale_factor, side_mode):
        left_weight = float(state["base_left_weight"])
        right_weight = float(state["base_right_weight"])
        left_derivative = float(state["base_left_derivative"])
        right_derivative = float(state["base_right_derivative"])

        if self.axis_lock in (None, AXIS_LOCK_X):
            if side_mode in ("both", "left"):
                left_weight = _scale_fcurve_weight(left_weight, scale_factor)

            if side_mode in ("both", "right"):
                right_weight = _scale_fcurve_weight(right_weight, scale_factor)

        if self.axis_lock in (None, AXIS_LOCK_Y):
            if side_mode in ("both", "left"):
                left_derivative = _scale_fcurve_tangent_angle(
                    left_derivative,
                    scale_factor,
                    self.derivative_scale,
                )

            if side_mode in ("both", "right"):
                right_derivative = _scale_fcurve_tangent_angle(
                    right_derivative,
                    scale_factor,
                    self.derivative_scale,
                )

        return left_weight, right_weight, left_derivative, right_derivative

    def _status_text(self, scale_factor):
        left_weight, right_weight = _average_fcurve_weights(self.tangent_states)
        left_angle, right_angle = _average_fcurve_tangent_angles(
            self.tangent_states,
            self.derivative_scale,
        )

        if self.axis_lock == AXIS_LOCK_X:
            label = "X tangent weights"
            values = "L %s  R %s" % (
                _format_scale(left_weight),
                _format_scale(right_weight),
            )
        elif self.axis_lock == AXIS_LOCK_Y:
            label = "Y tangent angles"
            values = "L %+.2f deg  R %+.2f deg" % (
                left_angle,
                right_angle,
            )
        else:
            label = "Tangent scale"
            values = "W L %s R %s | A L %+.2f R %+.2f deg" % (
                _format_scale(left_weight),
                _format_scale(right_weight),
                left_angle,
                right_angle,
            )

        if self.last_side_mode == "left":
            label = "Left " + label
        elif self.last_side_mode == "right":
            label = "Right " + label

        return "%s %sx | %s" % (
            label,
            _format_scale(scale_factor),
            values,
        )

    def _axis_overlay_lines(self):
        if self.axis_lock is None:
            return [], None

        if self.axis_lock == AXIS_LOCK_X:
            endpoint = (self.center_cursor[0] + 1.0, self.center_cursor[1])
        else:
            endpoint = (self.center_cursor[0], self.center_cursor[1] + 1.0)

        return [
            (self.center_cursor, endpoint),
        ], AXIS_GUIDE_COLORS.get(self.axis_lock, (255, 255, 255, 230))

    def _update_overlay(self, cursor_position=None, scale_factor=None):
        if cursor_position is None:
            cursor_position = _cursor_position()

        self._update_custom_cursor(cursor_position)

        if self.overlay is None:
            return

        if scale_factor is None:
            scale_factor = self.last_applied_factor

        try:
            axis_lines, axis_color = self._axis_overlay_lines()
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(scale_factor),
                axis_lines,
                axis_color,
                self.cursor_pixmap,
                self._cursor_angle(cursor_position),
                1.0,
            )
        except Exception:
            pass

    def _preview_current_weights(self, force=False, cursor_position=None):
        if cursor_position is None:
            cursor_position = _cursor_position()
        shift_down = _is_key_down(VK_SHIFT)
        ctrl_down = _is_key_down(VK_CONTROL)
        side_mode = self._side_mode(shift_down, ctrl_down)
        scale_factor = self._mouse_scale_factor(cursor_position)
        signature = (
            self.axis_lock,
            side_mode,
            int(round(scale_factor / PREVIEW_SCALE_EPSILON)),
        )

        if not force and signature == self.last_preview_signature:
            self._update_overlay(cursor_position, scale_factor)
            return

        for state in self.tangent_states:
            (
                left_weight,
                right_weight,
                left_derivative,
                right_derivative,
            ) = self._target_tangents_for_state(
                state,
                scale_factor,
                side_mode,
            )
            _set_fcurve_tangent_state_values(
                state,
                left_weight,
                right_weight,
                left_derivative,
                right_derivative,
                break_tangents=(side_mode != "both"),
            )
            state["last_left_weight"] = left_weight
            state["last_right_weight"] = right_weight
            state["last_left_derivative"] = left_derivative
            state["last_right_derivative"] = right_derivative

        self.last_applied_factor = scale_factor
        self.last_side_mode = side_mode
        self.last_preview_signature = signature
        _refresh_fcurve_widget(self.graph_widget)
        self._update_overlay(cursor_position, scale_factor)

    def _restore_original_weights(self):
        _restore_fcurve_weight_states(self.tangent_states)
        self.last_preview_signature = None
        _refresh_fcurve_widget(self.graph_widget)

    def _finish(self, accepted, final_cursor=None):
        if self.finished:
            return

        self.accepted = accepted
        self.finished = True

        try:
            if accepted:
                self._preview_current_weights(
                    force=True,
                    cursor_position=final_cursor,
                )
            else:
                self._restore_original_weights()
        except Exception:
            self.accepted = False
            self.error_text = traceback.format_exc()
            try:
                self._restore_original_weights()
            except Exception:
                pass

        self._stop_interaction()
        _clear_active_controller(self)

        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")
        elif self.accepted:
            print(
                "%s: scaled %d selected FCurve key tangent(s) by %.3fx."
                % (TOOL_NAME, len(self.tangent_states), self.last_applied_factor)
            )
        else:
            print("%s: FCurve tangent scaling canceled." % TOOL_NAME)

    def _tick(self):
        try:
            if self.pending_finish is not None:
                if not _is_key_down(self.pending_finish_vk_code):
                    self._schedule_mouse_finish()
                return

            left_down, left_pressed = _mouse_button_state(VK_LBUTTON, "LeftButton")
            right_down, right_pressed = _mouse_button_state(VK_RBUTTON, "RightButton")
            escape_down, escape_pressed = _key_state(VK_ESCAPE)
            return_down, return_pressed = _key_state(VK_RETURN)
            x_down, _x_pressed = _key_state(VK_X)
            y_down, _y_pressed = _key_state(VK_Y)
            self._update_custom_cursor(_cursor_position())

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self.start_cursor = _cursor_position()
                    self.start_radius = max(
                        _cursor_radius(self.center_cursor, self.start_cursor),
                        MIN_CURSOR_RADIUS,
                    )
                    self.was_left_down = False
                    self.was_right_down = False
                    self.was_escape_down = escape_down
                    self.was_return_down = return_down
                    self.was_x_down = x_down
                    self.was_y_down = y_down
                    self._preview_current_weights(force=True)
                return

            cancel_pressed = escape_down or escape_pressed
            accept_pressed = return_down or return_pressed
            axis_lock_request = None

            if x_down and not self.was_x_down:
                axis_lock_request = AXIS_LOCK_X
            elif y_down and not self.was_y_down:
                axis_lock_request = AXIS_LOCK_Y

            if cancel_pressed:
                self._finish(False)
                return

            if accept_pressed:
                self._finish(True)
                return

            if right_down and not self.was_right_down:
                self._begin_mouse_finish(False, VK_RBUTTON)
                return

            if left_down and not self.was_left_down:
                self._begin_mouse_finish(True, VK_LBUTTON)
                return

            if axis_lock_request is not None:
                self._set_axis_lock(axis_lock_request)
                self.was_left_down = left_down
                self.was_right_down = right_down
                self.was_escape_down = escape_down
                self.was_return_down = return_down
                self.was_x_down = x_down
                self.was_y_down = y_down
                return

            self._preview_current_weights()
            self.was_left_down = left_down
            self.was_right_down = right_down
            self.was_escape_down = escape_down
            self.was_return_down = return_down
            self.was_x_down = x_down
            self.was_y_down = y_down
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


class MouseDistanceScaleController(QtCore.QObject):
    def __init__(
        self,
        model_states,
        center_cursor,
        viewport_rect=None,
        camera=None,
    ):
        QtCore.QObject.__init__(self)
        self.model_states = model_states
        self.center_cursor = center_cursor
        self.viewport_rect = viewport_rect
        self.camera = camera
        self.overlay = None
        self.cursor_pixmaps = {}
        self.last_cursor_icon = None
        self.custom_cursor_active = False
        self.last_cursor_rotation_angle = None
        self.axis_lock = None
        self.axis_lock_space = None
        self.precision_multiplier = 1.0
        self.start_cursor = _cursor_position()
        self.start_radius = max(
            _cursor_radius(self.center_cursor, self.start_cursor),
            MIN_CURSOR_RADIUS,
        )
        self.last_preview_signature = None
        self.last_applied_factor = 1.0
        self.last_applied_snapped = False
        self.last_applied_scale_vectors = [
            list(state["original_scaling"])
            for state in self.model_states
        ]
        self.timer = None
        self.armed = False
        self.accepted = False
        self.finished = False
        self.numeric_input_text = ""
        self.numeric_input_active = False
        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False
        self.event_filter_installed = False
        self.error_text = None
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_return_down = _is_key_down(VK_RETURN)
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)
        self.was_z_down = _is_key_down(VK_Z)
        self.was_numeric_key_down = {
            vk_code: _is_key_down(vk_code)
            for vk_code, _value in NUMERIC_INPUT_KEYS
        }

    def start(self):
        app = QtWidgets.QApplication.instance()

        if app is None:
            FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
            return False

        if self.timer is not None:
            return True

        self.timer = QtCore.QTimer(self)
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)
        app.installEventFilter(self)
        self.event_filter_installed = True
        self._show_overlay()
        self._update_custom_cursor(_cursor_position(), force=True)
        return True

    def run(self):
        return self.start()

    def request_restart_from_cursor(self):
        if self.finished:
            return False

        try:
            self._capture_current_scales_as_base()
            self.start_cursor = _cursor_position()
            self.start_radius = max(
                _cursor_radius(self.center_cursor, self.start_cursor),
                MIN_CURSOR_RADIUS,
            )
            self.numeric_input_text = ""
            self.numeric_input_active = False
            self.last_preview_signature = None
            self._preview_current_transform(force=True)
            return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)
            return False

    def _show_overlay(self):
        if self.viewport_rect is None:
            return

        try:
            cursor_position = _cursor_position()
            self.overlay = ScaleOverlayWidget(self.viewport_rect)
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(self.last_applied_scale_vectors, 1.0, None),
                [],
                None,
                self._cursor_pixmap_for_icon(SCALE_CURSOR_ICON),
                self._cursor_angle(cursor_position),
                1.0,
            )
        except Exception:
            self.overlay = None

    def _hide_overlay(self):
        if self.overlay is None:
            return

        try:
            self.overlay.hide()
        except Exception:
            pass

        try:
            self.overlay.deleteLater()
        except Exception:
            pass

        self.overlay = None

    def _cursor_rotation_angle(self, cursor_position):
        try:
            dx = float(cursor_position[0]) - float(self.center_cursor[0])
            dy = float(cursor_position[1]) - float(self.center_cursor[1])

            if math.sqrt((dx * dx) + (dy * dy)) <= 0.000001:
                return self.last_cursor_rotation_angle

            return math.degrees(math.atan2(dy, dx))
        except Exception:
            return self.last_cursor_rotation_angle

    def _cursor_angle(self, cursor_position):
        angle = self._cursor_rotation_angle(cursor_position)

        if angle is None:
            return 0.0

        return angle + 90.0

    def _cursor_pixmap_for_icon(self, relative_icon_path):
        pixmap = self.cursor_pixmaps.get(relative_icon_path)

        if pixmap is None:
            pixmap = _load_cursor_pixmap(relative_icon_path)
            self.cursor_pixmaps[relative_icon_path] = pixmap

        return pixmap

    def _update_custom_cursor(self, cursor_position=None, force=False):
        app = QtWidgets.QApplication.instance()

        if app is None:
            return

        if cursor_position is None:
            cursor_position = _cursor_position()

        pixmap = self._cursor_pixmap_for_icon(SCALE_CURSOR_ICON)
        angle = self._cursor_angle(cursor_position)

        try:
            cursor = None

            if cursor is None:
                _hide_windows_cursor_once()
                cursor = QtGui.QCursor(_qt_cursor_shape("BlankCursor"))

            override_cursor = _qt_override_cursor(app)
            should_update_cursor = (
                force
                or not self.custom_cursor_active
                or override_cursor is None
                or self.last_cursor_icon != SCALE_CURSOR_ICON
            )

            if should_update_cursor:
                if self.custom_cursor_active and override_cursor is not None:
                    app.changeOverrideCursor(cursor)
                else:
                    app.setOverrideCursor(cursor)
                    self.custom_cursor_active = True

            self.last_cursor_icon = SCALE_CURSOR_ICON
            self.last_cursor_rotation_angle = angle - 90.0
        except Exception:
            pass

    def _restore_custom_cursor(self):
        app = QtWidgets.QApplication.instance()

        if app is not None:
            for _index in range(CURSOR_RESTORE_LIMIT):
                if _qt_override_cursor(app) is None:
                    break

                try:
                    app.restoreOverrideCursor()
                except Exception:
                    break

        self.custom_cursor_active = False
        self.last_cursor_icon = None
        self.last_cursor_rotation_angle = None
        _restore_windows_arrow_cursor()

    def _stop_interaction(self):
        app = QtWidgets.QApplication.instance()

        self._restore_custom_cursor()
        self._hide_overlay()

        if self.timer is not None:
            try:
                self.timer.stop()
            except Exception:
                pass
            try:
                self.timer.deleteLater()
            except Exception:
                pass
            self.timer = None

        # Keep the filter active while Qt drains the release/context-menu
        # events belonging to the click that completed this interaction.
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass

        if self.event_filter_installed and app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
            self.event_filter_installed = False

        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False

    def _report_result(self):
        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")

        if not self.accepted:
            print("%s canceled. Original scale restored." % TOOL_NAME)
            return

        average_scale = _average_scale(self.last_applied_scale_vectors)
        print(
            "%s applied scale X %s, Y %s, Z %s."
            % (
                TOOL_NAME,
                _format_scale(average_scale[0]),
                _format_scale(average_scale[1]),
                _format_scale(average_scale[2]),
            )
        )

    def _status_text(self, scale_vectors, scale_factor, numeric_value):
        average_scale = _average_scale(scale_vectors)
        vector_text = "X %s  Y %s  Z %s" % (
            _format_scale(average_scale[0]),
            _format_scale(average_scale[1]),
            _format_scale(average_scale[2]),
        )

        if numeric_value is not None:
            lead_text = "Scale %s" % _format_scale(numeric_value)
        else:
            lead_text = "Scale %sx" % _format_scale(scale_factor)

        if self.axis_lock is not None:
            axis_space = self.axis_lock_space or AXIS_SPACE_GLOBAL
            return "%s along %s %s | %s" % (
                lead_text,
                axis_space,
                self.axis_lock.upper(),
                vector_text,
            )

        return "%s | %s" % (lead_text, vector_text)

    def _update_overlay(
        self,
        cursor_position=None,
        scale_vectors=None,
        scale_factor=None,
        numeric_value=None,
    ):
        if self.overlay is None:
            return

        if cursor_position is None:
            cursor_position = _cursor_position()

        if scale_vectors is None:
            scale_vectors = self.last_applied_scale_vectors

        if scale_factor is None:
            scale_factor = self.last_applied_factor

        try:
            self._update_custom_cursor(cursor_position)
            axis_lines_global = []
            axis_line_color = None
            cursor_pixmap = self._cursor_pixmap_for_icon(SCALE_CURSOR_ICON)
            cursor_angle = self._cursor_angle(cursor_position)

            if self.axis_lock is not None:
                axis_space = self.axis_lock_space or AXIS_SPACE_GLOBAL
                axis_lines_global, axis_line_color = _axis_lock_overlay_lines(
                    self.camera,
                    self.viewport_rect,
                    self.model_states,
                    self.axis_lock,
                    axis_space,
                )

            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(scale_vectors, scale_factor, numeric_value),
                axis_lines_global,
                axis_line_color,
                cursor_pixmap,
                cursor_angle,
                1.0,
            )
        except Exception:
            pass

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()
            mouse_press_type = (
                QtCore.QEvent.Type.MouseButtonPress
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonPress
            )
            mouse_double_click_type = (
                QtCore.QEvent.Type.MouseButtonDblClick
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonDblClick
            )
            mouse_release_type = (
                QtCore.QEvent.Type.MouseButtonRelease
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.MouseButtonRelease
            )
            context_menu_type = (
                QtCore.QEvent.Type.ContextMenu
                if hasattr(QtCore.QEvent, "Type")
                else QtCore.QEvent.ContextMenu
            )

            if (
                event_type == context_menu_type
                and self.pending_finish_vk_code == VK_RBUTTON
            ):
                return True

            if not self.armed or self.finished:
                return False

            if event_type not in (
                mouse_press_type,
                mouse_double_click_type,
                mouse_release_type,
            ):
                return False

            button = event.button()

            if hasattr(QtCore.Qt, "MouseButton"):
                left_button = QtCore.Qt.MouseButton.LeftButton
                right_button = QtCore.Qt.MouseButton.RightButton
            else:
                left_button = QtCore.Qt.LeftButton
                right_button = QtCore.Qt.RightButton

            if event_type in (mouse_press_type, mouse_double_click_type):
                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON)
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON)
                    return True

            if (
                event_type == mouse_release_type
                and self.pending_finish is not None
                and (
                    (button == left_button and self.pending_finish_vk_code == VK_LBUTTON)
                    or (button == right_button and self.pending_finish_vk_code == VK_RBUTTON)
                )
            ):
                self._schedule_mouse_finish()
                return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._begin_mouse_finish(False, VK_RBUTTON)

        return False

    def _begin_mouse_finish(self, accepted, vk_code, cursor_position=None):
        if self.pending_finish is not None or self.finished:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = cursor_position or _cursor_position()
        self.pending_finish_scheduled = False

    def _schedule_mouse_finish(self):
        if (
            self.pending_finish is None
            or self.pending_finish_scheduled
            or self.finished
        ):
            return

        self.pending_finish_scheduled = True
        QtCore.QTimer.singleShot(
            MOUSE_FINISH_RELEASE_DELAY_MS,
            self._complete_pending_mouse_finish,
        )

    def _complete_pending_mouse_finish(self):
        if self.pending_finish is None or self.finished:
            return

        self._finish(self.pending_finish, self.pending_finish_cursor)

    def _set_key_states(
        self,
        left_down,
        right_down,
        escape_down,
        return_down,
        x_down,
        y_down,
        z_down,
    ):
        self.was_left_down = left_down
        self.was_right_down = right_down
        self.was_escape_down = escape_down
        self.was_return_down = return_down
        self.was_x_down = x_down
        self.was_y_down = y_down
        self.was_z_down = z_down

    def _set_axis_lock(self, axis_lock):
        if self.axis_lock == axis_lock:
            if self.axis_lock_space == AXIS_SPACE_GLOBAL:
                axis_lock_space = AXIS_SPACE_LOCAL
            else:
                axis_lock_space = AXIS_SPACE_GLOBAL
        else:
            axis_lock_space = AXIS_SPACE_GLOBAL

        self.axis_lock = axis_lock
        self.axis_lock_space = axis_lock_space
        self.last_preview_signature = None
        self._preview_current_transform(force=True)

    def _update_precision_mode(self, shift_down):
        precision_multiplier = PRECISION_MULTIPLIER if shift_down else 1.0

        if abs(precision_multiplier - self.precision_multiplier) <= 0.000001:
            return

        self.precision_multiplier = precision_multiplier
        self.last_preview_signature = None

    def _numeric_input_value(self):
        text = self.numeric_input_text

        if text in ("", "-", ".", "-."):
            return 0.0

        try:
            return float(text)
        except Exception:
            return 0.0

    def _append_numeric_input(self, value):
        previous_text = self.numeric_input_text

        if value == "backspace":
            self.numeric_input_text = self.numeric_input_text[:-1]
        elif value == ".":
            if "." not in self.numeric_input_text:
                if not self.numeric_input_text or self.numeric_input_text == "-":
                    self.numeric_input_text += "0"
                self.numeric_input_text += "."
        elif value == "-":
            if self.numeric_input_text.startswith("-"):
                self.numeric_input_text = self.numeric_input_text[1:]
            else:
                self.numeric_input_text = "-" + self.numeric_input_text
        else:
            self.numeric_input_text += value

        self.numeric_input_active = bool(self.numeric_input_text)

        if self.numeric_input_text != previous_text:
            self.last_preview_signature = None

    def _update_numeric_input(self):
        changed = False

        for vk_code, value in NUMERIC_INPUT_KEYS:
            down = _is_key_down(vk_code)

            if down and not self.was_numeric_key_down.get(vk_code, False):
                self._append_numeric_input(value)
                changed = True

            self.was_numeric_key_down[vk_code] = down

        return changed

    def _mouse_scale_factor(self, cursor_position):
        current_radius = max(
            _cursor_radius(self.center_cursor, cursor_position),
            MIN_CURSOR_RADIUS,
        )
        start_radius = max(self.start_radius, MIN_CURSOR_RADIUS)
        raw_factor = current_radius / start_radius
        scale_factor = 1.0 + ((raw_factor - 1.0) * self.precision_multiplier)
        return max(MIN_MOUSE_SCALE_FACTOR, scale_factor)

    def _effective_scale(self, cursor_position):
        numeric_value = None

        if self.numeric_input_active:
            return self.last_applied_factor, False, self._numeric_input_value()

        scale_factor = self._mouse_scale_factor(cursor_position)
        snap_to_increment = _is_key_down(VK_CONTROL)

        if snap_to_increment:
            scale_factor = _snap_scale_factor(scale_factor)

        return scale_factor, snap_to_increment, numeric_value

    def _capture_current_scales_as_base(self):
        for state in self.model_states:
            current_scaling = _local_scaling(state["model"])
            state["base_scaling"] = current_scaling

        self.last_applied_scale_vectors = [
            list(state["base_scaling"])
            for state in self.model_states
        ]

    def _preview_current_transform(self, force=False, cursor_position=None):
        if cursor_position is None:
            cursor_position = _cursor_position()
        scale_factor, snap_to_increment, numeric_value = self._effective_scale(cursor_position)
        target_scales = _target_scale_vectors(
            self.model_states,
            scale_factor,
            self.axis_lock,
            numeric_value,
        )

        signature = (
            self.axis_lock,
            self.axis_lock_space,
            self.numeric_input_text,
            snap_to_increment,
            int(round(scale_factor / PREVIEW_SCALE_EPSILON)),
        )

        if numeric_value is not None:
            signature = signature + (numeric_value,)

        if not force and self.last_preview_signature == signature:
            self._update_overlay(cursor_position, target_scales, scale_factor, numeric_value)
            return

        for index, state in enumerate(self.model_states):
            _set_local_scaling(state["model"], target_scales[index])

        self.last_applied_factor = scale_factor
        self.last_applied_snapped = snap_to_increment
        self.last_applied_scale_vectors = target_scales
        self.last_preview_signature = signature
        self._update_overlay(cursor_position, target_scales, scale_factor, numeric_value)

    def _restore_original_scales(self):
        for state in self.model_states:
            _set_local_scaling(state["model"], state["original_scaling"])
        self.last_preview_signature = None

    def _finish(self, accepted, final_cursor=None):
        if self.finished:
            return

        self.accepted = accepted
        self.finished = True

        if accepted:
            try:
                self._preview_current_transform(
                    force=True,
                    cursor_position=final_cursor,
                )
            except Exception:
                self.accepted = False
                if not self.error_text:
                    self.error_text = traceback.format_exc()
                try:
                    self._restore_original_scales()
                except Exception:
                    pass
        else:
            try:
                self._restore_original_scales()
            except Exception:
                if not self.error_text:
                    self.error_text = traceback.format_exc()

        self._stop_interaction()
        _clear_active_controller(self)
        self._report_result()

    def _tick(self):
        try:
            if self.pending_finish is not None:
                if not _is_key_down(self.pending_finish_vk_code):
                    self._schedule_mouse_finish()
                return

            left_down, left_pressed = _mouse_button_state(VK_LBUTTON, "LeftButton")
            right_down, right_pressed = _mouse_button_state(VK_RBUTTON, "RightButton")
            escape_down, escape_pressed = _key_state(VK_ESCAPE)
            return_down, return_pressed = _key_state(VK_RETURN)
            shift_down, _shift_pressed = _key_state(VK_SHIFT)
            ctrl_down, _ctrl_pressed = _key_state(VK_CONTROL)
            x_down, _x_pressed = _key_state(VK_X)
            y_down, _y_pressed = _key_state(VK_Y)
            z_down, _z_pressed = _key_state(VK_Z)

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self.start_cursor = _cursor_position()
                    self.start_radius = max(
                        _cursor_radius(self.center_cursor, self.start_cursor),
                        MIN_CURSOR_RADIUS,
                    )
                    self._set_key_states(
                        False,
                        False,
                        escape_down,
                        return_down,
                        x_down,
                        y_down,
                        z_down,
                    )
                    self._preview_current_transform(force=True)
                return

            cancel_pressed = escape_down or escape_pressed
            accept_pressed = return_down or return_pressed
            numeric_input_changed = self._update_numeric_input()
            axis_lock_request = None

            if x_down and not self.was_x_down:
                axis_lock_request = AXIS_LOCK_X
            elif y_down and not self.was_y_down:
                axis_lock_request = AXIS_LOCK_Y
            elif z_down and not self.was_z_down:
                axis_lock_request = AXIS_LOCK_Z

            if cancel_pressed:
                self._finish(False)
                return

            if accept_pressed:
                self._finish(True)
                return

            if right_down and not self.was_right_down:
                self._begin_mouse_finish(False, VK_RBUTTON)
                return

            if left_down and not self.was_left_down:
                self._begin_mouse_finish(True, VK_LBUTTON)
                return

            self._update_precision_mode(shift_down)

            if axis_lock_request is not None:
                self._set_axis_lock(axis_lock_request)
                self._set_key_states(
                    left_down,
                    right_down,
                    escape_down,
                    return_down,
                    x_down,
                    y_down,
                    z_down,
                )
                return

            if numeric_input_changed:
                self._preview_current_transform(force=True)
            else:
                self._preview_current_transform()

            self._set_key_states(
                left_down,
                right_down,
                escape_down,
                return_down,
                x_down,
                y_down,
                z_down,
            )
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


def _start_fcurve_tangent_weight_scale(graph_widget):
    tangent_states = _selected_fcurve_weight_states()

    if not tangent_states:
        return

    graph_rect = _qt_widget_rect(graph_widget)
    center_cursor, derivative_scale = _fcurve_scale_center(
        graph_widget,
        tangent_states,
    )
    controller = FCurveTangentWeightScaleController(
        tangent_states,
        graph_widget,
        center_cursor,
        graph_rect,
        derivative_scale,
    )
    _set_active_controller(controller)

    try:
        started = controller.start()
    except Exception:
        _clear_active_controller(controller)
        raise

    if not started:
        _clear_active_controller(controller)


def scale_selected_by_mouse_distance():
    active_controller = _get_active_controller()

    if active_controller is not None:
        active_controller.request_restart_from_cursor()
        return

    fcurve_graph_widget = _fcurve_graph_widget_for_cursor()

    if fcurve_graph_widget is not None:
        _start_fcurve_tangent_weight_scale(fcurve_graph_widget)
        return

    models = _selected_transformable_models()

    if not models:
        return

    model_states = [
        {
            "model": model,
            "original_scaling": _local_scaling(model),
            "base_scaling": _local_scaling(model),
            "original_translation": _world_translation(model),
            "original_rotation": _world_rotation(model),
            "local_axes": _local_axis_directions(model),
            "center_visible": _model_visible_for_center(model),
        }
        for model in models
    ]

    camera, view_right, view_up, view_depth = _camera_view_context()
    center_cursor = _scale_center_cursor(
        camera,
        model_states,
        view_right,
        view_up,
        view_depth,
    )
    viewport_rect = _viewport_global_rect(camera)

    controller = MouseDistanceScaleController(
        model_states,
        center_cursor,
        viewport_rect,
        camera,
    )

    _set_active_controller(controller)

    try:
        started = controller.start()
    except Exception:
        _clear_active_controller(controller)
        raise

    if not started:
        _clear_active_controller(controller)


def run_with_error_dialog():
    try:
        scale_selected_by_mouse_distance()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
