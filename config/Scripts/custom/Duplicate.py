"""Context-sensitive duplicate command for MotionBuilder."""

from __future__ import print_function

import os
import sys
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import (
    FBFCurveEditorUtility,
    FBGetLastSelectedModel,
    FBGetSelectedModels,
    FBMessageBox,
    FBModel,
    FBModelList,
    FBPlayerControl,
    FBSceneChangeType,
    FBSystem,
    FBTake,
    FBTime,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Duplicate"
MOVE_SCRIPT_NAME = "MoveSelectedAlongCameraView.py"

CONTEXT_VIEWER = "viewer"
CONTEXT_FCURVES = "fcurves"
CONTEXT_NAVIGATOR = "navigator"
CONTEXT_OTHER = "other"

FOCUS_SERVICE_ATTR = "_duplicate_navigator_focus_service"

FCURVE_TOKENS = (
    "fcurvelayerview",
    "fcurvepropertyview",
    "fcurves",
    "curvelayout",
)

VIEWER_TOKENS = (
    "viewerwithrightbar",
    "toolindex_1 viewer",
)

NAVIGATOR_TOKENS = (
    "navigator",
)

KEY_ATTRIBUTE_ACCESSORS = (
    ("tangent_break", "KeyGetTangentBreak", "KeySetTangentBreak"),
    ("tangent_clamp_mode", "KeyGetTangentClampMode", "KeySetTangentClampMode"),
    (
        "tangent_constant_mode",
        "KeyGetTangentConstantMode",
        "KeySetTangentConstantMode",
    ),
    ("tangent_custom_index", "KeyGetTangentCustomIndex", "KeySetTangentCustomIndex"),
    ("tcb_bias", "KeyGetTCBBias", "KeySetTCBBias"),
    ("tcb_continuity", "KeyGetTCBContinuity", "KeySetTCBContinuity"),
    ("tcb_tension", "KeyGetTCBTension", "KeySetTCBTension"),
    ("left_bezier_tangent", "KeyGetLeftBezierTangent", "KeySetLeftBezierTangent"),
    ("right_bezier_tangent", "KeyGetRightBezierTangent", "KeySetRightBezierTangent"),
    ("left_derivative", "KeyGetLeftDerivative", "KeySetLeftDerivative"),
    ("right_derivative", "KeyGetRightDerivative", "KeySetRightDerivative"),
    (
        "left_tangent_weight",
        "KeyGetLeftTangentWeight",
        "KeySetLeftTangentWeight",
    ),
    (
        "right_tangent_weight",
        "KeyGetRightTangentWeight",
        "KeySetRightTangentWeight",
    ),
    (
        "tangent_weight_mode",
        "KeyGetTangentWeightMode",
        "KeySetTangentWeightMode",
    ),
)


def _script_directory():
    candidates = [globals().get("__file__")]
    code = getattr(_script_directory, "__code__", None)
    if code is not None:
        candidates.append(getattr(code, "co_filename", None))

    for candidate in candidates:
        if not candidate or str(candidate).startswith("<"):
            continue
        directory = os.path.dirname(os.path.abspath(str(candidate)))
        if os.path.isdir(directory):
            return directory

    for directory in sys.path:
        if not directory:
            continue
        for candidate in (
            os.path.join(directory, "Duplicate.py"),
            os.path.join(directory, "custom", "Duplicate.py"),
        ):
            if os.path.isfile(candidate):
                return os.path.dirname(os.path.abspath(candidate))

    raise RuntimeError("Could not locate the Duplicate script folder.")


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

        for getter_name in ("objectName", "accessibleName", "windowTitle", "toolTip"):
            try:
                value = getattr(current, getter_name)()
            except Exception:
                value = ""
            if value:
                parts.append(str(value))

        try:
            if isinstance(current, QtWidgets.QTabWidget):
                parts.append(str(current.tabText(current.currentIndex())))
        except Exception:
            pass

        try:
            current = current.parentWidget()
        except Exception:
            current = None

    return " ".join(parts).lower()


def _context_for_widget(widget):
    description = _widget_description(widget)

    if any(token in description for token in FCURVE_TOKENS):
        return CONTEXT_FCURVES
    if any(token in description for token in VIEWER_TOKENS):
        return CONTEXT_VIEWER
    if any(token in description for token in NAVIGATOR_TOKENS):
        return CONTEXT_NAVIGATOR
    return CONTEXT_OTHER


def _visible_editor_context(app, global_position):
    matches = []

    for widget in app.allWidgets():
        try:
            if not widget.isVisible():
                continue
            context = _context_for_widget(widget)
            if context == CONTEXT_OTHER:
                continue
            top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
            rect = QtCore.QRect(top_left, widget.size())
            if rect.contains(global_position):
                matches.append((rect.width() * rect.height(), context))
        except Exception:
            pass

    if not matches:
        return CONTEXT_OTHER

    matches.sort(key=lambda match: match[0])
    return matches[0][1]


def _detect_context():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return CONTEXT_OTHER

    cursor_position = QtGui.QCursor.pos()
    try:
        widget = app.widgetAt(cursor_position)
    except Exception:
        widget = None

    if widget is not None:
        context = _context_for_widget(widget)
        if context != CONTEXT_OTHER:
            return context

    context = _visible_editor_context(app, cursor_position)
    if context != CONTEXT_OTHER:
        return context

    if widget is not None:
        return CONTEXT_OTHER
    return _context_for_widget(app.focusWidget())


def _component_key(component):
    if component is None:
        return None

    for attribute_name in ("LongName", "Name"):
        try:
            value = str(getattr(component, attribute_name))
        except Exception:
            value = ""
        if value:
            return "%s:%s" % (type(component).__name__, value)

    return "%s:%s" % (type(component).__name__, repr(component))


class _NavigatorFocusService(object):
    def __init__(self):
        self.scene = FBSystem().Scene
        self.active_kind = None
        self.active_component_key = None
        self.started = False
        self._scene_change_callback = self._on_scene_change
        self._take_change_callback = self._on_take_change

    def start(self):
        if self.started:
            return
        self.scene.OnChange.Add(self._scene_change_callback)
        self.scene.OnTakeChange.Add(self._take_change_callback)
        self.started = True

    def stop(self):
        if not self.started:
            return
        try:
            self.scene.OnChange.Remove(self._scene_change_callback)
        except Exception:
            pass
        try:
            self.scene.OnTakeChange.Remove(self._take_change_callback)
        except Exception:
            pass
        self.started = False

    def _remember(self, component):
        if isinstance(component, FBTake):
            self.active_kind = "take"
        elif isinstance(component, FBModel):
            self.active_kind = "model"
        else:
            return

        self.active_component_key = _component_key(component)

    def _on_scene_change(self, control, event):
        try:
            event_type = event.Type
            relevant_types = (
                FBSceneChangeType.kFBSceneChangeFocus,
                FBSceneChangeType.kFBSceneChangeHardSelect,
                FBSceneChangeType.kFBSceneChangeReSelect,
                FBSceneChangeType.kFBSceneChangeSelect,
                FBSceneChangeType.kFBSceneChangeActivate,
            )
            if event_type not in relevant_types:
                return

            for attribute_name in ("Component", "ChildComponent"):
                try:
                    component = getattr(event, attribute_name)
                except Exception:
                    component = None
                if isinstance(component, (FBTake, FBModel)):
                    self._remember(component)
                    return
        except Exception:
            pass

    def _on_take_change(self, control, event):
        try:
            self._remember(FBSystem().CurrentTake)
        except Exception:
            pass


def _focus_service():
    service = getattr(builtins, FOCUS_SERVICE_ATTR, None)
    if service is not None:
        return service

    service = _NavigatorFocusService()
    service.start()
    setattr(builtins, FOCUS_SERVICE_ATTR, service)
    return service


def _model_key(model):
    try:
        return model.UniqueName
    except Exception:
        return repr(model)


def _has_selected_parent(model, selected_keys):
    try:
        parent = model.Parent
    except Exception:
        return False

    while parent is not None:
        if _model_key(parent) in selected_keys:
            return True
        try:
            parent = parent.Parent
        except Exception:
            break

    return False


def _get_selected_top_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)

    selected = list(selected_models)
    selected_keys = set(_model_key(model) for model in selected)
    return [
        model
        for model in selected
        if not _has_selected_parent(model, selected_keys)
    ]


