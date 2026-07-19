import ctypes
import math
import os
import sys
import time
import traceback
import types

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
    FBMatrixMult,
    FBMessageBox,
    FBModelTransformationType,
    FBModelList,
    FBSystem,
    FBTangentMode,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Rotate Selected By Mouse Orbit"
ACTIVE_CONTROLLER_ATTR = "_rotate_selected_by_mouse_orbit_active_controller"
ACTIVE_STATE_MODULE = "_rotate_selected_by_mouse_orbit_state"

POLL_INTERVAL_MS = 16
MOUSE_FINISH_RELEASE_DELAY_MS = 50
MIN_CURSOR_RADIUS = 8.0
ANGLE_EPSILON = 0.0001
PREVIEW_ANGLE_EPSILON = 0.05
TRACKBALL_FACTOR = 0.01
PRECISION_MULTIPLIER = 0.1
TOGGLE_DEBOUNCE_SECONDS = 0.16
ROTATION_CURSOR_ICON = os.path.join("icons", "2arrow.png")
TRACKBALL_CURSOR_ICON = os.path.join("icons", "4arrow_colored.png")
IDC_ARROW = 32512
CURSOR_RESTORE_LIMIT = 12
TRACKBALL_CURSOR_SCALE = 0.725
OVERLAY_TEXT_MARGIN = 18
OVERLAY_TEXT_PADDING_X = 10
OVERLAY_TEXT_PADDING_Y = 5
AXIS_LINE_MIN_SCREEN_LENGTH = 4.0
MODE_ORBIT = "orbit"
MODE_TRACKBALL = "trackball"
AXIS_LOCK_X = "x"
AXIS_LOCK_Y = "y"
AXIS_LOCK_Z = "z"
AXIS_SPACE_GLOBAL = "global"
AXIS_SPACE_LOCAL = "local"
CURSOR_PIXMAP_CACHE = {}
FCURVE_MANUAL_DERIVATIVE_LIMIT = 1000000.0
FCURVE_MARKER_WINDOW_RADIUS = 5
FCURVE_MARKER_MIN_DENSITY = 20.0

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_BACKSPACE = 0x08
VK_R = 0x52
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
            return r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts"


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
    if relative_icon_path in CURSOR_PIXMAP_CACHE:
        return CURSOR_PIXMAP_CACHE[relative_icon_path]

    try:
        pixmap = QtGui.QPixmap(_cursor_icon_path(relative_icon_path))
        if not pixmap.isNull():
            CURSOR_PIXMAP_CACHE[relative_icon_path] = pixmap
            return pixmap
    except Exception:
        pass

    CURSOR_PIXMAP_CACHE[relative_icon_path] = None
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


def _event_loop_exec(loop):
    if hasattr(loop, "exec"):
        return loop.exec()
    return loop.exec_()


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


def _qt_pen_cap_style(name):
    if hasattr(QtCore.Qt, "PenCapStyle"):
        return getattr(QtCore.Qt.PenCapStyle, name)

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


def _active_controller_state_module():
    module = sys.modules.get(ACTIVE_STATE_MODULE)

    if module is None:
        module = types.ModuleType(ACTIVE_STATE_MODULE)
        sys.modules[ACTIVE_STATE_MODULE] = module

    return module


def _active_controller_holders():
    holders = [
        _active_controller_state_module(),
        builtins,
    ]

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
        and hasattr(controller, "request_mode_toggle")
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


def _angle_from_center(center, cursor):
    center_x, center_y = center
    cursor_x, cursor_y = cursor
    delta_x = float(cursor_x - center_x)
    delta_y = float(cursor_y - center_y)

    if math.sqrt((delta_x * delta_x) + (delta_y * delta_y)) < MIN_CURSOR_RADIUS:
        return None

    return math.degrees(math.atan2(-delta_y, delta_x))


def _wrapped_angle_delta(current_angle, previous_angle):
    delta = current_angle - previous_angle

    while delta > 180.0:
        delta -= 360.0

    while delta < -180.0:
        delta += 360.0

    return delta


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
    x, z = (x * cos_y) + (z * sin_y), (-x * sin_y) + (z * cos_y)
    x, y = (x * cos_z) - (y * sin_z), (x * sin_z) + (y * cos_z)

    return [x, y, z]


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
        rotation = _vector_to_list(camera.Rotation)
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


def _view_axis_toward_camera(camera, model_states, fallback_axis):
    if camera is not None:
        try:
            camera_position = _world_translation(camera)
            center = _selection_center(model_states)
            axis = _sub(camera_position, center)
            return _normalize(axis, fallback_axis)
        except Exception:
            pass

    return _normalize(fallback_axis, [0.0, 0.0, 1.0])


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


def _widget_description(widget):
    parts = []
    seen = set()
    current = widget

    while current is not None and id(current) not in seen:
        seen.add(id(current))

        try:
            meta = current.metaObject()
            if meta is not None:
                parts.append(str(meta.className()))
        except Exception:
            parts.append(type(current).__name__)

        for getter_name in (
            "objectName",
            "accessibleName",
            "windowTitle",
            "toolTip",
        ):
            try:
                value = getattr(current, getter_name)()
            except Exception:
                value = ""

            if value:
                parts.append(str(value))

        try:
            current = current.parentWidget()
        except Exception:
            current = None

    return " ".join(parts).lower()


def _widget_contains_global_point(widget, global_point):
    try:
        rect = _qt_widget_rect(widget)
        return _rect_contains_point(rect, global_point)
    except Exception:
        return False


def _distance_to_widget_rect(widget, global_point):
    try:
        x, y, width, height = _qt_widget_rect(widget)
        point_x = float(global_point.x())
        point_y = float(global_point.y())
        nearest_x = min(max(point_x, float(x)), float(x + width))
        nearest_y = min(max(point_y, float(y)), float(y + height))
        dx = point_x - nearest_x
        dy = point_y - nearest_y
        return (dx * dx) + (dy * dy)
    except Exception:
        return float("inf")


def _fcurve_graph_widget_for_cursor():
    app = QtWidgets.QApplication.instance()

    if app is None:
        return None

    cursor = _cursor_qpoint()

    try:
        widget_at_cursor = app.widgetAt(cursor)
    except Exception:
        widget_at_cursor = None

    # The graph itself is exposed as a QOpenGLWidget named "FCurve".  Do not
    # use FCurveLayerView here: that similarly named widget is the separate
    # Animation Layers panel, so it produces an unrelated orbit center.
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

    # Compatibility fallback for layouts where GetProperties does not expose
    # the default editor contents through Python.
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

    # MotionBuilder can mark a key while one of its tangent handles is the
    # active manipulation target without changing the regular key selection.
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


def _selected_fcurve_tangent_states():
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
                left_derivative = float(fcurve.KeyGetLeftDerivative(index))
                right_derivative = float(fcurve.KeyGetRightDerivative(index))
                tangent_mode = fcurve.KeyGetTangentMode(index)
                tangent_break = bool(fcurve.KeyGetTangentBreak(index))
            except Exception:
                continue

            manual_mode = (
                FBTangentMode.kFBTangentModeBreak
                if tangent_break or abs(left_derivative - right_derivative) > 0.000001
                else FBTangentMode.kFBTangentModeUser
            )
            states.append(
                {
                    "curve": fcurve,
                    "index": index,
                    "time_ticks": _fcurve_key_time_ticks(fcurve, index),
                    "value": _fcurve_key_value(fcurve, index),
                    "original_left_derivative": left_derivative,
                    "original_right_derivative": right_derivative,
                    "original_tangent_mode": tangent_mode,
                    "original_tangent_break": tangent_break,
                    "manual_tangent_mode": manual_mode,
                    "manual_prepared": False,
                }
            )

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


def _qt_widget_display_value(widget):
    display_value = None
    for getter_name in ("displayText", "text", "currentText", "value"):
        try:
            value = getattr(widget, getter_name)()
            if value is not None and str(value) != "":
                display_value = str(value)
                break
        except Exception:
            pass

    accessible_text = {}
    try:
        accessible_class = getattr(QtGui, "QAccessible", None)
        interface = accessible_class.queryAccessibleInterface(widget)
        text_enum = getattr(accessible_class, "Text", accessible_class)

        for text_name in ("Name", "Value", "Description", "Help"):
            text_type = getattr(text_enum, text_name, None)
            if text_type is None:
                continue
            value = interface.text(text_type)
            if value:
                accessible_text[text_name.lower()] = str(value)

        if display_value is None:
            display_value = accessible_text.get("value")
    except Exception:
        pass

    return display_value, accessible_text


def _fcurve_editor_widget(graph_widget):
    current = graph_widget

    while current is not None:
        try:
            if str(current.accessibleName() or "").lower() == "fcurvepropertyview":
                return current
            current = current.parentWidget()
        except Exception:
            return None

    return None


