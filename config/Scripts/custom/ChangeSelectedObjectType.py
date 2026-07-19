import traceback

from pyfbsdk import (
    FBCamera,
    FBFindModelByLabelName,
    FBGetSelectedModels,
    FBLight,
    FBMatrix,
    FBMessageBox,
    FBModelCube,
    FBModelList,
    FBModelMarker,
    FBModelNull,
    FBModelOptical,
    FBModelPath3D,
    FBModelPlane,
    FBModelRoot,
    FBModelSkeleton,
    FBModelTransformationType,
    FBPropertyType,
    FBSkeletonLook,
    FBSystem,
    FBVector3d,
)

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


TOOL_NAME = "Change Selected Object Type"

MODEL_TYPE_SPECS = [
    ("Null", FBModelNull, "null"),
    ("Marker", FBModelMarker, "marker"),
    ("Bone / Skeleton", FBModelSkeleton, "skeleton"),
    ("Cube", FBModelCube, "cube"),
    ("Plane", FBModelPlane, "plane"),
    ("Root", FBModelRoot, "root"),
    ("Camera", FBCamera, "camera"),
    ("Light", FBLight, "light"),
    ("Optical", FBModelOptical, "optical"),
    ("3D Path", FBModelPath3D, "path3d"),
]

TRANSFORM_CHANNELS = [
    ("Lcl Translation/X", "Translation"),
    ("Lcl Translation/Y", "Translation"),
    ("Lcl Translation/Z", "Translation"),
    ("Lcl Rotation/X", "Rotation"),
    ("Lcl Rotation/Y", "Rotation"),
    ("Lcl Rotation/Z", "Rotation"),
    ("Lcl Scaling/X", "Scaling"),
    ("Lcl Scaling/Y", "Scaling"),
    ("Lcl Scaling/Z", "Scaling"),
]

COMMON_MODEL_ATTRS = [
    "CastsShadows",
    "GeometricRotation",
    "GeometricScaling",
    "GeometricTranslation",
    "Pickable",
    "PostRotation",
    "PreRotation",
    "PrimaryVisibility",
    "QuaternionInterpolate",
    "ReceiveShadows",
    "RotationActive",
    "RotationMax",
    "RotationMaxX",
    "RotationMaxY",
    "RotationMaxZ",
    "RotationMin",
    "RotationMinX",
    "RotationMinY",
    "RotationMinZ",
    "RotationOrder",
    "RotationSpaceForLimitOnly",
    "ShadingMode",
    "Show",
    "SoftSelected",
    "Transformable",
    "Visibility",
    "VisibilityInheritance",
]

COMPATIBLE_DISPLAY_ATTRS = [
    "Color",
    "Length",
    "Size",
]

LOCAL_TRANSFORM_TYPES = [
    FBModelTransformationType.kModelTranslation,
    FBModelTransformationType.kModelRotation,
    FBModelTransformationType.kModelScaling,
]


def exec_dialog(dialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def dialog_code(name):
    if hasattr(QtWidgets.QDialog, "DialogCode"):
        return getattr(QtWidgets.QDialog.DialogCode, name)
    return getattr(QtWidgets.QDialog, name)


def dialog_button(name):
    if hasattr(QtWidgets.QDialogButtonBox, "StandardButton"):
        return getattr(QtWidgets.QDialogButtonBox.StandardButton, name)
    return getattr(QtWidgets.QDialogButtonBox, name)


class ChangeTypeDialog(QtWidgets.QDialog):
    def __init__(self, selected_count):
        QtWidgets.QDialog.__init__(self)
        self.setWindowTitle(TOOL_NAME)
        self.setModal(True)
        self.setMinimumWidth(360)

        self.type_combo = QtWidgets.QComboBox()
        for label, _cls, _key in MODEL_TYPE_SPECS:
            self.type_combo.addItem(label)

        buttons = QtWidgets.QDialogButtonBox(
            dialog_button("Ok") | dialog_button("Cancel")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Change {0} selected object(s) to:".format(selected_count)
            )
        )
        layout.addWidget(self.type_combo)
        layout.addWidget(buttons)

        QtCore.QTimer.singleShot(0, self.type_combo.setFocus)

    def selected_spec(self):
        return MODEL_TYPE_SPECS[self.type_combo.currentIndex()]


