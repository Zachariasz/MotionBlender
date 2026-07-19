import ctypes
import itertools
import math
import os
import sys
import traceback
import types

from pyfbsdk import (
    FBApplication,
    FBCameraSwitcher,
    FBCameraMatrixType,
    FBCameraType,
    FBCharacterKeyingMode,
    FBEffectorId,
    FBEffectorSetID,
    FBFCurve,
    FBFCurveEditorUtility,
    FBGetEffectorBodyPart,
    FBGetSelectedModels,
    FBMatrix,
    FBMessageBox,
    FBModelList,
    FBModelTransformationType,
    FBPlayerControl,
    FBSystem,
    FBTime,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Move Selected Along Camera View"

CURSOR_ICON_FILENAME = "4arrow.png"
CURSOR_ICON_FALLBACK_PATH = r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts\custom\icons\4arrow.png"
CURSOR_ICON_SCALE = 0.5

SENSITIVITY = 1.0
SLOW_MULTIPLIER = 0.2
FAST_MULTIPLIER = 5.0
FALLBACK_WORLD_UNITS_PER_PIXEL = 0.25
POLL_INTERVAL_MS = 16
MOUSE_FINISH_RELEASE_DELAY_MS = 40
OVERLAY_TEXT_MARGIN = 18
OVERLAY_TEXT_PADDING_X = 10
OVERLAY_TEXT_PADDING_Y = 5
AXIS_LINE_MIN_SCREEN_LENGTH = 4.0
HIK_EFFECTOR_ID_LIMIT = 64
HIK_EFFECTOR_SET_LIMIT = 16
HIK_FK_MODEL_LIMIT = 256
HIK_CHANGE_EPSILON = 0.00001
TARGET_CHANGE_EPSILON = 0.000001
KEY_VALUE_MIN_VISIBLE_RANGE = 2.0
KEY_VALUE_RANGE_PADDING = 1.2
KEY_VALUE_CHANGE_EPSILON = 0.000001
FCURVE_MARKER_DENSITY_RADIUS = 3
FCURVE_MARKER_MIN_DENSITY = 24
FCURVE_MARKER_MIN_SEPARATION = 8.0
FCURVE_MARKER_MAX_FIT_COMBINATIONS = 6000
FCURVE_MARKER_MAX_RESIDUAL = 2.5
FCURVE_AXIS_LABEL_WIDTH = 41
FCURVE_AXIS_LABEL_HEIGHT = 8
FCURVE_AXIS_OCR_CANDIDATES_PER_ROW = 20
FCURVE_AXIS_OCR_MAX_SCORE = 0.75
FCURVE_AXIS_CACHE_STATE_MODULE = "_move_selected_fcurve_scale_state"
FCURVE_AXIS_CACHE_ATTR = "axis_scale_calibrations"
FCURVE_AXIS_CACHE_SPACING_TOLERANCE = 2.0
FCURVE_MINOR_GRID_CACHE_SPACING_TOLERANCE = 0.75
FCURVE_TIME_SPAN_CACHE_TOLERANCE_TICKS = 2
FCURVE_AXIS_STRONG_MIN_MATCHES = 3
FCURVE_AXIS_STRONG_MAX_SCORE = 0.62

try:
    FCURVE_AXIS_LABEL_CANDIDATE_CACHE
except NameError:
    FCURVE_AXIS_LABEL_CANDIDATE_CACHE = {}

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_BACK = 0x08
VK_ESCAPE = 0x1B
VK_X = 0x58
VK_Y = 0x59
VK_Z = 0x5A
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE
VK_SUBTRACT = 0x6D
VK_DECIMAL = 0x6E

GLOBAL_AXIS_DIRECTIONS = {
    "x": [1.0, 0.0, 0.0],
    "y": [0.0, 1.0, 0.0],
    "z": [0.0, 0.0, 1.0],
}

AXIS_GUIDE_COLORS = {
    "x": (235, 55, 55, 230),
    "y": (50, 220, 90, 230),
    "z": (75, 135, 255, 230),
}

NUMERIC_INPUT_KEYS = (
    ("0", 0x30),
    ("1", 0x31),
    ("2", 0x32),
    ("3", 0x33),
    ("4", 0x34),
    ("5", 0x35),
    ("6", 0x36),
    ("7", 0x37),
    ("8", 0x38),
    ("9", 0x39),
    ("0", 0x60),
    ("1", 0x61),
    ("2", 0x62),
    ("3", 0x63),
    ("4", 0x64),
    ("5", 0x65),
    ("6", 0x66),
    ("7", 0x67),
    ("8", 0x68),
    ("9", 0x69),
    (".", VK_OEM_PERIOD),
    (".", VK_DECIMAL),
    ("-", VK_OEM_MINUS),
    ("-", VK_SUBTRACT),
    ("backspace", VK_BACK),
)


def _cursor_position():
    position = QtGui.QCursor.pos()
    return position.x(), position.y()


def _cursor_qpoint():
    return QtGui.QCursor.pos()


def _cursor_icon_candidates():
    candidates = []

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "icons", CURSOR_ICON_FILENAME))
    except Exception:
        pass

    try:
        user_config_path = FBSystem().UserConfigPath
        if user_config_path:
            candidates.append(os.path.join(
                user_config_path,
                "Scripts",
                "custom",
                "icons",
                CURSOR_ICON_FILENAME,
            ))
    except Exception:
        pass

    candidates.append(CURSOR_ICON_FALLBACK_PATH)
    return candidates


def _size_all_cursor():
    cursor_shape_container = getattr(QtCore.Qt, "CursorShape", QtCore.Qt)
    cursor_shape = getattr(cursor_shape_container, "SizeAllCursor", None)

    if cursor_shape is None:
        cursor_shape = getattr(QtCore.Qt, "SizeAllCursor")

    return QtGui.QCursor(cursor_shape)


def _move_cursor():
    for icon_path in _cursor_icon_candidates():
        if not icon_path or not os.path.exists(icon_path):
            continue

        pixmap = QtGui.QPixmap(icon_path)
        if pixmap.isNull():
            continue

        aspect_mode_container = getattr(QtCore.Qt, "AspectRatioMode", QtCore.Qt)
        transform_mode_container = getattr(QtCore.Qt, "TransformationMode", QtCore.Qt)
        target_width = max(1, int(round(pixmap.width() * CURSOR_ICON_SCALE)))
        target_height = max(1, int(round(pixmap.height() * CURSOR_ICON_SCALE)))
        pixmap = pixmap.scaled(
            target_width,
            target_height,
            getattr(aspect_mode_container, "KeepAspectRatio"),
            getattr(transform_mode_container, "SmoothTransformation"),
        )

        return QtGui.QCursor(pixmap, pixmap.width() // 2, pixmap.height() // 2)

    return _size_all_cursor()


def _is_key_down(vk_code):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _mul(values, scalar):
    return [values[0] * scalar, values[1] * scalar, values[2] * scalar]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _length(values):
    return math.sqrt(sum(component * component for component in values))


def _normalize(values, fallback):
    length = _length(values)
    if length <= 0.000001:
        return list(fallback)
    return [component / length for component in values]


def _selected_transformable_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)
    return [
        model
        for model in selected_models
        if getattr(model, "Transformable", True)
    ]


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