def _fcurve_tangent_angle_widgets(graph_widget):
    app = QtWidgets.QApplication.instance()
    editor_widget = _fcurve_editor_widget(graph_widget)
    result = {"left": None, "right": None}

    if app is None or editor_widget is None:
        return result

    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []

    names = {
        "tangeantinfield": "left",
        "tangeantoutfield": "right",
    }

    for widget in widgets:
        try:
            side = names.get(str(widget.accessibleName() or "").lower())
            if side is None or not widget.isVisible():
                continue

            current = widget
            while current is not None and current is not editor_widget:
                current = current.parentWidget()

            if current is editor_widget:
                result[side] = widget
        except Exception:
            pass

    return result


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
    # The FCurve OpenGL widget includes the current-time strip below the
    # editable graph. Its bright playhead marker can be mistaken for the
    # selected key, so do not scan that strip for a rotation center.
    timeline_height = max(
        int(round(34.0 * scale_y)),
        int(round(image_height * 0.15)),
    )
    graph_image_bottom = max(border_y + 1, image_height - timeline_height)
    cursor_image_x = float(cursor_local_x) * scale_x
    cursor_image_y = float(cursor_local_y) * scale_y
    density_bins = {}
    details.update(
        {
            "image_size": [image_width, image_height],
            "widget_size": [widget_width, widget_height],
            "scale": [scale_x, scale_y],
            "bin_size": [bin_width, bin_height],
            "cursor_local": [cursor_local_x, cursor_local_y],
            "cursor_image": [cursor_image_x, cursor_image_y],
        }
    )

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
            or image_y > image_height - border_y
        ):
            continue

        distance = math.sqrt(
            ((image_x - cursor_image_x) ** 2)
            + ((image_y - cursor_image_y) ** 2)
        )
        candidates.append((density, distance, image_x, image_y))

    if not candidates:
        details["reason"] = "no_marker_candidates"
        details["density_bin_count"] = len(density_bins)
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
    details.update(
        {
            "reason": "selected_marker_candidate",
            "density_bin_count": len(density_bins),
            "candidate_count": len(candidates),
            "maximum_density": maximum_density,
            "strong_threshold": strong_threshold,
            "strong_candidate_count": len(strong_candidates),
            "top_candidates": [
                {
                    "density": round(candidate[0], 3),
                    "distance_to_cursor": round(candidate[1], 3),
                    "image_center": [round(candidate[2], 3), round(candidate[3], 3)],
                }
                for candidate in sorted(
                    candidates,
                    key=lambda candidate: candidate[0],
                    reverse=True,
                )[:25]
            ],
            "chosen_image_center": [best_x, best_y],
            "chosen_local_center": [
                float(best_x) / scale_x,
                float(best_y) / scale_y,
            ],
        }
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


def _median(values):
    ordered = sorted(float(value) for value in values)
    count = len(ordered)

    if count <= 0:
        return None
    if count % 2:
        return ordered[count // 2]

    middle = count // 2
    return (ordered[middle - 1] + ordered[middle]) * 0.5


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
    return (
        selected_x / image_scale_x,
        selected_y / image_scale_y,
        pixels_per_second / abs(pixels_per_value),
    )


def _fcurve_graph_derivative_scale(
    graph_widget,
    selected_center_local,
    tangent_states,
    details,
):
    scale_details = {"reason": "not_detected"}
    details["graph_derivative_scale"] = scale_details

    if not tangent_states or selected_center_local is None:
        scale_details["reason"] = "missing_selected_key"
        return None

    state = tangent_states[0]
    fcurve = state["curve"]
    selected_index = int(state["index"])

    try:
        pixmap = graph_widget.grab()
        image = pixmap.toImage()
        if pixmap.isNull() or image.isNull():
            scale_details["reason"] = "null_graph_snapshot"
            return None
    except Exception as error:
        scale_details["reason"] = "graph_snapshot_exception"
        scale_details["error"] = repr(error)
        return None

    widget_width = max(1.0, float(graph_widget.width()))
    widget_height = max(1.0, float(graph_widget.height()))
    image_width = int(image.width())
    image_height = int(image.height())
    scale_x = float(image_width) / widget_width
    scale_y = float(image_height) / widget_height
    selected_x = float(selected_center_local[0]) * scale_x
    selected_y = float(selected_center_local[1]) * scale_y
    pixels = set()

    for image_y in range(image_height):
        for image_x in range(image_width):
            try:
                if _fcurve_tangent_pixel(image.pixelColor(image_x, image_y)):
                    pixels.add((image_x, image_y))
            except Exception:
                pass

    components = []
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

        components.append(component)

    key_markers = []
    for component in components:
        if len(component) < 16:
            continue

        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        width = max(xs) - min(xs) + 1
        height = max(ys) - min(ys) + 1

        # Unselected FCurve keys are isolated pink 6x6 squares. Tangent
        # handles are connected to their guide line and therefore have a
        # substantially wider component.
        if width > 9 or height > 9:
            continue

        key_markers.append(
            (
                (min(xs) + max(xs)) * 0.5,
                (min(ys) + max(ys)) * 0.5,
            )
        )

    try:
        keys = list(fcurve.Keys)
        selected_time = float(keys[selected_index].Time.GetSecondDouble())
        selected_value = float(keys[selected_index].Value)
    except Exception as error:
        scale_details["reason"] = "selected_key_data_exception"
        scale_details["error"] = repr(error)
        return None

    left_markers = sorted(
        (marker for marker in key_markers if marker[0] < selected_x - 4.0),
        key=lambda marker: marker[0],
        reverse=True,
    )
    right_markers = sorted(
        (marker for marker in key_markers if marker[0] > selected_x + 4.0),
        key=lambda marker: marker[0],
    )
    assignments = []

    for offset, marker in enumerate(left_markers, 1):
        key_index = selected_index - offset
        if key_index < 0:
            break
        assignments.append((marker, key_index))

    for offset, marker in enumerate(right_markers, 1):
        key_index = selected_index + offset
        if key_index >= len(keys):
            break
        assignments.append((marker, key_index))

    horizontal_scales = []
    vertical_scales = []
    assignments_summary = []

    for marker, key_index in assignments:
        try:
            key_time = float(keys[key_index].Time.GetSecondDouble())
            key_value = float(keys[key_index].Value)
        except Exception:
            continue

        delta_time = key_time - selected_time
        delta_value = key_value - selected_value
        delta_x = float(marker[0]) - selected_x
        delta_y = float(marker[1]) - selected_y

        if abs(delta_time) > 0.000001 and abs(delta_x) > 1.0:
            horizontal_scales.append(abs(delta_x / delta_time))
        if abs(delta_value) > 0.000001 and abs(delta_y) > 1.0:
            vertical_scales.append(abs(delta_y / delta_value))

        assignments_summary.append(
            {
                "key_index": key_index,
                "marker": [marker[0], marker[1]],
                "time_seconds": key_time,
                "value": key_value,
            }
        )

    pixels_per_second = _median(horizontal_scales)
    pixels_per_value = _median(vertical_scales)

    scale_details.update(
        {
            "selected_center_image": [selected_x, selected_y],
            "selected_key_index": selected_index,
            "selected_time_seconds": selected_time,
            "selected_value": selected_value,
            "key_markers": [[marker[0], marker[1]] for marker in key_markers],
            "assignments": assignments_summary,
            "pixels_per_second": pixels_per_second,
            "pixels_per_value": pixels_per_value,
        }
    )

    if (
        pixels_per_second is None
        or pixels_per_value is None
        or pixels_per_second <= 0.000001
        or pixels_per_value <= 0.000001
    ):
        scale_details["reason"] = "insufficient_key_markers"
        return None

    derivative_scale = pixels_per_second / pixels_per_value
    scale_details["reason"] = "detected_from_key_markers"
    scale_details["derivative_per_screen_slope"] = derivative_scale
    return derivative_scale


def _fcurve_orbit_center(graph_widget, tangent_states):
    rect_x, rect_y, rect_width, rect_height = _qt_widget_rect(graph_widget)
    cursor = _cursor_qpoint()
    cursor_local_x = _clamp(float(cursor.x() - rect_x), 0.0, float(rect_width))
    cursor_local_y = _clamp(float(cursor.y() - rect_y), 0.0, float(rect_height))
    key_graph_data = _fcurve_selected_key_graph_data(
        graph_widget,
        tangent_states,
    )

    if key_graph_data is not None:
        local_x, local_y, derivative_scale = key_graph_data
    else:
        calculation_details = {}
        detected_center = _fcurve_snapshot_key_center(
            graph_widget,
            cursor_local_x,
            cursor_local_y,
            calculation_details,
        )

        if detected_center is None:
            local_x = cursor_local_x
            local_y = cursor_local_y
        else:
            local_x, local_y = detected_center

        derivative_scale = _fcurve_graph_derivative_scale(
            graph_widget,
            (local_x, local_y),
            tangent_states,
            calculation_details,
        )

    local_x = _clamp(float(local_x), 0.0, float(rect_width))
    local_y = _clamp(float(local_y), 0.0, float(rect_height))
    center = (rect_x + local_x, rect_y + local_y)
    return center, derivative_scale


def _rotated_fcurve_derivative(derivative, angle_degrees, derivative_scale=None):
    scale = float(derivative_scale or 1.0)
    if abs(scale) <= 0.000001:
        scale = 1.0

    angle = math.atan(float(derivative) / scale) + math.radians(float(angle_degrees))
    cosine = math.cos(angle)

    if abs(cosine) <= 0.000001:
        return math.copysign(FCURVE_MANUAL_DERIVATIVE_LIMIT, math.sin(angle))

    return _clamp(
        math.tan(angle) * scale,
        -FCURVE_MANUAL_DERIVATIVE_LIMIT,
        FCURVE_MANUAL_DERIVATIVE_LIMIT,
    )


def _set_fcurve_tangent_states_angle(
    tangent_states,
    angle_degrees,
    derivative_scale=None,
):
    for state in tangent_states:
        fcurve = state["curve"]
        index = state["index"]

        if not state["manual_prepared"]:
            fcurve.KeySetTangentMode(index, state["manual_tangent_mode"])
            fcurve.KeySetTangentBreak(
                index,
                state["manual_tangent_mode"] == FBTangentMode.kFBTangentModeBreak,
            )
            state["manual_prepared"] = True

        fcurve.KeySetLeftDerivative(
            index,
            _rotated_fcurve_derivative(
                state["original_left_derivative"],
                angle_degrees,
                derivative_scale,
            ),
        )
        fcurve.KeySetRightDerivative(
            index,
            _rotated_fcurve_derivative(
                state["original_right_derivative"],
                angle_degrees,
                derivative_scale,
            ),
        )


def _restore_fcurve_tangent_states(tangent_states):
    for state in tangent_states:
        fcurve = state["curve"]
        index = state["index"]
        fcurve.KeySetTangentMode(index, state["manual_tangent_mode"])
        fcurve.KeySetTangentBreak(index, state["original_tangent_break"])
        fcurve.KeySetLeftDerivative(index, state["original_left_derivative"])
        fcurve.KeySetRightDerivative(index, state["original_right_derivative"])
        fcurve.KeySetTangentMode(index, state["original_tangent_mode"])
        fcurve.KeySetTangentBreak(index, state["original_tangent_break"])
        state["manual_prepared"] = False


def _refresh_fcurve_widget(graph_widget):
    try:
        graph_widget.update()
    except Exception:
        pass


class RotationOverlayWidget(QtWidgets.QWidget):
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
        self.axis_line_global = None
        self.axis_line_color = None
        self.cursor_icon_pixmap = None
        self.cursor_icon_angle = 0.0
        self.cursor_icon_name = None
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
        axis_line_global=None,
        axis_line_color=None,
        cursor_icon_pixmap=None,
        cursor_icon_angle=0.0,
        cursor_icon_name=None,
        cursor_icon_scale=1.0,
    ):
        self.center_global = center_global
        self.cursor_global = cursor_global
        self.axis_line_global = axis_line_global
        self.axis_line_color = axis_line_color
        self.cursor_icon_pixmap = cursor_icon_pixmap
        self.cursor_icon_angle = cursor_icon_angle
        self.cursor_icon_name = cursor_icon_name
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

    def _draw_trackball_cursor_fallback(self, painter, cursor):
        if cursor is None or self.cursor_icon_name != TRACKBALL_CURSOR_ICON:
            return

        size = 44.0 * float(self.cursor_icon_scale or 1.0)
        arm = size * 0.42
        head = size * 0.18
        center_x = cursor.x()
        center_y = cursor.y()

        painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 190)))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 210), 1))
        painter.drawEllipse(QtCore.QPointF(center_x, center_y), size * 0.13, size * 0.13)

        arrows = [
            (QtGui.QColor(245, 45, 45, 255), -arm, 0.0, -head, 0.0),
            (QtGui.QColor(45, 245, 85, 255), arm, 0.0, head, 0.0),
            (QtGui.QColor(60, 145, 255, 255), 0.0, -arm, 0.0, -head),
            (QtGui.QColor(255, 220, 45, 255), 0.0, arm, 0.0, head),
        ]

        for color, end_x, end_y, base_x, base_y in arrows:
            pen = QtGui.QPen(color, max(3, int(size * 0.08)))
            pen.setCapStyle(_qt_pen_cap_style("RoundCap"))
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(center_x + base_x, center_y + base_y),
                QtCore.QPointF(center_x + end_x, center_y + end_y),
            )
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtGui.QPen(color, 1))

            if abs(end_x) > abs(end_y):
                direction = 1.0 if end_x > 0 else -1.0
                points = [
                    QtCore.QPointF(center_x + end_x, center_y + end_y),
                    QtCore.QPointF(center_x + end_x - (direction * head), center_y + end_y - head),
                    QtCore.QPointF(center_x + end_x - (direction * head), center_y + end_y + head),
                ]
            else:
                direction = 1.0 if end_y > 0 else -1.0
                points = [
                    QtCore.QPointF(center_x + end_x, center_y + end_y),
                    QtCore.QPointF(center_x + end_x - head, center_y + end_y - (direction * head)),
                    QtCore.QPointF(center_x + end_x + head, center_y + end_y - (direction * head)),
                ]

            painter.drawPolygon(QtGui.QPolygonF(points))

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

        center = self._local_point(self.center_global)
        cursor = self._local_point(self.cursor_global)

        if self.axis_line_global is not None and self.axis_line_color is not None:
            axis_center = self._local_point(self.axis_line_global[0])
            axis_point = self._local_point(self.axis_line_global[1])

            if axis_center is not None and axis_point is not None:
                dx = axis_point.x() - axis_center.x()
                dy = axis_point.y() - axis_center.y()
                length = math.sqrt((dx * dx) + (dy * dy))

                if length > 0.000001:
                    scale = max(self.width(), self.height()) * 1.5
                    dx = (dx / length) * scale
                    dy = (dy / length) * scale
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
                    painter.drawLine(
                        QtCore.QPointF(axis_center.x() - dx, axis_center.y() - dy),
                        QtCore.QPointF(axis_center.x() + dx, axis_center.y() + dy),
                    )

        if center is not None and cursor is not None:
            line_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 230))
            line_pen.setWidth(2)
            line_pen.setStyle(_qt_pen_style("DashLine"))
            painter.setPen(line_pen)
            painter.drawLine(center, cursor)

        cursor_icon_drawn = False

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
                cursor_icon_drawn = True
            except Exception:
                try:
                    painter.restore()
                except Exception:
                    pass

        if not cursor_icon_drawn:
            self._draw_trackball_cursor_fallback(painter, cursor)

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
        clip_z = (matrix_values[8] * x) + (matrix_values[9] * y) + (matrix_values[10] * z) + matrix_values[11]
        clip_w = (matrix_values[12] * x) + (matrix_values[13] * y) + (matrix_values[14] * z) + matrix_values[15]
    else:
        clip_x = (matrix_values[0] * x) + (matrix_values[4] * y) + (matrix_values[8] * z) + matrix_values[12]
        clip_y = (matrix_values[1] * x) + (matrix_values[5] * y) + (matrix_values[9] * z) + matrix_values[13]
        clip_z = (matrix_values[2] * x) + (matrix_values[6] * y) + (matrix_values[10] * z) + matrix_values[14]
        clip_w = (matrix_values[3] * x) + (matrix_values[7] * y) + (matrix_values[11] * z) + matrix_values[15]

    if abs(clip_w) <= 0.000001:
        return None

    return clip_x / clip_w, clip_y / clip_w, clip_z / clip_w


