import traceback

from pyfbsdk import (
    FBColor,
    FBFindModelByLabelName,
    FBMessageBox,
    FBModel,
    FBModelTransformationType,
    FBModelNull,
    FBModelPath3D,
    FBSystem,
    FBVector3d,
    FBVector4d,
)


TOOL_NAME = "Create Grid Axis Lines"
GRID_HALF_LENGTH = 500.0
LINE_HEIGHT = 0.0

X_AXIS_NAME = "Grid Axis Guide - X Red"
Z_AXIS_NAME = "Grid Axis Guide - Z Blue"
PARENT_NULL_NAME = "Scene"
TRANSFORM_PROPERTY_NAME_GROUPS = (
    ("Translation (Lcl)", "Lcl Translation"),
    ("Rotation (Lcl)", "Lcl Rotation"),
    ("Scaling (Lcl)", "Lcl Scaling"),
)
AXIS_DUPLICATE_SEPARATORS = (" ", "_", ".", "(", "-")


def set_if_available(model, attribute_name, value):
    try:
        setattr(model, attribute_name, value)
    except Exception:
        pass


def model_name_matches(model, name):
    for attribute_name in ("Name", "LongName"):
        try:
            value = str(getattr(model, attribute_name))
        except Exception:
            continue

        if value == name or value.endswith("::" + name):
            return True

    return False


def model_name_values(model):
    values = []
    for attribute_name in ("Name", "LongName"):
        try:
            value = str(getattr(model, attribute_name))
        except Exception:
            continue

        if value and value not in values:
            values.append(value)

    return values


def short_model_name(value):
    value = str(value).replace("\\", "/")

    if "/" in value:
        value = value.rsplit("/", 1)[-1]

    if "::" in value:
        value = value.rsplit("::", 1)[-1]

    if ":" in value:
        value = value.rsplit(":", 1)[-1]

    return value


def is_path_model(model):
    if isinstance(model, FBModelPath3D):
        return True

    return all(
        hasattr(model, attribute_name)
        for attribute_name in ("PathKeyGetCount", "PathKeySet", "PathKeyRemove")
    )


def axis_name_matches(model, base_name):
    if not is_path_model(model):
        return False

    for value in model_name_values(model):
        short_name = short_model_name(value)
        if short_name == base_name:
            return True

        for separator in AXIS_DUPLICATE_SEPARATORS:
            if short_name.startswith(base_name + separator):
                return True

    return False


def model_has_exact_short_name(model, name):
    for value in model_name_values(model):
        if short_model_name(value) == name:
            return True

    return False


def set_model_name(model, name):
    try:
        model.SetName(name)
        return
    except Exception:
        pass

    try:
        model.Name = name
    except Exception:
        pass


def axis_candidates(base_name):
    candidates = []

    for component in FBSystem().Scene.Components:
        if axis_name_matches(component, base_name):
            candidates.append(component)

    return candidates


def choose_axis_path(base_name):
    candidates = axis_candidates(base_name)
    if not candidates:
        return FBModelPath3D(base_name)

    primary = candidates[0]
    for candidate in candidates:
        if model_has_exact_short_name(candidate, base_name):
            primary = candidate
            break

    for candidate in candidates:
        if candidate is primary:
            continue

        try:
            candidate.FBDelete()
        except Exception:
            pass

    if not model_has_exact_short_name(primary, base_name):
        set_model_name(primary, base_name)

    return primary


def is_scene_parent_model(model):
    return isinstance(model, FBModel)


def find_model_by_name(name):
    model = FBFindModelByLabelName(name)
    if model is not None and is_scene_parent_model(model):
        return model

    for component in FBSystem().Scene.Components:
        if is_scene_parent_model(component) and model_name_matches(component, name):
            return component

    return None


def find_property(model, property_names):
    for property_name in property_names:
        try:
            prop = model.PropertyList.Find(property_name)
        except Exception:
            prop = None

        if prop is not None:
            return prop

    return None


def lock_vector_property(prop):
    if prop is None:
        return

    for index in range(3):
        try:
            prop.SetMemberLocked(index, True)
        except Exception:
            pass

    try:
        prop.SetLocked(True)
    except Exception:
        pass


def lock_scene_null_transforms(scene_null):
    for property_names in TRANSFORM_PROPERTY_NAME_GROUPS:
        lock_vector_property(find_property(scene_null, property_names))

    set_if_available(scene_null, "Transformable", False)


def get_scene_null():
    scene_null = find_model_by_name(PARENT_NULL_NAME)
    if scene_null is None:
        scene_null = FBModelNull(PARENT_NULL_NAME)
        scene_null.Show = True
        scene_null.Visibility = True
        scene_null.Translation = FBVector3d(0.0, 0.0, 0.0)
        scene_null.Rotation = FBVector3d(0.0, 0.0, 0.0)
        scene_null.Scaling = FBVector3d(1.0, 1.0, 1.0)
    else:
        set_if_available(scene_null, "Show", True)
        set_if_available(scene_null, "Visibility", True)

    lock_scene_null_transforms(scene_null)

    return scene_null


def configure_axis_path(path, translation, start_point, end_point, color, parent):
    path.Show = True
    path.Visibility = True
    path.Color = color

    set_if_available(path, "Pickable", False)
    set_if_available(path, "Transformable", False)
    set_if_available(path, "PathLengthShow", False)

    try:
        path.ShowCurveControls(False)
    except Exception:
        pass

    try:
        path.ShowCurvePoints(False)
    except Exception:
        pass

    while path.PathKeyGetCount() > 2:
        path.PathKeyRemove(path.PathKeyGetCount() - 1)

    while path.PathKeyGetCount() < 2:
        path.PathKeyEndAdd(FBVector4d(0.0, LINE_HEIGHT, 0.0, 0.0))

    path.PathKeySet(0, start_point)
    path.PathKeySet(1, end_point)

    try:
        path.Selected = False
    except Exception:
        pass

    try:
        path.Parent = parent
    except Exception:
        pass

    try:
        path.SetVector(translation, FBModelTransformationType.kModelTranslation, True)
    except Exception:
        path.Translation = translation

    try:
        path.SetVector(FBVector3d(0.0, 0.0, 0.0), FBModelTransformationType.kModelRotation, True)
    except Exception:
        path.Rotation = FBVector3d(0.0, 0.0, 0.0)

    return path


def ensure_axis_path(name, translation, start_point, end_point, color, parent):
    path = choose_axis_path(name)
    return configure_axis_path(path, translation, start_point, end_point, color, parent)


def create_grid_axis_lines():
    parent = get_scene_null()

    half = float(GRID_HALF_LENGTH)
    y = float(LINE_HEIGHT)

    x_axis = ensure_axis_path(
        X_AXIS_NAME,
        FBVector3d(-half, y, 0.0),
        FBVector4d(0.0, 0.0, 0.0, 0.0),
        FBVector4d(half * 2.0, 0.0, 0.0, 0.0),
        FBColor(1.0, 0.0, 0.0),
        parent,
    )

    z_axis = ensure_axis_path(
        Z_AXIS_NAME,
        FBVector3d(0.0, y, -half),
        FBVector4d(0.0, 0.0, 0.0, 0.0),
        FBVector4d(0.0, 0.0, half * 2.0, 0.0),
        FBColor(0.0, 0.25, 1.0),
        parent,
    )

    FBSystem().Scene.Evaluate()
    return x_axis, z_axis


def main():
    return create_grid_axis_lines()


try:
    main()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