def _active_model():
    try:
        model = FBGetLastSelectedModel()
    except Exception:
        model = None

    if model is None:
        return None

    try:
        if not bool(model.Selected):
            return None
    except Exception:
        return None

    return model


def _selected_takes():
    result = []

    for take in FBSystem().Scene.Takes:
        try:
            if bool(take.Selected):
                result.append(take)
        except Exception:
            pass

    return result


def _same_component(left, right):
    if left is None or right is None:
        return False
    try:
        if left == right:
            return True
    except Exception:
        pass
    return _component_key(left) == _component_key(right)


def _navigator_active_kind():
    service = _focus_service()
    if service.active_kind in ("model", "take"):
        return service.active_kind

    selected_takes = _selected_takes()
    active_model = _active_model()
    if selected_takes and active_model is not None:
        return None

    current_take = FBSystem().CurrentTake
    if any(_same_component(take, current_take) for take in selected_takes):
        return "take"

    if active_model is not None:
        return "model"

    if selected_takes:
        return "take"
    return None


def _duplicate_selected_models(require_active=False):
    if require_active and _active_model() is None:
        FBMessageBox(
            TOOL_NAME,
            "Click an object to make it active before duplicating in Navigator.",
            "OK",
        )
        return 0

    selected = _get_selected_top_models()
    if not selected:
        FBMessageBox(TOOL_NAME, "Select at least one object to duplicate.", "OK")
        return 0

    duplicates = []
    for model in selected:
        duplicate = model.Clone()
        if duplicate is None:
            raise RuntimeError("Could not duplicate: %s" % model.LongName)
        duplicates.append(duplicate)

    for model in selected:
        model.Selected = False
    for duplicate in duplicates:
        duplicate.Selected = True

    print("Duplicated %d selected object(s)." % len(duplicates))
    return len(duplicates)