def _matrix_projection_candidate(point, rect, matrix_values, row_major):
    ndc = _project_point_with_matrix_values(point, matrix_values, row_major)

    if ndc is None:
        return None

    ndc_x, ndc_y, _ndc_z = ndc

    if not all(math.isfinite(value) for value in (ndc_x, ndc_y)):
        return None

    rect_x, rect_y, rect_width, rect_height = rect
    screen_x = rect_x + ((ndc_x + 1.0) * 0.5 * rect_width)
    screen_y = rect_y + ((1.0 - ndc_y) * 0.5 * rect_height)
    return screen_x, screen_y


def _inverse_projection_error(camera, point, rect, screen_point):
    try:
        rect_x, rect_y, _rect_width, _rect_height = rect
        camera_position = _world_translation(camera)
        distance = _length(_sub(point, camera_position))
        viewport_x = float(screen_point[0]) - float(rect_x)
        viewport_y = float(screen_point[1]) - float(rect_y)
        world = camera.InverseProjection(viewport_x, viewport_y, distance, True)
        projected_world = _vector_to_list(world)
        return _length(_sub(projected_world, point))
    except Exception:
        return None


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

    return _matrix_projection_candidate(
        point,
        rect,
        matrix_values,
        False,
    )


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


def _orbit_center_cursor(camera, model_states, view_right, view_up, view_depth):
    center = _camera_project_center(
        camera,
        model_states,
        view_right,
        view_up,
        view_depth,
    )

    if center is not None:
        return center

    print("%s: could not project selected center to the viewport; using cursor start as orbit center." % TOOL_NAME)
    return _cursor_position()


# Keep live rotation math in Python; pyfbsdk quaternion conversion crashed this host.
def _matrix_multiply(a, b):
    result = []

    for row in range(3):
        result_row = []
        for column in range(3):
            result_row.append(
                (a[row][0] * b[0][column])
                + (a[row][1] * b[1][column])
                + (a[row][2] * b[2][column])
            )
        result.append(result_row)

    return result


def _identity_matrix():
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _matrix_transpose(matrix):
    return [
        [matrix[0][0], matrix[1][0], matrix[2][0]],
        [matrix[0][1], matrix[1][1], matrix[2][1]],
        [matrix[0][2], matrix[1][2], matrix[2][2]],
    ]


def _zero_rotation():
    return [0.0, 0.0, 0.0]


def _rotation_matrix_x(angle_radians):
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)

    return [
        [1.0, 0.0, 0.0],
        [0.0, cosine, -sine],
        [0.0, sine, cosine],
    ]


def _rotation_matrix_y(angle_radians):
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)

    return [
        [cosine, 0.0, sine],
        [0.0, 1.0, 0.0],
        [-sine, 0.0, cosine],
    ]


