"""Scene-persistent settings and exact-model FBX motion export."""

from __future__ import absolute_import

import json
import os


SETTINGS_OBJECT_NAME = "MOBU_TOOLS_MANAGER_EXPORT_SETTINGS"
PROPERTY_FOLDER = "MTM Export Folder"
PROPERTY_FILE_NAME = "MTM Export File Name"
PROPERTY_ONE_TAKE = "MTM Export One Take Per File"
PROPERTY_MODELS = "MTM Export Model Long Names"


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
        yield model, depth
        descendants = tuple(getattr(model, "Children", ()) or ())
        pending.extend(
            (child, depth + 1) for child in reversed(descendants)
        )


def _settings_object(scene, sdk, create=False):
    for item in tuple(getattr(scene, "UserObjects", ()) or ()):
        if str(getattr(item, "Name", "") or "") == SETTINGS_OBJECT_NAME:
            return item
    if not create:
        return None
    return sdk.FBUserObject(SETTINGS_OBJECT_NAME)


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


def read_settings(system, application, sdk):
    scene = system.Scene
    owner = _settings_object(scene, sdk, create=False)
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
    owner = _settings_object(system.Scene, sdk, create=True)
    property_type = sdk.FBPropertyType
    _property(
        owner,
        sdk,
        PROPERTY_FOLDER,
        property_type.kFBPT_charptr,
        "String",
    ).Data = str(settings.folder)
    _property(
        owner,
        sdk,
        PROPERTY_FILE_NAME,
        property_type.kFBPT_charptr,
        "String",
    ).Data = _fbx_file_name(settings.file_name)
    _property(
        owner,
        sdk,
        PROPERTY_ONE_TAKE,
        property_type.kFBPT_bool,
        "Bool",
    ).Data = bool(settings.one_take_per_file)
    _property(
        owner,
        sdk,
        PROPERTY_MODELS,
        property_type.kFBPT_charptr,
        "String",
    ).Data = json.dumps(
        list(_unique_strings(settings.model_names)),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return owner


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
        for model in all_models
    )
    requested_names = set(settings.model_names)
    try:
        for model in all_models:
            model.Selected = model_long_name(model) in requested_names
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
