import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import (
    FBCamera,
    FBConstraint,
    FBConstraintManager,
    FBGetSelectedModels,
    FBMatrix,
    FBMessageBox,
    FBModel,
    FBModelList,
    FBModelNull,
    FBModelTransformationType,
    FBSystem,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Lock Camera To Selected"

SCENE_NULL_NAME = "Scene"
FOLLOW_RIG_NAME = "Selected Object Follow Camera Rig"
FOLLOW_CAMERA_NAME = "Selected Object Follow Camera"
FOLLOW_CONSTRAINT_NAME = "Selected Object Follow Camera - Position"
PRODUCER_PERSPECTIVE_NAME = "Producer Perspective"

ENABLE_VIEWPORT_SWITCH = True
DEBUG_MONITOR_ATTR = "_codex_camera_viewport_debug_monitor"

INTEREST_NAVIGATION_LOCK_PROPERTY_NAMES = (
    "LockInterestNavigation",
    "CameraLockInterestNavigation",
    "Lock Interest Navigation",
)

VIEWER_ACTION_RETRY_DELAYS_MS = (0, 50, 150, 300, 600)

_viewport_activation_done = False


def _debug_mark(label, **data):
    try:
        monitor = getattr(builtins, DEBUG_MONITOR_ATTR, None)
        if monitor is not None:
            monitor.mark(label, **data)
    except Exception:
        pass

def _short_name(value):
    value = str(value).replace("\\", "/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    if "::" in value:
        value = value.rsplit("::", 1)[-1]
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    return value


def _name_values(component):
    values = []
    for attribute_name in ("Name", "LongName"):
        try:
            value = str(getattr(component, attribute_name))
        except Exception:
            continue
        if value and value not in values:
            values.append(value)
    return values


def _has_exact_short_name(component, name):
    return any(_short_name(value) == name for value in _name_values(component))


def _has_tool_name(component, base_name):
    for value in _name_values(component):
        short_name = _short_name(value)
        if short_name == base_name:
            return True
        if short_name.startswith(base_name):
            suffix = short_name[len(base_name):].strip(" _.-()")
            if suffix.isdigit():
                return True
    return False


def _set_name(component, name):
    try:
        component.SetName(name)
        return
    except Exception:
        pass
    try:
        component.Name = name
    except Exception:
        pass


def _set_if_available(component, attribute_name, value):
    try:
        setattr(component, attribute_name, value)
    except Exception:
        pass


def _lock_interest_navigation(camera):
    for property_name in INTEREST_NAVIGATION_LOCK_PROPERTY_NAMES:
        try:
            camera_property = camera.PropertyList.Find(property_name)
        except Exception:
            camera_property = None

        if camera_property is None:
            continue

        try:
            camera_property.Data = True
            return True
        except Exception:
            continue

    return False


def _delete_component(component):
    try:
        component.FBDelete()
    except Exception:
        pass


def _choose_one(candidates, canonical_name):
    if not candidates:
        return None

    primary = candidates[0]
    for candidate in candidates:
        if _has_exact_short_name(candidate, canonical_name):
            primary = candidate
            break

    for candidate in candidates:
        if candidate is not primary:
            _delete_component(candidate)

    if not _has_exact_short_name(primary, canonical_name):
        _set_name(primary, canonical_name)

    return primary


def _find_scene_model(name):
    for component in FBSystem().Scene.Components:
        if isinstance(component, FBModel) and _has_exact_short_name(component, name):
            return component
    return None


def _ensure_scene_null():
    scene_null = _find_scene_model(SCENE_NULL_NAME)
    if scene_null is not None:
        return scene_null

    scene_null = FBModelNull(SCENE_NULL_NAME)
    scene_null.Show = True
    scene_null.Visibility = True
    scene_null.Translation = FBVector3d(0.0, 0.0, 0.0)
    scene_null.Rotation = FBVector3d(0.0, 0.0, 0.0)
    scene_null.Scaling = FBVector3d(1.0, 1.0, 1.0)
    return scene_null


def _ensure_follow_rig(scene_null):
    candidates = [
        component
        for component in FBSystem().Scene.Components
        if isinstance(component, FBModelNull)
        and _has_tool_name(component, FOLLOW_RIG_NAME)
    ]
    rig = _choose_one(candidates, FOLLOW_RIG_NAME)
    if rig is None:
        rig = FBModelNull(FOLLOW_RIG_NAME)
        rig.Show = True

    rig.Parent = scene_null
    _set_if_available(rig, "Visibility", False)
    _set_if_available(rig, "Pickable", False)
    return rig


def _ensure_follow_camera(follow_rig):
    candidates = [
        camera
        for camera in FBSystem().Scene.Cameras
        if not bool(getattr(camera, "SystemCamera", False))
        and _has_tool_name(camera, FOLLOW_CAMERA_NAME)
    ]
    camera = _choose_one(candidates, FOLLOW_CAMERA_NAME)
    if camera is None:
        camera = FBCamera(FOLLOW_CAMERA_NAME)

    camera.Show = True
    camera.Visibility = True
    camera.Parent = follow_rig
    _set_if_available(camera, "ViewCameraInterest", False)
    return camera


def _ensure_position_constraint():
    candidates = [
        constraint
        for constraint in FBSystem().Scene.Constraints
        if isinstance(constraint, FBConstraint)
        and _has_tool_name(constraint, FOLLOW_CONSTRAINT_NAME)
    ]
    constraint = _choose_one(candidates, FOLLOW_CONSTRAINT_NAME)
    if constraint is not None and constraint.ReferenceGroupGetCount() >= 2:
        return constraint

    if constraint is not None:
        _delete_component(constraint)

    manager = FBConstraintManager()
    exact_index = None
    fallback_index = None
    for index in range(manager.TypeGetCount()):
        type_name = str(manager.TypeGetName(index))
        lowered = type_name.casefold()
        if lowered == "position":
            exact_index = index
            break
        if fallback_index is None and "position" in lowered:
            fallback_index = index

    type_index = exact_index if exact_index is not None else fallback_index
    if type_index is None:
        raise RuntimeError("MotionBuilder's Position constraint type was not found.")

    constraint = manager.TypeCreateConstraint(type_index)
    if constraint is None:
        raise RuntimeError("MotionBuilder could not create the Position constraint.")

    _set_name(constraint, FOLLOW_CONSTRAINT_NAME)
    return constraint


def _find_producer_perspective():
    system_cameras = [
        camera
        for camera in FBSystem().Scene.Cameras
        if bool(getattr(camera, "SystemCamera", False))
    ]

    for camera in system_cameras:
        if _has_exact_short_name(camera, PRODUCER_PERSPECTIVE_NAME):
            return camera

    for camera in system_cameras:
        if "perspective" in " ".join(_name_values(camera)).casefold():
            return camera

    if system_cameras:
        return system_cameras[0]

    raise RuntimeError("Producer Perspective camera was not found.")


def _selected_target():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)

    for model in selected_models:
        if isinstance(model, FBCamera) and _has_tool_name(model, FOLLOW_CAMERA_NAME):
            continue
        if isinstance(model, FBModelNull) and _has_tool_name(model, FOLLOW_RIG_NAME):
            continue
        if _has_exact_short_name(model, SCENE_NULL_NAME):
            continue
        return model

    return None


def _global_vector(model, transformation_type):
    value = FBVector3d()
    model.GetVector(value, transformation_type, True)
    return value


def _set_global_vector(model, value, transformation_type):
    model.SetVector(value, transformation_type, True)


def _copy_producer_camera_state(producer_camera, follow_camera):
    matrix = FBMatrix()
    producer_camera.GetMatrix(
        matrix,
        FBModelTransformationType.kModelTransformation,
        True,
    )
    follow_camera.SetMatrix(
        matrix,
        FBModelTransformationType.kModelTransformation,
        True,
    )

    for attribute_name in (
        "FieldOfView",
        "NearPlaneDistance",
        "FarPlaneDistance",
        "PixelAspectRatio",
        "Roll",
        "ViewShowAxis",
        "ViewShowGrid",
        "ViewShowManipulators",
        "ViewShowTimeCode",
    ):
        try:
            setattr(follow_camera, attribute_name, getattr(producer_camera, attribute_name))
        except Exception:
            pass


def _clear_constraint_references(constraint):
    for group_index in range(constraint.ReferenceGroupGetCount()):
        while constraint.ReferenceGetCount(group_index) > 0:
            reference = constraint.ReferenceGet(group_index, 0)
            if reference is None:
                break
            if not constraint.ReferenceRemove(group_index, reference):
                break


def _constraint_group_indices(constraint):
    constrained_index = None
    source_index = None

    for group_index in range(constraint.ReferenceGroupGetCount()):
        try:
            group_name = str(constraint.ReferenceGroupGetName(group_index)).casefold()
        except Exception:
            group_name = ""

        if source_index is None and ("source" in group_name or "parent" in group_name):
            source_index = group_index
        if constrained_index is None and (
            "constrained" in group_name
            or "child" in group_name
            or "recipient" in group_name
        ):
            constrained_index = group_index

    if constrained_index is None:
        constrained_index = 0
    if source_index is None:
        source_index = 1 if constraint.ReferenceGroupGetCount() > 1 else 0

    return constrained_index, source_index


def _configure_follow_constraint(constraint, follow_rig, target):
    constraint.Active = False
    _clear_constraint_references(constraint)

    constrained_index, source_index = _constraint_group_indices(constraint)
    if not constraint.ReferenceAdd(constrained_index, follow_rig):
        raise RuntimeError("Could not assign the camera rig to the Position constraint.")
    if not constraint.ReferenceAdd(source_index, target):
        raise RuntimeError("Could not assign the selected object as the follow target.")

    _set_if_available(constraint, "Lock", False)
    constraint.SnapSuggested()
    constraint.Active = True


def _normalized_action_text(action):
    try:
        text = str(action.text())
    except Exception:
        return ""
    return text.replace("&", "").split("\t", 1)[0].strip()


def _all_qt_actions(app):
    action_class = getattr(QtGui, "QAction", None)
    if action_class is None:
        action_class = QtWidgets.QAction

    actions = []
    seen = set()

    for widget in app.allWidgets():
        if isinstance(widget, QtWidgets.QMenu):
            try:
                menu_actions = widget.actions()
            except Exception:
                menu_actions = []
            for action in menu_actions:
                key = id(action)
                if key not in seen:
                    seen.add(key)
                    actions.append(action)

    for root in app.topLevelWidgets():
        try:
            child_actions = root.findChildren(action_class)
        except Exception:
            child_actions = []
        for action in child_actions:
            key = id(action)
            if key not in seen:
                seen.add(key)
                actions.append(action)

    return actions


def _find_qt_action(app, action_text):
    for action in _all_qt_actions(app):
        if _normalized_action_text(action) == action_text:
            return action
    return None


def _refresh_perspective_menus(app):
    for widget in app.allWidgets():
        if not isinstance(widget, QtWidgets.QMenu):
            continue
        try:
            title = str(widget.title()).replace("&", "").split("\t", 1)[0].strip()
        except Exception:
            title = ""
        if title != "Perspective":
            continue
        try:
            widget.aboutToShow.emit()
        except Exception:
            pass


def _find_follow_camera():
    system = FBSystem()
    for scene_camera in system.Scene.Cameras:
        if (
            not bool(getattr(scene_camera, "SystemCamera", False))
            and _has_exact_short_name(scene_camera, FOLLOW_CAMERA_NAME)
        ):
            return scene_camera
    return None


def _trigger_look_through_selected(app, viewport_camera):
    action = _find_qt_action(app, "Look Through Selected")
    if action is None:
        return False

    previous_selection = FBModelList()
    FBGetSelectedModels(previous_selection, None, True, True)

    for model in previous_selection:
        try:
            model.Selected = False
        except Exception:
            pass
    viewport_camera.Selected = True

    try:
        _debug_mark("before_trigger_look_through_selected")
        action.trigger()
        _debug_mark("after_trigger_look_through_selected")
    finally:
        viewport_camera.Selected = False
        for model in previous_selection:
            try:
                model.Selected = True
            except Exception:
                pass
    return True


def _activate_camera_from_viewer_action(attempt_index=0):
    global _viewport_activation_done

    if _viewport_activation_done:
        return

    viewport_camera = _find_follow_camera()

    if viewport_camera is None:
        _debug_mark("viewport_camera_not_found")
        FBMessageBox(
            TOOL_NAME + " Error",
            'Camera "{}" was not found in the scene.'.format(FOLLOW_CAMERA_NAME),
            "OK",
        )
        return

    _debug_mark(
        "viewport_camera_resolved",
        camera_name=str(viewport_camera.Name),
        camera_long_name=str(viewport_camera.LongName),
    )

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("MotionBuilder's Qt application was not found.")

    _refresh_perspective_menus(app)
    camera_action = _find_qt_action(app, FOLLOW_CAMERA_NAME)
    if camera_action is not None:
        _debug_mark("before_trigger_follow_camera_action")
        camera_action.trigger()
        _viewport_activation_done = True
        _debug_mark("after_trigger_follow_camera_action")
        return

    if _trigger_look_through_selected(app, viewport_camera):
        _viewport_activation_done = True
        return

    next_index = attempt_index + 1
    if next_index < len(VIEWER_ACTION_RETRY_DELAYS_MS):
        delay_ms = VIEWER_ACTION_RETRY_DELAYS_MS[next_index]
        QtCore.QTimer.singleShot(
            delay_ms,
            lambda index=next_index: _activate_camera_from_viewer_action(index),
        )
        return

    FBMessageBox(
        TOOL_NAME + " Error",
        'Viewer action "{}" was not found.'.format(FOLLOW_CAMERA_NAME),
        "OK",
    )


def _show_camera_in_viewport(camera):
    global _viewport_activation_done

    if not _has_exact_short_name(camera, FOLLOW_CAMERA_NAME):
        raise RuntimeError(
            'The camera prepared for the Viewer is not "{}".'.format(
                FOLLOW_CAMERA_NAME
            )
        )

    _viewport_activation_done = False
    _debug_mark("before_queue_viewport_qt_callback")
    QtCore.QTimer.singleShot(0, _activate_camera_from_viewer_action)
    _debug_mark("after_queue_viewport_qt_callback")


def lock_camera_to_selected():
    target = _selected_target()
    if target is None:
        _debug_mark("no_selected_target")
        return None

    _debug_mark(
        "lock_camera_started",
        target_name=str(target.Name),
        target_long_name=str(target.LongName),
    )

    system = FBSystem()
    producer_camera = _find_producer_perspective()
    scene_null = _ensure_scene_null()
    follow_rig = _ensure_follow_rig(scene_null)
    follow_camera = _ensure_follow_camera(follow_rig)
    constraint = _ensure_position_constraint()
    _debug_mark(
        "follow_camera_ensured",
        camera_name=str(follow_camera.Name),
        camera_long_name=str(follow_camera.LongName),
    )

    constraint.Active = False

    target_translation = _global_vector(
        target,
        FBModelTransformationType.kModelTranslation,
    )
    _set_global_vector(
        follow_rig,
        target_translation,
        FBModelTransformationType.kModelTranslation,
    )
    _set_global_vector(
        follow_rig,
        FBVector3d(0.0, 0.0, 0.0),
        FBModelTransformationType.kModelRotation,
    )
    _set_global_vector(
        follow_rig,
        FBVector3d(1.0, 1.0, 1.0),
        FBModelTransformationType.kModelScaling,
    )

    _copy_producer_camera_state(producer_camera, follow_camera)
    follow_camera.Interest = target
    _lock_interest_navigation(follow_camera)
    _configure_follow_constraint(constraint, follow_rig, target)

    system.Scene.Evaluate()
    _debug_mark("scene_setup_evaluated")
    if ENABLE_VIEWPORT_SWITCH:
        _show_camera_in_viewport(follow_camera)
    _debug_mark("lock_camera_finished")
    return follow_camera


def main():
    return lock_camera_to_selected()


try:
    main()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-2000:], "OK")
