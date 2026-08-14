"""Scene-persistent settings and exact-model FBX motion export."""

from __future__ import absolute_import

import json
import os


SETTINGS_OBJECT_NAME = "MOBU_TOOLS_MANAGER_EXPORT_SETTINGS"
PRESET_MODEL_NAME = "ExportPreset"
PROPERTY_FOLDER = "MTM Export Folder"
PROPERTY_FILE_NAME = "MTM Export File Name"
PROPERTY_ONE_TAKE = "MTM Export One Take Per File"
PROPERTY_MODELS = "MTM Export Model Long Names"
PROPERTY_MEMBER = "MTM Export Enabled"


class ExportSettings(object):
    def __init__(
        self,
        folder="",
        file_name="export.fbx",
        one_take_per_file=False,
        model_names=(),
    ):
        self.folder = str(folder or "")
        self.file_name = _fbx_file_name(file_name)
        self.one_take_per_file = bool(one_take_per_file)
        self.model_names = tuple(_unique_strings(model_names))

    @property
    def output_path(self):
        return os.path.abspath(os.path.join(self.folder, self.file_name))


def _unique_strings(values):
    result = []
    for value in values or ():
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _fbx_file_name(value):
    value = os.path.basename(str(value or "").strip()) or "export.fbx"
    if not value.lower().endswith(".fbx"):
        value += ".fbx"
    return value


def _default_folder(system, application):
    scene_path = str(getattr(application, "FBXFileName", "") or "").strip()
    if scene_path:
        return os.path.dirname(os.path.abspath(scene_path))
    return os.path.abspath(
        str(getattr(system, "UserConfigPath", "") or os.getcwd())
    )


def _default_file_name(application):
    scene_path = str(getattr(application, "FBXFileName", "") or "").strip()
    if not scene_path:
        return "export.fbx"
    stem = os.path.splitext(os.path.basename(scene_path))[0]
    return _fbx_file_name((stem or "scene") + "_export")


def model_long_name(model):
    value = str(getattr(model, "LongName", "") or "").strip()
    return value or str(getattr(model, "Name", "") or "").strip()


def iter_model_hierarchy(scene):
    """Yield ``(model, depth)`` without retaining results across invalidation."""
    root = getattr(scene, "RootModel", None)
    children = (
        tuple(getattr(root, "Children", ()) or ()) if root is not None else ()
    )
    pending = [(model, 0) for model in reversed(children)]
    while pending:
        model, depth = pending.pop()
        if str(getattr(model, "Name", "") or "") == PRESET_MODEL_NAME:
            continue
        yield model, depth
        descendants = tuple(getattr(model, "Children", ()) or ())
        pending.extend(
            (child, depth + 1) for child in reversed(descendants)
        )


def _preset_model(scene, sdk, create=False):
    root = getattr(scene, "RootModel", None)
    for model in tuple(getattr(root, "Children", ()) or ()):
        if str(getattr(model, "Name", "") or "") == PRESET_MODEL_NAME:
            return model
    if not create:
        return None
    return sdk.FBModelNull(PRESET_MODEL_NAME)


def _settings_object(scene):
    for item in tuple(getattr(scene, "UserObjects", ()) or ()):
        if str(getattr(item, "Name", "") or "") == SETTINGS_OBJECT_NAME:
            return item
    return None


def _delete_legacy_settings_objects(scene):
    for item in tuple(getattr(scene, "UserObjects", ()) or ()):
        if str(getattr(item, "Name", "") or "") != SETTINGS_OBJECT_NAME:
            continue
        delete = getattr(item, "FBDelete", None)
        if callable(delete):
            delete()


def _property(owner, sdk, name, property_type, data_type):
    prop = owner.PropertyList.Find(name)
    if prop is None:
        prop = owner.PropertyCreate(
            name,
            property_type,
            data_type,
            False,
            True,
            None,
        )
    if prop is None:
        raise RuntimeError("Could not create scene export property: " + name)
    return prop


def _property_data(owner, name, default):
    if owner is None:
        return default
    prop = owner.PropertyList.Find(name)
    return default if prop is None else prop.Data


def _settings_from_marked_models(scene):
    marked_models = []
    stored_values = None
    for model, _depth in iter_model_hierarchy(scene):
        if not bool(_property_data(model, PROPERTY_MEMBER, False)):
            continue
        marked_models.append(model_long_name(model))
        if stored_values is None:
            stored_values = (
                _property_data(model, PROPERTY_FOLDER, ""),
                _property_data(model, PROPERTY_FILE_NAME, "export.fbx"),
                bool(_property_data(model, PROPERTY_ONE_TAKE, False)),
            )
    if not marked_models or stored_values is None:
        return None
    return ExportSettings(
        folder=stored_values[0],
        file_name=stored_values[1],
        one_take_per_file=stored_values[2],
        model_names=marked_models,
    )


def _settings_from_preset(scene, sdk):
    owner = _preset_model(scene, sdk, create=False)
    if owner is None:
        return None
    raw_models = _property_data(owner, PROPERTY_MODELS, "")
    try:
        decoded_models = json.loads(str(raw_models or "[]"))
        if not isinstance(decoded_models, (list, tuple)):
            return None
    except (TypeError, ValueError):
        return None
    return ExportSettings(
        folder=_property_data(owner, PROPERTY_FOLDER, ""),
        file_name=_property_data(owner, PROPERTY_FILE_NAME, "export.fbx"),
        one_take_per_file=bool(
            _property_data(owner, PROPERTY_ONE_TAKE, False)
        ),
        model_names=tuple(_unique_strings(decoded_models)),
    )


