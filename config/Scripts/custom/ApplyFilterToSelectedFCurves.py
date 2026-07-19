from pyfbsdk import (
    FBFCurve,
    FBFilterManager,
    FBMessageBox,
    FBSystem,
    FBUndoManager,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

import traceback


WINDOW_TITLE = "Apply Filter to Selected FCurve Keys"
CONTROLLER_ATTRIBUTE = "_apply_filter_to_selected_fcurves_controller"

# These built-in filters need sibling curves from the same animation node.
# Other filters are tried on individual selected curves first. This also keeps
# plug-in scalar filters working without needing a hard-coded registry.
VECTOR_FILTER_NAMES = {
    "Gimbal Killer",
    "Key Sync",
    "Smooth Translation",
    "Transformation",
    "Unroll Rotations",
}


def _curve_has_keys(fcurve):
    try:
        return len(fcurve.Keys) > 0
    except Exception:
        return False


def _key_is_selected(fcurve, index):
    try:
        return bool(fcurve.KeyGetSelected(index))
    except Exception:
        try:
            return bool(fcurve.Keys[index].Selected)
        except Exception:
            return False


def _selected_key_range(fcurve):
    selected_times = []

    try:
        key_count = len(fcurve.Keys)
    except Exception:
        return None

    for index in range(key_count):
        if not _key_is_selected(fcurve, index):
            continue

        try:
            key_time = fcurve.Keys[index].Time
            selected_times.append((int(key_time.Get()), key_time))
        except Exception:
            pass

    if not selected_times:
        return None

    selected_times.sort(key=lambda item: item[0])
    return {
        "start_ticks": selected_times[0][0],
        "start_time": selected_times[0][1],
        "stop_ticks": selected_times[-1][0],
        "stop_time": selected_times[-1][1],
        "key_count": len(selected_times),
    }


def _get_layer_indices(take):
    indices = set()
    if take is None:
        return indices

    try:
        indices.add(int(take.GetCurrentLayer()))
    except Exception:
        pass

    try:
        for index in range(take.GetLayerCount()):
            layer = take.GetLayer(index)
            if layer and layer.IsSelected():
                indices.add(index)
    except Exception:
        pass

    return indices


def _add_curve_target(
    registry,
    fcurve,
    node=None,
    parent_node=None,
    prop=None,
    layer_index=None,
):
    if not fcurve or not _curve_has_keys(fcurve):
        return None

    target = registry.get(fcurve)
    if target is None:
        target = {
            "curve": fcurve,
            "node": node,
            "parent_node": parent_node,
            "property": prop,
            "layer_index": layer_index,
        }
        registry[fcurve] = target
        return target

    if target["node"] is None and node is not None:
        target["node"] = node
    if target["parent_node"] is None and parent_node is not None:
        target["parent_node"] = parent_node
    if target["property"] is None and prop is not None:
        target["property"] = prop
    if target["layer_index"] is None and layer_index is not None:
        target["layer_index"] = layer_index
    return target


def _scan_animation_node(
    registry,
    animation_node,
    prop,
    layer_indices,
    parent_node=None,
):
    if not animation_node:
        return

    current_layer = None
    try:
        current_layer = int(FBSystem().CurrentTake.GetCurrentLayer())
    except Exception:
        pass

    try:
        _add_curve_target(
            registry,
            animation_node.FCurve,
            animation_node,
            parent_node,
            prop,
            current_layer,
        )
    except Exception:
        pass

    for layer_index in layer_indices:
        try:
            _add_curve_target(
                registry,
                animation_node.GetFCurve(layer_index),
                animation_node,
                parent_node,
                prop,
                layer_index,
            )
        except Exception:
            pass

    try:
        children = list(animation_node.Nodes)
    except Exception:
        children = []

    for child_node in children:
        _scan_animation_node(
            registry,
            child_node,
            prop,
            layer_indices,
            parent_node=animation_node,
        )


def _scan_property(
    registry,
    prop,
    layer_indices,
):
    try:
        animation_node = prop.GetAnimationNode()
    except Exception:
        animation_node = None

    if not animation_node:
        return

    _scan_animation_node(
        registry,
        animation_node,
        prop,
        layer_indices,
    )


def collect_selected_curve_targets():
    system = FBSystem()
    scene = system.Scene
    layer_indices = _get_layer_indices(system.CurrentTake)
    registry = {}

    # Direct scene scan catches FCurves that are already exposed as components.
    for component in scene.Components:
        if isinstance(component, FBFCurve):
            _add_curve_target(registry, component)

    # Property traversal supplies the owning property/node information needed by
    # vector filters and catches curves on the active animation layer.
    for component in scene.Components:
        try:
            properties = list(component.PropertyList)
        except Exception:
            continue

        for prop in properties:
            try:
                if prop.IsAnimatable():
                    _scan_property(registry, prop, layer_indices)
            except Exception:
                pass

    selected_targets = []
    for target in registry.values():
        selected_range = _selected_key_range(target["curve"])
        if selected_range is None:
            continue
        target["selected_range"] = selected_range
        selected_targets.append(target)

    return selected_targets


def _unique_properties(targets):
    result = []
    seen = set()
    for target in targets:
        prop = target["property"]
        if prop is None:
            continue
        try:
            key = hash(prop)
        except Exception:
            key = id(prop)
        if key in seen:
            continue
        seen.add(key)
        result.append(prop)
    return result


def _group_by_parent_node(targets):
    groups = {}
    singles = []
    for target in targets:
        parent_node = target["parent_node"]
        if parent_node is None:
            singles.append(target)
            continue

        layer_index = target["layer_index"]
        key = (id(parent_node), layer_index)
        group = groups.get(key)
        if group is None:
            group = {
                "node": parent_node,
                "layer_index": layer_index,
                "targets": [],
            }
            groups[key] = group
        group["targets"].append(target)
    return list(groups.values()), singles


def _set_current_layer(take, layer_index):
    if take is None or layer_index is None:
        return
    try:
        if int(take.GetCurrentLayer()) != int(layer_index):
            take.SetCurrentLayer(int(layer_index))
    except Exception:
        pass


def _set_filter_range(filter_object, targets):
    ranges = [
        target.get("selected_range")
        for target in targets
        if target.get("selected_range") is not None
    ]
    if not ranges:
        return False

    start_range = min(ranges, key=lambda item: item["start_ticks"])
    stop_range = max(ranges, key=lambda item: item["stop_ticks"])
    filter_object.Start = start_range["start_time"]
    filter_object.Stop = stop_range["stop_time"]
    return True


def _apply_vector_groups(filter_object, targets, take):
    successful_curves = set()
    failed_curves = set()
    groups, singles = _group_by_parent_node(targets)

    for group in groups:
        _set_current_layer(take, group["layer_index"])
        try:
            _set_filter_range(filter_object, group["targets"])
            succeeded = bool(filter_object.Apply(group["node"], False))
        except Exception:
            succeeded = False

        destination = successful_curves if succeeded else failed_curves
        for target in group["targets"]:
            destination.add(target["curve"])

    for target in singles:
        _set_current_layer(take, target["layer_index"])
        try:
            _set_filter_range(filter_object, [target])
            succeeded = bool(filter_object.Apply(target["curve"]))
        except Exception:
            succeeded = False
        destination = successful_curves if succeeded else failed_curves
        destination.add(target["curve"])

    return successful_curves, failed_curves


def _apply_scalar_curves(filter_object, targets, take):
    successful_curves = set()
    failed_targets = []

    for target in targets:
        _set_current_layer(take, target["layer_index"])
        try:
            _set_filter_range(filter_object, [target])
            succeeded = bool(filter_object.Apply(target["curve"]))
        except Exception:
            succeeded = False

        if succeeded:
            successful_curves.add(target["curve"])
        else:
            failed_targets.append(target)

    # A plug-in vector filter may not be in VECTOR_FILTER_NAMES. If every
    # selected sibling failed as a scalar, retry that group as one vector node.
    retry_groups, retry_singles = _group_by_parent_node(failed_targets)
    failed_curves = {target["curve"] for target in retry_singles}

    for group in retry_groups:
        _set_current_layer(take, group["layer_index"])
        try:
            _set_filter_range(filter_object, group["targets"])
            succeeded = bool(filter_object.Apply(group["node"], False))
        except Exception:
            succeeded = False
        destination = successful_curves if succeeded else failed_curves
        for target in group["targets"]:
            destination.add(target["curve"])

    return successful_curves, failed_curves


def apply_filter_to_selected_fcurves(filter_name, show_feedback=True):
    targets = collect_selected_curve_targets()
    if not targets:
        if show_feedback:
            FBMessageBox(
                WINDOW_TITLE,
                "No selected FCurve keys were found.",
                "OK",
            )
        return {"selected": 0, "applied": 0, "failed": 0}

    manager = FBFilterManager()
    filter_object = manager.CreateFilter(str(filter_name))
    if not filter_object:
        if show_feedback:
            FBMessageBox(
                WINDOW_TITLE,
                "MotionBuilder could not create the '%s' filter." % filter_name,
                "OK",
            )
        return {"selected": len(targets), "applied": 0, "failed": len(targets)}

    system = FBSystem()
    take = system.CurrentTake
    original_layer = None
    try:
        if take is not None:
            original_layer = int(take.GetCurrentLayer())
    except Exception:
        original_layer = None

    undo_manager = FBUndoManager()
    owns_transaction = False
    try:
        if not undo_manager.TransactionIsOpen():
            owns_transaction = bool(
                undo_manager.TransactionBegin("Apply %s Filter" % filter_name)
            )
        for prop in _unique_properties(targets):
            try:
                undo_manager.TransactionAddProperty(prop)
            except Exception:
                pass

        if str(filter_name) in VECTOR_FILTER_NAMES:
            successful, failed = _apply_vector_groups(filter_object, targets, take)
        else:
            successful, failed = _apply_scalar_curves(filter_object, targets, take)
    finally:
        if original_layer is not None:
            _set_current_layer(take, original_layer)
        try:
            filter_object.FBDelete()
        except Exception:
            pass
        if owns_transaction:
            try:
                undo_manager.TransactionEnd()
            except Exception:
                pass

    system.Scene.Evaluate()
    applied_count = len(successful)
    failed_count = len(failed)

    print(
        "%s: applied to %d selected FCurve(s); %d failed."
        % (filter_name, applied_count, failed_count)
    )

    if show_feedback and failed_count:
        message = (
            "Applied '%s' to %d of %d selected FCurve(s).\n\n"
            "%d curve(s) were incompatible with this filter or the filter "
            "reported no change."
        ) % (filter_name, applied_count, len(targets), failed_count)
        FBMessageBox(WINDOW_TITLE, message, "OK")

    return {
        "selected": len(targets),
        "applied": applied_count,
        "failed": failed_count,
    }


class FilterMenuController(QtCore.QObject):
    def __init__(self, parent=None):
        super(FilterMenuController, self).__init__(parent)
        self.menu = QtWidgets.QMenu()
        self.menu.setTitle(WINDOW_TITLE)

        manager = FBFilterManager()
        filter_names = [str(name) for name in manager.FilterTypeNames]
        for filter_name in filter_names:
            action = self.menu.addAction(filter_name)
            action.setData(filter_name)

        if not filter_names:
            action = self.menu.addAction("No filters are available")
            action.setEnabled(False)

        self.menu.triggered.connect(self.on_triggered)
        self.menu.aboutToHide.connect(self.on_about_to_hide)

    def show(self):
        self.menu.popup(QtGui.QCursor.pos())

    def close(self):
        try:
            self.menu.close()
            self.menu.deleteLater()
        except Exception:
            pass

    def on_triggered(self, action):
        try:
            filter_name = str(action.data())
            if filter_name:
                apply_filter_to_selected_fcurves(filter_name)
        except Exception:
            FBMessageBox(
                WINDOW_TITLE,
                traceback.format_exc()[-1800:],
                "OK",
            )

    def on_about_to_hide(self):
        QtCore.QTimer.singleShot(0, self._release)

    def _release(self):
        if getattr(builtins, CONTROLLER_ATTRIBUTE, None) is self:
            setattr(builtins, CONTROLLER_ATTRIBUTE, None)
        try:
            self.menu.deleteLater()
        except Exception:
            pass
        self.deleteLater()


def show_filter_menu():
    application = QtWidgets.QApplication.instance()
    if application is None:
        FBMessageBox(
            WINDOW_TITLE,
            "Could not find the MotionBuilder Qt application.",
            "OK",
        )
        return None

    old_controller = getattr(builtins, CONTROLLER_ATTRIBUTE, None)
    if old_controller is not None:
        try:
            old_controller.close()
        except Exception:
            pass

    controller = FilterMenuController(application)
    setattr(builtins, CONTROLLER_ATTRIBUTE, controller)
    controller.show()
    return controller


if globals().get("SHOW_FILTER_MENU", True):
    show_filter_menu()