def _model_key(model):
    try:
        return model.UniqueName
    except Exception:
        return repr(model)


def _model_depth(model):
    depth = 0
    parent = model.Parent

    while parent is not None:
        depth += 1
        parent = parent.Parent

    return depth


def _safe_copy_attr(source, target, attr_name):
    try:
        setattr(target, attr_name, getattr(source, attr_name))
        return True
    except Exception:
        return False


def _copy_current_local_transform(source, target):
    for transform_type in LOCAL_TRANSFORM_TYPES:
        vector = FBVector3d()
        source.GetVector(vector, transform_type, False)
        target.SetVector(vector, transform_type, False)


def _matrix(model, global_info):
    matrix = FBMatrix()
    model.GetMatrix(
        matrix,
        FBModelTransformationType.kModelTransformation,
        global_info,
    )
    return matrix


def _set_matrix(model, matrix, global_info):
    model.SetMatrix(
        matrix,
        FBModelTransformationType.kModelTransformation,
        global_info,
    )


def _local_transform_vectors(model):
    vectors = []

    for transform_type in LOCAL_TRANSFORM_TYPES:
        vector = FBVector3d()
        model.GetVector(vector, transform_type, False)
        vectors.append((transform_type, vector))

    return vectors


def _set_local_transform_vectors(model, vectors):
    for transform_type, vector in vectors:
        model.SetVector(vector, transform_type, False)


def _copy_model_state(source, target):
    for attr_name in COMMON_MODEL_ATTRS:
        _safe_copy_attr(source, target, attr_name)

    for attr_name in COMPATIBLE_DISPLAY_ATTRS:
        _safe_copy_attr(source, target, attr_name)

    _copy_current_local_transform(source, target)

    try:
        target.SetSchematicPosition(source.GetSchematicPosition())
    except Exception:
        pass

    try:
        if source.IsCollapsedInSchematic():
            target.CollapseInSchematic()
        else:
            target.ExpandInSchematic()
    except Exception:
        pass


def _evaluate_scene():
    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass


def _snapshot_transform(source):
    parent = source.Parent

    return {
        "depth": _model_depth(source),
        "long_name": source.LongName,
        "name": source.Name,
        "parent": parent,
        "parent_key": _model_key(parent) if parent is not None else None,
        "parent_long_name": parent.LongName if parent is not None else None,
        "parent_name": parent.Name if parent is not None else None,
        "global_matrix": _matrix(source, True),
        "local_matrix": _matrix(source, False),
        "local_vectors": _local_transform_vectors(source),
    }


def _same_model(left, right):
    if left is None or right is None:
        return False

    if left is right:
        return True

    try:
        if left == right:
            return True
    except Exception:
        pass

    try:
        return _model_key(left) == _model_key(right)
    except Exception:
        return False


def _same_parent(left, right):
    if left is None and right is None:
        return True
    return _same_model(left, right)


def _is_model_like(component):
    return hasattr(component, "Parent") and hasattr(component, "Children")


def _model_matches(model, long_name, name):
    try:
        if long_name and model.LongName == long_name:
            return True
        if name and model.Name == name:
            return True
    except Exception:
        pass

    return False


def _find_model_in_hierarchy(root, long_name, name):
    if root is None:
        return None

    for child in root.Children:
        if _model_matches(child, long_name, name):
            return child

        result = _find_model_in_hierarchy(child, long_name, name)
        if result is not None:
            return result

    return None


def _find_scene_model(long_name, name):
    if long_name:
        try:
            model = FBFindModelByLabelName(long_name)
            if model is not None:
                return model
        except Exception:
            pass

    system = FBSystem()
    result = _find_model_in_hierarchy(system.Scene.RootModel, long_name, name)
    if result is not None:
        return result

    for component in system.Scene.Components:
        try:
            if not _is_model_like(component):
                continue
            if _model_matches(component, long_name, name):
                return component
        except Exception:
            pass

    return None