def read_settings(system, application, sdk):
    scene = system.Scene
    preset_settings = _settings_from_preset(scene, sdk)
    if preset_settings is not None:
        return preset_settings
    model_settings = _settings_from_marked_models(scene)
    if model_settings is not None:
        return model_settings
    owner = _settings_object(scene)
    default_models = tuple(
        model_long_name(model)
        for model, _depth in iter_model_hierarchy(scene)
        if bool(getattr(model, "Selected", False))
    )
    raw_models = _property_data(owner, PROPERTY_MODELS, "")
    try:
        decoded_models = json.loads(str(raw_models or "[]"))
        if not isinstance(decoded_models, (list, tuple)):
            decoded_models = ()
        model_names = tuple(_unique_strings(decoded_models))
    except (TypeError, ValueError):
        model_names = ()
    if owner is None:
        model_names = default_models
    return ExportSettings(
        folder=_property_data(
            owner,
            PROPERTY_FOLDER,
            _default_folder(system, application),
        ),
        file_name=_property_data(
            owner,
            PROPERTY_FILE_NAME,
            _default_file_name(application),
        ),
        one_take_per_file=bool(
            _property_data(owner, PROPERTY_ONE_TAKE, False)
        ),
        model_names=model_names,
    )


def write_settings(system, sdk, settings):
    all_models, configured_models, missing = resolve_models(
        system.Scene,
        settings.model_names,
    )
    if missing:
        raise RuntimeError(
            "The configured export objects are missing or renamed:\n"
            + "\n".join(missing)
        )
    del configured_models
    property_type = sdk.FBPropertyType
    preset = _preset_model(system.Scene, sdk, create=True)
    _property(
        preset,
        sdk,
        PROPERTY_FOLDER,
        property_type.kFBPT_charptr,
        "String",
    ).Data = str(settings.folder)
    _property(
        preset,
        sdk,
        PROPERTY_FILE_NAME,
        property_type.kFBPT_charptr,
        "String",
    ).Data = _fbx_file_name(settings.file_name)
    _property(
        preset,
        sdk,
        PROPERTY_ONE_TAKE,
        property_type.kFBPT_bool,
        "Bool",
    ).Data = bool(settings.one_take_per_file)
    _property(
        preset,
        sdk,
        PROPERTY_MODELS,
        property_type.kFBPT_charptr,
        "String",
    ).Data = json.dumps(
        list(_unique_strings(settings.model_names)),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    # Remove markers left by the previous persistence implementation. The
    # complete preset now has one deterministic owner that is exported with
    # the selected hierarchy objects.
    managed_properties = (
        PROPERTY_FOLDER,
        PROPERTY_FILE_NAME,
        PROPERTY_ONE_TAKE,
        PROPERTY_MEMBER,
    )
    for model in all_models:
        for property_name in managed_properties:
            prop = model.PropertyList.Find(property_name)
            if prop is not None:
                model.PropertyRemove(prop)

    _delete_legacy_settings_objects(system.Scene)

    return preset


def resolve_models(scene, model_names):
    requested = set(_unique_strings(model_names))
    resolved = []
    found = set()
    all_models = []
    for model, _depth in iter_model_hierarchy(scene):
        all_models.append(model)
        name = model_long_name(model)
        if name in requested:
            resolved.append(model)
            found.add(name)
    missing = tuple(sorted(requested.difference(found)))
    return tuple(all_models), tuple(resolved), missing


def export_fbx(system, application, sdk, settings=None):
    settings = settings or read_settings(system, application, sdk)
    if not settings.folder:
        raise RuntimeError("Set an export folder in Export Settings.")
    if not os.path.isdir(settings.folder):
        raise RuntimeError(
            "The export folder does not exist: " + settings.folder
        )
    if not settings.model_names:
        raise RuntimeError(
            "Select at least one hierarchy object in Export Settings."
        )

    # Store the preset on a scene Null and force that Null into the selected
    # model export so its custom properties travel with the FBX.
    preset = write_settings(system, sdk, settings)
    all_models, export_models, missing = resolve_models(
        system.Scene,
        settings.model_names,
    )
    if missing:
        raise RuntimeError(
            "The configured export objects are missing or renamed:\n"
            + "\n".join(missing)
        )
    if not export_models:
        raise RuntimeError(
            "None of the configured hierarchy objects are available."
        )

    output_path = settings.output_path
    selection_states = tuple(
        (model, bool(getattr(model, "Selected", False)))
        for model in tuple(all_models) + (preset,)
    )
    requested_names = set(settings.model_names)
    try:
        for model in all_models:
            model.Selected = model_long_name(model) in requested_names
        preset.Selected = True
        options = sdk.FBMotionFileExportOptions(output_path)
        options.ModelSelection = sdk.FBModelSelection.kFBSelectedModels
        options.OneTakePerFile = bool(settings.one_take_per_file)
        options.AddPrefix = bool(settings.one_take_per_file)
        options.FileCreation = sdk.FBFileCreation.kFBOverwrite
        if not bool(options.IsValid()):
            raise RuntimeError(
                "MotionBuilder rejected the FBX export path or take settings."
            )
        if not bool(application.FileExportWithOptions(options)):
            raise RuntimeError(
                "MotionBuilder did not complete the FBX export."
            )
        if settings.one_take_per_file:
            paths = [
                str(options.GetTakeFilePath(index) or "")
                for index in range(int(options.GetTakeCount()))
                if bool(options.GetTakeSelect(index))
            ]
            return tuple(path for path in paths if path)
        return (output_path,)
    finally:
        for model, selected in selection_states:
            model.Selected = selected