def _vector_to_list(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def _copy_vector(values):
    return FBVector3d(values[0], values[1], values[2])


def _model_vector(model, transform_type, global_space):
    vector = FBVector3d()
    model.GetVector(vector, transform_type, global_space)
    return _vector_to_list(vector)


def _world_translation(model):
    try:
        return _model_vector(model, FBModelTransformationType.kModelTranslation, True)
    except Exception:
        return _vector_to_list(model.Translation)


def _set_world_translation(model, values):
    vector = _copy_vector(values)

    try:
        model.SetVector(vector, FBModelTransformationType.kModelTranslation, True)
    except Exception:
        model.Translation = vector


def _evaluate_scene():
    try:
        return bool(FBSystem().Scene.Evaluate())
    except Exception:
        return False


def _world_rotation(model):
    try:
        return _model_vector(model, FBModelTransformationType.kModelRotation, True)
    except Exception:
        return _vector_to_list(model.Rotation)


def _numeric_value(value, fallback):
    try:
        return float(value)
    except Exception:
        pass

    try:
        return float(value.Data)
    except Exception:
        return fallback


def _resolve_and_evaluate_scene():
    try:
        FBSystem().Scene.CandidateEvaluationAndResolve()
    except Exception:
        pass

    return _evaluate_scene()


def _find_property(owner, property_name):
    try:
        return owner.PropertyList.Find(property_name)
    except Exception:
        return None


def _component_key(component):
    for attribute_name in ("LongName", "Name"):
        try:
            value = str(getattr(component, attribute_name))
        except Exception:
            value = ""
        if value:
            return value
    return str(component)


def _same_component(left, right):
    if left is None or right is None:
        return False

    try:
        if left == right:
            return True
    except Exception:
        pass

    return _component_key(left) == _component_key(right)


def _characters_current_first():
    result = []

    try:
        current_character = FBApplication().CurrentCharacter
    except Exception:
        current_character = None

    if current_character is not None:
        result.append(current_character)

    try:
        scene_characters = list(FBSystem().Scene.Characters)
    except Exception:
        scene_characters = []

    for character in scene_characters:
        if any(_same_component(character, item) for item in result):
            continue
        result.append(character)

    return result


def _current_control_set(character):
    try:
        return character.GetCurrentControlSet()
    except Exception:
        pass

    try:
        return character.GetCurrentControlSet(True)
    except Exception:
        return None


def _enum_value(enum_type, numeric_value):
    try:
        return enum_type(numeric_value)
    except Exception:
        return numeric_value


def _find_hik_effector(model):
    reach_property = _find_property(model, "IK Reach Translation")
    if reach_property is None:
        return None

    for character in _characters_current_first():
        control_set = _current_control_set(character)
        if control_set is None:
            continue

        for numeric_effector_id in range(HIK_EFFECTOR_ID_LIMIT):
            effector_id = _enum_value(FBEffectorId, numeric_effector_id)

            try:
                candidate = character.GetEffectorModel(effector_id)
            except Exception:
                candidate = None

            if _same_component(candidate, model):
                return {
                    "character": character,
                    "control_set": control_set,
                    "effector_id": effector_id,
                    "effector_set_id": None,
                    "reach_property": reach_property,
                    "original_reach": _numeric_value(reach_property, 0.0),
                }

            for numeric_set_id in range(1, HIK_EFFECTOR_SET_LIMIT):
                effector_set_id = _enum_value(FBEffectorSetID, numeric_set_id)
                try:
                    candidate = character.GetEffectorModel(effector_id, effector_set_id)
                except Exception:
                    candidate = None

                if _same_component(candidate, model):
                    return {
                        "character": character,
                        "control_set": control_set,
                        "effector_id": effector_id,
                        "effector_set_id": effector_set_id,
                        "reach_property": reach_property,
                        "original_reach": _numeric_value(reach_property, 0.0),
                    }

    return None


def _hik_pin_affects_current_manipulation(character, effector_id):
    try:
        keying_mode = character.KeyingMode
    except Exception:
        return True

    try:
        if keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingSelection:
            return False
    except Exception:
        pass

    try:
        is_body_part = (
            keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingBodyPart
        )
    except Exception:
        is_body_part = False

    if not is_body_part:
        return True

    try:
        active_body_parts = list(character.GetActiveBodyPart())
        body_part_index = int(FBGetEffectorBodyPart(effector_id))
        return (
            0 <= body_part_index < len(active_body_parts)
            and bool(active_body_parts[body_part_index])
        )
    except Exception:
        return True


def _capture_hik_pin_reach_overrides(character):
    overrides = []

    for numeric_effector_id in range(HIK_EFFECTOR_ID_LIMIT):
        effector_id = _enum_value(FBEffectorId, numeric_effector_id)

        try:
            model = character.GetEffectorModel(effector_id)
        except Exception:
            model = None

        if model is None:
            continue

        if not _hik_pin_affects_current_manipulation(character, effector_id):
            continue

        try:
            translation_pinned = bool(character.IsTranslationPin(effector_id))
        except Exception:
            translation_pinned = False

        try:
            rotation_pinned = bool(character.IsRotationPin(effector_id))
        except Exception:
            rotation_pinned = False

        if not translation_pinned and not rotation_pinned:
            continue

        translation_property = (
            _find_property(model, "IK Reach Translation")
            if translation_pinned
            else None
        )
        rotation_property = (
            _find_property(model, "IK Reach Rotation")
            if rotation_pinned
            else None
        )
        pull_property = (
            _find_property(model, "IK Pull")
            if translation_pinned
            else None
        )

        if (
            translation_property is None
            and rotation_property is None
            and pull_property is None
        ):
            continue

        overrides.append({
            "model": model,
            "translation_property": translation_property,
            "original_translation": (
                _numeric_value(translation_property, 0.0)
                if translation_property is not None
                else None
            ),
            "rotation_property": rotation_property,
            "original_rotation": (
                _numeric_value(rotation_property, 0.0)
                if rotation_property is not None
                else None
            ),
            "pull_property": pull_property,
            "original_pull": (
                _numeric_value(pull_property, 0.0)
                if pull_property is not None
                else None
            ),
        })

    return overrides


def _capture_fk_baselines(control_set):
    baselines = []
    seen = set()

    for index in range(HIK_FK_MODEL_LIMIT):
        try:
            model = control_set.GetFKModel(index)
        except Exception:
            model = None

        if model is None:
            continue

        key = _component_key(model)
        if key in seen:
            continue

        try:
            translation = _model_vector(
                model,
                FBModelTransformationType.kModelTranslation,
                False,
            )
            rotation = _model_vector(
                model,
                FBModelTransformationType.kModelRotation,
                False,
            )
        except Exception:
            continue

        seen.add(key)
        baselines.append({
            "key": key,
            "model": model,
            "translation": translation,
            "rotation": rotation,
        })

    return baselines


def _build_hik_move_contexts(model_states):
    contexts_by_character = {}

    for state in model_states:
        state["hik_effector"] = _find_hik_effector(state["model"])
        info = state["hik_effector"]
        if info is None:
            continue

        character_key = _component_key(info["character"])
        context = contexts_by_character.get(character_key)
        if context is None:
            context = {
                "character": info["character"],
                "control_set": info["control_set"],
                "effectors": [],
                "pinned_effectors": [],
                "states": [],
                "fk_baselines": [],
                "fk_by_key": {},
                "previous_changed": [],
            }
            contexts_by_character[character_key] = context

        context["states"].append(state)
        if not any(
            _same_component(state["model"], item["model"])
            for item in context["effectors"]
        ):
            context["effectors"].append({
                "model": state["model"],
                "reach_property": info["reach_property"],
                "original_reach": info["original_reach"],
            })

    contexts = []

    for context in contexts_by_character.values():
        baselines = _capture_fk_baselines(context["control_set"])
        if not baselines:
            for state in context["states"]:
                state["hik_effector"] = None
            continue

        context["fk_baselines"] = baselines
        context["fk_by_key"] = {
            state["key"]: state
            for state in baselines
        }
        context["pinned_effectors"] = _capture_hik_pin_reach_overrides(
            context["character"]
        )
        contexts.append(context)

    return contexts


def _set_hik_reach_values(context, temporary_active):
    for effector in context["effectors"]:
        value = 100.0 if temporary_active else effector["original_reach"]
        effector["reach_property"].Data = value

    for effector in context["pinned_effectors"]:
        translation_property = effector["translation_property"]
        if translation_property is not None:
            translation_property.Data = (
                100.0
                if temporary_active
                else effector["original_translation"]
            )

        rotation_property = effector["rotation_property"]
        if rotation_property is not None:
            rotation_property.Data = (
                100.0
                if temporary_active
                else effector["original_rotation"]
            )

        pull_property = effector["pull_property"]
        if pull_property is not None:
            pull_property.Data = (
                100.0
                if temporary_active
                else effector["original_pull"]
            )


def _vectors_differ(left, right, epsilon=HIK_CHANGE_EPSILON):
    return any(
        abs(float(left[index]) - float(right[index])) > epsilon
        for index in range(3)
    )


def _capture_changed_fk_states(context):
    changed_states = []

    for baseline in context["fk_baselines"]:
        model = baseline["model"]
        translation = _model_vector(
            model,
            FBModelTransformationType.kModelTranslation,
            False,
        )
        rotation = _model_vector(
            model,
            FBModelTransformationType.kModelRotation,
            False,
        )

        if not (
            _vectors_differ(translation, baseline["translation"])
            or _vectors_differ(rotation, baseline["rotation"])
        ):
            continue

        changed_states.append({
            "key": baseline["key"],
            "model": model,
            "translation": translation,
            "rotation": rotation,
        })

    return changed_states


def _apply_fk_states(states):
    for state in states:
        model = state["model"]
        model.SetVector(
            _copy_vector(state["translation"]),
            FBModelTransformationType.kModelTranslation,
            False,
        )
        model.SetVector(
            _copy_vector(state["rotation"]),
            FBModelTransformationType.kModelRotation,
            False,
        )


def _baseline_states_for_previous(context):
    return [
        context["fk_by_key"][state["key"]]
        for state in context["previous_changed"]
        if state["key"] in context["fk_by_key"]
    ]


def _selection_center(model_states):
    center = [0.0, 0.0, 0.0]

    for state in model_states:
        center = _add(center, state["original"])

    return _mul(center, 1.0 / float(len(model_states)))


def _points_center(points):
    center = [0.0, 0.0, 0.0]

    for point in points:
        center = _add(center, point)

    return _mul(center, 1.0 / float(len(points)))


def _qt_window_flag(name):
    if hasattr(QtCore.Qt, "WindowType"):
        return getattr(QtCore.Qt.WindowType, name)

    return getattr(QtCore.Qt, name)


def _qt_widget_attribute(name):
    if hasattr(QtCore.Qt, "WidgetAttribute"):
        return getattr(QtCore.Qt.WidgetAttribute, name)

    return getattr(QtCore.Qt, name)


def _set_widget_attribute(widget, attribute_name, enabled=True):
    try:
        widget.setAttribute(_qt_widget_attribute(attribute_name), enabled)
    except Exception:
        pass


def _qt_alignment_flag(name):
    if hasattr(QtCore.Qt, "AlignmentFlag"):
        return getattr(QtCore.Qt.AlignmentFlag, name)

    return getattr(QtCore.Qt, name)


def _qt_text_elide_mode(name):
    if hasattr(QtCore.Qt, "TextElideMode"):
        return getattr(QtCore.Qt.TextElideMode, name)

    return getattr(QtCore.Qt, name)


def _qt_event_type(name):
    if hasattr(QtCore.QEvent, "Type"):
        return getattr(QtCore.QEvent.Type, name)

    return getattr(QtCore.QEvent, name)


def _qt_mouse_button(name):
    if hasattr(QtCore.Qt, "MouseButton"):
        return getattr(QtCore.Qt.MouseButton, name)

    return getattr(QtCore.Qt, name)


def _qt_widget_rect(widget):
    top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
    return top_left.x(), top_left.y(), int(widget.width()), int(widget.height())


def _rect_contains_point(rect, point):
    x, y, width, height = rect
    return x <= point.x() <= x + width and y <= point.y() <= y + height


def _widget_accessible_name(widget):
    try:
        return str(widget.accessibleName() or "").lower()
    except Exception:
        return ""


def _editor_surface_for_cursor(accessible_name):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    cursor = _cursor_qpoint()

    try:
        widget = app.widgetAt(cursor)
    except Exception:
        widget = None

    current = widget
    while current is not None:
        try:
            if (
                _widget_accessible_name(current) == accessible_name
                and _rect_contains_point(_qt_widget_rect(current), cursor)
            ):
                return current
            current = current.parentWidget()
        except Exception:
            current = None

    candidates = []
    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []

    for candidate in widgets:
        try:
            if (
                candidate.isVisible()
                and candidate.width() > 20
                and candidate.height() > 10
                and _widget_accessible_name(candidate) == accessible_name
                and _rect_contains_point(_qt_widget_rect(candidate), cursor)
            ):
                candidates.append(candidate)
        except Exception:
            pass

    if not candidates:
        return None

    candidates.sort(key=lambda item: int(item.width()) * int(item.height()))
    return candidates[0]


def _fcurve_graph_widget_for_cursor():
    # FCurveLayerView is the separate Animation Layers surface.  The graph
    # itself is the QOpenGLWidget whose accessible name is exactly FCurve.
    return _editor_surface_for_cursor("fcurve")


def _timeline_widget_for_cursor():
    # MotionBuilder exposes the key strip in Transport Controls as TimeCursor.
    return _editor_surface_for_cursor("timecursor")


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


def _current_layer_indices():
    indices = set()
    take = FBSystem().CurrentTake

    if take is None:
        return indices

    try:
        indices.add(int(take.GetCurrentLayer()))
    except Exception:
        pass

    try:
        for index in range(int(take.GetLayerCount())):
            layer = take.GetLayer(index)
            if layer is not None and layer.IsSelected():
                indices.add(index)
    except Exception:
        pass

    return indices


def _scan_animation_node_fcurves(animation_node, layer_indices, curves):
    if animation_node is None:
        return

    try:
        _add_fcurve(curves, animation_node.FCurve)
    except Exception:
        pass

    for layer_index in layer_indices:
        try:
            _add_fcurve(curves, animation_node.GetFCurve(layer_index))
        except Exception:
            pass

    try:
        child_nodes = list(animation_node.Nodes)
    except Exception:
        child_nodes = []

    for child_node in child_nodes:
        _scan_animation_node_fcurves(child_node, layer_indices, curves)


def _displayed_fcurves():
    curves = set()
    properties = []
    layer_indices = _current_layer_indices()

    try:
        FBFCurveEditorUtility().GetProperties(properties, False)
    except Exception:
        properties = []

    for prop in properties:
        try:
            if prop.IsAnimated():
                _scan_animation_node_fcurves(
                    prop.GetAnimationNode(),
                    layer_indices,
                    curves,
                )
        except Exception:
            pass

    return list(curves)


def _scene_fcurves():
    curves = set()
    system = FBSystem()
    layer_indices = _current_layer_indices()

    try:
        components = list(system.Scene.Components)
    except Exception:
        components = []

    for component in components:
        if isinstance(component, FBFCurve):
            _add_fcurve(curves, component)

        try:
            properties = list(component.PropertyList)
        except Exception:
            properties = []

        for prop in properties:
            try:
                if prop.IsAnimatable():
                    _scan_animation_node_fcurves(
                        prop.GetAnimationNode(),
                        layer_indices,
                        curves,
                    )
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

    # MotionBuilder leaves MarkedForManipulation set after later box-selection
    # changes, so it is not valid selection state for a new move operation.
    return False


def _fcurve_key_value(fcurve, index):
    try:
        return float(fcurve.Keys[index].Value)
    except Exception:
        try:
            return float(fcurve.KeyGetValue(index))
        except Exception:
            return 0.0


def _selected_key_states(curves):
    states = []

    for fcurve in curves:
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            if not _fcurve_key_is_selected(fcurve, index):
                continue

            try:
                key = fcurve.Keys[index]
                states.append(
                    {
                        "curve": fcurve,
                        "index": index,
                        "key": key,
                        "original_time_ticks": int(key.Time.Get()),
                        "original_value": _fcurve_key_value(fcurve, index),
                        "original_selected": bool(key.Selected),
                    }
                )
            except Exception:
                pass

    return states


def _fcurve_time_span_ticks():
    try:
        time_span = FBFCurveEditorUtility().GetTimeSpan()
        return int(time_span.GetStart().Get()), int(time_span.GetStop().Get())
    except Exception:
        return None


def _timeline_time_span_ticks():
    try:
        player = FBPlayerControl()
        return int(player.ZoomWindowStart.Get()), int(player.ZoomWindowStop.Get())
    except Exception:
        return None


def _frame_ticks():
    try:
        frames_per_second = float(FBPlayerControl().GetTransportFps())
    except Exception:
        frames_per_second = 0.0

    if frames_per_second <= 0.000001:
        return max(1, int(FBTime(0, 0, 0, 1).Get()))

    return max(1, int(round(float(FBTime.OneSecond.Get()) / frames_per_second)))


def _refresh_scene_after_fcurve_edit():
    system = FBSystem()
    current_time = FBTime(system.LocalTime.Get())
    current_ticks = int(current_time.Get())
    frame_ticks = _frame_ticks()
    refresh_ticks = current_ticks + frame_ticks

    try:
        take = system.CurrentTake
        time_span = take.LocalTimeSpan if take is not None else None
        start_ticks = int(time_span.GetStart().Get())
        stop_ticks = int(time_span.GetStop().Get())
        if refresh_ticks > stop_ticks and current_ticks - frame_ticks >= start_ticks:
            refresh_ticks = current_ticks - frame_ticks
    except Exception:
        pass

    try:
        player = FBPlayerControl()
        refresh_succeeded = bool(player.Goto(FBTime(refresh_ticks)))
        restore_succeeded = bool(player.Goto(current_time))
        if refresh_succeeded and restore_succeeded:
            return True
    except Exception:
        pass

    return _evaluate_scene()


def _ticks_per_pixel(widget, time_span):
    if widget is None or time_span is None:
        return float(_frame_ticks())

    start_ticks, stop_ticks = time_span
    width = max(1.0, float(widget.width()))
    visible_ticks = abs(float(stop_ticks - start_ticks))

    if visible_ticks <= 0.0:
        return float(_frame_ticks())

    return visible_ticks / width


def _fcurve_value_per_pixel(curves, graph_widget):
    values = []

    for fcurve in curves:
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            try:
                values.append(_fcurve_key_value(fcurve, index))
            except Exception:
                pass

    graph_height = max(1.0, float(graph_widget.height()))

    if not values:
        return KEY_VALUE_MIN_VISIBLE_RANGE / graph_height

    value_range = max(values) - min(values)
    if value_range < KEY_VALUE_MIN_VISIBLE_RANGE:
        center_scale = max(abs(sum(values) / float(len(values))) * 0.1, 1.0)
        value_range = max(KEY_VALUE_MIN_VISIBLE_RANGE, center_scale * 2.0)

    return (value_range * KEY_VALUE_RANGE_PADDING) / graph_height


def _fcurve_graph_snapshot(graph_widget):
    try:
        pixmap = graph_widget.grab()
        image = pixmap.toImage()
        if pixmap.isNull() or image.isNull():
            return None

        image_format = (
            QtGui.QImage.Format.Format_RGBA8888
            if hasattr(QtGui.QImage, "Format")
            else QtGui.QImage.Format_RGBA8888
        )
        image = image.convertToFormat(image_format)
        size = (
            int(image.sizeInBytes())
            if hasattr(image, "sizeInBytes")
            else int(image.byteCount())
        )
        bits = image.bits()
        try:
            bits.setsize(size)
        except Exception:
            pass
        raw = bytes(bits)
        if len(raw) < size:
            return None
        return image, raw, int(image.bytesPerLine())
    except Exception:
        return None


def _fcurve_key_marker_pixel(red, green, blue):
    pink = (
        red >= 150
        and green >= 90
        and blue >= 90
        and red - max(green, blue) >= 20
        and abs(green - blue) <= 20
    )
    selected_red = red >= 180 and green <= 80 and blue <= 80
    return pink or selected_red


def _fcurve_unselected_key_marker_pixel(red, green, blue):
    return (
        red >= 150
        and green >= 90
        and blue >= 90
        and red - max(green, blue) >= 20
        and abs(green - blue) <= 20
    )


def _fcurve_isolated_unselected_key_markers(snapshot):
    image, raw, bytes_per_line = snapshot
    pixels = set()

    for image_y in range(int(image.height())):
        offset = image_y * bytes_per_line
        for image_x in range(int(image.width())):
            if _fcurve_unselected_key_marker_pixel(
                raw[offset],
                raw[offset + 1],
                raw[offset + 2],
            ):
                pixels.add((image_x, image_y))
            offset += 4

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

    return sorted(markers, key=lambda marker: marker[0])


def _fcurve_dense_key_markers(snapshot):
    image, raw, bytes_per_line = snapshot
    image_width = int(image.width())
    image_height = int(image.height())
    colored_pixels = set()

    for image_y in range(image_height):
        offset = image_y * bytes_per_line
        for image_x in range(image_width):
            if _fcurve_key_marker_pixel(
                raw[offset],
                raw[offset + 1],
                raw[offset + 2],
            ):
                colored_pixels.add((image_x, image_y))
            offset += 4

    radius = FCURVE_MARKER_DENSITY_RADIUS
    dense_pixels = []
    for image_x, image_y in colored_pixels:
        density = 0
        for neighbor_y in range(image_y - radius, image_y + radius + 1):
            for neighbor_x in range(image_x - radius, image_x + radius + 1):
                if (neighbor_x, neighbor_y) in colored_pixels:
                    density += 1

        if density >= FCURVE_MARKER_MIN_DENSITY:
            dense_pixels.append((density, image_x, image_y))

    markers = []
    minimum_distance_squared = FCURVE_MARKER_MIN_SEPARATION ** 2
    for density, image_x, image_y in sorted(dense_pixels, reverse=True):
        if any(
            ((image_x - marker_x) ** 2) + ((image_y - marker_y) ** 2)
            <= minimum_distance_squared
            for _marker_density, marker_x, marker_y in markers
        ):
            continue
        markers.append((density, image_x, image_y))

    return sorted(markers, key=lambda marker: marker[1])


def _linear_screen_fit(input_values, screen_values):
    input_average = sum(input_values) / float(len(input_values))
    screen_average = sum(screen_values) / float(len(screen_values))
    denominator = sum(
        (value - input_average) ** 2
        for value in input_values
    )
    if denominator <= 0.000001:
        return None

    slope = sum(
        (input_value - input_average) * (screen_value - screen_average)
        for input_value, screen_value in zip(input_values, screen_values)
    ) / denominator
    intercept = screen_average - (slope * input_average)
    residual = math.sqrt(
        sum(
            (
                screen_value
                - (intercept + (slope * input_value))
            ) ** 2
            for input_value, screen_value in zip(input_values, screen_values)
        ) / float(len(input_values))
    )
    return slope, intercept, residual


def _fcurve_unselected_marker_scale(graph_widget, key_states, snapshot):
    markers = _fcurve_isolated_unselected_key_markers(snapshot)
    if len(markers) < 2:
        return None

    selected_by_curve = {}
    curves = []
    for state in key_states:
        curve = state["curve"]
        curve_id = id(curve)
        if curve_id not in selected_by_curve:
            selected_by_curve[curve_id] = set()
            curves.append(curve)
        selected_by_curve[curve_id].add(int(state["index"]))

    best_fit = None
    for curve in curves:
        try:
            keys = list(curve.Keys)
        except Exception:
            continue

        selected_indices = selected_by_curve.get(id(curve), set())
        key_entries = sorted(
            (
                (
                    index,
                    float(key.Time.GetSecondDouble()),
                    _fcurve_key_value(curve, index),
                )
                for index, key in enumerate(keys)
            ),
            key=lambda entry: entry[1],
        )
        remaining_keys = [
            entry
            for entry in key_entries
            if entry[0] not in selected_indices
        ]
        curve_markers = list(markers)

        if len(selected_indices) == 1 and len(curve_markers) == len(remaining_keys) + 1:
            selected_index = next(iter(selected_indices))
            selected_sorted_index = next(
                (
                    sorted_index
                    for sorted_index, entry in enumerate(key_entries)
                    if entry[0] == selected_index
                ),
                None,
            )
            if selected_sorted_index == 0:
                curve_markers.pop(0)
            elif selected_sorted_index == len(key_entries) - 1:
                curve_markers.pop()

        if len(remaining_keys) < 2 or len(curve_markers) != len(remaining_keys):
            continue

        horizontal_fit = _linear_screen_fit(
            [entry[1] for entry in remaining_keys],
            [marker[0] for marker in curve_markers],
        )
        vertical_fit = _linear_screen_fit(
            [entry[2] for entry in remaining_keys],
            [marker[1] for marker in curve_markers],
        )
        if horizontal_fit is None or vertical_fit is None:
            continue
        if horizontal_fit[0] <= 0.000001 or vertical_fit[0] >= -0.000001:
            continue
        if (
            horizontal_fit[2] > FCURVE_MARKER_MAX_RESIDUAL
            or vertical_fit[2] > FCURVE_MARKER_MAX_RESIDUAL
        ):
            continue

        candidate = (
            -(len(remaining_keys)),
            horizontal_fit[2] + vertical_fit[2],
            horizontal_fit[0],
            vertical_fit[0],
        )
        if best_fit is None or candidate[:2] < best_fit[:2]:
            best_fit = candidate

    if best_fit is None:
        return None

    image = snapshot[0]
    image_scale_x = float(image.width()) / max(1.0, float(graph_widget.width()))
    image_scale_y = float(image.height()) / max(1.0, float(graph_widget.height()))
    local_pixels_per_second = best_fit[2] / image_scale_x
    local_pixels_per_value = best_fit[3] / image_scale_y
    return (
        float(FBTime.OneSecond.Get()) / local_pixels_per_second,
        1.0 / abs(local_pixels_per_value),
    )


def _fcurve_grid_layout(snapshot):
    image, raw, bytes_per_line = snapshot
    image_width = int(image.width())
    image_height = int(image.height())
    sample_xs = list(range(60, max(61, image_width - 30), 12))
    if not sample_xs:
        return [], None

    major_rows = []
    all_grid_rows = []
    minimum_score = max(3, int(len(sample_xs) * 0.8))
    for image_y in range(4, max(5, image_height - 34)):
        row_offset = image_y * bytes_per_line
        major_score = 0
        grid_score = 0
        for image_x in sample_xs:
            offset = row_offset + (image_x * 4)
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            if red != green or green != blue:
                continue
            if 45 <= red <= 88:
                grid_score += 1
            if 72 <= red <= 88:
                major_score += 1

        if grid_score >= minimum_score:
            if not all_grid_rows or image_y - all_grid_rows[-1] > 2:
                all_grid_rows.append(image_y)
        if major_score >= minimum_score:
            if not major_rows or image_y - major_rows[-1] > 2:
                major_rows.append(image_y)

    grid_spacing = _fcurve_axis_grid_spacing(all_grid_rows)
    return major_rows, grid_spacing


def _fcurve_major_grid_rows(snapshot):
    return _fcurve_grid_layout(snapshot)[0]


def _fcurve_axis_glyph_masks(font):
    image_format = (
        QtGui.QImage.Format.Format_RGB32
        if hasattr(QtGui.QImage, "Format")
        else QtGui.QImage.Format_RGB32
    )
    metrics = QtGui.QFontMetrics(font)
    glyph_masks = {}

    for character in "-0123456789.":
        image = QtGui.QImage(12, FCURVE_AXIS_LABEL_HEIGHT, image_format)
        image.fill(QtGui.QColor(41, 41, 41))
        painter = QtGui.QPainter(image)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(199, 199, 199))
        painter.drawText(0, FCURVE_AXIS_LABEL_HEIGHT, character)
        painter.end()
        glyph_masks[character] = {
            (image_x, image_y)
            for image_y in range(FCURVE_AXIS_LABEL_HEIGHT)
            for image_x in range(image.width())
            if image.pixelColor(image_x, image_y).red() > 90
        }

    return metrics, glyph_masks