def _replacement_parent(snapshot, pairs, snapshots, replacements_by_key):
    parent = snapshot["parent"]

    if parent is None:
        return None

    parent_key = snapshot["parent_key"]
    replacement = replacements_by_key.get(parent_key)

    if replacement is not None:
        return replacement

    parent_long_name = snapshot["parent_long_name"]

    for source, target, source_key in pairs:
        if _same_model(parent, source):
            return target

        source_snapshot = snapshots[source_key]
        if parent_long_name and parent_long_name == source_snapshot["long_name"]:
            return target

    live_parent = _find_scene_model(parent_long_name, snapshot["parent_name"])
    return live_parent if live_parent is not None else parent


def _set_parent_preserve_transform(model, parent, snapshot):
    global_matrix = snapshot["global_matrix"]

    try:
        try:
            model.Visible = True
        except Exception:
            pass

        _set_global_matrix(model, global_matrix)
        _evaluate_scene()

        model.Parent = parent
        _evaluate_scene()

        if not _same_parent(model.Parent, parent):
            model.Parent = None
            _evaluate_scene()
            _set_global_matrix(model, global_matrix)
            _evaluate_scene()
            model.Parent = parent
            _evaluate_scene()

        if not _same_parent(model.Parent, parent):
            model.Parent = parent
            _evaluate_scene()

        if not _same_parent(model.Parent, parent) and parent is not None:
            try:
                parent.ConnectSrc(model)
                _evaluate_scene()
            except Exception:
                pass

        if not _same_parent(model.Parent, parent):
            try:
                model.Parent = parent
                _evaluate_scene()
            except Exception:
                pass

        return _same_parent(model.Parent, parent)
    except Exception:
        try:
            _set_global_matrix(model, global_matrix)
            _evaluate_scene()
        except Exception:
            pass
        return False


def _restore_local_transform(model, snapshot):
    try:
        _set_local_transform_vectors(model, snapshot["local_vectors"])
        _set_matrix(model, snapshot["local_matrix"], False)
        _evaluate_scene()
        return True
    except Exception:
        return False


def _parent_label(model):
    parent = None
    try:
        parent = model.Parent
    except Exception:
        pass

    if parent is None:
        return "<none>"

    try:
        return parent.LongName
    except Exception:
        return repr(parent)


def _model_class_label(model):
    try:
        return model.ClassName()
    except Exception:
        return model.__class__.__name__


def _assign_replacement_parents(pairs, snapshots, replacements_by_key):
    ordered_pairs = sorted(pairs, key=lambda pair: snapshots[pair[2]]["depth"])
    failures = []

    for _source, target, source_key in ordered_pairs:
        snapshot = snapshots[source_key]
        parent = _replacement_parent(
            snapshot,
            pairs,
            snapshots,
            replacements_by_key,
        )
        if not _set_parent_preserve_transform(target, parent, snapshot):
            failures.append(
                "{0} -> {1}: wanted {2}, got {3}".format(
                    snapshot["name"],
                    _model_class_label(target),
                    snapshot["parent_long_name"] or "<none>",
                    _parent_label(target),
                )
            )

    return failures


def _restore_replacement_transforms(pairs, snapshots):
    ordered_pairs = sorted(pairs, key=lambda pair: snapshots[pair[2]]["depth"])

    for _source, target, source_key in ordered_pairs:
        _restore_local_transform(target, snapshots[source_key])

    _evaluate_scene()


def _apply_target_defaults(target, type_key):
    try:
        target.Show = True
    except Exception:
        pass

    try:
        target.Visible = True
    except Exception:
        pass

    if type_key == "skeleton":
        try:
            target.Look = FBSkeletonLook.kFBSkeletonLookBone
        except Exception:
            pass


def _selected_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)
    return [model for model in selected_models]


def _is_system_camera(model):
    try:
        return isinstance(model, FBCamera) and model.SystemCamera
    except Exception:
        return False


def _show_type_dialog(selected_count):
    dialog = ChangeTypeDialog(selected_count)
    if exec_dialog(dialog) != dialog_code("Accepted"):
        return None
    return dialog.selected_spec()


def _create_replacement(source, target_class, type_key, index):
    target = target_class("__TypeChangeTemp_{0}__".format(index))
    _apply_target_defaults(target, type_key)
    return target