def _unique_take_copy_name(source_name, reserved_names):
    base_name = "%s Copy" % source_name
    candidate = base_name
    suffix = 2

    while candidate.lower() in reserved_names:
        candidate = "%s %d" % (base_name, suffix)
        suffix += 1

    reserved_names.add(candidate.lower())
    return candidate


def _duplicate_selected_takes():
    system = FBSystem()
    selected = _selected_takes()
    if not selected:
        FBMessageBox(
            TOOL_NAME,
            "Select at least one take in Navigator before duplicating.",
            "OK",
        )
        return 0

    reserved_names = set(str(take.Name).lower() for take in system.Scene.Takes)
    original_current_take = system.CurrentTake
    created = []

    try:
        for source_take in selected:
            system.CurrentTake = source_take
            copy_name = _unique_take_copy_name(source_take.Name, reserved_names)
            duplicate = source_take.CopyTake(copy_name)
            if duplicate is None:
                raise RuntimeError("Could not duplicate take: %s" % source_take.Name)
            created.append(duplicate)

        for take in selected:
            take.Selected = False
        for take in created:
            take.Selected = True

        system.CurrentTake = created[-1]
    except Exception:
        try:
            system.CurrentTake = original_current_take
        except Exception:
            pass

        for take in reversed(created):
            try:
                take.FBDelete()
            except Exception:
                pass

        for take in selected:
            try:
                take.Selected = True
            except Exception:
                pass
        raise

    print("Duplicated %d selected take(s)." % len(created))
    return len(created)


def _add_fcurve(curves, fcurve):
    if fcurve is None:
        return

    try:
        if len(fcurve.Keys) <= 0:
            return
    except Exception:
        return

    for existing in curves:
        if existing is fcurve:
            return
        try:
            if existing == fcurve:
                return
        except Exception:
            pass

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
        children = list(animation_node.Nodes)
    except Exception:
        children = []

    for child in children:
        _scan_animation_node_fcurves(child, layer_indices, curves)