def _fcurve_axis_label_mask(text, metrics, glyph_masks):
    cursor_x = FCURVE_AXIS_LABEL_WIDTH - metrics.horizontalAdvance(text)
    mask = set()

    for character in text:
        for glyph_x, glyph_y in glyph_masks.get(character, ()):
            image_x = cursor_x + glyph_x
            if 0 <= image_x < FCURVE_AXIS_LABEL_WIDTH:
                mask.add((image_x, glyph_y))
        cursor_x += metrics.horizontalAdvance(character)

    return mask


def _fcurve_scale_state_module():
    state_module = sys.modules.get(FCURVE_AXIS_CACHE_STATE_MODULE)
    if state_module is None:
        state_module = types.ModuleType(FCURVE_AXIS_CACHE_STATE_MODULE)
        sys.modules[FCURVE_AXIS_CACHE_STATE_MODULE] = state_module
    return state_module


def _fcurve_axis_label_candidates(font):
    try:
        cache_key = font.toString()
    except Exception:
        cache_key = str(font)
    state_module = _fcurve_scale_state_module()
    persistent_cache = getattr(state_module, "axis_label_candidates", None)
    if not isinstance(persistent_cache, dict):
        persistent_cache = {}
        setattr(state_module, "axis_label_candidates", persistent_cache)

    cached = persistent_cache.get(cache_key)
    if cached is not None:
        return cached

    metrics, glyph_masks = _fcurve_axis_glyph_masks(font)
    labels = {"0", "-0"}

    for exponent in range(-10, 13):
        for mantissa in (1.0, 2.0, 5.0):
            increment = mantissa * (10.0 ** exponent)
            decimals = max(0, -int(math.floor(math.log10(increment))))
            for index in range(-20, 21):
                value = index * increment
                fixed_text = "%.*f" % (decimals, value)
                labels.add(fixed_text)
                if decimals > 0:
                    labels.add(fixed_text.rstrip("0").rstrip("."))
                    labels.add("%.*f" % (decimals + 1, value))

    candidates = []
    for text in labels:
        if text in ("", "-"):
            continue
        try:
            value = float(text)
        except Exception:
            continue
        candidates.append(
            (
                text,
                value,
                _fcurve_axis_label_mask(text, metrics, glyph_masks),
            )
        )

    persistent_cache[cache_key] = candidates
    FCURVE_AXIS_LABEL_CANDIDATE_CACHE[cache_key] = candidates
    return candidates