def _find_animation_node(node_path, root_node):
    result = None
    parts = node_path.split("/")

    for child_node in root_node.Nodes:
        if child_node.Name == parts[0]:
            if len(parts) > 1:
                result = _find_animation_node(
                    node_path.replace("{0}/".format(parts[0]), "", 1),
                    child_node,
                )
            else:
                result = child_node
            break

    return result


def _get_layer_curve(node, layer_index):
    try:
        return node.GetFCurve(layer_index)
    except Exception:
        return None


def _key_replace(dst_curve, src_curve):
    try:
        dst_curve.KeyReplaceBy(src_curve)
        return True
    except Exception:
        return False


def _copy_curve(src_node, dst_node, take):
    copied = False

    try:
        if src_node.FCurve and dst_node.FCurve:
            copied = _key_replace(dst_node.FCurve, src_node.FCurve) or copied
    except Exception:
        pass

    try:
        layer_count = take.GetLayerCount()
    except Exception:
        layer_count = 0

    for layer_index in range(layer_count):
        src_curve = _get_layer_curve(src_node, layer_index)
        dst_curve = _get_layer_curve(dst_node, layer_index)
        if src_curve and dst_curve:
            copied = _key_replace(dst_curve, src_curve) or copied

    return copied


def _find_child_animation_node(parent_node, child_name):
    for child_node in parent_node.Nodes:
        if child_node.Name == child_name:
            return child_node
    return None


def _copy_animation_node_tree(src_node, dst_node, take):
    if not src_node or not dst_node:
        return 0

    copied_count = 0
    if _copy_curve(src_node, dst_node, take):
        copied_count += 1

    for src_child in src_node.Nodes:
        dst_child = _find_child_animation_node(dst_node, src_child.Name)
        copied_count += _copy_animation_node_tree(src_child, dst_child, take)

    return copied_count


def _safe_prop_name(prop):
    try:
        return prop.GetName()
    except Exception:
        return prop.Name


def _is_user_property(prop):
    try:
        return prop.IsUserProperty()
    except Exception:
        return False


def _is_property_animated(prop):
    try:
        return prop.IsAnimated()
    except Exception:
        return False


def _set_property_animated(prop, state):
    try:
        prop.SetAnimated(state)
        return True
    except Exception:
        try:
            prop.SetAnimated(state, False)
            return True
        except Exception:
            return False


def _property_data_type(prop):
    try:
        return prop.GetDataTypeName()
    except Exception:
        return ""


def _property_reference_source(prop):
    try:
        if prop.IsReferenceProperty():
            return prop.GetReferencedProperty()
    except Exception:
        pass
    return None


def _copy_enum_strings(source_prop, target_prop):
    try:
        if source_prop.GetPropertyType() != FBPropertyType.kFBPT_enum:
            return
    except Exception:
        return

    try:
        source_list = source_prop.GetEnumStringList(False)
        target_list = target_prop.GetEnumStringList(True)
        if source_list is None or target_list is None:
            return

        try:
            target_list.Clear()
        except Exception:
            pass

        try:
            count = source_list.GetCount()
        except Exception:
            count = len(source_list)

        for index in range(count):
            try:
                target_list.Add(source_list.GetAt(index), source_list.GetReferenceAt(index))
            except Exception:
                target_list.Add(source_list.GetAt(index))

        target_prop.NotifyEnumStringListChanged()
    except Exception:
        pass


def _copy_property_value(source_prop, target_prop):
    try:
        target_prop.Data = source_prop.Data
        return True
    except Exception:
        pass

    try:
        return target_prop.SetString(source_prop.AsString())
    except Exception:
        return False


def _copy_property_limits(source_prop, target_prop):
    try:
        target_prop.SetMin(source_prop.GetMin(), source_prop.IsMinClamp())
    except Exception:
        pass

    try:
        target_prop.SetMax(source_prop.GetMax(), source_prop.IsMaxClamp())
    except Exception:
        pass


def _copy_property_locks(source_prop, target_prop):
    try:
        count = source_prop.GetSubMemberCount()
    except Exception:
        count = 0

    for index in range(count):
        try:
            target_prop.SetMemberLocked(index, source_prop.IsMemberLocked(index))
        except Exception:
            pass

    try:
        target_prop.SetLocked(source_prop.IsLocked())
    except Exception:
        pass