def _displayed_fcurves():
    curves = []
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

    return curves


def _key_is_selected(fcurve, index):
    try:
        if bool(fcurve.KeyGetSelected(index)):
            return True
    except Exception:
        pass

    try:
        return bool(fcurve.Keys[index].Selected)
    except Exception:
        return False


def _key_value(fcurve, index):
    try:
        return float(fcurve.KeyGetValue(index))
    except Exception:
        return float(fcurve.Keys[index].Value)


def _capture_key(fcurve, index):
    state = {
        "curve": fcurve,
        "source_time_ticks": int(fcurve.KeyGetTime(index).Get()),
        "value": _key_value(fcurve, index),
        "interpolation": fcurve.KeyGetInterpolation(index),
        "tangent_mode": fcurve.KeyGetTangentMode(index),
    }

    for name, getter_name, _setter_name in KEY_ATTRIBUTE_ACCESSORS:
        try:
            state[name] = getattr(fcurve, getter_name)(index)
        except Exception:
            pass

    return state


def _selected_key_states(curves):
    states = []

    for fcurve in curves:
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            if _key_is_selected(fcurve, index):
                states.append(_capture_key(fcurve, index))

    return states


def _frame_ticks():
    try:
        frames_per_second = float(FBPlayerControl().GetTransportFps())
    except Exception:
        frames_per_second = 0.0

    if frames_per_second <= 0.000001:
        return max(1, int(FBTime(0, 0, 0, 1).Get()))
    return max(1, int(round(float(FBTime.OneSecond.Get()) / frames_per_second)))


def _existing_key_times(curves):
    result = {}

    for fcurve in curves:
        times = set()
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            key_count = 0

        for index in range(key_count):
            try:
                times.add(int(fcurve.KeyGetTime(index).Get()))
            except Exception:
                try:
                    times.add(int(fcurve.Keys[index].Time.Get()))
                except Exception:
                    pass

        result[id(fcurve)] = times

    return result


def _collision_free_frame_offset(states, curves):
    existing_times = _existing_key_times(curves)
    frame_ticks = _frame_ticks()
    offset_frames = 1

    while True:
        tick_offset = offset_frames * frame_ticks
        if all(
            state["source_time_ticks"] + tick_offset
            not in existing_times.get(id(state["curve"]), set())
            for state in states
        ):
            return offset_frames, tick_offset
        offset_frames += 1


def _find_key_index_at_ticks(fcurve, time_ticks):
    try:
        key_count = len(fcurve.Keys)
    except Exception:
        return None

    for index in range(key_count):
        try:
            if int(fcurve.KeyGetTime(index).Get()) == int(time_ticks):
                return index
        except Exception:
            try:
                if int(fcurve.Keys[index].Time.Get()) == int(time_ticks):
                    return index
            except Exception:
                pass

    return None


def _apply_key_attributes(fcurve, index, state):
    for name, _getter_name, setter_name in KEY_ATTRIBUTE_ACCESSORS:
        if name not in state:
            continue
        try:
            getattr(fcurve, setter_name)(index, state[name])
        except Exception:
            pass


def _set_all_key_selection(curves, selected):
    for fcurve in curves:
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            try:
                fcurve.KeySetSelected(index, bool(selected))
            except Exception:
                try:
                    fcurve.Keys[index].Selected = bool(selected)
                except Exception:
                    pass


def _delete_created_keys(created):
    for state in reversed(created):
        index = _find_key_index_at_ticks(state["curve"], state["target_time_ticks"])
        if index is None:
            continue
        try:
            state["curve"].KeyDelete(index, index)
        except Exception:
            pass