def _fcurve_axis_row_mask(snapshot, image_y):
    _image, raw, bytes_per_line = snapshot
    mask = set()
    first_y = image_y - 3

    for local_y in range(FCURVE_AXIS_LABEL_HEIGHT):
        sample_y = first_y + local_y
        if sample_y < 0:
            continue
        row_offset = sample_y * bytes_per_line
        for image_x in range(FCURVE_AXIS_LABEL_WIDTH):
            offset = row_offset + (image_x * 4)
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            if (
                red > 90
                and abs(red - green) <= 3
                and abs(green - blue) <= 3
            ):
                mask.add((image_x, local_y))

    return mask


def _fcurve_axis_value_per_pixel(graph_widget, snapshot, details=None):
    grid_rows, minor_grid_spacing = _fcurve_grid_layout(snapshot)
    if details is not None:
        details["grid_rows"] = list(grid_rows)
        details["minor_grid_spacing"] = minor_grid_spacing
    if len(grid_rows) < 2:
        if details is not None:
            details["reason"] = "fewer_than_two_major_grid_rows"
        return None

    label_candidates = _fcurve_axis_label_candidates(graph_widget.font())
    row_candidates = []
    for image_y in grid_rows:
        actual_mask = _fcurve_axis_row_mask(snapshot, image_y)
        scored = []
        for text, value, candidate_mask in label_candidates:
            union = actual_mask | candidate_mask
            score = float(len(actual_mask ^ candidate_mask)) / max(
                1.0,
                float(len(union)),
            )
            if score <= FCURVE_AXIS_OCR_MAX_SCORE:
                scored.append((score, value, text))

        row_candidates.append(
            sorted(scored)[:FCURVE_AXIS_OCR_CANDIDATES_PER_ROW]
        )

    best_sequence = None
    for first_index in range(len(grid_rows) - 1):
        for second_index in range(first_index + 1, len(grid_rows)):
            row_delta = float(grid_rows[second_index] - grid_rows[first_index])
            if row_delta <= 0.0:
                continue

            for first_candidate in row_candidates[first_index]:
                for second_candidate in row_candidates[second_index]:
                    value_per_image_pixel = (
                        first_candidate[1] - second_candidate[1]
                    ) / row_delta
                    if value_per_image_pixel <= 0.0:
                        continue

                    matched_candidates = []
                    for row_index, image_y in enumerate(grid_rows):
                        predicted_value = first_candidate[1] - (
                            (image_y - grid_rows[first_index])
                            * value_per_image_pixel
                        )
                        tolerance = max(
                            abs(value_per_image_pixel) * 0.05,
                            abs(predicted_value) * 0.000001,
                            0.000000000001,
                        )
                        matching = [
                            candidate
                            for candidate in row_candidates[row_index]
                            if abs(candidate[1] - predicted_value) <= tolerance
                        ]
                        if matching:
                            best_match = min(matching)
                            matched_candidates.append(
                                (
                                    image_y,
                                    best_match[0],
                                    best_match[1],
                                    best_match[2],
                                )
                            )

                    if len(matched_candidates) < 2:
                        continue

                    average_score = sum(
                        candidate[1]
                        for candidate in matched_candidates
                    ) / float(len(matched_candidates))
                    sequence = (
                        -len(matched_candidates),
                        average_score,
                        value_per_image_pixel,
                        matched_candidates,
                    )
                    if best_sequence is None or sequence[:2] < best_sequence[:2]:
                        best_sequence = sequence

    if best_sequence is None:
        if details is not None:
            details["reason"] = "no_consistent_axis_label_sequence"
        return None

    image_height = float(snapshot[0].height())
    image_scale_y = image_height / max(1.0, float(graph_widget.height()))
    value_per_pixel = best_sequence[2] * image_scale_y
    if details is not None:
        details.update(
            {
                "reason": "decoded_axis_labels",
                "match_count": -best_sequence[0],
                "average_score": best_sequence[1],
                "value_per_pixel": value_per_pixel,
                "matched_labels": [
                    {
                        "row": candidate[0],
                        "score": candidate[1],
                        "value": candidate[2],
                        "text": candidate[3],
                    }
                    for candidate in best_sequence[3]
                ],
            }
        )
    return value_per_pixel


def _fcurve_axis_grid_spacing(grid_rows):
    spacings = [
        float(grid_rows[index + 1] - grid_rows[index])
        for index in range(len(grid_rows) - 1)
        if grid_rows[index + 1] > grid_rows[index]
    ]
    if not spacings:
        return None
    return sum(spacings) / float(len(spacings))