def _create_custom_property(source_prop, target):
    name = _safe_prop_name(source_prop)

    existing = target.PropertyList.Find(name)
    if existing is not None:
        if _is_user_property(existing):
            return existing
        return None

    try:
        return target.PropertyCreate(
            name,
            source_prop.GetPropertyType(),
            _property_data_type(source_prop),
            source_prop.IsAnimatable(),
            True,
            _property_reference_source(source_prop),
        )
    except Exception:
        return None


def _copy_custom_properties(source, target):
    copied_props = 0
    animated_prop_pairs = []
    copied_prop_pairs = []

    for source_prop in source.PropertyList:
        if not _is_user_property(source_prop):
            continue

        target_prop = _create_custom_property(source_prop, target)
        if target_prop is None:
            continue

        _copy_enum_strings(source_prop, target_prop)
        _copy_property_value(source_prop, target_prop)
        _copy_property_limits(source_prop, target_prop)

        copied_props += 1
        copied_prop_pairs.append((source_prop, target_prop))

        if _is_property_animated(source_prop):
            _set_property_animated(target_prop, True)
            animated_prop_pairs.append((source_prop, target_prop))

    return copied_props, animated_prop_pairs, copied_prop_pairs


def _copy_custom_property_locks(prop_pairs):
    for source_prop, target_prop in prop_pairs:
        _copy_property_locks(source_prop, target_prop)


def _copy_custom_property_animation_current_take(source_prop, target_prop, take):
    source_node = None
    target_node = None

    try:
        source_node = source_prop.GetAnimationNode()
    except Exception:
        pass

    try:
        target_node = target_prop.GetAnimationNode()
    except Exception:
        pass

    return _copy_animation_node_tree(source_node, target_node, take)


def _copy_custom_property_animation_all_takes(prop_pairs):
    if not prop_pairs:
        return 0

    system = FBSystem()
    original_take = system.CurrentTake
    copied_count = 0

    try:
        takes = [take for take in system.Scene.Takes]
        for take in takes:
            system.CurrentTake = take
            for source_prop, target_prop in prop_pairs:
                copied_count += _copy_custom_property_animation_current_take(
                    source_prop,
                    target_prop,
                    take,
                )
    finally:
        system.CurrentTake = original_take

    return copied_count


def _copy_transform_animation_current_take(source, target, take):
    animated_groups = set()
    copied_count = 0

    for node_path, group_name in TRANSFORM_CHANNELS:
        src_node = _find_animation_node(node_path, source.AnimationNode)
        if not src_node:
            continue

        has_curve = False
        try:
            has_curve = src_node.FCurve is not None
        except Exception:
            pass

        if not has_curve:
            try:
                layer_count = take.GetLayerCount()
            except Exception:
                layer_count = 0

            for layer_index in range(layer_count):
                if _get_layer_curve(src_node, layer_index):
                    has_curve = True
                    break

        if not has_curve:
            continue

        if group_name not in animated_groups:
            try:
                getattr(target, group_name).SetAnimated(True)
                animated_groups.add(group_name)
            except Exception:
                continue

        dst_node = _find_animation_node(node_path, target.AnimationNode)
        if dst_node and _copy_curve(src_node, dst_node, take):
            copied_count += 1

    return copied_count


def _copy_transform_animation_all_takes(pairs):
    system = FBSystem()
    original_take = system.CurrentTake
    copied_count = 0

    try:
        takes = [take for take in system.Scene.Takes]
        for take in takes:
            system.CurrentTake = take
            for source, target, _source_key in pairs:
                copied_count += _copy_transform_animation_current_take(
                    source,
                    target,
                    take,
                )
    finally:
        system.CurrentTake = original_take

    return copied_count


def _global_matrix(model):
    return _matrix(model, True)


def _set_global_matrix(model, matrix):
    _set_matrix(model, matrix, True)


def _reparent_unselected_children(sources, replacements_by_key, selected_keys):
    for source in sources:
        replacement = replacements_by_key[_model_key(source)]
        children = [child for child in source.Children]

        for child in children:
            if _model_key(child) in selected_keys:
                continue

            matrix = _global_matrix(child)
            child.Parent = replacement
            _set_global_matrix(child, matrix)