def _rotation_matrix_z(angle_radians):
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)

    return [
        [cosine, -sine, 0.0],
        [sine, cosine, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _euler_xyz_to_matrix(rotation_degrees):
    rx, ry, rz = [math.radians(value) for value in rotation_degrees]

    return _matrix_multiply(
        _rotation_matrix_z(rz),
        _matrix_multiply(_rotation_matrix_y(ry), _rotation_matrix_x(rx)),
    )


def _axis_angle_to_matrix(axis, angle_degrees):
    axis = _normalize(axis, [1.0, 0.0, 0.0])
    x, y, z = axis
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    one_minus_cosine = 1.0 - cosine

    return [
        [
            cosine + (x * x * one_minus_cosine),
            (x * y * one_minus_cosine) - (z * sine),
            (x * z * one_minus_cosine) + (y * sine),
        ],
        [
            (y * x * one_minus_cosine) + (z * sine),
            cosine + (y * y * one_minus_cosine),
            (y * z * one_minus_cosine) - (x * sine),
        ],
        [
            (z * x * one_minus_cosine) - (y * sine),
            (z * y * one_minus_cosine) + (x * sine),
            cosine + (z * z * one_minus_cosine),
        ],
    ]


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _matrix_to_euler_xyz(matrix):
    y = math.asin(_clamp(-matrix[2][0], -1.0, 1.0))
    cy = math.cos(y)

    if abs(cy) > 0.000001:
        x = math.atan2(matrix[2][1], matrix[2][2])
        z = math.atan2(matrix[1][0], matrix[0][0])
    else:
        x = 0.0
        z = math.atan2(-matrix[0][1], matrix[1][1])

    return [math.degrees(x), math.degrees(y), math.degrees(z)]


def _rotated_rotation(original_rotation, axis, angle_degrees):
    delta_matrix = _axis_angle_to_matrix(axis, angle_degrees)
    original_matrix = _euler_xyz_to_matrix(original_rotation)
    result_matrix = _matrix_multiply(delta_matrix, original_matrix)
    return _matrix_to_euler_xyz(result_matrix)


def _locally_rotated_rotation(original_rotation, axis, angle_degrees):
    delta_matrix = _axis_angle_to_matrix(axis, angle_degrees)
    original_matrix = _euler_xyz_to_matrix(original_rotation)
    result_matrix = _matrix_multiply(original_matrix, delta_matrix)
    return _matrix_to_euler_xyz(result_matrix)


def _fbmatrix_from_values(values):
    matrix = FBMatrix()

    for index in range(16):
        try:
            matrix[index] = float(values[index])
        except Exception:
            matrix[index] = 1.0 if index in (0, 5, 10, 15) else 0.0

    return matrix


def _fbmatrix_from_matrix3(matrix3):
    matrix = FBMatrix()

    for index in range(16):
        matrix[index] = 0.0

    matrix[15] = 1.0

    for row in range(3):
        for column in range(3):
            matrix[(column * 4) + row] = float(matrix3[row][column])

    return matrix


def _fbmatrix_from_axis_angle(axis, angle_degrees):
    return _fbmatrix_from_matrix3(_axis_angle_to_matrix(axis, angle_degrees))


def _model_global_rotation_matrix_values(model):
    matrix = FBMatrix()
    model.GetMatrix(matrix, FBModelTransformationType.kModelRotation, True)
    return _fbmatrix_values(matrix)


def _global_rotation_matrix_key(rotation_key):
    if rotation_key.endswith("_rotation"):
        return rotation_key[:-len("_rotation")] + "_global_rotation_matrix"

    return rotation_key + "_global_rotation_matrix"


def _model_hierarchy_depth(model):
    depth = 0
    visited = set()
    parent = _model_parent(model)

    while parent is not None:
        parent_id = id(parent)

        if parent_id in visited:
            break

        visited.add(parent_id)
        depth += 1
        parent = _model_parent(parent)

    return depth


def _model_states_parent_first(model_states):
    return sorted(
        model_states,
        key=lambda state: _model_hierarchy_depth(state.get("model")),
    )


def _target_global_rotation_matrix(base_global_rotation_matrix, axis, angle_degrees):
    delta_matrix = _fbmatrix_from_axis_angle(axis, angle_degrees)
    base_matrix = _fbmatrix_from_values(base_global_rotation_matrix)
    target_matrix = FBMatrix()
    FBMatrixMult(target_matrix, delta_matrix, base_matrix)
    return target_matrix


def _effective_local_rotation_matrix(rotation, pre_rotation=None, post_rotation=None):
    pre_matrix = _euler_xyz_to_matrix(pre_rotation or _zero_rotation())
    rotation_matrix = _euler_xyz_to_matrix(rotation)
    post_matrix = _euler_xyz_to_matrix(post_rotation or _zero_rotation())
    return _matrix_multiply(
        pre_matrix,
        _matrix_multiply(rotation_matrix, post_matrix),
    )


def _channel_rotation_from_effective_local_matrix(
    local_matrix,
    pre_rotation=None,
    post_rotation=None,
):
    pre_matrix = _euler_xyz_to_matrix(pre_rotation or _zero_rotation())
    post_matrix = _euler_xyz_to_matrix(post_rotation or _zero_rotation())
    channel_matrix = _matrix_multiply(
        _matrix_transpose(pre_matrix),
        _matrix_multiply(local_matrix, _matrix_transpose(post_matrix)),
    )
    return _matrix_to_euler_xyz(channel_matrix)


def _parent_compensated_global_rotation(
    original_rotation,
    parent_world_rotation,
    axis,
    angle_degrees,
    pre_rotation=None,
    post_rotation=None,
):
    delta_matrix = _axis_angle_to_matrix(axis, angle_degrees)
    original_local_matrix = _effective_local_rotation_matrix(
        original_rotation,
        pre_rotation,
        post_rotation,
    )
    original_world_matrix = _matrix_multiply(parent_world_rotation, original_local_matrix)
    result_world_matrix = _matrix_multiply(delta_matrix, original_world_matrix)
    result_local_matrix = _matrix_multiply(
        _matrix_transpose(parent_world_rotation),
        result_world_matrix,
    )
    return _channel_rotation_from_effective_local_matrix(
        result_local_matrix,
        pre_rotation,
        post_rotation,
    )


def _model_parent(model):
    try:
        return model.Parent
    except Exception:
        return None


def _state_by_model_id(model_states):
    return {
        id(state["model"]): state
        for state in model_states
        if state.get("model") is not None
    }


def _model_rotation_values(model, model_state_by_id, rotation_key):
    state = model_state_by_id.get(id(model))

    if state is not None:
        return state[rotation_key]

    try:
        return _vector_to_list(model.Rotation)
    except Exception:
        return [0.0, 0.0, 0.0]


def _model_pre_rotation_values(model, model_state_by_id=None):
    state = None

    if model_state_by_id is not None:
        state = model_state_by_id.get(id(model))

    if state is not None:
        return state.get("pre_rotation", _zero_rotation())

    try:
        return _vector_to_list(model.PreRotation)
    except Exception:
        return _zero_rotation()


def _model_post_rotation_values(model, model_state_by_id=None):
    state = None

    if model_state_by_id is not None:
        state = model_state_by_id.get(id(model))

    if state is not None:
        return state.get("post_rotation", _zero_rotation())

    try:
        return _vector_to_list(model.PostRotation)
    except Exception:
        return _zero_rotation()


def _model_world_rotation_matrix(model, model_state_by_id, rotation_key, visited=None):
    if model is None:
        return _identity_matrix()

    if visited is None:
        visited = set()

    model_id = id(model)

    if model_id in visited:
        return _identity_matrix()

    visited.add(model_id)
    parent = _model_parent(model)
    parent_world = _model_world_rotation_matrix(
        parent,
        model_state_by_id,
        rotation_key,
        visited,
    )
    local_rotation = _model_rotation_values(model, model_state_by_id, rotation_key)
    local_matrix = _effective_local_rotation_matrix(
        local_rotation,
        _model_pre_rotation_values(model, model_state_by_id),
        _model_post_rotation_values(model, model_state_by_id),
    )
    return _matrix_multiply(parent_world, local_matrix)


def _model_parent_world_rotation_matrix(model, model_state_by_id, rotation_key):
    return _model_world_rotation_matrix(
        _model_parent(model),
        model_state_by_id,
        rotation_key,
    )


def _set_model_states_to_axis_angle(model_states, axis, angle_degrees, rotation_key):
    global_matrix_key = _global_rotation_matrix_key(rotation_key)

    for state in _model_states_parent_first(model_states):
        base_global_rotation_matrix = state.get(global_matrix_key)

        if base_global_rotation_matrix is None:
            base_global_rotation_matrix = _model_global_rotation_matrix_values(state["model"])
            state[global_matrix_key] = base_global_rotation_matrix

        target_matrix = _target_global_rotation_matrix(
            base_global_rotation_matrix,
            axis,
            angle_degrees,
        )
        state["model"].SetMatrix(
            target_matrix,
            FBModelTransformationType.kModelRotation,
            True,
        )


def _set_model_states_to_axis_lock_angle(
    model_states,
    axis_lock,
    axis_space,
    angle_degrees,
    rotation_key,
):
    axis = _axis_lock_vector(axis_lock)

    for state in _model_states_parent_first(model_states):
        if axis_space == AXIS_SPACE_LOCAL:
            rotation = _locally_rotated_rotation(
                state[rotation_key],
                axis,
                angle_degrees,
            )
            state["model"].Rotation = _copy_vector3d(rotation)
        else:
            global_matrix_key = _global_rotation_matrix_key(rotation_key)
            base_global_rotation_matrix = state.get(global_matrix_key)

            if base_global_rotation_matrix is None:
                base_global_rotation_matrix = _model_global_rotation_matrix_values(state["model"])
                state[global_matrix_key] = base_global_rotation_matrix

            target_matrix = _target_global_rotation_matrix(
                base_global_rotation_matrix,
                axis,
                angle_degrees,
            )
            state["model"].SetMatrix(
                target_matrix,
                FBModelTransformationType.kModelRotation,
                True,
            )


def _capture_model_state_base_rotations(model_states):
    for state in model_states:
        state["mode_base_rotation"] = _vector_to_list(state["model"].Rotation)
        state["mode_base_global_rotation_matrix"] = _model_global_rotation_matrix_values(state["model"])


def _restore_model_state_rotations(model_states):
    for state in model_states:
        state["model"].Rotation = _copy_vector3d(state["original_rotation"])


def _precision_multiplier(shift_down):
    if shift_down:
        return PRECISION_MULTIPLIER
    return 1.0


def _snap_degrees_to_ten(angle_degrees):
    if angle_degrees >= 0.0:
        return math.floor((angle_degrees / 10.0) + 0.5) * 10.0

    return math.ceil((angle_degrees / 10.0) - 0.5) * 10.0


def _trackball_axis_angle(start_cursor, cursor, view_right, view_up, precision_multiplier):
    axis_vector = _trackball_rotation_vector(
        start_cursor,
        cursor,
        view_right,
        view_up,
        precision_multiplier,
    )
    angle_radians = _length(axis_vector)

    if angle_radians <= 0.000001:
        return [1.0, 0.0, 0.0], 0.0

    return _normalize(axis_vector, [1.0, 0.0, 0.0]), math.degrees(angle_radians)


def _trackball_rotation_vector(start_cursor, cursor, view_right, view_up, precision_multiplier):
    start_x, start_y = start_cursor
    cursor_x, cursor_y = cursor
    factor = TRACKBALL_FACTOR * precision_multiplier
    phi_x = float(cursor_y - start_y) * factor
    phi_y = float(cursor_x - start_x) * factor
    return _add(
        _mul(view_right, phi_x),
        _mul(view_up, phi_y),
    )


def _axis_lock_vector(axis_lock):
    if axis_lock == AXIS_LOCK_X:
        return [1.0, 0.0, 0.0]

    if axis_lock == AXIS_LOCK_Y:
        return [0.0, 1.0, 0.0]

    return [0.0, 0.0, 1.0]


def _axis_lock_color(axis_lock):
    if axis_lock == AXIS_LOCK_X:
        return 235, 55, 55, 230

    if axis_lock == AXIS_LOCK_Y:
        return 70, 210, 85, 230

    return 70, 135, 255, 230


def _matrix_transform_vector(matrix, vector):
    return [
        (matrix[0][0] * vector[0]) + (matrix[0][1] * vector[1]) + (matrix[0][2] * vector[2]),
        (matrix[1][0] * vector[0]) + (matrix[1][1] * vector[1]) + (matrix[1][2] * vector[2]),
        (matrix[2][0] * vector[0]) + (matrix[2][1] * vector[1]) + (matrix[2][2] * vector[2]),
    ]


def _axis_lock_projection_vector(model_states, axis_lock, axis_space, rotation_key):
    axis = _axis_lock_vector(axis_lock)

    if axis_space != AXIS_SPACE_LOCAL or not model_states:
        return axis

    state = model_states[0]
    model_state_by_id = _state_by_model_id(model_states)
    parent_world_rotation = _model_parent_world_rotation_matrix(
        state["model"],
        model_state_by_id,
        rotation_key,
    )
    matrix = _matrix_multiply(
        parent_world_rotation,
        _euler_xyz_to_matrix(state[rotation_key]),
    )
    return _normalize(_matrix_transform_vector(matrix, axis), axis)


def _axis_lock_overlay_line(
    camera,
    viewport_rect,
    center_cursor,
    model_states,
    axis_lock,
    axis_space,
    rotation_key,
):
    if camera is None or viewport_rect is None or center_cursor is None or axis_lock is None:
        return None, None

    try:
        center_world = _selection_center(model_states)
        axis = _axis_lock_projection_vector(
            model_states,
            axis_lock,
            axis_space,
            rotation_key,
        )
        axis = _normalize(axis, _axis_lock_vector(axis_lock))
        camera_position = _world_translation(camera)
        camera_distance = _length(_sub(center_world, camera_position))
        base_scale = max(camera_distance * 0.25, 1.0)

        for scale_factor in (0.25, 1.0, 4.0, 16.0, 64.0, 256.0):
            scale = base_scale * scale_factor

            for direction in (1.0, -1.0):
                endpoint_world = _add(center_world, _mul(axis, scale * direction))
                endpoint_screen = _camera_project_point_matrix(
                    camera,
                    endpoint_world,
                    viewport_rect,
                )

                if endpoint_screen is None:
                    continue

                screen_delta = _sub(
                    [endpoint_screen[0], endpoint_screen[1], 0.0],
                    [center_cursor[0], center_cursor[1], 0.0],
                )

                if _length(screen_delta) >= AXIS_LINE_MIN_SCREEN_LENGTH:
                    return (center_cursor, endpoint_screen), _axis_lock_color(axis_lock)
    except Exception:
        pass

    return None, None


def _trackball_axis_lock_angle(
    start_cursor,
    cursor,
    view_right,
    view_up,
    precision_multiplier,
    projection_axis,
):
    rotation_vector = _trackball_rotation_vector(
        start_cursor,
        cursor,
        view_right,
        view_up,
        precision_multiplier,
    )
    return math.degrees(_dot(rotation_vector, projection_axis))


class MouseOrbitAngleController(QtCore.QObject):
    def __init__(
        self,
        model_states,
        orbit_axis,
        orbit_center,
        view_right,
        view_up,
        viewport_rect=None,
        camera=None,
    ):
        QtCore.QObject.__init__(self)
        self.session_id = int(time.time() * 1000.0)
        self.model_states = model_states
        self.orbit_axis = orbit_axis
        self.center_cursor = orbit_center
        self.view_right = view_right
        self.view_up = view_up
        self.viewport_rect = viewport_rect
        self.camera = camera
        self.overlay = None
        self.cursor_pixmaps = {}
        self.last_cursor_icon = None
        self.custom_cursor_active = False
        self.last_cursor_rotation_angle = None
        self.mode = MODE_ORBIT
        self.axis_lock = None
        self.axis_lock_space = None
        self.used_trackball = False
        self.precision_multiplier = 1.0
        self.trackball_start_cursor = _cursor_position()
        self.last_orbit_angle = None
        self.orbit_angle = 0.0
        self.last_preview_signature = None
        self.last_applied_angle = 0.0
        self.last_applied_snapped = False
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
        self.ignore_r_until_release = False
        self.last_toggle_time = 0.0
        self.last_logged_input_state = None
        self.error_text = None
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_return_down = _is_key_down(VK_RETURN)
        self.was_r_down = _is_key_down(VK_R)
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
        self._log_event("start")
        return True

    def run(self):
        return self.start()

    def _show_overlay(self):
        if self.viewport_rect is None:
            return

        try:
            cursor_position = _cursor_position()
            _cursor_icon, cursor_pixmap, cursor_angle = self._cursor_visual(cursor_position)
            self.overlay = RotationOverlayWidget(self.viewport_rect)
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(self.last_applied_angle),
                None,
                None,
                cursor_pixmap,
                cursor_angle,
                _cursor_icon,
                self._cursor_scale_for_mode(),
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

    def _cursor_icon_for_mode(self):
        if self.mode == MODE_TRACKBALL:
            return TRACKBALL_CURSOR_ICON

        return ROTATION_CURSOR_ICON

    def _cursor_angle_for_mode(self, cursor_position):
        if self.mode == MODE_TRACKBALL:
            return 0.0

        angle = self._cursor_rotation_angle(cursor_position)

        if angle is None:
            return 0.0

        return angle

    def _cursor_scale_for_mode(self):
        if self.mode == MODE_TRACKBALL:
            return TRACKBALL_CURSOR_SCALE

        return 1.0

    def _cursor_pixmap_for_icon(self, relative_icon_path):
        pixmap = self.cursor_pixmaps.get(relative_icon_path)

        if pixmap is None:
            pixmap = _load_cursor_pixmap(relative_icon_path)
            self.cursor_pixmaps[relative_icon_path] = pixmap

        return pixmap

    def _cursor_visual(self, cursor_position):
        relative_icon_path = self._cursor_icon_for_mode()
        return (
            relative_icon_path,
            self._cursor_pixmap_for_icon(relative_icon_path),
            self._cursor_angle_for_mode(cursor_position),
        )

    def _update_custom_cursor(self, cursor_position=None, force=False):
        app = QtWidgets.QApplication.instance()

        if app is None:
            return

        if cursor_position is None:
            cursor_position = _cursor_position()

        relative_icon_path, _pixmap, angle = self._cursor_visual(cursor_position)

        log_cursor_change = force or self.last_cursor_icon != relative_icon_path

        if log_cursor_change:
            self._log_event(
                "cursor_icon",
                icon=relative_icon_path,
                resolved_path=_cursor_icon_path(relative_icon_path),
                pixmap_loaded=_pixmap is not None,
                pixmap_width=_pixmap.width() if _pixmap is not None else 0,
                pixmap_height=_pixmap.height() if _pixmap is not None else 0,
                angle=round(angle, 3),
                force=force,
            )

        try:
            if self.mode == MODE_TRACKBALL:
                cursor = _cursor_from_pixmap(_pixmap, angle, self._cursor_scale_for_mode())
                cursor_shape = "pixmap"
            else:
                cursor = None
                cursor_shape = "blank"

            if cursor is None:
                _hide_windows_cursor_once()
                cursor = QtGui.QCursor(_qt_cursor_shape("BlankCursor"))
                cursor_shape = "blank"

            override_cursor = _qt_override_cursor(app)
            should_update_cursor = (
                force
                or not self.custom_cursor_active
                or override_cursor is None
                or self.last_cursor_icon != relative_icon_path
            )

            if should_update_cursor:
                if self.custom_cursor_active and override_cursor is not None:
                    app.changeOverrideCursor(cursor)
                else:
                    app.setOverrideCursor(cursor)
                    self.custom_cursor_active = True

            if log_cursor_change:
                self._log_event(
                    "cursor_override",
                    icon=relative_icon_path,
                    shape=cursor_shape,
                    angle=round(angle, 3),
                    scale=round(self._cursor_scale_for_mode(), 3),
                    updated=should_update_cursor,
                )

            self.last_cursor_icon = relative_icon_path
            self.last_cursor_rotation_angle = angle
        except Exception:
            pass

    def _restore_custom_cursor(self):
        app = QtWidgets.QApplication.instance()
        restored_overrides = 0

        if app is not None:
            for _index in range(CURSOR_RESTORE_LIMIT):
                if _qt_override_cursor(app) is None:
                    break

                try:
                    app.restoreOverrideCursor()
                    restored_overrides += 1
                except Exception:
                    break

        self._log_event(
            "cursor_restored",
            restored_overrides=restored_overrides,
            app_present=app is not None,
        )
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

        # Keep the application filter alive until all queued events from the
        # finishing mouse gesture have been consumed.
        if self.event_filter_installed and app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
            self.event_filter_installed = False

    def _report_result(self):
        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")

        if not self.accepted:
            print("%s canceled. Original rotation restored." % TOOL_NAME)
            return

        applied_angle = self.last_applied_angle

        if (
            not self.used_trackball
            and self.mode == MODE_ORBIT
            and abs(applied_angle) <= ANGLE_EPSILON
        ):
            print("%s accepted at 0 degrees. No rotation applied." % TOOL_NAME)
            return

        if self.used_trackball:
            print("%s applied rotation with trackball mode." % TOOL_NAME)
        else:
            print("%s applied %.3f degrees." % (TOOL_NAME, applied_angle))

    def _status_text(self, angle):
        if self.mode == MODE_TRACKBALL:
            label = "Trackball"
        else:
            label = "Rotation"

        text = "%s %.3f deg" % (label, angle)

        if self.axis_lock is not None:
            axis_space = self.axis_lock_space or AXIS_SPACE_GLOBAL
            text += " along %s %s" % (axis_space, self.axis_lock.upper())

        return text

    def _update_overlay(self, cursor_position=None, angle=None):
        if cursor_position is None:
            cursor_position = _cursor_position()

        self._update_custom_cursor(cursor_position)

        if self.overlay is None:
            return

        if angle is None:
            angle = self.last_applied_angle

        try:
            axis_line_global = None
            axis_line_color = None
            _cursor_icon, cursor_pixmap, cursor_angle = self._cursor_visual(cursor_position)

            if self.axis_lock is not None:
                axis_space = self.axis_lock_space or AXIS_SPACE_GLOBAL
                axis_line_global, axis_line_color = _axis_lock_overlay_line(
                    self.camera,
                    self.viewport_rect,
                    self.center_cursor,
                    self.model_states,
                    self.axis_lock,
                    axis_space,
                    "mode_base_rotation",
                )

            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(angle),
                axis_line_global,
                axis_line_color,
                cursor_pixmap,
                cursor_angle,
                _cursor_icon,
                self._cursor_scale_for_mode(),
            )
        except Exception:
            pass

    def _log_event(self, event, **values):
        return

    def _log_input_state(
        self,
        left_down,
        right_down,
        escape_down,
        return_down,
        r_down,
        shift_down,
        ctrl_down,
        x_down,
        y_down,
        z_down,
    ):
        signature = (
            left_down,
            right_down,
            escape_down,
            return_down,
            r_down,
            shift_down,
            ctrl_down,
            x_down,
            y_down,
            z_down,
            self.mode,
            self.axis_lock,
            self.axis_lock_space,
            self.armed,
            self.ignore_r_until_release,
        )

        if signature == self.last_logged_input_state:
            return

        self.last_logged_input_state = signature
        self._log_event(
            "input_state",
            left_down=left_down,
            right_down=right_down,
            escape_down=escape_down,
            return_down=return_down,
            r_down=r_down,
            shift_down=shift_down,
            ctrl_down=ctrl_down,
            x_down=x_down,
            y_down=y_down,
            z_down=z_down,
        )

    def _begin_mouse_finish(self, accepted, vk_code, source):
        if self.finished or self.pending_finish is not None:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = _cursor_position()
        self.pending_finish_scheduled = False
        self._log_event(
            "mouse_finish_armed",
            accepted=accepted,
            vk_code=vk_code,
            source=source,
            cursor=self.pending_finish_cursor,
        )

    def _schedule_mouse_finish(self):
        if (
            self.finished
            or self.pending_finish is None
            or self.pending_finish_scheduled
        ):
            return

        self.pending_finish_scheduled = True
        try:
            QtCore.QTimer.singleShot(
                MOUSE_FINISH_RELEASE_DELAY_MS,
                self._complete_mouse_finish,
            )
        except Exception:
            self._complete_mouse_finish()

    def _complete_mouse_finish(self):
        if self.finished or self.pending_finish is None:
            return

        accepted = self.pending_finish
        cursor_position = self.pending_finish_cursor
        self.pending_finish_scheduled = False
        self._log_event(
            "mouse_finish_complete",
            accepted=accepted,
            cursor=cursor_position,
        )
        self._finish(accepted, cursor_position)

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()
            event_types = QtCore.QEvent.Type if hasattr(QtCore.QEvent, "Type") else QtCore.QEvent
            mouse_press_type = event_types.MouseButtonPress
            mouse_double_click_type = event_types.MouseButtonDblClick
            mouse_release_type = event_types.MouseButtonRelease
            context_menu_type = event_types.ContextMenu

            # Qt often posts this after RMB release. Consume it while the
            # gesture guard is active, even if the controller is about to end.
            if self.pending_finish is False and event_type == context_menu_type:
                return True

            if not self.armed or self.finished:
                return False

            if hasattr(QtCore.Qt, "MouseButton"):
                left_button = QtCore.Qt.MouseButton.LeftButton
                right_button = QtCore.Qt.MouseButton.RightButton
            else:
                left_button = QtCore.Qt.LeftButton
                right_button = QtCore.Qt.RightButton

            if event_type in (mouse_press_type, mouse_double_click_type):
                button = event.button()

                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON, "qt_press")
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON, "qt_press")
                    return True

            if self.pending_finish is not None:
                if event_type == mouse_release_type:
                    button = event.button()
                    if button in (left_button, right_button):
                        if button == (
                            left_button
                            if self.pending_finish_vk_code == VK_LBUTTON
                            else right_button
                        ):
                            self._schedule_mouse_finish()
                        return True

                if event_type in (mouse_press_type, mouse_double_click_type):
                    button = event.button()
                    if button in (left_button, right_button):
                        return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._begin_mouse_finish(False, VK_RBUTTON, "event_filter_error")
            self._schedule_mouse_finish()

        return False

    def _update_angle_from_cursor(self, cursor_position):
        orbit_angle = _angle_from_center(self.center_cursor, cursor_position)

        if orbit_angle is None:
            return

        if self.last_orbit_angle is None:
            self.last_orbit_angle = orbit_angle
            return

        self.orbit_angle += (
            _wrapped_angle_delta(orbit_angle, self.last_orbit_angle)
            * self.precision_multiplier
        )
        self.last_orbit_angle = orbit_angle

    def _set_key_states(
        self,
        left_down,
        right_down,
        escape_down,
        return_down,
        r_down,
        x_down,
        y_down,
        z_down,
    ):
        self.was_left_down = left_down
        self.was_right_down = right_down
        self.was_escape_down = escape_down
        self.was_return_down = return_down
        self.was_r_down = r_down
        self.was_x_down = x_down
        self.was_y_down = y_down
        self.was_z_down = z_down

    def _switch_rotation_mode(self, cursor_position):
        _capture_model_state_base_rotations(self.model_states)
        self.last_preview_signature = None

        if self.mode == MODE_ORBIT:
            self.mode = MODE_TRACKBALL
            self.used_trackball = True
            self.trackball_start_cursor = cursor_position
        else:
            self.mode = MODE_ORBIT
            self.orbit_angle = 0.0
            self.last_orbit_angle = _angle_from_center(self.center_cursor, cursor_position)

        cursor_icon, cursor_pixmap, cursor_angle = self._cursor_visual(cursor_position)
        self._log_event(
            "mode_switched",
            new_mode=self.mode,
            cursor_icon=cursor_icon,
            cursor_pixmap_loaded=cursor_pixmap is not None,
            cursor_angle=round(cursor_angle, 3),
        )
        self._update_custom_cursor(cursor_position, force=True)
        self._preview_current_transform(force=True)

        if self.overlay is not None:
            try:
                self.overlay.repaint()
            except Exception:
                pass

    def _set_axis_lock(self, axis_lock):
        previous_axis_lock = self.axis_lock
        previous_axis_lock_space = self.axis_lock_space

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
        self._log_event(
            "axis_lock_changed",
            previous_axis_lock=previous_axis_lock,
            previous_axis_lock_space=previous_axis_lock_space,
            new_axis_lock=axis_lock,
            new_axis_lock_space=axis_lock_space,
        )
        self._preview_current_transform(force=True)

    def _clear_axis_lock(self, source, cursor_position=None):
        if self.axis_lock is None:
            return False

        if cursor_position is None:
            cursor_position = _cursor_position()

        previous_axis_lock = self.axis_lock
        previous_axis_lock_space = self.axis_lock_space
        _capture_model_state_base_rotations(self.model_states)
        self.axis_lock = None
        self.axis_lock_space = None
        self.last_preview_signature = None

        if self.mode == MODE_TRACKBALL:
            self.trackball_start_cursor = cursor_position
        else:
            self.orbit_angle = 0.0
            self.last_orbit_angle = _angle_from_center(self.center_cursor, cursor_position)

        self._log_event(
            "axis_lock_cleared",
            source=source,
            previous_axis_lock=previous_axis_lock,
            previous_axis_lock_space=previous_axis_lock_space,
        )
        r_down_now = _is_key_down(VK_R)
        self.was_r_down = r_down_now
        self.ignore_r_until_release = r_down_now
        self.last_toggle_time = time.time()
        self._preview_current_transform(force=True)
        return True

    def _toggle_rotation_mode(self, source, cursor_position=None):
        if self.finished:
            return False

        if cursor_position is None:
            cursor_position = _cursor_position()

        if self._clear_axis_lock(source, cursor_position):
            return True

        now = time.time()
        r_down_now = _is_key_down(VK_R)

        if (now - self.last_toggle_time) < TOGGLE_DEBOUNCE_SECONDS:
            self._log_event(
                "toggle_ignored",
                source=source,
                reason="debounce",
                r_down=r_down_now,
            )
            return True

        if source == "external" and self.ignore_r_until_release and r_down_now and self.was_r_down:
            self._log_event(
                "toggle_ignored",
                source=source,
                reason="same_key_hold",
                r_down=r_down_now,
            )
            return True

        previous_mode = self.mode
        self._switch_rotation_mode(cursor_position)
        self.last_toggle_time = now
        self.was_r_down = r_down_now
        self.ignore_r_until_release = r_down_now
        self._log_event(
            "toggle_applied",
            source=source,
            previous_mode=previous_mode,
            r_down=r_down_now,
        )
        return True

    def request_mode_toggle(self):
        return self._toggle_rotation_mode("external")

    def _update_precision_mode(self, shift_down, cursor_position):
        precision_multiplier = _precision_multiplier(shift_down)

        if abs(precision_multiplier - self.precision_multiplier) <= 0.000001:
            return

        if self.mode == MODE_TRACKBALL:
            self._preview_current_transform(force=True)
            _capture_model_state_base_rotations(self.model_states)
            self.trackball_start_cursor = cursor_position
            self.last_preview_signature = None

        self.precision_multiplier = precision_multiplier

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
            self._log_event(
                "numeric_input_changed",
                previous_text=previous_text,
                new_text=self.numeric_input_text,
                value=self._numeric_input_value(),
            )

    def _update_numeric_input(self):
        changed = False

        for vk_code, value in NUMERIC_INPUT_KEYS:
            down = _is_key_down(vk_code)

            if down and not self.was_numeric_key_down.get(vk_code, False):
                self._append_numeric_input(value)
                changed = True

            self.was_numeric_key_down[vk_code] = down

        return changed

    def _effective_angle(self, angle):
        if self.numeric_input_active:
            return self._numeric_input_value(), False

        snap_to_ten = _is_key_down(VK_CONTROL)

        if snap_to_ten:
            return _snap_degrees_to_ten(angle), True

        return angle, False

    def _preview_current_transform(self, force=False, cursor_position=None):
        if cursor_position is None:
            cursor_position = _cursor_position()

        if self.axis_lock is not None:
            axis_space = self.axis_lock_space or AXIS_SPACE_GLOBAL

            if self.mode == MODE_TRACKBALL:
                projection_axis = _axis_lock_projection_vector(
                    self.model_states,
                    self.axis_lock,
                    axis_space,
                    "mode_base_rotation",
                )
                angle = _trackball_axis_lock_angle(
                    self.trackball_start_cursor,
                    cursor_position,
                    self.view_right,
                    self.view_up,
                    self.precision_multiplier,
                    projection_axis,
                )
                signature = (
                    self.mode,
                    self.axis_lock,
                    axis_space,
                    cursor_position[0],
                    cursor_position[1],
                    self.precision_multiplier,
                )
            else:
                angle = self.orbit_angle
                signature = (
                    self.mode,
                    self.axis_lock,
                    axis_space,
                    int(round(self.orbit_angle / PREVIEW_ANGLE_EPSILON)),
                )

            angle, snap_to_ten = self._effective_angle(angle)
            signature = signature + (snap_to_ten, angle)

            if not force and self.last_preview_signature == signature:
                self._update_overlay(cursor_position, angle)
                return

            _set_model_states_to_axis_lock_angle(
                self.model_states,
                self.axis_lock,
                axis_space,
                angle,
                "mode_base_rotation",
            )
            self.last_applied_angle = angle
            self.last_applied_snapped = snap_to_ten
            self.last_preview_signature = signature
            self._update_overlay(cursor_position, angle)
            return

        if self.mode == MODE_TRACKBALL:
            axis, angle = _trackball_axis_angle(
                self.trackball_start_cursor,
                cursor_position,
                self.view_right,
                self.view_up,
                self.precision_multiplier,
            )
            angle, snap_to_ten = self._effective_angle(angle)
            signature = (
                self.mode,
                cursor_position[0],
                cursor_position[1],
                self.precision_multiplier,
                snap_to_ten,
                angle,
            )
        else:
            axis = self.orbit_axis
            angle, snap_to_ten = self._effective_angle(self.orbit_angle)
            signature = (
                self.mode,
                snap_to_ten,
                int(round(angle / PREVIEW_ANGLE_EPSILON)),
            )

        if not force and self.last_preview_signature == signature:
            self._update_overlay(cursor_position, angle)
            return

        _set_model_states_to_axis_angle(
            self.model_states,
            axis,
            angle,
            "mode_base_rotation",
        )
        self.last_applied_angle = angle
        self.last_applied_snapped = snap_to_ten
        self.last_preview_signature = signature
        self._update_overlay(cursor_position, angle)

    def _restore_original_rotations(self):
        _restore_model_state_rotations(self.model_states)
        self.last_preview_signature = None

    def _finish(self, accepted, finish_cursor_position=None):
        if self.finished:
            return

        self._log_event("finish", accepted=accepted)
        self.accepted = accepted
        self.finished = True

        if accepted:
            try:
                self._preview_current_transform(
                    force=True,
                    cursor_position=finish_cursor_position,
                )
            except Exception:
                self.accepted = False
                if not self.error_text:
                    self.error_text = traceback.format_exc()
                try:
                    self._restore_original_rotations()
                except Exception:
                    pass
        else:
            try:
                self._restore_original_rotations()
            except Exception:
                if not self.error_text:
                    self.error_text = traceback.format_exc()

        self._stop_interaction()
        _clear_active_controller(self)
        self._report_result()

    def _tick(self):
        try:
            if self.pending_finish is not None:
                if (
                    self.pending_finish_vk_code is None
                    or not _is_key_down(self.pending_finish_vk_code)
                ):
                    self._schedule_mouse_finish()
                return

            left_down, left_pressed = _mouse_button_state(VK_LBUTTON, "LeftButton")
            right_down, right_pressed = _mouse_button_state(VK_RBUTTON, "RightButton")
            escape_down, escape_pressed = _key_state(VK_ESCAPE)
            return_down, return_pressed = _key_state(VK_RETURN)
            r_down, r_pressed = _key_state(VK_R)
            shift_down, _shift_pressed = _key_state(VK_SHIFT)
            ctrl_down, _ctrl_pressed = _key_state(VK_CONTROL)
            x_down, _x_pressed = _key_state(VK_X)
            y_down, _y_pressed = _key_state(VK_Y)
            z_down, _z_pressed = _key_state(VK_Z)
            self._log_input_state(
                left_down,
                right_down,
                escape_down,
                return_down,
                r_down,
                shift_down,
                ctrl_down,
                x_down,
                y_down,
                z_down,
            )
            self._update_custom_cursor(_cursor_position())

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self._log_event("armed")
                    _capture_model_state_base_rotations(self.model_states)
                    self.last_orbit_angle = _angle_from_center(
                        self.center_cursor,
                        _cursor_position(),
                    )
                    self._set_key_states(
                        False,
                        False,
                        escape_down,
                        return_down,
                        r_down,
                        x_down,
                        y_down,
                        z_down,
                    )
                    self._preview_current_transform(force=True)
                return

            cancel_pressed = escape_down or escape_pressed
            accept_pressed = return_down or return_pressed
            if self.ignore_r_until_release:
                r_toggled = False
                if not r_down:
                    self.ignore_r_until_release = False
                    self._log_event("r_release_seen")
            else:
                r_toggled = r_down and not self.was_r_down

            numeric_input_changed = self._update_numeric_input()
            axis_lock_request = None

            if x_down and not self.was_x_down:
                axis_lock_request = AXIS_LOCK_X
            elif y_down and not self.was_y_down:
                axis_lock_request = AXIS_LOCK_Y
            elif z_down and not self.was_z_down:
                axis_lock_request = AXIS_LOCK_Z

            if cancel_pressed:
                self._log_event(
                    "finish_requested",
                    accepted=False,
                    source="poll",
                    escape_down=escape_down,
                    escape_pressed=escape_pressed,
                    right_down=right_down,
                    right_pressed=right_pressed,
                )
                self._finish(False)
                return

            if accept_pressed:
                self._log_event(
                    "finish_requested",
                    accepted=True,
                    source="poll",
                    left_down=left_down,
                    left_pressed=left_pressed,
                    return_down=return_down,
                    return_pressed=return_pressed,
                )
                self._finish(True)
                return

            if right_down or right_pressed:
                self._begin_mouse_finish(False, VK_RBUTTON, "poll")
                return

            if left_down or left_pressed:
                self._begin_mouse_finish(True, VK_LBUTTON, "poll")
                return

            cursor_position = _cursor_position()
            self._update_precision_mode(shift_down, cursor_position)

            if axis_lock_request is not None:
                self._set_axis_lock(axis_lock_request)
                self._set_key_states(
                    left_down,
                    right_down,
                    escape_down,
                    return_down,
                    r_down,
                    x_down,
                    y_down,
                    z_down,
                )
                return

            if numeric_input_changed:
                self._preview_current_transform(force=True)

            if r_toggled:
                self._toggle_rotation_mode("poll", cursor_position)
                self._set_key_states(
                    left_down,
                    right_down,
                    escape_down,
                    return_down,
                    r_down,
                    x_down,
                    y_down,
                    z_down,
                )
                return

            if self.mode == MODE_ORBIT:
                self._update_angle_from_cursor(cursor_position)

            self._preview_current_transform()

            self._set_key_states(
                left_down,
                right_down,
                escape_down,
                return_down,
                r_down,
                x_down,
                y_down,
                z_down,
            )
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