def _fcurve_axis_cache():
    state_module = _fcurve_scale_state_module()
    cache = getattr(state_module, FCURVE_AXIS_CACHE_ATTR, None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(state_module, FCURVE_AXIS_CACHE_ATTR, cache)
    return cache


def _fcurve_axis_cache_key(graph_widget):
    try:
        return str(int(graph_widget.winId()))
    except Exception:
        return "widget_%d" % id(graph_widget)


def _fcurve_cache_dimensions_match(calibration, graph_widget, snapshot):
    image = snapshot[0]
    return (
        int(calibration.get("graph_width", 0)) == int(graph_widget.width())
        and int(calibration.get("graph_height", 0)) == int(graph_widget.height())
        and int(calibration.get("image_width", 0)) == int(image.width())
        and int(calibration.get("image_height", 0)) == int(image.height())
    )


def _fcurve_scale_cache_entry(graph_widget, snapshot):
    cache = _fcurve_axis_cache()
    cache_key = _fcurve_axis_cache_key(graph_widget)
    calibration = cache.get(cache_key)
    if calibration is None or not _fcurve_cache_dimensions_match(
        calibration,
        graph_widget,
        snapshot,
    ):
        image = snapshot[0]
        calibration = {
            "graph_width": int(graph_widget.width()),
            "graph_height": int(graph_widget.height()),
            "image_width": int(image.width()),
            "image_height": int(image.height()),
        }
        cache[cache_key] = calibration
    return calibration


def _store_fcurve_axis_scale(
    graph_widget,
    snapshot,
    grid_rows,
    value_per_pixel,
    minor_grid_spacing=None,
):
    spacing = _fcurve_axis_grid_spacing(grid_rows)
    if value_per_pixel is None or value_per_pixel <= 0.0:
        return

    calibration = _fcurve_scale_cache_entry(graph_widget, snapshot)
    calibration.update(
        {
            "grid_spacing": spacing,
            "minor_grid_spacing": minor_grid_spacing,
            "value_per_pixel": float(value_per_pixel),
        }
    )


def _cached_fcurve_axis_scale(
    graph_widget,
    snapshot,
    grid_rows,
    minor_grid_spacing=None,
):
    calibration = _fcurve_axis_cache().get(
        _fcurve_axis_cache_key(graph_widget)
    )
    if calibration is None:
        return None

    if not _fcurve_cache_dimensions_match(calibration, graph_widget, snapshot):
        return None

    cached_spacing = calibration.get("grid_spacing")
    current_spacing = _fcurve_axis_grid_spacing(grid_rows)
    if cached_spacing is not None and current_spacing is not None:
        if (
            abs(float(cached_spacing) - float(current_spacing))
            > FCURVE_AXIS_CACHE_SPACING_TOLERANCE
        ):
            return None

    cached_minor_spacing = calibration.get("minor_grid_spacing")
    if cached_minor_spacing is not None and minor_grid_spacing is not None:
        if (
            abs(float(cached_minor_spacing) - float(minor_grid_spacing))
            > FCURVE_MINOR_GRID_CACHE_SPACING_TOLERANCE
        ):
            return None

    try:
        value_per_pixel = float(calibration["value_per_pixel"])
        return value_per_pixel if value_per_pixel > 0.0 else None
    except Exception:
        return None


def _store_fcurve_horizontal_scale(
    graph_widget,
    snapshot,
    time_span,
    ticks_per_pixel,
):
    if time_span is None or ticks_per_pixel is None or ticks_per_pixel <= 0.0:
        return

    calibration = _fcurve_scale_cache_entry(graph_widget, snapshot)
    calibration.update(
        {
            "time_span_duration": abs(int(time_span[1]) - int(time_span[0])),
            "ticks_per_pixel": float(ticks_per_pixel),
        }
    )


def _cached_fcurve_horizontal_scale(graph_widget, snapshot, time_span):
    if time_span is None:
        return None

    calibration = _fcurve_axis_cache().get(
        _fcurve_axis_cache_key(graph_widget)
    )
    if calibration is None or not _fcurve_cache_dimensions_match(
        calibration,
        graph_widget,
        snapshot,
    ):
        return None

    current_duration = abs(int(time_span[1]) - int(time_span[0]))
    try:
        cached_duration = int(calibration["time_span_duration"])
        ticks_per_pixel = float(calibration["ticks_per_pixel"])
    except Exception:
        return None

    if (
        abs(current_duration - cached_duration)
        > FCURVE_TIME_SPAN_CACHE_TOLERANCE_TICKS
        or ticks_per_pixel <= 0.0
    ):
        return None
    return ticks_per_pixel


def _resolved_fcurve_value_per_pixel(
    graph_widget,
    snapshot,
    axis_value_per_pixel,
    axis_details,
    marker_value_per_pixel=None,
):
    grid_rows = axis_details.get("grid_rows", [])
    minor_grid_spacing = axis_details.get("minor_grid_spacing")
    axis_is_strong = (
        axis_value_per_pixel is not None
        and int(axis_details.get("match_count", 0))
        >= FCURVE_AXIS_STRONG_MIN_MATCHES
        and float(axis_details.get("average_score", 1.0))
        <= FCURVE_AXIS_STRONG_MAX_SCORE
    )

    if marker_value_per_pixel is not None:
        resolved = marker_value_per_pixel
        if axis_value_per_pixel is not None:
            ratio = axis_value_per_pixel / marker_value_per_pixel
            if 0.9 <= ratio <= 1.1:
                resolved = axis_value_per_pixel
        _store_fcurve_axis_scale(
            graph_widget,
            snapshot,
            grid_rows,
            resolved,
            minor_grid_spacing,
        )
        return resolved

    if axis_is_strong:
        _store_fcurve_axis_scale(
            graph_widget,
            snapshot,
            grid_rows,
            axis_value_per_pixel,
            minor_grid_spacing,
        )
        return axis_value_per_pixel

    cached = _cached_fcurve_axis_scale(
        graph_widget,
        snapshot,
        grid_rows,
        minor_grid_spacing,
    )
    if cached is not None:
        return cached
    return axis_value_per_pixel


def _fcurve_axis_fallback_value_per_pixel(graph_widget, snapshot):
    axis_details = {}
    axis_value_per_pixel = _fcurve_axis_value_per_pixel(
        graph_widget,
        snapshot,
        axis_details,
    )
    return _resolved_fcurve_value_per_pixel(
        graph_widget,
        snapshot,
        axis_value_per_pixel,
        axis_details,
    )


def _fcurve_rendered_scale(graph_widget, key_states):
    snapshot = _fcurve_graph_snapshot(graph_widget)
    if snapshot is None:
        return None

    time_span = _fcurve_time_span_ticks()
    grid_rows, minor_grid_spacing = _fcurve_grid_layout(snapshot)
    cached_value_per_pixel = _cached_fcurve_axis_scale(
        graph_widget,
        snapshot,
        grid_rows,
        minor_grid_spacing,
    )
    cached_ticks_per_pixel = _cached_fcurve_horizontal_scale(
        graph_widget,
        snapshot,
        time_span,
    )
    if (
        cached_ticks_per_pixel is not None
        and cached_value_per_pixel is not None
    ):
        return cached_ticks_per_pixel, cached_value_per_pixel

    unselected_marker_scale = _fcurve_unselected_marker_scale(
        graph_widget,
        key_states,
        snapshot,
    )
    if unselected_marker_scale is not None:
        ticks_per_pixel, value_per_pixel = unselected_marker_scale
        _store_fcurve_axis_scale(
            graph_widget,
            snapshot,
            grid_rows,
            value_per_pixel,
            minor_grid_spacing,
        )
        _store_fcurve_horizontal_scale(
            graph_widget,
            snapshot,
            time_span,
            ticks_per_pixel,
        )
        return ticks_per_pixel, value_per_pixel

    markers = _fcurve_dense_key_markers(snapshot)
    if len(markers) < 2:
        ticks_per_pixel = cached_ticks_per_pixel or _ticks_per_pixel(
            graph_widget,
            time_span,
        )
        value_per_pixel = cached_value_per_pixel
        if value_per_pixel is None:
            value_per_pixel = _fcurve_axis_fallback_value_per_pixel(
                graph_widget,
                snapshot,
            )
        _store_fcurve_horizontal_scale(
            graph_widget,
            snapshot,
            time_span,
            ticks_per_pixel,
        )
        return ticks_per_pixel, value_per_pixel

    image = snapshot[0]
    image_width = int(image.width())
    image_height = int(image.height())
    selected_curves = []
    seen_curve_ids = set()

    for state in key_states:
        fcurve = state["curve"]
        curve_id = id(fcurve)
        if curve_id in seen_curve_ids:
            continue
        seen_curve_ids.add(curve_id)
        selected_curves.append(fcurve)

    best_fit = None
    combinations_tested = 0
    for fcurve in selected_curves:
        try:
            keys = list(fcurve.Keys)
        except Exception:
            continue

        key_entries = []
        for index, key in enumerate(keys):
            try:
                time_ticks = int(key.Time.Get())
                if time_span is not None:
                    span_start, span_stop = sorted(time_span)
                    if time_ticks < span_start or time_ticks > span_stop:
                        continue
                key_entries.append(
                    (
                        float(key.Time.GetSecondDouble()),
                        _fcurve_key_value(fcurve, index),
                    )
                )
            except Exception:
                pass

        key_entries.sort(key=lambda entry: entry[0])
        maximum_fit_size = min(len(key_entries), len(markers))
        minimum_fit_size = 2 if maximum_fit_size == 2 else max(3, maximum_fit_size - 2)

        for fit_size in range(maximum_fit_size, minimum_fit_size - 1, -1):
            key_combination_count = math.comb(len(key_entries), fit_size)
            marker_combination_count = math.comb(len(markers), fit_size)
            fit_combination_count = key_combination_count * marker_combination_count
            remaining_budget = (
                FCURVE_MARKER_MAX_FIT_COMBINATIONS - combinations_tested
            )
            if fit_combination_count > remaining_budget:
                continue

            for key_subset in itertools.combinations(key_entries, fit_size):
                times = [entry[0] for entry in key_subset]
                values = [entry[1] for entry in key_subset]

                for marker_subset in itertools.combinations(markers, fit_size):
                    combinations_tested += 1
                    marker_xs = [float(marker[1]) for marker in marker_subset]
                    marker_ys = [float(marker[2]) for marker in marker_subset]
                    horizontal_fit = _linear_screen_fit(times, marker_xs)
                    vertical_fit = _linear_screen_fit(values, marker_ys)
                    if horizontal_fit is None or vertical_fit is None:
                        continue

                    pixels_per_second = horizontal_fit[0]
                    pixels_per_value = vertical_fit[0]
                    horizontal_residual = horizontal_fit[2]
                    vertical_residual = vertical_fit[2]
                    if pixels_per_second <= 0.000001 or pixels_per_value >= -0.000001:
                        continue
                    if (
                        horizontal_residual > FCURVE_MARKER_MAX_RESIDUAL
                        or vertical_residual > FCURVE_MARKER_MAX_RESIDUAL
                    ):
                        continue

                    score = horizontal_residual + vertical_residual
                    candidate = (
                        -fit_size,
                        score,
                        pixels_per_second,
                        pixels_per_value,
                    )
                    if best_fit is None or candidate[:2] < best_fit[:2]:
                        best_fit = candidate

    if best_fit is None:
        ticks_per_pixel = cached_ticks_per_pixel or _ticks_per_pixel(
            graph_widget,
            time_span,
        )
        value_per_pixel = cached_value_per_pixel
        if value_per_pixel is None:
            value_per_pixel = _fcurve_axis_fallback_value_per_pixel(
                graph_widget,
                snapshot,
            )
        _store_fcurve_horizontal_scale(
            graph_widget,
            snapshot,
            time_span,
            ticks_per_pixel,
        )
        return ticks_per_pixel, value_per_pixel

    pixels_per_second = best_fit[2]
    pixels_per_value = best_fit[3]
    image_scale_x = float(image_width) / max(1.0, float(graph_widget.width()))
    image_scale_y = float(image_height) / max(1.0, float(graph_widget.height()))
    local_pixels_per_second = pixels_per_second / image_scale_x
    local_pixels_per_value = pixels_per_value / image_scale_y
    if (
        local_pixels_per_second <= 0.000001
        or abs(local_pixels_per_value) <= 0.000001
    ):
        ticks_per_pixel = cached_ticks_per_pixel or _ticks_per_pixel(
            graph_widget,
            time_span,
        )
        value_per_pixel = cached_value_per_pixel
        if value_per_pixel is None:
            value_per_pixel = _fcurve_axis_fallback_value_per_pixel(
                graph_widget,
                snapshot,
            )
        _store_fcurve_horizontal_scale(
            graph_widget,
            snapshot,
            time_span,
            ticks_per_pixel,
        )
        return ticks_per_pixel, value_per_pixel

    ticks_per_pixel = float(FBTime.OneSecond.Get()) / local_pixels_per_second
    marker_value_per_pixel = 1.0 / abs(local_pixels_per_value)
    resolved_value_per_pixel = cached_value_per_pixel or marker_value_per_pixel
    _store_fcurve_axis_scale(
        graph_widget,
        snapshot,
        grid_rows,
        resolved_value_per_pixel,
        minor_grid_spacing,
    )
    _store_fcurve_horizontal_scale(
        graph_widget,
        snapshot,
        time_span,
        ticks_per_pixel,
    )

    return ticks_per_pixel, resolved_value_per_pixel


def _refresh_key_editor(widget):
    try:
        widget.update()
    except Exception:
        pass

    try:
        widget.repaint()
    except Exception:
        pass


def _camera_int(camera, attribute_name, fallback):
    try:
        value = int(getattr(camera, attribute_name, fallback) or fallback)
        if value > 0:
            return value
    except Exception:
        pass

    return fallback


def _font_metric_width(metrics, text):
    try:
        return metrics.horizontalAdvance(text)
    except Exception:
        return metrics.width(text)


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


def _local_axis_directions(model):
    try:
        rotation = _world_rotation(model)
        return {
            "x": _normalize(_rotate_xyz(GLOBAL_AXIS_DIRECTIONS["x"], rotation), GLOBAL_AXIS_DIRECTIONS["x"]),
            "y": _normalize(_rotate_xyz(GLOBAL_AXIS_DIRECTIONS["y"], rotation), GLOBAL_AXIS_DIRECTIONS["y"]),
            "z": _normalize(_rotate_xyz(GLOBAL_AXIS_DIRECTIONS["z"], rotation), GLOBAL_AXIS_DIRECTIONS["z"]),
        }
    except Exception:
        return {
            "x": list(GLOBAL_AXIS_DIRECTIONS["x"]),
            "y": list(GLOBAL_AXIS_DIRECTIONS["y"]),
            "z": list(GLOBAL_AXIS_DIRECTIONS["z"]),
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
        print("%s: could not read current camera; using world X/Y." % TOOL_NAME)
        return None, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]

    try:
        rotation = _world_rotation(camera)
        view_right = _normalize(_rotate_xyz([0.0, 0.0, 1.0], rotation), [0.0, 0.0, 1.0])
        view_up = _normalize(_rotate_xyz([0.0, 1.0, 0.0], rotation), [0.0, 1.0, 0.0])
        view_depth = _normalize(_rotate_xyz([1.0, 0.0, 0.0], rotation), [1.0, 0.0, 0.0])
        return camera, view_right, view_up, view_depth
    except Exception:
        print("%s: could not read camera rotation; using world X/Y." % TOOL_NAME)
        return camera, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]