def _rename_replacements(pairs, old_names):
    for _source, target, source_key in pairs:
        try:
            target.Name = old_names[source_key]
        except Exception:
            pass


def change_selected_object_type():
    selected = _selected_models()

    if not selected:
        FBMessageBox(TOOL_NAME, "Select at least one object to change.", "OK")
        return

    spec = _show_type_dialog(len(selected))
    if spec is None:
        return

    target_label, target_class, type_key = spec
    protected = [model for model in selected if _is_system_camera(model)]
    candidates = [model for model in selected if model not in protected]
    unchanged = [model for model in candidates if isinstance(model, target_class)]
    sources = [model for model in candidates if not isinstance(model, target_class)]

    if not sources:
        if protected:
            FBMessageBox(
                TOOL_NAME,
                "Nothing changed. System cameras cannot be replaced.",
                "OK",
            )
        else:
            FBMessageBox(
                TOOL_NAME,
                "Selected object(s) are already {0}.".format(target_label),
                "OK",
            )
        return

    selected_keys = set(_model_key(model) for model in sources)
    old_names = {}
    replacements_by_key = {}
    transform_snapshots = {}
    custom_prop_pairs = []
    custom_prop_lock_pairs = []
    copied_custom_props = 0
    pairs = []

    _evaluate_scene()

    for index, source in enumerate(sources):
        source_key = _model_key(source)
        old_names[source_key] = source.Name
        transform_snapshots[source_key] = _snapshot_transform(source)
        target = _create_replacement(source, target_class, type_key, index)
        _evaluate_scene()
        replacements_by_key[source_key] = target
        pairs.append((source, target, source_key))

    _assign_replacement_parents(pairs, transform_snapshots, replacements_by_key)
    _evaluate_scene()

    for source, target, _source_key in pairs:
        _copy_model_state(source, target)
        prop_count, prop_pairs, prop_lock_pairs = _copy_custom_properties(source, target)
        copied_custom_props += prop_count
        custom_prop_pairs.extend(prop_pairs)
        custom_prop_lock_pairs.extend(prop_lock_pairs)

    _restore_replacement_transforms(pairs, transform_snapshots)
    _reparent_unselected_children(sources, replacements_by_key, selected_keys)
    _restore_replacement_transforms(pairs, transform_snapshots)
    copied_curves = _copy_transform_animation_all_takes(pairs)
    copied_custom_curves = _copy_custom_property_animation_all_takes(custom_prop_pairs)
    _copy_custom_property_locks(custom_prop_lock_pairs)
    _restore_replacement_transforms(pairs, transform_snapshots)

    for source in sources:
        source.Selected = False

    for source in sorted(sources, key=_model_depth, reverse=True):
        source.FBDelete()

    _evaluate_scene()
    _rename_replacements(pairs, old_names)
    _assign_replacement_parents(pairs, transform_snapshots, replacements_by_key)
    _evaluate_scene()
    _restore_replacement_transforms(pairs, transform_snapshots)
    parent_failures = _assign_replacement_parents(
        pairs,
        transform_snapshots,
        replacements_by_key,
    )

    for _source, target, _source_key in pairs:
        target.Selected = True

    for model in unchanged:
        model.Selected = True

    message = "Changed {0} object(s) to {1}.".format(len(pairs), target_label)
    if unchanged:
        message += " Skipped {0} already-matching object(s).".format(len(unchanged))
    if protected:
        message += " Skipped {0} system camera(s).".format(len(protected))

    if parent_failures:
        FBMessageBox(
            TOOL_NAME,
            "Changed object type, but parent restore failed for:\n\n{0}".format(
                "\n".join(parent_failures[:10])
            ),
            "OK",
        )

    print(
        "{0} Copied {1} transform FCurve channel(s), {2} custom property value(s), "
        "and {3} custom-property FCurve channel(s).".format(
            message,
            copied_curves,
            copied_custom_props,
            copied_custom_curves,
        )
    )


def run_with_error_dialog():
    try:
        change_selected_object_type()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