class FCurveTangentRotateController(QtCore.QObject):
    def __init__(
        self,
        tangent_states,
        graph_widget,
        orbit_center,
        graph_rect,
        derivative_scale,
    ):
        QtCore.QObject.__init__(self)
        self.session_id = int(time.time() * 1000.0)
        self.tangent_states = tangent_states
        self.graph_widget = graph_widget
        self.tangent_angle_widgets = _fcurve_tangent_angle_widgets(graph_widget)
        self.derivative_scale = derivative_scale
        self.center_cursor = orbit_center
        self.graph_rect = graph_rect
        self.overlay = None
        self.cursor_pixmap = _load_cursor_pixmap(ROTATION_CURSOR_ICON)
        self.custom_cursor_active = False
        self.last_cursor_rotation_angle = None
        self.precision_multiplier = 1.0
        self.last_orbit_angle = None
        self.orbit_angle = 0.0
        self.last_preview_signature = None
        self.last_applied_angle = 0.0
        self.timer = None
        self.armed = False
        self.accepted = False
        self.finished = False
        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False
        self.event_filter_installed = False
        self.numeric_input_text = ""
        self.numeric_input_active = False
        self.error_text = None
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_return_down = _is_key_down(VK_RETURN)
        self.was_numeric_key_down = {
            vk_code: _is_key_down(vk_code)
            for vk_code, _value in NUMERIC_INPUT_KEYS
        }

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
        self._log_event("fcurve_start", key_count=len(self.tangent_states))
        return True

    def run(self):
        return self.start()

    def request_mode_toggle(self):
        # A repeated R belongs to the same FCurve tangent operation. There is
        # no trackball/axis mode in a two-dimensional graph.
        self._log_event("fcurve_repeat_r_ignored")
        return True

    def _log_event(self, event, **values):
        return

    def _show_overlay(self):
        try:
            cursor_position = _cursor_position()
            self.overlay = RotationOverlayWidget(self.graph_rect)
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(0.0),
                None,
                None,
                self.cursor_pixmap,
                self._cursor_rotation_angle(cursor_position),
                ROTATION_CURSOR_ICON,
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

    def _status_text(self, angle):
        left_value, _left_accessible = _qt_widget_display_value(
            self.tangent_angle_widgets.get("left")
        ) if self.tangent_angle_widgets.get("left") is not None else (None, {})
        right_value, _right_accessible = _qt_widget_display_value(
            self.tangent_angle_widgets.get("right")
        ) if self.tangent_angle_widgets.get("right") is not None else (None, {})

        if left_value is not None and right_value is not None:
            return "Tangents  L %s deg   R %s deg" % (left_value, right_value)

        if self.derivative_scale is not None and self.tangent_states:
            state = self.tangent_states[0]
            scale = float(self.derivative_scale)
            left_angle = -math.degrees(
                math.atan(float(state["original_left_derivative"]) / scale)
                + math.radians(float(angle))
            )
            right_angle = math.degrees(
                math.atan(float(state["original_right_derivative"]) / scale)
                + math.radians(float(angle))
            )

            while left_angle > 90.0:
                left_angle -= 180.0
            while left_angle < -90.0:
                left_angle += 180.0
            while right_angle > 90.0:
                right_angle -= 180.0
            while right_angle < -90.0:
                right_angle += 180.0

            return "Tangents  L %+.3f deg   R %+.3f deg" % (
                left_angle,
                right_angle,
            )

        return "Tangent rotation %+.3f deg" % float(angle)

    def _update_overlay(self, cursor_position=None, angle=None):
        if cursor_position is None:
            cursor_position = _cursor_position()

        self._update_custom_cursor(cursor_position)

        if self.overlay is None:
            return

        if angle is None:
            angle = self.last_applied_angle

        try:
            self.overlay.set_overlay_data(
                self.center_cursor,
                cursor_position,
                self._status_text(angle),
                None,
                None,
                self.cursor_pixmap,
                self._cursor_rotation_angle(cursor_position),
                ROTATION_CURSOR_ICON,
                1.0,
            )
        except Exception:
            pass

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

        if self.event_filter_installed and app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
            self.event_filter_installed = False

    def _begin_mouse_finish(self, accepted, vk_code, source):
        if self.finished or self.pending_finish is not None:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = _cursor_position()
        self.pending_finish_scheduled = False
        self._log_event(
            "fcurve_mouse_finish_armed",
            accepted=accepted,
            vk_code=vk_code,
            source=source,
            cursor=self.pending_finish_cursor,
        )

    def _schedule_mouse_finish(self):
        if (
            self.finished
            or self.pending_finish is None
            or self.pending_finish_scheduled
        ):
            return

        self.pending_finish_scheduled = True
        try:
            QtCore.QTimer.singleShot(
                MOUSE_FINISH_RELEASE_DELAY_MS,
                self._complete_mouse_finish,
            )
        except Exception:
            self._complete_mouse_finish()

    def _complete_mouse_finish(self):
        if self.finished or self.pending_finish is None:
            return

        accepted = self.pending_finish
        cursor_position = self.pending_finish_cursor
        self.pending_finish_scheduled = False
        self._log_event(
            "fcurve_mouse_finish_complete",
            accepted=accepted,
            cursor=cursor_position,
        )
        self._finish(accepted, cursor_position)

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()
            event_types = QtCore.QEvent.Type if hasattr(QtCore.QEvent, "Type") else QtCore.QEvent
            mouse_press_type = event_types.MouseButtonPress
            mouse_double_click_type = event_types.MouseButtonDblClick
            mouse_release_type = event_types.MouseButtonRelease
            context_menu_type = event_types.ContextMenu

            if self.pending_finish is False and event_type == context_menu_type:
                return True

            if not self.armed or self.finished:
                return False

            if hasattr(QtCore.Qt, "MouseButton"):
                left_button = QtCore.Qt.MouseButton.LeftButton
                right_button = QtCore.Qt.MouseButton.RightButton
            else:
                left_button = QtCore.Qt.LeftButton
                right_button = QtCore.Qt.RightButton

            if event_type in (mouse_press_type, mouse_double_click_type):
                button = event.button()

                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON, "qt_press")
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON, "qt_press")
                    return True

            if self.pending_finish is not None:
                if event_type == mouse_release_type:
                    button = event.button()
                    if button in (left_button, right_button):
                        if button == (
                            left_button
                            if self.pending_finish_vk_code == VK_LBUTTON
                            else right_button
                        ):
                            self._schedule_mouse_finish()
                        return True

                if event_type in (mouse_press_type, mouse_double_click_type):
                    button = event.button()
                    if button in (left_button, right_button):
                        return True
        except Exception:
            self.error_text = traceback.format_exc()
            self._begin_mouse_finish(False, VK_RBUTTON, "event_filter_error")
            self._schedule_mouse_finish()

        return False

    def _update_angle_from_cursor(self, cursor_position):
        angle = _angle_from_center(self.center_cursor, cursor_position)

        if angle is None:
            return

        if self.last_orbit_angle is None:
            self.last_orbit_angle = angle
            return

        self.orbit_angle += (
            _wrapped_angle_delta(angle, self.last_orbit_angle)
            * self.precision_multiplier
        )
        self.last_orbit_angle = angle

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

    def _effective_angle(self):
        if self.numeric_input_active:
            return self._numeric_input_value()

        if _is_key_down(VK_CONTROL):
            return _snap_degrees_to_ten(self.orbit_angle)

        return self.orbit_angle

    def _preview_current_tangents(self, force=False, cursor_position=None):
        angle = self._effective_angle()
        signature = (
            self.numeric_input_text if self.numeric_input_active else None,
            bool(_is_key_down(VK_CONTROL)),
            int(round(angle / PREVIEW_ANGLE_EPSILON)),
        )
        if cursor_position is None:
            cursor_position = _cursor_position()

        if not force and signature == self.last_preview_signature:
            self._update_overlay(cursor_position, angle)
            return

        _set_fcurve_tangent_states_angle(
            self.tangent_states,
            angle,
            self.derivative_scale,
        )
        self.last_applied_angle = angle
        self.last_preview_signature = signature
        _refresh_fcurve_widget(self.graph_widget)
        self._update_overlay(cursor_position, angle)

    def _restore_original_tangents(self):
        _restore_fcurve_tangent_states(self.tangent_states)
        self.last_preview_signature = None
        _refresh_fcurve_widget(self.graph_widget)

    def _finish(self, accepted, finish_cursor_position=None):
        if self.finished:
            return

        self.accepted = accepted
        self.finished = True

        try:
            if accepted:
                self._preview_current_tangents(
                    force=True,
                    cursor_position=finish_cursor_position,
                )
                if abs(self.last_applied_angle) <= ANGLE_EPSILON:
                    self._restore_original_tangents()
            else:
                self._restore_original_tangents()
        except Exception:
            self.accepted = False
            self.error_text = traceback.format_exc()
            try:
                self._restore_original_tangents()
            except Exception:
                pass

        self._stop_interaction()
        _clear_active_controller(self)

        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")
        elif self.accepted:
            print(
                "%s: rotated %d selected FCurve key tangent(s) by %.3f degrees."
                % (TOOL_NAME, len(self.tangent_states), self.last_applied_angle)
            )
        else:
            print("%s: FCurve tangent rotation canceled." % TOOL_NAME)

    def _tick(self):
        try:
            if self.pending_finish is not None:
                if (
                    self.pending_finish_vk_code is None
                    or not _is_key_down(self.pending_finish_vk_code)
                ):
                    self._schedule_mouse_finish()
                return

            left_down, left_pressed = _mouse_button_state(VK_LBUTTON, "LeftButton")
            right_down, right_pressed = _mouse_button_state(VK_RBUTTON, "RightButton")
            escape_down, escape_pressed = _key_state(VK_ESCAPE)
            return_down, return_pressed = _key_state(VK_RETURN)
            shift_down, _shift_pressed = _key_state(VK_SHIFT)
            self._update_custom_cursor(_cursor_position())

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self.last_orbit_angle = _angle_from_center(
                        self.center_cursor,
                        _cursor_position(),
                    )
                    self.was_left_down = False
                    self.was_right_down = False
                    self.was_escape_down = escape_down
                    self.was_return_down = return_down
                    self._preview_current_tangents(force=True)
                return

            cancel_pressed = escape_down or escape_pressed
            accept_pressed = return_down or return_pressed

            if cancel_pressed:
                self._finish(False)
                return

            if accept_pressed:
                self._finish(True)
                return

            if right_down or right_pressed:
                self._begin_mouse_finish(False, VK_RBUTTON, "poll")
                return

            if left_down or left_pressed:
                self._begin_mouse_finish(True, VK_LBUTTON, "poll")
                return

            cursor_position = _cursor_position()
            self.precision_multiplier = _precision_multiplier(shift_down)
            self._update_numeric_input()
            self._update_angle_from_cursor(cursor_position)
            self._preview_current_tangents()
            self.was_left_down = left_down
            self.was_right_down = right_down
            self.was_escape_down = escape_down
            self.was_return_down = return_down
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