def _duplicate_selected_fcurve_keys():
    curves = _displayed_fcurves()
    states = _selected_key_states(curves)
    if not states:
        FBMessageBox(
            TOOL_NAME,
            "Select at least one key in the active FCurves editor.",
            "OK",
        )
        return 0

    offset_frames, tick_offset = _collision_free_frame_offset(states, curves)
    created = []
    affected_curves = list(dict((id(state["curve"]), state["curve"]) for state in states).values())

    for curve in affected_curves:
        try:
            curve.EditBegin()
        except Exception:
            pass

    try:
        for state in states:
            target_ticks = state["source_time_ticks"] + tick_offset
            index = state["curve"].KeyAdd(
                FBTime(target_ticks),
                state["value"],
                state["interpolation"],
                state["tangent_mode"],
            )
            if index is None or int(index) < 0:
                raise RuntimeError("MotionBuilder could not add a duplicated FCurve key.")

            state["target_time_ticks"] = target_ticks
            created.append(state)
            _apply_key_attributes(state["curve"], int(index), state)

        _set_all_key_selection(curves, False)
        for state in created:
            index = _find_key_index_at_ticks(
                state["curve"],
                state["target_time_ticks"],
            )
            if index is None:
                raise RuntimeError("A duplicated FCurve key could not be resolved.")
            state["curve"].KeySetSelected(index, True)
    except Exception:
        _delete_created_keys(created)
        for state in states:
            index = _find_key_index_at_ticks(
                state["curve"],
                state["source_time_ticks"],
            )
            if index is not None:
                try:
                    state["curve"].KeySetSelected(index, True)
                except Exception:
                    pass
        raise
    finally:
        for curve in affected_curves:
            try:
                curve.EditEnd()
            except Exception:
                pass

    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass

    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            for widget in app.allWidgets():
                try:
                    if widget.accessibleName() == "FCurve" and widget.isVisible():
                        widget.update()
                        if hasattr(widget, "repaint"):
                            widget.repaint()
                except Exception:
                    pass
    except Exception:
        pass

    print(
        "Duplicated %d selected FCurve key(s) by %+d frame(s)."
        % (len(created), offset_frames)
    )
    return len(created)


def _run_move_script(context_name=CONTEXT_FCURVES):
    try:
        import mobu_tools_manager
        mgr = mobu_tools_manager.get_manager()
        target_domain = (
            "fcurve"
            if context_name == CONTEXT_FCURVES
            else ("viewer" if context_name == CONTEXT_VIEWER else "other")
        )
        invocation = mgr._transform_invocation("move")
        if target_domain in ("fcurve", "viewer"):
            invocation["domain"] = target_domain
            invocation["ui_context"] = target_domain
        invocation["launcher_key"] = None
        invocation["activate_immediately"] = True
        session = mgr.dispatch("transform.move_camera_plane", invocation=invocation)
        if session is not None:
            return session
    except Exception:
        pass

    path = os.path.join(_script_directory(), MOVE_SCRIPT_NAME)
    if not os.path.isfile(path):
        raise RuntimeError("Move script does not exist:\n%s" % path)

    with open(path, "r", encoding="utf-8-sig") as source_file:
        source = source_file.read()

    namespace = {
        "__file__": path,
        "__name__": "__main__",
        "__package__": None,
        "__builtins__": __builtins__,
    }
    script_directory = os.path.dirname(path)
    added_to_path = script_directory not in sys.path
    if added_to_path:
        sys.path.insert(0, script_directory)

    try:
        exec(compile(source, path, "exec"), namespace, namespace)
    finally:
        if added_to_path:
            try:
                sys.path.remove(script_directory)
            except ValueError:
                pass


def duplicate_for_context():
    _focus_service()
    context = _detect_context()

    if context == CONTEXT_FCURVES:
        if _duplicate_selected_fcurve_keys():
            _run_move_script(CONTEXT_FCURVES)
        return

    if context == CONTEXT_NAVIGATOR:
        active_kind = _navigator_active_kind()
        if active_kind == "take":
            _duplicate_selected_takes()
            return
        if active_kind == "model":
            _duplicate_selected_models(require_active=True)
            return

        FBMessageBox(
            TOOL_NAME,
            "Click an object or take to make it active before duplicating.",
            "OK",
        )
        return

    if _duplicate_selected_models() and context == CONTEXT_VIEWER:
        _run_move_script(CONTEXT_VIEWER)


def run_with_error_dialog():
    try:
        duplicate_for_context()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