def _orthographic_units_per_pixel(
    camera,
    model_states,
    view_right=None,
    view_up=None,
):
    try:
        viewport_width = max(int(getattr(camera, "CameraViewportWidth", 0) or 0), 1)
        viewport_height = max(int(getattr(camera, "CameraViewportHeight", 0) or 0), 1)
        rect = (0, 0, viewport_width, viewport_height)
        center = _selection_center(model_states)

        if view_right is None or view_up is None:
            rotation = _world_rotation(camera)
            view_right = _normalize(
                _rotate_xyz([0.0, 0.0, 1.0], rotation),
                [0.0, 0.0, 1.0],
            )
            view_up = _normalize(
                _rotate_xyz([0.0, 1.0, 0.0], rotation),
                [0.0, 1.0, 0.0],
            )

        matrix = FBMatrix()
        try:
            camera.GetCameraMatrix(matrix, FBCameraMatrixType.kFBModelViewProj, None)
        except TypeError:
            camera.GetCameraMatrix(matrix, FBCameraMatrixType.kFBModelViewProj)
        matrix_values = _fbmatrix_values(matrix)
        center_screen = _matrix_projection_candidate(
            center,
            rect,
            matrix_values,
            False,
        )
        if center_screen is None:
            return None

        sample_distance = 100.0
        samples = []
        for axis in (view_right, view_up):
            endpoint = _add(center, _mul(axis, sample_distance))
            endpoint_screen = _matrix_projection_candidate(
                endpoint,
                rect,
                matrix_values,
                False,
            )
            if endpoint_screen is None:
                continue

            delta_x = endpoint_screen[0] - center_screen[0]
            delta_y = endpoint_screen[1] - center_screen[1]
            pixel_distance = math.sqrt((delta_x * delta_x) + (delta_y * delta_y))
            if pixel_distance > 0.000001:
                samples.append(sample_distance / pixel_distance)

        if not samples:
            return None
        return sum(samples) / float(len(samples))
    except Exception:
        return None


def _viewport_units_per_pixel(
    camera,
    view_depth,
    model_states,
    view_right=None,
    view_up=None,
):
    if camera is None:
        return FALLBACK_WORLD_UNITS_PER_PIXEL * SENSITIVITY

    try:
        viewport_height = max(int(getattr(camera, "CameraViewportHeight", 0) or 0), 1)

        if getattr(camera, "Type", None) == FBCameraType.kFBCameraTypeOrthogonal:
            projected_units = _orthographic_units_per_pixel(
                camera,
                model_states,
                view_right,
                view_up,
            )
            if projected_units is not None and projected_units > 0.000001:
                return projected_units * SENSITIVITY

            ortho_zoom = _numeric_value(getattr(camera, "OrthoZoom", None), 0.0)
            if ortho_zoom > 0.000001:
                return max((2.0 * ortho_zoom / float(viewport_height)) * SENSITIVITY, 0.000001)

        camera_position = _world_translation(camera)
        to_selection = _sub(_selection_center(model_states), camera_position)
        depth = abs(_dot(to_selection, view_depth))

        if depth <= 0.000001:
            depth = max(_length(to_selection), 1.0)

        field_of_view = _numeric_value(getattr(camera, "FieldOfViewY", None), 0.0)
        if field_of_view <= 0.000001:
            field_of_view = _numeric_value(getattr(camera, "FieldOfView", None), 40.0)

        if field_of_view <= 0.000001:
            return FALLBACK_WORLD_UNITS_PER_PIXEL * SENSITIVITY

        world_height = 2.0 * depth * math.tan(math.radians(field_of_view) * 0.5)
        units = world_height / float(viewport_height)

        if units <= 0.000001:
            return FALLBACK_WORLD_UNITS_PER_PIXEL * SENSITIVITY

        return units * SENSITIVITY
    except Exception:
        print("%s: could not calculate viewport scale; using fixed scale." % TOOL_NAME)
        return FALLBACK_WORLD_UNITS_PER_PIXEL * SENSITIVITY


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


def _axis_overlay_line(camera, viewport_rect, center_world, axis_direction, axis_name):
    if camera is None or viewport_rect is None or center_world is None or axis_direction is None:
        return None

    try:
        axis_direction = _normalize(axis_direction, GLOBAL_AXIS_DIRECTIONS.get(axis_name, [1.0, 0.0, 0.0]))
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
                endpoint_screen = _camera_project_point_matrix(camera, endpoint_world, viewport_rect)

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


class AxisGuideOverlay(QtWidgets.QWidget):
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
        self.axis_lines_global = []
        self.axis_line_color = None
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

        self.set_viewport_rect(viewport_rect)

    def set_viewport_rect(self, viewport_rect):
        if viewport_rect is None:
            return

        self.viewport_rect = viewport_rect
        x, y, width, height = viewport_rect
        self.setGeometry(int(x), int(y), int(width), int(height))

    def set_overlay_data(self, axis_lines_global, axis_line_color, status_text):
        self.axis_lines_global = axis_lines_global or []
        self.axis_line_color = axis_line_color
        self.status_text = status_text or ""

        if not self.axis_lines_global and not self.status_text:
            self.hide()
            return

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


class AxisGuide(object):
    def __init__(self, camera, viewport_rect):
        self.camera = camera
        self.viewport_rect = viewport_rect
        self.overlay = None
        self.failed = False

    def cleanup(self):
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

    def update(self, axis_name, line_specs, status_text):
        if (not status_text and (axis_name is None or not line_specs)) or self.failed:
            self._hide_overlay()
            return

        if self.viewport_rect is None:
            return

        try:
            axis_lines = []

            if axis_name is not None and line_specs and self.camera is not None:
                for center, direction in line_specs:
                    axis_line = _axis_overlay_line(
                        self.camera,
                        self.viewport_rect,
                        center,
                        direction,
                        axis_name,
                    )

                    if axis_line is not None:
                        axis_lines.append(axis_line)

            if not axis_lines and not status_text:
                self._hide_overlay()
                return

            self._overlay().set_overlay_data(
                axis_lines,
                AXIS_GUIDE_COLORS.get(axis_name, (255, 255, 255, 230)),
                status_text,
            )
        except Exception:
            self.failed = True
            self.cleanup()
            print("%s: axis guide disabled after an update error." % TOOL_NAME)

    def _overlay(self):
        if self.overlay is None:
            self.overlay = AxisGuideOverlay(self.viewport_rect)

        return self.overlay

    def _hide_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.set_overlay_data([], None, "")
            except Exception:
                pass


class KeyMoveController(QtCore.QObject):
    def __init__(
        self,
        key_states,
        editor_widget,
        timeline_only,
        ticks_per_pixel,
        value_per_pixel,
    ):
        QtCore.QObject.__init__(self)
        self.key_states = key_states
        self.editor_widget = editor_widget
        self.timeline_only = bool(timeline_only)
        self.ticks_per_pixel = float(ticks_per_pixel)
        self.value_per_pixel = float(value_per_pixel)
        self.frame_ticks = _frame_ticks()
        self.start_cursor = _cursor_position()
        self.loop = None
        self.timer = None
        self.overlay = None
        self.armed = False
        self.accepted = False
        self.finished = False
        self.error_text = None
        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False
        self.event_filter_installed = False
        self.axis_lock = "x" if self.timeline_only else None
        self.numeric_text = ""
        self.numeric_key_states = {}
        self.cursor_override_active = False
        self.last_frame_offset = 0
        self.last_value_offset = 0.0
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)
        self.was_z_down = _is_key_down(VK_Z)
        self._refresh_numeric_key_states()

    def run(self):
        if QtWidgets.QApplication.instance() is None:
            return False

        self.loop = QtCore.QEventLoop()
        self.timer = QtCore.QTimer()
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(self)
        self.event_filter_installed = True
        self._show_overlay()
        self._push_move_cursor()

        try:
            _event_loop_exec(self.loop)
        finally:
            self._restore_move_cursor()

            if self.event_filter_installed:
                try:
                    app.removeEventFilter(self)
                except Exception:
                    pass
                self.event_filter_installed = False

            if self.timer is not None:
                self.timer.stop()
                self.timer = None

            if self.overlay is not None:
                try:
                    self.overlay.hide()
                    self.overlay.deleteLater()
                except Exception:
                    pass
                self.overlay = None

        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")

        return self.accepted

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()

            if (
                event_type == _qt_event_type("ContextMenu")
                and (
                    self.pending_finish is not None
                    or self.pending_finish_vk_code == VK_RBUTTON
                )
            ):
                event.accept()
                return True

            if not self.armed or self.finished:
                return False

            press_types = (
                _qt_event_type("MouseButtonPress"),
                _qt_event_type("MouseButtonDblClick"),
            )
            release_type = _qt_event_type("MouseButtonRelease")

            if event_type not in press_types and event_type != release_type:
                return False

            button = event.button()
            left_button = _qt_mouse_button("LeftButton")
            right_button = _qt_mouse_button("RightButton")

            if event_type in press_types:
                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON)
                    event.accept()
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON)
                    event.accept()
                    return True

                return False

            if (
                button == left_button
                and self.pending_finish_vk_code == VK_LBUTTON
            ):
                self._schedule_mouse_finish()
                event.accept()
                return True

            if (
                button == right_button
                and self.pending_finish_vk_code == VK_RBUTTON
            ):
                self._schedule_mouse_finish()
                event.accept()
                return True
        except Exception:
            self.error_text = traceback.format_exc()
            self.pending_finish = False
            self.pending_finish_vk_code = VK_RBUTTON
            self.pending_finish_cursor = _cursor_position()
            self._schedule_mouse_finish()

        return False

    def _begin_mouse_finish(self, accepted, vk_code):
        if self.pending_finish is not None or self.finished:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = _cursor_position()

    def _schedule_mouse_finish(self):
        if self.pending_finish is None or self.pending_finish_scheduled:
            return

        self.pending_finish_scheduled = True
        QtCore.QTimer.singleShot(
            MOUSE_FINISH_RELEASE_DELAY_MS,
            self._complete_pending_mouse_finish,
        )

    def _complete_pending_mouse_finish(self):
        if self.finished or self.pending_finish is None:
            return

        accepted = bool(self.pending_finish)
        cursor_position = self.pending_finish_cursor or _cursor_position()

        try:
            if accepted:
                frame_offset, value_offset = self._offsets_from_cursor(
                    cursor_position
                )
                self._set_key_offsets(frame_offset, value_offset, force=True)
        except Exception:
            accepted = False
            self.error_text = traceback.format_exc()

        self.pending_finish = None
        self._finish(accepted)

    def _overlay_rect(self):
        if not self.timeline_only:
            return _qt_widget_rect(self.editor_widget)

        current = self.editor_widget
        best_rect = _qt_widget_rect(current)

        while current is not None:
            try:
                rect = _qt_widget_rect(current)
                if current.isVisible() and rect[2] >= best_rect[2] and rect[3] >= 80:
                    best_rect = rect
                    break
                current = current.parentWidget()
            except Exception:
                break

        return best_rect

    def _show_overlay(self):
        try:
            self.overlay = AxisGuideOverlay(self._overlay_rect())
            self._update_overlay()
        except Exception:
            self.overlay = None

    def _push_move_cursor(self):
        app = QtWidgets.QApplication.instance()
        if app is None or self.cursor_override_active:
            return

        try:
            QtWidgets.QApplication.setOverrideCursor(_move_cursor())
            self.cursor_override_active = True
            app.processEvents()
        except Exception:
            self.cursor_override_active = False

    def _restore_move_cursor(self):
        if not self.cursor_override_active:
            return

        app = QtWidgets.QApplication.instance()

        try:
            QtWidgets.QApplication.restoreOverrideCursor()
        except Exception:
            pass

        self.cursor_override_active = False

        try:
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _refresh_axis_key_states(self):
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)
        self.was_z_down = _is_key_down(VK_Z)

    def _refresh_numeric_key_states(self):
        for _token, vk_code in NUMERIC_INPUT_KEYS:
            self.numeric_key_states[vk_code] = _is_key_down(vk_code)

    def _handle_axis_keys(self):
        x_down = _is_key_down(VK_X)
        y_down = _is_key_down(VK_Y)
        z_down = _is_key_down(VK_Z)

        if x_down and not self.was_x_down:
            if self.timeline_only:
                self.axis_lock = "x"
            else:
                self.axis_lock = None if self.axis_lock == "x" else "x"

        if y_down and not self.was_y_down and not self.timeline_only:
            self.axis_lock = None if self.axis_lock == "y" else "y"

        self.was_x_down = x_down
        self.was_y_down = y_down
        self.was_z_down = z_down

    def _typed_numeric_value(self):
        if self.numeric_text in ("", "-", ".", "-."):
            return None

        try:
            return float(self.numeric_text)
        except Exception:
            return None

    def _handle_numeric_token(self, token):
        if token == "backspace":
            self.numeric_text = self.numeric_text[:-1]
        elif token == ".":
            if "." not in self.numeric_text:
                if self.numeric_text in ("", "-"):
                    self.numeric_text += "0."
                else:
                    self.numeric_text += "."
        elif token == "-":
            if self.numeric_text.startswith("-"):
                self.numeric_text = self.numeric_text[1:]
            else:
                self.numeric_text = "-" + self.numeric_text
        else:
            self.numeric_text += token

    def _handle_numeric_keys(self):
        for token, vk_code in NUMERIC_INPUT_KEYS:
            is_down = _is_key_down(vk_code)
            was_down = self.numeric_key_states.get(vk_code, False)

            if is_down and not was_down:
                self._handle_numeric_token(token)

            self.numeric_key_states[vk_code] = is_down

    def _offsets_from_cursor(self, cursor_position):
        delta_x = float(cursor_position[0] - self.start_cursor[0])
        delta_y = float(cursor_position[1] - self.start_cursor[1])
        frame_offset = int(round(
            (delta_x * self.ticks_per_pixel) / float(self.frame_ticks)
        ))
        value_offset = -delta_y * self.value_per_pixel

        numeric_value = self._typed_numeric_value()
        if numeric_value is not None:
            if self.axis_lock == "y" and not self.timeline_only:
                frame_offset = 0
                value_offset = numeric_value
            else:
                frame_offset = int(round(numeric_value))
                value_offset = 0.0

        if self.timeline_only or self.axis_lock == "x":
            value_offset = 0.0
        elif self.axis_lock == "y":
            frame_offset = 0

        return frame_offset, value_offset

    def _set_key_offsets(self, frame_offset, value_offset, force=False):
        if (
            not force
            and frame_offset == self.last_frame_offset
            and abs(value_offset - self.last_value_offset) <= KEY_VALUE_CHANGE_EPSILON
        ):
            self._update_overlay()
            return

        tick_offset = int(frame_offset) * int(self.frame_ticks)
        previous_tick_offset = int(self.last_frame_offset) * int(self.frame_ticks)
        moving_right = tick_offset > previous_tick_offset
        ordered_states = sorted(
            self.key_states,
            key=lambda state: state["original_time_ticks"],
            reverse=moving_right,
        )

        for state in ordered_states:
            state["key"].Time = FBTime(state["original_time_ticks"] + tick_offset)

        for state in self.key_states:
            state["key"].Value = state["original_value"] + float(value_offset)
            try:
                state["key"].Selected = state["original_selected"]
            except Exception:
                pass

        self.last_frame_offset = int(frame_offset)
        self.last_value_offset = float(value_offset)
        _refresh_scene_after_fcurve_edit()
        _refresh_key_editor(self.editor_widget)
        self._update_overlay()

    def _status_text(self):
        frame_text = "%+d frame%s" % (
            self.last_frame_offset,
            "" if abs(self.last_frame_offset) == 1 else "s",
        )

        if self.timeline_only or self.axis_lock == "x":
            return "Move keys %s" % frame_text

        value_text = "%+.3f value" % self.last_value_offset
        if self.axis_lock == "y":
            return "Move keys %s" % value_text

        return "Move keys %s, %s" % (frame_text, value_text)

    def _update_overlay(self):
        if self.overlay is None:
            return

        axis_name = "x" if self.timeline_only else self.axis_lock
        axis_lines = []
        axis_color = None

        if axis_name == "x":
            axis_lines = [
                (self.start_cursor, (self.start_cursor[0] + 1, self.start_cursor[1]))
            ]
            axis_color = AXIS_GUIDE_COLORS["x"]
        elif axis_name == "y":
            axis_lines = [
                (self.start_cursor, (self.start_cursor[0], self.start_cursor[1] + 1))
            ]
            axis_color = AXIS_GUIDE_COLORS["y"]

        try:
            self.overlay.set_overlay_data(
                axis_lines,
                axis_color,
                self._status_text(),
            )
        except Exception:
            pass

    def _restore_original_keys(self):
        self._set_key_offsets(0, 0.0, force=True)

    def _finish(self, accepted):
        if self.finished:
            return

        self.accepted = bool(accepted)
        self.finished = True

        if not self.accepted:
            try:
                self._restore_original_keys()
            except Exception:
                if self.error_text is None:
                    self.error_text = traceback.format_exc()

        if self.timer is not None:
            self.timer.stop()

        if self.loop is not None:
            self.loop.quit()

    def _tick(self):
        try:
            left_down = _is_key_down(VK_LBUTTON)
            right_down = _is_key_down(VK_RBUTTON)
            escape_down = _is_key_down(VK_ESCAPE)

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self.start_cursor = _cursor_position()
                    self.was_left_down = False
                    self.was_right_down = False
                    self.was_escape_down = escape_down
                    self._refresh_axis_key_states()
                    self._refresh_numeric_key_states()
                    self._update_overlay()
                return

            if self.pending_finish is not None:
                if (
                    self.pending_finish_vk_code is not None
                    and not _is_key_down(self.pending_finish_vk_code)
                ):
                    self._schedule_mouse_finish()
                return

            if escape_down and not self.was_escape_down:
                self._finish(False)
                return

            if right_down and not self.was_right_down:
                self._begin_mouse_finish(False, VK_RBUTTON)
                return

            if left_down and not self.was_left_down:
                self._begin_mouse_finish(True, VK_LBUTTON)
                return

            self._handle_axis_keys()
            self._handle_numeric_keys()
            frame_offset, value_offset = self._offsets_from_cursor(_cursor_position())
            self._set_key_offsets(frame_offset, value_offset)

            self.was_left_down = left_down
            self.was_right_down = right_down
            self.was_escape_down = escape_down
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