def _start_fcurve_tangent_rotation(graph_widget):
    tangent_states = _selected_fcurve_tangent_states()

    if not tangent_states:
        return

    graph_rect = _qt_widget_rect(graph_widget)
    orbit_center, derivative_scale = _fcurve_orbit_center(
        graph_widget,
        tangent_states,
    )
    controller = FCurveTangentRotateController(
        tangent_states,
        graph_widget,
        orbit_center,
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


def rotate_selected_by_mouse_orbit():
    active_controller = _get_active_controller()

    if active_controller is not None:
        try:
            active_controller._log_event("entry_reused_active_controller")
        except Exception:
            pass
        active_controller.request_mode_toggle()
        return

    fcurve_graph_widget = _fcurve_graph_widget_for_cursor()

    if fcurve_graph_widget is not None:
        _start_fcurve_tangent_rotation(fcurve_graph_widget)
        return

    models = _selected_transformable_models()

    if not models:
        return

    model_states = []

    for model in models:
        rotation = _vector_to_list(model.Rotation)
        global_rotation_matrix = _model_global_rotation_matrix_values(model)
        model_states.append(
            {
                "model": model,
                "original_rotation": rotation,
                "mode_base_rotation": list(rotation),
                "original_global_rotation_matrix": global_rotation_matrix,
                "mode_base_global_rotation_matrix": list(global_rotation_matrix),
                "pre_rotation": _model_pre_rotation_values(model),
                "post_rotation": _model_post_rotation_values(model),
                "original_translation": _world_translation(model),
                "center_visible": _model_visible_for_center(model),
            }
        )

    camera, view_right, view_up, fallback_view_axis = _camera_view_context()
    view_axis = _view_axis_toward_camera(camera, model_states, fallback_view_axis)
    orbit_center = _orbit_center_cursor(
        camera,
        model_states,
        view_right,
        view_up,
        fallback_view_axis,
    )
    viewport_rect = _viewport_global_rect(camera)

    controller = MouseOrbitAngleController(
        model_states,
        view_axis,
        orbit_center,
        view_right,
        view_up,
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
        controller._log_event("start_failed")
        _clear_active_controller(controller)


def run_with_error_dialog():
    try:
        rotate_selected_by_mouse_orbit()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