class MouseMoveController(QtCore.QObject):
    def __init__(
        self,
        model_states,
        hik_contexts,
        view_right,
        view_up,
        units_per_pixel,
        camera,
        viewport_rect,
    ):
        QtCore.QObject.__init__(self)
        self.model_states = model_states
        self.hik_contexts = hik_contexts
        self.view_right = view_right
        self.view_up = view_up
        self.units_per_pixel = units_per_pixel
        self.start_cursor = _cursor_position()
        self.loop = None
        self.timer = None
        self.axis_guide = AxisGuide(camera, viewport_rect)
        self.armed = False
        self.accepted = False
        self.finished = False
        self.error_text = None
        self.pending_finish = None
        self.pending_finish_vk_code = None
        self.pending_finish_cursor = None
        self.pending_finish_scheduled = False
        self.event_filter_installed = False
        self.axis_lock = None
        self.axis_space = "global"
        self.numeric_text = ""
        self.numeric_direction = list(self.view_right)
        self.numeric_key_states = {}
        self.cursor_override_active = False
        self.last_target_positions = [
            list(state["original"])
            for state in self.model_states
        ]
        self.was_left_down = _is_key_down(VK_LBUTTON)
        self.was_right_down = _is_key_down(VK_RBUTTON)
        self.was_escape_down = _is_key_down(VK_ESCAPE)
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)
        self.was_z_down = _is_key_down(VK_Z)
        self._refresh_numeric_key_states()

    def run(self):
        if QtWidgets.QApplication.instance() is None:
            FBMessageBox(TOOL_NAME, "Could not find the MotionBuilder Qt application.", "OK")
            return False

        self.loop = QtCore.QEventLoop()
        self.timer = QtCore.QTimer()
        _set_precise_timer(self.timer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(self)
        self.event_filter_installed = True

        self._push_move_cursor()

        try:
            _event_loop_exec(self.loop)
        finally:
            for context in self.hik_contexts:
                _set_hik_reach_values(context, False)

            self._restore_move_cursor()

            if self.event_filter_installed:
                try:
                    app.removeEventFilter(self)
                except Exception:
                    pass
                self.event_filter_installed = False

            if self.timer is not None:
                self.timer.stop()
                self.timer = None

            self.axis_guide.cleanup()


        if self.error_text:
            FBMessageBox(TOOL_NAME + " Error", self.error_text, "OK")

        return self.accepted

    def eventFilter(self, watched, event):
        try:
            event_type = event.type()

            if (
                event_type == _qt_event_type("ContextMenu")
                and (
                    self.pending_finish is not None
                    or self.pending_finish_vk_code == VK_RBUTTON
                )
            ):
                event.accept()
                return True

            if not self.armed or self.finished:
                return False

            press_types = (
                _qt_event_type("MouseButtonPress"),
                _qt_event_type("MouseButtonDblClick"),
            )
            release_type = _qt_event_type("MouseButtonRelease")

            if event_type not in press_types and event_type != release_type:
                return False

            button = event.button()
            left_button = _qt_mouse_button("LeftButton")
            right_button = _qt_mouse_button("RightButton")

            if event_type in press_types:
                if button == left_button:
                    self._begin_mouse_finish(True, VK_LBUTTON)
                    event.accept()
                    return True

                if button == right_button:
                    self._begin_mouse_finish(False, VK_RBUTTON)
                    event.accept()
                    return True

                return False

            if (
                button == left_button
                and self.pending_finish_vk_code == VK_LBUTTON
            ):
                self._schedule_mouse_finish()
                event.accept()
                return True

            if (
                button == right_button
                and self.pending_finish_vk_code == VK_RBUTTON
            ):
                self._schedule_mouse_finish()
                event.accept()
                return True
        except Exception:
            self.error_text = traceback.format_exc()
            self.pending_finish = False
            self.pending_finish_vk_code = VK_RBUTTON
            self.pending_finish_cursor = _cursor_position()
            self._schedule_mouse_finish()

        return False

    def _begin_mouse_finish(self, accepted, vk_code):
        if self.pending_finish is not None or self.finished:
            return

        self.pending_finish = bool(accepted)
        self.pending_finish_vk_code = vk_code
        self.pending_finish_cursor = _cursor_position()

    def _schedule_mouse_finish(self):
        if self.pending_finish is None or self.pending_finish_scheduled:
            return

        self.pending_finish_scheduled = True
        QtCore.QTimer.singleShot(
            MOUSE_FINISH_RELEASE_DELAY_MS,
            self._complete_pending_mouse_finish,
        )

    def _complete_pending_mouse_finish(self):
        if self.finished or self.pending_finish is None:
            return

        accepted = bool(self.pending_finish)
        cursor_position = self.pending_finish_cursor or _cursor_position()

        try:
            if accepted:
                self._set_models_to_offset(cursor_position)
        except Exception:
            accepted = False
            self.error_text = traceback.format_exc()

        self.pending_finish = None
        self._finish(accepted)

    def _push_move_cursor(self):
        app = QtWidgets.QApplication.instance()
        if app is None or self.cursor_override_active:
            return

        try:
            QtWidgets.QApplication.setOverrideCursor(_move_cursor())
            self.cursor_override_active = True
            app.processEvents()
        except Exception:
            self.cursor_override_active = False

    def _restore_move_cursor(self):
        if not self.cursor_override_active:
            return

        app = QtWidgets.QApplication.instance()

        try:
            QtWidgets.QApplication.restoreOverrideCursor()
        except Exception:
            pass

        self.cursor_override_active = False

        try:
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _current_multiplier(self):
        if _is_key_down(VK_CONTROL):
            return SLOW_MULTIPLIER
        if _is_key_down(VK_SHIFT):
            return FAST_MULTIPLIER
        return 1.0

    def _refresh_axis_key_states(self):
        self.was_x_down = _is_key_down(VK_X)
        self.was_y_down = _is_key_down(VK_Y)
        self.was_z_down = _is_key_down(VK_Z)

    def _refresh_numeric_key_states(self):
        for _token, vk_code in NUMERIC_INPUT_KEYS:
            self.numeric_key_states[vk_code] = _is_key_down(vk_code)

    def _toggle_axis_lock(self, axis_name):
        if axis_name != self.axis_lock:
            self.axis_lock = axis_name
            self.axis_space = "global"
        elif self.axis_space == "global":
            self.axis_space = "local"
        else:
            self.axis_space = "global"

        print("%s: locked %s axis in %s space." % (
            TOOL_NAME,
            self.axis_lock.upper(),
            self.axis_space,
        ))

    def _handle_axis_keys(self):
        axis_keys = (
            ("x", VK_X, "was_x_down"),
            ("y", VK_Y, "was_y_down"),
            ("z", VK_Z, "was_z_down"),
        )

        for axis_name, vk_code, state_name in axis_keys:
            is_down = _is_key_down(vk_code)
            was_down = getattr(self, state_name)

            if is_down and not was_down:
                self._toggle_axis_lock(axis_name)

            setattr(self, state_name, is_down)

    def _typed_numeric_distance(self):
        if self.numeric_text in ("", "-", ".", "-."):
            return None

        try:
            return float(self.numeric_text)
        except Exception:
            return None

    def _handle_numeric_token(self, token):
        previous_text = self.numeric_text

        if token == "backspace":
            self.numeric_text = self.numeric_text[:-1]
        elif token == ".":
            if "." not in self.numeric_text:
                if self.numeric_text in ("", "-"):
                    self.numeric_text += "0."
                else:
                    self.numeric_text += "."
        elif token == "-":
            if self.numeric_text.startswith("-"):
                self.numeric_text = self.numeric_text[1:]
            else:
                self.numeric_text = "-" + self.numeric_text
        else:
            self.numeric_text += token

        if self.numeric_text == previous_text:
            return

        if self._typed_numeric_distance() is None:
            if self.numeric_text:
                print("%s: numeric distance %s." % (TOOL_NAME, self.numeric_text))
            else:
                print("%s: numeric distance cleared." % TOOL_NAME)
            return

        print("%s: numeric distance %s." % (TOOL_NAME, self.numeric_text))

    def _handle_numeric_keys(self):
        for token, vk_code in NUMERIC_INPUT_KEYS:
            is_down = _is_key_down(vk_code)
            was_down = self.numeric_key_states.get(vk_code, False)

            if is_down and not was_down:
                self._handle_numeric_token(token)

            self.numeric_key_states[vk_code] = is_down

    def _axis_direction_for_state(self, state):
        if self.axis_lock is None:
            return None

        if self.axis_space == "local":
            return state["local_axes"].get(self.axis_lock)

        return GLOBAL_AXIS_DIRECTIONS.get(self.axis_lock)

    def _constrained_offset(self, offset, state):
        axis_direction = self._axis_direction_for_state(state)
        if axis_direction is None:
            return offset

        axis_direction = _normalize(axis_direction, GLOBAL_AXIS_DIRECTIONS[self.axis_lock])
        return _mul(axis_direction, _dot(offset, axis_direction))

    def _numeric_offset_for_state(self, raw_offset, state):
        distance = self._typed_numeric_distance()
        if distance is None:
            return self._constrained_offset(raw_offset, state)

        axis_direction = self._axis_direction_for_state(state)
        if axis_direction is not None:
            axis_direction = _normalize(axis_direction, GLOBAL_AXIS_DIRECTIONS[self.axis_lock])
            return _mul(axis_direction, distance)

        direction = _normalize(raw_offset, self.numeric_direction)
        return _mul(direction, distance)

    def _axis_guide_lines(self, target_positions):
        if self.axis_lock is None:
            return []

        if self.axis_space == "local":
            return [
                (target_positions[index], state["local_axes"].get(self.axis_lock))
                for index, state in enumerate(self.model_states)
            ]

        axis_direction = GLOBAL_AXIS_DIRECTIONS.get(self.axis_lock)
        return [(_points_center(target_positions), axis_direction)]

    def _format_distance(self, value):
        if abs(value) < 0.0005:
            value = 0.0

        return "%.3f" % value

    def _xyz_status(self, values):
        return "X %s  Y %s  Z %s" % (
            self._format_distance(values[0]),
            self._format_distance(values[1]),
            self._format_distance(values[2]),
        )

    def _locked_status_distance(self, target_positions):
        distances = []

        for index, state in enumerate(self.model_states):
            axis_direction = self._axis_direction_for_state(state)
            if axis_direction is None:
                continue

            axis_direction = _normalize(axis_direction, GLOBAL_AXIS_DIRECTIONS[self.axis_lock])
            offset = _sub(target_positions[index], state["original"])
            distances.append(_dot(offset, axis_direction))

        if not distances:
            return 0.0

        return sum(distances) / float(len(distances))

    def _status_text(self, target_positions):
        original_center = _selection_center(self.model_states)
        target_center = _points_center(target_positions)
        center_delta = _sub(target_center, original_center)
        xyz_text = self._xyz_status(center_delta)

        if self.axis_lock is None:
            return "Move %s" % xyz_text

        return "Move %s along %s %s | %s" % (
            self._format_distance(self._locked_status_distance(target_positions)),
            self.axis_space,
            self.axis_lock.upper(),
            xyz_text,
        )

    def _target_positions_match_last(self, target_positions):
        if len(target_positions) != len(self.last_target_positions):
            return False

        for index, target_position in enumerate(target_positions):
            if _vectors_differ(
                target_position,
                self.last_target_positions[index],
                TARGET_CHANGE_EPSILON,
            ):
                return False

        return True

    def _apply_target_positions(self, target_positions):
        for context in self.hik_contexts:
            _apply_fk_states(_baseline_states_for_previous(context))
            _set_hik_reach_values(context, True)

        for index, state in enumerate(self.model_states):
            _set_world_translation(state["model"], target_positions[index])

        _evaluate_scene()

        if not self.hik_contexts:
            return

        solved_by_context = [
            (context, _capture_changed_fk_states(context))
            for context in self.hik_contexts
        ]

        for context, changed_states in solved_by_context:
            _set_hik_reach_values(context, False)
            _apply_fk_states(changed_states)
            context["previous_changed"] = changed_states

        _resolve_and_evaluate_scene()

    def _set_models_to_offset(self, cursor_position):
        start_x, start_y = self.start_cursor
        cursor_x, cursor_y = cursor_position
        delta_x = float(cursor_x - start_x)
        delta_y = float(cursor_y - start_y)
        units = self.units_per_pixel * self._current_multiplier()

        offset = _add(
            _mul(self.view_right, delta_x * units),
            _mul(self.view_up, -delta_y * units),
        )

        if _length(offset) > 0.000001:
            self.numeric_direction = _normalize(offset, self.numeric_direction)

        target_positions = []

        for state in self.model_states:
            constrained_offset = self._numeric_offset_for_state(offset, state)
            target_position = _add(state["original"], constrained_offset)
            target_positions.append(target_position)

        if not self._target_positions_match_last(target_positions):
            self._apply_target_positions(target_positions)
            self.last_target_positions = [list(position) for position in target_positions]

        self.axis_guide.update(
            self.axis_lock,
            self._axis_guide_lines(target_positions),
            self._status_text(target_positions),
        )

    def _restore_original_positions(self):
        for context in self.hik_contexts:
            _apply_fk_states(context["fk_baselines"])
            _set_hik_reach_values(context, True)

        for state in self.model_states:
            _set_world_translation(state["model"], state["original"])

        _evaluate_scene()

        for context in self.hik_contexts:
            _set_hik_reach_values(context, False)
            _apply_fk_states(context["fk_baselines"])
            context["previous_changed"] = []

        if self.hik_contexts:
            _resolve_and_evaluate_scene()

    def _finish(self, accepted):
        if self.finished:
            return

        self.accepted = accepted
        self.finished = True

        if not accepted:
            self._restore_original_positions()

        if self.timer is not None:
            self.timer.stop()

        if self.loop is not None:
            self.loop.quit()

    def _tick(self):
        try:
            left_down = _is_key_down(VK_LBUTTON)
            right_down = _is_key_down(VK_RBUTTON)
            escape_down = _is_key_down(VK_ESCAPE)

            if not self.armed:
                if not left_down and not right_down:
                    self.armed = True
                    self.start_cursor = _cursor_position()
                    self.was_left_down = False
                    self.was_right_down = False
                    self.was_escape_down = escape_down
                    self._refresh_axis_key_states()
                    self._refresh_numeric_key_states()
                return

            if self.pending_finish is not None:
                if (
                    self.pending_finish_vk_code is not None
                    and not _is_key_down(self.pending_finish_vk_code)
                ):
                    self._schedule_mouse_finish()
                return

            if escape_down and not self.was_escape_down:
                self._finish(False)
                return

            if right_down and not self.was_right_down:
                self._begin_mouse_finish(False, VK_RBUTTON)
                return

            if left_down and not self.was_left_down:
                self._begin_mouse_finish(True, VK_LBUTTON)
                return

            self._handle_axis_keys()
            self._handle_numeric_keys()
            self._set_models_to_offset(_cursor_position())

            self.was_left_down = left_down
            self.was_right_down = right_down
            self.was_escape_down = escape_down
        except Exception:
            self.error_text = traceback.format_exc()
            self._finish(False)


def move_selected_along_camera_view_modal():
    models = _selected_transformable_models()

    if not models:
        return

    _evaluate_scene()

    model_states = [
        {
            "model": model,
            "original": _world_translation(model),
            "local_axes": _local_axis_directions(model),
        }
        for model in models
    ]
    hik_contexts = _build_hik_move_contexts(model_states)

    camera, view_right, view_up, view_depth = _camera_view_context()
    units_per_pixel = _viewport_units_per_pixel(
        camera,
        view_depth,
        model_states,
        view_right,
        view_up,
    )
    viewport_rect = _viewport_global_rect(camera)

    controller = MouseMoveController(
        model_states,
        hik_contexts,
        view_right,
        view_up,
        units_per_pixel,
        camera,
        viewport_rect,
    )

    if controller.run():
        print("%s accepted." % TOOL_NAME)
        return

    print("%s canceled. Original position restored." % TOOL_NAME)


def _move_selected_keys_in_editor(editor_widget, timeline_only):
    curves = _scene_fcurves() if timeline_only else _displayed_fcurves()
    key_states = _selected_key_states(curves)

    if not key_states:
        return

    time_span = (
        _timeline_time_span_ticks()
        if timeline_only
        else _fcurve_time_span_ticks()
    )
    ticks_per_pixel = _ticks_per_pixel(editor_widget, time_span)
    value_per_pixel = (
        0.0
        if timeline_only
        else _fcurve_value_per_pixel(curves, editor_widget)
    )
    if not timeline_only:
        rendered_scale = _fcurve_rendered_scale(editor_widget, key_states)
        if rendered_scale is not None:
            rendered_ticks_per_pixel, rendered_value_per_pixel = rendered_scale
            if rendered_ticks_per_pixel is not None:
                ticks_per_pixel = rendered_ticks_per_pixel
            if rendered_value_per_pixel is not None:
                value_per_pixel = rendered_value_per_pixel

    controller = KeyMoveController(
        key_states,
        editor_widget,
        timeline_only,
        ticks_per_pixel,
        value_per_pixel,
    )

    if controller.run():
        print(
            "%s: moved %d selected key(s)."
            % (TOOL_NAME, len(key_states))
        )
        return

    print("%s: key movement canceled." % TOOL_NAME)


def move_selected_along_camera_view():
    fcurve_graph_widget = _fcurve_graph_widget_for_cursor()
    if fcurve_graph_widget is not None:
        _move_selected_keys_in_editor(fcurve_graph_widget, False)
        return

    timeline_widget = _timeline_widget_for_cursor()
    if timeline_widget is not None:
        _move_selected_keys_in_editor(timeline_widget, True)
        return

    move_selected_along_camera_view_modal()


def run_with_error_dialog():
    try:
        move_selected_along_camera_view()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
