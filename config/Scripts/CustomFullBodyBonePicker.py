from pyfbsdk import *
from pyfbsdk_additions import *
import json
import os
import traceback
import xml.etree.ElementTree as ET

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import getCppPointer, wrapInstance, isValid
except Exception:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import getCppPointer, wrapInstance, isValid


TOOL_NAME = "Custom Full Body Bone Picker"
VIEW_RESOURCE = "FullBody"
CHARACTER_CONTROLS_DIR = r"C:\Program Files\Autodesk\MotionBuilder 2026\bin\system\CharacterControls"
CONFIG_NAMES = ("CharacterControlsConfigFull.xml", "CharacterControlsConfig.xml")

BACKGROUND_LEFT = 0
SELECTOR_ROWS_TOP = 5
SELECTOR_ROW_HEIGHT = 26
BAKE_ROW_TOP = SELECTOR_ROWS_TOP + (SELECTOR_ROW_HEIGHT * 2) + 5
BAKE_ROW_HEIGHT = 23
TOOLBAR_TOP = BAKE_ROW_TOP + BAKE_ROW_HEIGHT + 5
TOOLBAR_HEIGHT = 22
BACKGROUND_TOP = TOOLBAR_TOP + TOOLBAR_HEIGHT + 5
BACKGROUND_WIDTH = 250
BACKGROUND_HEIGHT = 380
MARGIN = 0
TOOL_WIDTH = BACKGROUND_LEFT + BACKGROUND_WIDTH + MARGIN
TOOL_HEIGHT = BACKGROUND_TOP + BACKGROUND_HEIGHT + MARGIN
MIN_TOOL_WIDTH = 96
MIN_TOOL_HEIGHT = 180
PICKER_UI_HORIZONTAL = "horizontal"
PICKER_UI_VERTICAL = "vertical"
VERTICAL_TOOLBAR_WIDTH = 24
VERTICAL_TOOLBAR_GAP = 4
COLLAPSED_SELECTOR_HEIGHT = 14
SELECTOR_CHEVRON_WIDTH = 18
PICKER_UI_SETTINGS_ORGANIZATION = "CustomFullBodyBonePicker"
PICKER_UI_SETTINGS_APPLICATION = "PickerUI"
DOCK_OBJECT_NAME = "CustomFullBodyBonePickerDock"
DOCK_WIDTH = 253
DOCK_LAYOUT_FILENAME = "CustomFullBodyBonePickerDockLayout.json"

TOOLBAR_BUTTON_SPECS = (
    ("ik_visibility", "HIKCharacterToolIK.svg", "IK effector visibility"),
    ("fk_visibility", "HIKCharacterToolFK.svg", "FK effector visibility"),
    ("skeleton_visibility", "HIKCharacterToolSkeleton.svg", "Skeleton visibility"),
    ("key_full_body", "HIKCharacterToolFullBody.svg", "Full Body keying set"),
    ("key_full_body_no_pull", "HIKCharacterToolFullBodyNoPull.svg", "Full Body No Pull Manip keying set"),
    ("key_body_part", "HIKCharacterToolBodyPart.svg", "Body Part keying set"),
    ("key_selection", "HIKCharacterToolSelection.svg", "Selection keying set"),
    ("pin_translation", "HIKCharacterToolPinT.svg", "Pin Translation on selected IK effectors"),
    ("pin_rotation", "HIKCharacterToolPinR.svg", "Pin Rotation on selected IK effectors"),
    ("release_all_pins", "HIKCharacterToolReleaseAll.svg", "Temporarily bypass all pinning"),
    ("pinning_presets", "HIKCharacterToolPinningPreset.svg", "Pinning preset menu"),
    ("stance_pose", "HIKCharacterToolStancePose.svg", "Stance Pose"),
)
CUSTOM_PINNING_PRESET_SUFFIX = ".custom_full_body_picker.json"

IK_SIZE = 13.0
IK_SMALL_SIZE = 9.0
AUXILIARY_SIZE = IK_SIZE
AUXILIARY_GAP = 7.0
AUXILIARY_DISTANCE = 28.0
AUXILIARY_COLUMNS = 3
CHEST_AUXILIARY_EFFECTOR_IDS = (9, 10)
FORCE_FULL_SIZE_EFFECTOR_IDS = (0, 9, 11, 12, 16, 17, 18, 19)
FK_ENDPOINT_INSET = IK_SIZE * 0.5
FK_HIT_WIDTH = 8.0
BOX_DRAG_THRESHOLD = 5.0
SLIDER_STEPS = 1000
SLIDER_POPUP_SCALE = 0.5
EFFECTOR_SLIDER_SPECS = (
    ("IK Blend T", "IK Reach Translation"),
    ("IK Blend R", "IK Reach Rotation"),
    ("IK Pull", "IK Pull"),
)
SELECTION_KEYING_GROUP_NAMES = (
    "CustomFullBodyPickerSelectionTRS",
    "CustomHandPickerSelectionTRS",
)

_TOOL = None
_PICKER_DATA = None
_LAST_UI_KEYING_MODE = None
_FK_MODEL_CACHE = {"control_set": None, "models": {}}
_NATIVE_WIDGET = None


def component_name(component):
    if component is None:
        return ""
    for attr_name in ("LongName", "Name", "LabelName"):
        try:
            value = getattr(component, attr_name)
        except Exception:
            value = ""
        if value:
            return str(value)
    try:
        return str(component)
    except Exception:
        return ""


def find_character_controls_config():
    candidates = []
    for filename in CONFIG_NAMES:
        candidates.append(os.path.join(CHARACTER_CONTROLS_DIR, filename))

    try:
        app_path = str(FBSystem().ApplicationPath)
    except Exception:
        app_path = ""
    if app_path:
        bin_dir = app_path if os.path.basename(app_path).lower() == "bin" else os.path.dirname(app_path)
        cc_dir = os.path.join(bin_dir, "system", "CharacterControls")
        for filename in CONFIG_NAMES:
            candidate = os.path.join(cc_dir, filename)
            if candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError("Could not find MotionBuilder Character Controls configuration.")


def read_picker_data():
    config_path = find_character_controls_config()
    root = ET.parse(config_path).getroot()
    resource_path = root.find("ResourcePath")
    resource_dir_name = resource_path.get("value", "DefaultImages") if resource_path is not None else "DefaultImages"

    view = None
    for candidate in root.findall("View"):
        if candidate.get("resource") == VIEW_RESOURCE:
            view = candidate
            break
    if view is None:
        raise RuntimeError("The FullBody Character Controls view is missing from:\n" + config_path)

    anchors = {}
    for anchor in view.findall("Anchor"):
        try:
            anchors[anchor.get("name")] = (float(anchor.get("x")), float(anchor.get("y")))
        except Exception:
            pass

    items = []
    for element in list(view):
        tag = element.tag
        if tag not in ("Button", "IK", "FK"):
            continue
        try:
            model_id = int(element.get("id"))
        except Exception:
            continue

        if tag == "FK":
            start = anchors.get(element.get("anchor1"))
            end = anchors.get(element.get("anchor2"))
            if start is None or end is None:
                continue
            item = {
                "kind": "fk",
                "id": model_id,
                "start": start,
                "end": end,
            }
        else:
            center = anchors.get(element.get("anchor"))
            if center is None:
                continue
            resource = element.get("resource", "")
            item = {
                "kind": "reference" if tag == "Button" else "ik",
                "id": model_id,
                "center": center,
                "small": "small" in resource.lower() and not (tag == "IK" and model_id in FORCE_FULL_SIZE_EFFECTOR_IDS),
            }

        item["body_part"] = element.get("body_part", "")
        item["tooltip"] = element.get("tooltip", "%s %s" % (tag, model_id))
        if item["kind"] == "fk" and item["tooltip"] == "Spine":
            start_x, start_y = item["start"]
            end_x, end_y = item["end"]
            spine_names = ("Spine", "Spine1", "Spine2")
            for spine_index, spine_name in enumerate(spine_names):
                start_ratio = float(spine_index) / float(len(spine_names))
                end_ratio = float(spine_index + 1) / float(len(spine_names))
                split_item = dict(item)
                split_item["tooltip"] = spine_name
                split_item["start"] = (
                    start_x + (end_x - start_x) * start_ratio,
                    start_y + (end_y - start_y) * start_ratio,
                )
                split_item["end"] = (
                    start_x + (end_x - start_x) * end_ratio,
                    start_y + (end_y - start_y) * end_ratio,
                )
                split_item["start_inset"] = FK_ENDPOINT_INSET if spine_index == 0 else 1.0
                split_item["end_inset"] = FK_ENDPOINT_INSET if spine_index == len(spine_names) - 1 else 1.0
                items.append(split_item)
        else:
            items.append(item)

    head_anchor = anchors.get("ikHead0")
    if head_anchor is not None:
        items.append({
            "kind": "fk",
            "id": 14,
            "start": head_anchor,
            "end": (head_anchor[0], max(4.0, head_anchor[1] - 24.0)),
            "start_inset": FK_ENDPOINT_INSET,
            "end_inset": 1.0,
            "body_part": "Neck",
            "tooltip": "Head",
        })

    background_path = os.path.join(os.path.dirname(config_path), resource_dir_name, VIEW_RESOURCE + ".png")
    return {
        "config_path": config_path,
        "background_path": background_path,
        "items": items,
    }


def picker_data():
    global _PICKER_DATA
    if _PICKER_DATA is None:
        _PICKER_DATA = read_picker_data()
    return _PICKER_DATA


def get_current_character():
    app = FBApplication()
    try:
        if app.CurrentCharacter is not None:
            return app.CurrentCharacter
    except Exception:
        pass
    try:
        characters = [character for character in FBSystem().Scene.Characters]
    except Exception:
        characters = []
    if len(characters) == 1:
        return characters[0]
    return None


def effector_id_from_int(value):
    try:
        return FBEffectorId(value)
    except Exception:
        return value


def effector_set_id_from_int(value):
    try:
        return FBEffectorSetID(value)
    except Exception:
        return value


def auxiliary_effector_set_ids():
    result = []
    try:
        values = list(FBEffectorSetID.values.values())
    except Exception:
        values = []
    for value in values:
        try:
            numeric = int(value)
        except Exception:
            continue
        if numeric <= 0:
            continue
        try:
            if numeric >= int(FBEffectorSetID.FBLastEffectorSetIndex):
                continue
        except Exception:
            if numeric >= 15:
                continue
        result.append((numeric, value))
    return result


def auxiliary_model_is_pivot(model):
    if model is None:
        return False
    try:
        ik_sync = model.PropertyList.Find("IKSync", False)
    except Exception:
        ik_sync = None
    try:
        draw_link = model.PropertyList.Find("DrawLink", False)
    except Exception:
        draw_link = None
    try:
        return bool(ik_sync is not None and draw_link is not None and ik_sync.Data and draw_link.Data)
    except Exception:
        return False


def auxiliary_models_for_effector(character, effector_id):
    result = []
    if character is None:
        return result
    for numeric_set_id, set_id in auxiliary_effector_set_ids():
        try:
            model = character.GetEffectorModel(effector_id, set_id)
        except Exception:
            model = None
        if model is not None:
            result.append((numeric_set_id, model, auxiliary_model_is_pivot(model)))
    return result


def all_auxiliary_models(character):
    result = []
    seen = set()
    for item in picker_data()["items"]:
        if item.get("kind") != "ik":
            continue
        try:
            numeric_id = int(item.get("id"))
        except Exception:
            continue
        if numeric_id in seen:
            continue
        seen.add(numeric_id)
        for _set_id, model, _pivot in auxiliary_models_for_effector(
            character, effector_id_from_int(numeric_id)
        ):
            result.append(model)
    return unique_models(result)


def normalized_fk_name(value):
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def expected_control_set_fk_names(tooltip):
    compact = "".join(str(tooltip or "").split())
    candidates = [compact]
    for side in ("Left", "Right"):
        if not compact.startswith(side):
            continue
        part = compact[len(side):]
        if part == "Toe":
            candidates.append(side + "ToeBase")
        elif part == "Collar":
            candidates.append(side + "Shoulder")
        elif part.startswith(("InThumb", "InIndex", "InMiddle", "InRing", "InPinky", "InExtra")):
            finger = part[2:]
            if finger == "Extra":
                finger = "ExtraFinger"
            candidates.append(side + "InHand" + finger)
        elif part.startswith(("Thumb", "Index", "Middle", "Ring", "Pinky", "Extra")):
            if part.startswith("Extra"):
                part = "ExtraFinger" + part[len("Extra"):]
            candidates.append(side + "Hand" + part)
        break
    return [normalized_fk_name(candidate) for candidate in candidates]


def get_current_control_set(character):
    if character is None:
        return None
    try:
        return character.GetCurrentControlSet()
    except Exception:
        return None


def same_component(first, second):
    if first is second:
        return True
    if first is None or second is None:
        return False
    try:
        if first == second:
            return True
    except Exception:
        pass
    return component_name(first) == component_name(second) and type(first).__name__ == type(second).__name__


def scene_characters():
    try:
        return [character for character in FBSystem().Scene.Characters]
    except Exception:
        return []


def scene_actors():
    try:
        return [actor for actor in FBSystem().Scene.Actors]
    except Exception:
        return []


def character_source_state(character):
    if character is None:
        return "none", None
    try:
        if not bool(character.ActiveInput):
            return "none", None
    except Exception:
        return "none", None
    try:
        input_character = character.InputCharacter
    except Exception:
        input_character = None
    if input_character is not None:
        return "character", input_character
    try:
        input_actor = character.InputActor
    except Exception:
        input_actor = None
    if input_actor is not None:
        return "actor", input_actor
    control_set = get_current_control_set(character)
    if control_set is not None:
        return "control_rig", control_set
    return "none", None


def source_options_for_character(character):
    options = [("None", "none", None)]
    control_set = get_current_control_set(character)
    if control_set is not None:
        options.append(("Control Rig", "control_rig", control_set))
    for candidate in scene_characters():
        if same_component(candidate, character):
            continue
        options.append((component_name(candidate), "character", candidate))
    for actor in scene_actors():
        options.append((component_name(actor), "actor", actor))
    return options


def apply_character_source(character, source_kind, source_component=None):
    if character is None:
        return
    try:
        character.ActiveInput = False
    except Exception:
        pass

    if source_kind == "none":
        evaluate_scene()
        return

    if source_kind == "character":
        character.InputCharacter = source_component
        character.InputType = FBCharacterInputType.kFBCharacterInputCharacter
    elif source_kind == "actor":
        character.InputActor = source_component
        character.InputType = FBCharacterInputType.kFBCharacterInputActor
    elif source_kind == "control_rig":
        try:
            character.InputCharacter = None
        except Exception:
            pass
        try:
            character.InputActor = None
        except Exception:
            pass
    else:
        return

    character.ActiveInput = True
    evaluate_scene()


def get_control_set_fk_models(control_set):
    global _FK_MODEL_CACHE
    if control_set is None:
        return {}
    if _FK_MODEL_CACHE.get("control_set") is control_set:
        return _FK_MODEL_CACHE.get("models", {})

    models = {}
    for index in range(256):
        try:
            fk_name = control_set.GetFKName(index)
        except Exception:
            fk_name = ""
        try:
            model = control_set.GetFKModel(index)
        except Exception:
            model = None
        if fk_name and model is not None:
            models[normalized_fk_name(fk_name)] = model

    _FK_MODEL_CACHE = {"control_set": control_set, "models": models}
    return models


def get_fk_model_for_item(character, item):
    control_set = get_current_control_set(character)
    models = get_control_set_fk_models(control_set)
    for expected_name in expected_control_set_fk_names(item.get("tooltip")):
        model = models.get(expected_name)
        if model is not None:
            return model
    return None


def get_model_for_item(character, item):
    if character is None or item is None:
        return None

    kind = item.get("kind")
    model_id = item.get("id")
    if kind == "reference":
        control_set = get_current_control_set(character)
        if control_set is None:
            return None
        try:
            return control_set.GetReferenceModel()
        except Exception:
            return None

    if kind == "fk":
        return get_fk_model_for_item(character, item)

    if kind in ("aux_effector", "aux_pivot"):
        try:
            effector_id = effector_id_from_int(int(model_id))
            set_id = effector_set_id_from_int(int(item.get("effector_set_id")))
            return character.GetEffectorModel(effector_id, set_id)
        except Exception:
            return None

    effector_id = effector_id_from_int(model_id)
    try:
        model = character.GetEffectorModel(effector_id, FBEffectorSetID.FBEffectorSetDefault)
        if model is not None:
            return model
    except Exception:
        pass
    for pivot_index in (0, 1, 2):
        try:
            model = character.GetIKEffectorModel(effector_id, pivot_index)
            if model is not None:
                return model
        except Exception:
            pass
    return None


def split_fk_item(item, names):
    start_x, start_y = item["start"]
    end_x, end_y = item["end"]
    result = []
    count = len(names)
    for index, name in enumerate(names):
        start_ratio = float(index) / float(count)
        end_ratio = float(index + 1) / float(count)
        split_item = dict(item)
        split_item["tooltip"] = name
        split_item["start"] = (
            start_x + (end_x - start_x) * start_ratio,
            start_y + (end_y - start_y) * start_ratio,
        )
        split_item["end"] = (
            start_x + (end_x - start_x) * end_ratio,
            start_y + (end_y - start_y) * end_ratio,
        )
        split_item["start_inset"] = FK_ENDPOINT_INSET if index == 0 else 1.0
        split_item["end_inset"] = FK_ENDPOINT_INSET if index == count - 1 else 1.0
        result.append(split_item)
    return result


def picker_items_for_character(character):
    base_items = list(picker_data()["items"])
    neck_item = next(
        (
            item for item in base_items
            if item.get("kind") == "fk" and item.get("tooltip") == "Neck"
        ),
        None,
    )
    if neck_item is None:
        return base_items
    split_items = split_fk_item(neck_item, ("Neck", "Neck1", "Neck2"))
    if character is None or not all(get_model_for_item(character, item) is not None for item in split_items):
        return base_items
    result = []
    for item in base_items:
        if item is neck_item:
            result.extend(split_items)
        else:
            result.append(item)
    return result


def is_model_selected(model):
    try:
        return model is not None and bool(model.Selected)
    except Exception:
        return False


def model_identity(model):
    return component_name(model)


def unique_models(models):
    result = []
    seen = set()
    for model in models:
        if model is None:
            continue
        identity = model_identity(model)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(model)
    return result


def evaluate_scene():
    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass


def character_controls_dock_widgets():
    try:
        widgets = list(QtWidgets.QApplication.instance().allWidgets())
    except Exception:
        return []
    result = []
    for widget in widgets:
        try:
            if not isinstance(widget, QtWidgets.QDockWidget):
                continue
            text = (widget.windowTitle() + " " + widget.objectName()).lower()
            if "character controls" in text or "charactercontrols" in text:
                result.append(widget)
        except Exception:
            pass
    return result


def qobject_identity(obj):
    try:
        return int(getCppPointer(obj)[0])
    except Exception:
        return id(obj)


def capture_character_controls_visibility():
    return {
        qobject_identity(dock): bool(dock.isVisible())
        for dock in character_controls_dock_widgets()
    }


def restore_character_controls_visibility(visibility):
    created_dock = False
    for dock in character_controls_dock_widgets():
        identity = qobject_identity(dock)
        was_visible = bool(visibility.get(identity, False))
        if identity not in visibility:
            created_dock = True
        if was_visible:
            continue
        try:
            dock.hide()
            dock.setVisible(False)
        except Exception:
            pass
    if created_dock:
        # The first SDK selection of a control-rig model creates and shows the
        # native Character Controls dock synchronously.  Re-apply the saved
        # picker docking relation after that newly-created dock is hidden.
        try:
            QtCore.QTimer.singleShot(0, restore_picker_dock_layout)
        except Exception:
            pass


def clear_model_selection():
    models = FBModelList()
    FBGetSelectedModels(models, None, True, False)
    for model in models:
        try:
            model.Selected = False
        except Exception:
            pass


def make_model_last_selected(model):
    if model is None:
        return
    try:
        model.Transformable = True
    except Exception:
        pass
    try:
        FBSetLastSelectedModel(model)
    except Exception:
        pass
    try:
        model.HardSelect()
    except Exception:
        pass


def component_matches_name(component, target_name):
    name = component_name(component)
    return name == target_name or name.endswith("::" + target_name)


def remove_custom_selection_keying_groups():
    groups = []
    try:
        for component in FBSystem().Scene.Components:
            if any(component_matches_name(component, name) for name in SELECTION_KEYING_GROUP_NAMES):
                groups.append(component)
    except Exception:
        groups = []
    for group in groups:
        try:
            group.SetActive(False)
        except Exception:
            pass
        try:
            group.ClearAllItems()
        except Exception:
            pass
        try:
            group.FBDelete()
        except Exception:
            pass


def keying_mode_candidates():
    result = []
    for name in (
        "kFBCharacterKeyingFullBody",
        "kFBCharacterKeyingFullBodyNoPull",
        "kFBCharacterKeyingBodyPart",
        "kFBCharacterKeyingSelection",
    ):
        try:
            result.append(getattr(FBCharacterKeyingMode, name))
        except Exception:
            pass
    return result


def is_full_body_mode(mode):
    for name in ("kFBCharacterKeyingFullBody", "kFBCharacterKeyingFullBodyNoPull"):
        try:
            if mode == getattr(FBCharacterKeyingMode, name):
                return True
        except Exception:
            pass
    return False


def normalize_keying_mode(mode):
    if is_full_body_mode(mode):
        return mode
    for name in ("kFBCharacterKeyingBodyPart", "kFBCharacterKeyingSelection"):
        try:
            value = getattr(FBCharacterKeyingMode, name)
            if mode == value:
                return value
        except Exception:
            pass
    return None


def qt_key_from_keyboard_token(token):
    token = str(token or "").strip().upper()
    aliases = {
        "INS": "INSERT",
        "DEL": "DELETE",
        "BKSP": "BACKSPACE",
        "ESC": "ESCAPE",
        "PGUP": "PAGEUP",
        "PGDN": "PAGEDOWN",
    }
    token = aliases.get(token, token)
    try:
        return getattr(QtCore.Qt, "Key_" + token)
    except Exception:
        return None


def qt_modifiers_from_keyboard_token(token):
    modifiers = QtCore.Qt.NoModifier
    parts = str(token or "").upper().replace("+", " ").replace("|", " ").split()
    modifier_names = {
        "SHFT": QtCore.Qt.ShiftModifier,
        "SHIFT": QtCore.Qt.ShiftModifier,
        "CTRL": QtCore.Qt.ControlModifier,
        "CONTROL": QtCore.Qt.ControlModifier,
        "ALT": QtCore.Qt.AltModifier,
        "META": QtCore.Qt.MetaModifier,
    }
    for part in parts:
        if part == "NONE":
            continue
        modifier = modifier_names.get(part)
        if modifier is not None:
            modifiers |= modifier
    return modifiers


def configured_character_keying_shortcuts():
    action_modes = {
        "action.tool.character.full_body": "kFBCharacterKeyingFullBody",
        "action.tool.character.body_parts": "kFBCharacterKeyingBodyPart",
        "action.tool.character.selection": "kFBCharacterKeyingSelection",
    }
    config_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    keyboard_dir = os.path.join(config_root, "Keyboard")
    paths = []
    try:
        paths = [
            os.path.join(keyboard_dir, filename)
            for filename in os.listdir(keyboard_dir)
            if filename.lower().endswith(".txt")
        ]
    except Exception:
        paths = []
    paths.sort(key=lambda path: (os.path.basename(path).lower() != "blender.txt", path.lower()))

    bindings = {}
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8-sig") as stream:
                lines = stream.readlines()
        except Exception:
            continue
        for line in lines:
            if "=" not in line:
                continue
            action_name, value = [part.strip() for part in line.split("=", 1)]
            enum_name = action_modes.get(action_name)
            if enum_name is None or "{" not in value or "}" not in value:
                continue
            binding = value.split("{", 1)[1].split("}", 1)[0].strip()
            if ":" not in binding:
                continue
            modifier_token, key_event_token = binding.split(":", 1)
            key_parts = key_event_token.split("*", 1)
            if len(key_parts) > 1 and key_parts[1].strip().upper() != "DN":
                continue
            key = qt_key_from_keyboard_token(key_parts[0])
            if key is None:
                continue
            bindings[(key, qt_modifiers_from_keyboard_token(modifier_token))] = enum_name
        if bindings:
            break

    if not bindings:
        bindings = {
            (QtCore.Qt.Key_1, QtCore.Qt.NoModifier): "kFBCharacterKeyingFullBody",
            (QtCore.Qt.Key_2, QtCore.Qt.NoModifier): "kFBCharacterKeyingBodyPart",
            (QtCore.Qt.Key_3, QtCore.Qt.NoModifier): "kFBCharacterKeyingSelection",
        }
    return bindings


def qt_text_parts(obj):
    result = []
    for attr_name in ("text", "toolTip", "statusTip", "whatsThis", "accessibleName", "objectName", "windowTitle"):
        try:
            attr = getattr(obj, attr_name)
            value = attr() if callable(attr) else attr
        except Exception:
            value = None
        if value:
            result.append(str(value))
    return result


def keying_mode_matches_text(text, mode):
    text = text.lower()
    if is_full_body_mode(mode):
        return "full body" in text or "fullbody" in text
    try:
        if mode == FBCharacterKeyingMode.kFBCharacterKeyingBodyPart:
            return "body part" in text or "bodypart" in text
    except Exception:
        pass
    try:
        if mode == FBCharacterKeyingMode.kFBCharacterKeyingSelection:
            return "selection" in text and "selected properties" not in text
    except Exception:
        pass
    return False


def read_keying_mode_from_ui():
    try:
        widgets = list(QtWidgets.QApplication.instance().allWidgets())
    except Exception:
        return None
    for widget in widgets:
        try:
            if not isinstance(widget, QtWidgets.QAbstractButton) or not widget.isChecked():
                continue
        except Exception:
            continue
        own_text = " ".join(qt_text_parts(widget)).lower()
        ancestor_parts = []
        current = widget
        for _index in range(32):
            if current is None:
                break
            ancestor_parts.extend(qt_text_parts(current))
            try:
                current = current.parentWidget()
            except Exception:
                current = None
        ancestor_text = " ".join(ancestor_parts).lower()
        if "character controls" not in ancestor_text and "charactercontrols" not in ancestor_text:
            continue
        for mode in keying_mode_candidates():
            if keying_mode_matches_text(own_text, mode):
                return normalize_keying_mode(mode)
    return None


def get_character_controls_keying_mode(character):
    global _LAST_UI_KEYING_MODE
    ui_mode = normalize_keying_mode(read_keying_mode_from_ui())
    if ui_mode is not None:
        _LAST_UI_KEYING_MODE = ui_mode
        return ui_mode
    if _LAST_UI_KEYING_MODE is not None:
        return _LAST_UI_KEYING_MODE
    # Reading FBCharacter.KeyingMode before Character Controls has been
    # initialized can create/show the native Character Controls dock.  Passive
    # picker updates must never initialize that UI.
    return None


def restore_character_controls_keying_mode(character, mode):
    if character is None or mode is None:
        return
    remove_custom_selection_keying_groups()
    try:
        character.KeyingMode = mode
    except Exception:
        pass


def select_items(items, additive=False):
    character = get_current_character()
    if character is None:
        return
    models = unique_models([get_model_for_item(character, item) for item in items])
    if not models:
        return
    character_controls_visibility = capture_character_controls_visibility()
    try:
        if not additive:
            clear_model_selection()
        for model in models:
            try:
                model.Transformable = True
            except Exception:
                pass
            try:
                model.Selected = True
            except Exception:
                pass
        make_model_last_selected(models[-1])
        evaluate_scene()
    finally:
        restore_character_controls_visibility(character_controls_visibility)


def select_item(item, additive=False):
    character = get_current_character()
    if character is None:
        return
    model = get_model_for_item(character, item)
    if model is None:
        return
    character_controls_visibility = capture_character_controls_visibility()
    try:
        if additive:
            try:
                model.Selected = not bool(model.Selected)
            except Exception:
                return
            if is_model_selected(model):
                make_model_last_selected(model)
        else:
            clear_model_selection()
            try:
                model.Selected = True
            except Exception:
                pass
            make_model_last_selected(model)
        evaluate_scene()
    finally:
        restore_character_controls_visibility(character_controls_visibility)


def distance_to_segment(px, py, start, end):
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared <= 0.000001:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_squared))
    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy
    return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5


def shortened_fk_segment(item):
    x1, y1 = item["start"]
    x2, y2 = item["end"]
    dx = x2 - x1
    dy = y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0001:
        return (x1, y1), (x2, y2)
    default_inset = min(FK_ENDPOINT_INSET, length * 0.225)
    start_inset = min(float(item.get("start_inset", default_inset)), length * 0.45)
    end_inset = min(float(item.get("end_inset", default_inset)), length * 0.45)
    unit_x = dx / length
    unit_y = dy / length
    return (
        (x1 + unit_x * start_inset, y1 + unit_y * start_inset),
        (x2 - unit_x * end_inset, y2 - unit_y * end_inset),
    )


def find_property(owner, property_name):
    if owner is None:
        return None
    try:
        prop = owner.PropertyList.Find(property_name)
        if prop is not None:
            return prop
    except Exception:
        pass
    try:
        for prop in owner.PropertyList:
            try:
                if str(prop.GetName()) == property_name:
                    return prop
            except Exception:
                pass
    except Exception:
        pass
    return None


def get_effector_slider_properties(model):
    return {property_name: find_property(model, property_name) for _label, property_name in EFFECTOR_SLIDER_SPECS}


def model_has_effector_sliders(model):
    if model is None:
        return False
    props = get_effector_slider_properties(model)
    return any(prop is not None for prop in props.values())


def get_selected_effector_model():
    try:
        last_selected = FBGetLastSelectedModel()
    except Exception:
        last_selected = None
    if model_has_effector_sliders(last_selected):
        return last_selected

    selected_models = FBModelList()
    try:
        FBGetSelectedModels(selected_models, None, True, False)
    except Exception:
        return None
    for model in reversed([item for item in selected_models]):
        if model_has_effector_sliders(model):
            return model
    return None


def selected_effector_slider_models(context_model=None):
    selected_models = FBModelList()
    try:
        FBGetSelectedModels(selected_models, None, True, False)
    except Exception:
        selected_models = []
    models = unique_models(
        model for model in selected_models
        if model_has_effector_sliders(model)
    )
    if (
        context_model is not None
        and is_model_selected(context_model)
        and model_has_effector_sliders(context_model)
        and not any(same_component(context_model, model) for model in models)
    ):
        models.append(context_model)
    return models


def property_float(prop):
    try:
        return float(prop.Data)
    except Exception:
        return 0.0


def property_range(prop):
    min_value = 0.0
    max_value = 100.0
    try:
        min_value = float(prop.GetMin())
    except Exception:
        pass
    try:
        max_value = float(prop.GetMax())
    except Exception:
        pass
    if max_value <= min_value:
        min_value = 0.0
        max_value = 100.0
    return min_value, max_value


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def property_has_key_at_current_time(prop):
    if prop is None:
        return False
    try:
        node = prop.GetAnimationNode()
    except Exception:
        node = None
    if node is None:
        return False
    try:
        if node.IsKey():
            return True
    except Exception:
        pass
    try:
        current_ticks = FBSystem().LocalTime.Get()
        for key in node.FCurve.Keys:
            if key.Time.Get() == current_ticks:
                return True
    except Exception:
        pass
    return False


def delete_fcurve_keys_at_current_time(fcurve, current_time, current_ticks):
    if fcurve is None:
        return False
    indexes = []
    try:
        for index, key in enumerate(fcurve.Keys):
            if key.Time.Get() == current_ticks:
                indexes.append(index)
    except Exception:
        indexes = []
    removed = False
    for index in reversed(indexes):
        try:
            if fcurve.KeyDelete(index, index):
                removed = True
        except Exception:
            pass
    if removed:
        return True
    try:
        return bool(fcurve.KeyDelete(current_time, current_time, True))
    except Exception:
        return False


def remove_animation_node_key_at_current_time(node, current_time, current_ticks):
    if node is None:
        return False
    removed = False
    try:
        node.KeyRemoveAt(current_time)
        removed = True
    except Exception:
        pass
    try:
        fcurve = node.FCurve
    except Exception:
        fcurve = None
    if delete_fcurve_keys_at_current_time(fcurve, current_time, current_ticks):
        removed = True
    try:
        children = node.Nodes
    except Exception:
        children = []
    for child in children:
        if remove_animation_node_key_at_current_time(child, current_time, current_ticks):
            removed = True
    return removed


def remove_property_key_at_current_time(prop):
    if prop is None:
        return False
    try:
        current_time = FBSystem().LocalTime
        current_ticks = current_time.Get()
    except Exception:
        return False
    removed = False
    try:
        prop.KeyRemoveAt(current_time)
        removed = True
    except Exception:
        pass
    try:
        node = prop.GetAnimationNode()
    except Exception:
        node = None
    if remove_animation_node_key_at_current_time(node, current_time, current_ticks):
        removed = True
    return removed


def animation_node_key_count(node):
    if node is None:
        return 0
    count = 0
    try:
        fcurve = node.FCurve
    except Exception:
        fcurve = None
    if fcurve is not None:
        try:
            count += len(fcurve.Keys)
        except Exception:
            pass
    try:
        children = node.Nodes
    except Exception:
        children = []
    for child in children:
        count += animation_node_key_count(child)
    return count


def property_key_count_in_current_take(prop):
    if prop is None:
        return 0
    take = getattr(FBSystem(), "CurrentTake", None)
    if take is None:
        try:
            return animation_node_key_count(prop.GetAnimationNode())
        except Exception:
            return 0
    try:
        original_layer = int(take.GetCurrentLayer())
        layer_count = int(take.GetLayerCount())
    except Exception:
        original_layer = 0
        layer_count = 1
    count = 0
    try:
        for layer_index in range(max(1, layer_count)):
            try:
                take.SetCurrentLayer(layer_index)
                node = prop.GetAnimationNode()
            except Exception:
                node = None
            count += animation_node_key_count(node)
    finally:
        try:
            take.SetCurrentLayer(original_layer)
        except Exception:
            pass
    return count


def delete_all_fcurve_keys(fcurve):
    if fcurve is None:
        return 0
    try:
        original_count = len(fcurve.Keys)
    except Exception:
        return 0
    if original_count <= 0:
        return 0

    try:
        fcurve.EditClear()
    except Exception:
        pass
    try:
        if len(fcurve.Keys) == 0:
            return original_count
    except Exception:
        pass
    try:
        fcurve.KeyDelete(0, original_count - 1)
    except Exception:
        pass
    try:
        remaining_count = len(fcurve.Keys)
    except Exception:
        remaining_count = original_count
    if remaining_count:
        for index in reversed(range(remaining_count)):
            try:
                fcurve.KeyDelete(index, index)
            except Exception:
                pass
    try:
        return max(0, original_count - len(fcurve.Keys))
    except Exception:
        return 0


def remove_all_animation_node_keys(node):
    if node is None:
        return 0
    removed_count = 0
    try:
        fcurve = node.FCurve
    except Exception:
        fcurve = None
    removed_count += delete_all_fcurve_keys(fcurve)
    try:
        children = list(node.Nodes)
    except Exception:
        children = []
    for child in children:
        removed_count += remove_all_animation_node_keys(child)
    return removed_count


def remove_all_property_keys_in_current_take(prop):
    if prop is None:
        return 0
    take = getattr(FBSystem(), "CurrentTake", None)
    if take is None:
        try:
            return remove_all_animation_node_keys(prop.GetAnimationNode())
        except Exception:
            return 0
    try:
        original_layer = int(take.GetCurrentLayer())
        layer_count = int(take.GetLayerCount())
    except Exception:
        original_layer = 0
        layer_count = 1
    removed_count = 0
    try:
        for layer_index in range(max(1, layer_count)):
            try:
                take.SetCurrentLayer(layer_index)
                node = prop.GetAnimationNode()
            except Exception:
                node = None
            removed_count += remove_all_animation_node_keys(node)
    finally:
        try:
            take.SetCurrentLayer(original_layer)
        except Exception:
            pass
    return removed_count


def effector_blend_is_active(model):
    if model is None:
        return False
    for prop in get_effector_slider_properties(model).values():
        if prop is None:
            continue
        min_value, _max_value = property_range(prop)
        if property_float(prop) > min_value + 0.001:
            return True
    return False


def normalized_effector_property_value(model, property_name):
    prop = find_property(model, property_name)
    if prop is None:
        return 0.0
    min_value, max_value = property_range(prop)
    return clamp((property_float(prop) - min_value) / (max_value - min_value), 0.0, 1.0)


def effector_fill_color(pull_ratio, alpha=255):
    pull_ratio = clamp(float(pull_ratio), 0.0, 1.0)
    green = (96, 251, 96)
    red = (169, 40, 43)
    return QtGui.QColor(
        int(round(green[0] + (red[0] - green[0]) * pull_ratio)),
        int(round(green[1] + (red[1] - green[1]) * pull_ratio)),
        int(round(green[2] + (red[2] - green[2]) * pull_ratio)),
        int(alpha),
    )


def effector_pin_states(character, item):
    if character is None or item is None or item.get("kind") != "ik":
        return False, False
    try:
        effector_id = FBEffectorId(int(item.get("id")))
    except Exception:
        return False, False
    try:
        translation_pinned = bool(character.IsTranslationPin(effector_id))
    except Exception:
        translation_pinned = False
    try:
        rotation_pinned = bool(character.IsRotationPin(effector_id))
    except Exception:
        rotation_pinned = False
    return translation_pinned, rotation_pinned


def picker_effector_ids(character, selected_only=False):
    result = []
    seen = set()
    for item in picker_data()["items"]:
        if item.get("kind") != "ik":
            continue
        try:
            numeric_id = int(item.get("id"))
        except Exception:
            continue
        if numeric_id in seen:
            continue
        model = get_model_for_item(character, item)
        if model is None or (selected_only and not is_model_selected(model)):
            continue
        seen.add(numeric_id)
        result.append(effector_id_from_int(numeric_id))
    return result


def character_visibility(character, getter_name):
    if character is None:
        return False
    try:
        return bool(getattr(character, getter_name)())
    except Exception:
        return False


def set_character_visibility(character, setter_name, visible):
    if character is None:
        return
    getattr(character, setter_name)(bool(visible))
    evaluate_scene()


def pinning_preset_directory():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PinningPresets"))


def saved_pinning_preset_names():
    directory = pinning_preset_directory()
    try:
        filenames = os.listdir(directory)
    except Exception:
        return []
    names = []
    seen = set()
    for filename in filenames:
        full_path = os.path.join(directory, filename)
        if not os.path.isfile(full_path):
            continue
        if filename.lower().endswith(CUSTOM_PINNING_PRESET_SUFFIX):
            try:
                with open(full_path, "r", encoding="utf-8") as stream:
                    name = str(json.load(stream).get("name", "")).strip()
            except Exception:
                name = filename[:-len(CUSTOM_PINNING_PRESET_SUFFIX)].strip()
        else:
            name = os.path.splitext(filename)[0].strip()
        normalized = name.lower()
        if name and normalized not in seen:
            seen.add(normalized)
            names.append(name)
    return sorted(names, key=lambda value: value.lower())


def custom_pinning_preset_path(preset_name):
    safe_name = "".join(character if character not in '<>:"/\\|?*' else "_" for character in str(preset_name)).strip(" .")
    if not safe_name:
        safe_name = "PinningPreset"
    return os.path.join(pinning_preset_directory(), safe_name + CUSTOM_PINNING_PRESET_SUFFIX)


def find_custom_pinning_preset_path(preset_name):
    target = str(preset_name).strip().lower()
    directory = pinning_preset_directory()
    try:
        filenames = os.listdir(directory)
    except Exception:
        return None
    for filename in filenames:
        if not filename.lower().endswith(CUSTOM_PINNING_PRESET_SUFFIX):
            continue
        full_path = os.path.join(directory, filename)
        try:
            with open(full_path, "r", encoding="utf-8") as stream:
                stored_name = str(json.load(stream).get("name", "")).strip().lower()
        except Exception:
            stored_name = filename[:-len(CUSTOM_PINNING_PRESET_SUFFIX)].strip().lower()
        if stored_name == target:
            return full_path
    return None


def save_custom_pinning_preset(character, preset_name):
    if character is None:
        return False
    os.makedirs(pinning_preset_directory(), exist_ok=True)
    pins = []
    for effector_id in picker_effector_ids(character):
        pins.append({
            "id": int(effector_id),
            "translation": bool(character.IsTranslationPin(effector_id)),
            "rotation": bool(character.IsRotationPin(effector_id)),
        })
    payload = {"name": str(preset_name), "pins": pins}
    with open(custom_pinning_preset_path(preset_name), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
    return True


def load_custom_pinning_preset(character, preset_name):
    path = find_custom_pinning_preset_path(preset_name)
    if character is None or path is None:
        return False
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    for pin in payload.get("pins", []):
        effector_id = effector_id_from_int(int(pin.get("id")))
        character.SetTranslationPin(effector_id, bool(pin.get("translation", False)))
        character.SetRotationPin(effector_id, bool(pin.get("rotation", False)))
    evaluate_scene()
    return True


def delete_custom_pinning_preset(preset_name):
    path = find_custom_pinning_preset_path(preset_name)
    if path is None:
        return False
    os.remove(path)
    return True


def rename_custom_pinning_preset(old_name, new_name):
    old_path = find_custom_pinning_preset_path(old_name)
    if old_path is None:
        return False
    new_path = custom_pinning_preset_path(new_name)
    with open(old_path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    payload["name"] = str(new_name)
    temporary_path = new_path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
        os.replace(temporary_path, new_path)
        if os.path.normcase(os.path.abspath(old_path)) != os.path.normcase(os.path.abspath(new_path)):
            os.remove(old_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
    return True


def rename_pinning_preset(character, old_name, new_name):
    if rename_custom_pinning_preset(old_name, new_name):
        return True
    if character is None:
        return False
    effector_ids = picker_effector_ids(character)
    original_pins = [
        (
            effector_id,
            bool(character.IsTranslationPin(effector_id)),
            bool(character.IsRotationPin(effector_id)),
        )
        for effector_id in effector_ids
    ]
    try:
        if not bool(FBLoadCharacterPinningPreset(str(old_name))):
            return False
        if not bool(FBSaveCharacterPinningPreset(str(new_name), True)):
            return False
        if not bool(FBDeleteCharacterPinningPreset(str(old_name))):
            FBDeleteCharacterPinningPreset(str(new_name))
            return False
        return True
    finally:
        for effector_id, translation_pinned, rotation_pinned in original_pins:
            character.SetTranslationPin(effector_id, translation_pinned)
            character.SetRotationPin(effector_id, rotation_pinned)
        evaluate_scene()


def selected_picker_models(character):
    models = []
    for item in picker_items_for_character(character):
        model = get_model_for_item(character, item)
        if is_model_selected(model):
            models.append(model)
    for model in all_auxiliary_models(character):
        if is_model_selected(model):
            models.append(model)
    return unique_models(models)


def current_character_keying_mode(character):
    if character is None:
        return None
    return get_character_controls_keying_mode(character)


def control_rig_bake_label(character):
    mode = current_character_keying_mode(character)
    try:
        if mode == FBCharacterKeyingMode.kFBCharacterKeyingBodyPart:
            return "Bake Body Part"
    except Exception:
        pass
    try:
        if mode == FBCharacterKeyingMode.kFBCharacterKeyingSelection:
            return "Bake Selection"
    except Exception:
        pass
    return "Bake Control Rig"


def create_character_plot_options(plot_to_skeleton=False):
    options = FBPlotOptions()
    options.ConstantKeyReducerKeepOneKey = True
    options.PlotAllTakes = False
    options.PlotOnFrame = True
    options.PlotPeriod = FBTime(0, 0, 0, 1)
    options.PlotTranslationOnRootOnly = bool(plot_to_skeleton)
    options.PreciseTimeDiscontinuities = True
    options.RotationFilterToApply = FBRotationFilter.kFBRotationFilterGimbleKiller
    options.UseConstantKeyReducer = False
    for property_name, value in (
        ("PlotLockedProperties", True),
        ("PlotAuxEffectors", True),
        ("EvaluateDeformation", True),
    ):
        try:
            setattr(options, property_name, value)
        except Exception:
            pass
    return options


def plot_current_character(plot_where, plot_to_skeleton=False):
    character = get_current_character()
    if character is None:
        return False
    options = create_character_plot_options(plot_to_skeleton)
    return bool(character.PlotAnimation(plot_where, options))


class PickerChevronButton(QtWidgets.QToolButton):
    """Small tail-less chevron used to collapse/expand the selector area."""

    def __init__(self, parent=None):
        QtWidgets.QToolButton.__init__(self, parent)
        self._collapsed = False
        self.setAutoRaise(False)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
            "QToolButton:hover { background: #3f5968; border: 1px solid #7791a0; }"
            "QToolButton:pressed { background: #243844; }"
            "QToolButton::menu-indicator { image: none; }"
        )

    def setCollapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.update()

    def paintEvent(self, event):
        QtWidgets.QToolButton.paintEvent(self, event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(218, 218, 218), max(1.2, self.width() / 13.0))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        center_x = self.rect().center().x()
        center_y = self.rect().center().y()
        half_width = max(3.0, min(5.0, self.width() * 0.28))
        half_height = max(2.0, min(3.5, self.height() * 0.18))
        if self._collapsed:
            points = (
                QtCore.QPointF(center_x - half_width, center_y - half_height),
                QtCore.QPointF(center_x, center_y + half_height),
                QtCore.QPointF(center_x + half_width, center_y - half_height),
            )
        else:
            points = (
                QtCore.QPointF(center_x - half_width, center_y + half_height),
                QtCore.QPointF(center_x, center_y - half_height),
                QtCore.QPointF(center_x + half_width, center_y + half_height),
            )
        painter.drawPolyline(QtGui.QPolygonF(points))
        painter.end()


class FullBodyPickerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setMinimumSize(MIN_TOOL_WIDTH, MIN_TOOL_HEIGHT)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.ui_layout_mode = PICKER_UI_HORIZONTAL
        self.selector_area_collapsed = False
        self.load_picker_ui_settings()
        self.character_keying_shortcuts = configured_character_keying_shortcuts()
        self.items = picker_data()["items"]
        self.adaptive_neck_signature = None
        self.auxiliary_items_cache = []
        self.auxiliary_refresh_counter = 0
        self.background_pixmap = QtGui.QPixmap(picker_data()["background_path"])
        resource_dir = os.path.dirname(picker_data()["background_path"])
        self.translation_pin_icon = QtGui.QIcon(os.path.join(resource_dir, "pinT_enabled.svg"))
        self.rotation_pin_icon = QtGui.QIcon(os.path.join(resource_dir, "pinR_enabled.svg"))
        self.hover_item = None
        self.drag_start = None
        self.drag_current = None
        self.drag_press_item = None
        self.box_selecting = False
        self.drag_additive = False
        self.updating_slider_ui = False
        self.updating_selector_ui = False
        self.character_options = []
        self.source_options = []
        self.character_selector_signature = None
        self.source_selector_signature = None
        self.character_label = None
        self.character_combo = None
        self.source_label = None
        self.source_combo = None
        self.selector_toggle_button = None
        self.create_selector_controls()
        self.character_menu_button = None
        self.native_character_root_menu = None
        self.character_menu_actions = {}
        self.character_menu_sections = {}
        self.picker_ui_action_group = None
        self.picker_ui_action_group = None
        self.character_menu_window = None
        self.character_menu_window_position = None
        self.create_character_menu_button(resource_dir)
        self.bake_buttons = {}
        self.bake_in_progress = False
        self.create_bake_controls()
        self.toolbar_buttons = {}
        self.keying_button_group = QtWidgets.QButtonGroup(self)
        self.keying_button_group.setExclusive(True)
        self.pinning_preset_menu = None
        self.pin_bypass_active = False
        self.pin_bypass_character = None
        self.pin_bypass_snapshot = []
        self.create_toolbar_controls(resource_dir)
        self.slider_popup_menu = None
        self.slider_popup_widget = None
        self.slider_popup_action = None
        self.slider_context_model = None
        self.slider_context_item = None
        self.slider_context_label = None
        self.slider_controls = {}
        self.slider_key_context_menu = None
        self.slider_key_context_action = None
        self.slider_key_context_property = None
        self.create_slider_controls()
        self.auxiliary_menu = None
        self.auxiliary_menu_actions = {}
        self.auxiliary_context_item = None
        self.create_auxiliary_menu()
        self.refresh_adaptive_picker_items()
        self.refresh_auxiliary_items()
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.timeout.connect(self.on_refresh_timer)
        self.refresh_timer.start(150)
        self.apply_picker_ui_layout(False)
        self.refresh_selector_ui()
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.refresh_slider_ui()

    def combo_style(self):
        return (
            "QComboBox { color: #eeeeee; background: #393939; border: 1px solid #666; padding: 2px 6px; }"
            "QComboBox:hover { border-color: #8b8b8b; }"
            "QComboBox:disabled { color: #777; background: #292929; }"
            "QComboBox QAbstractItemView { color: #eeeeee; background: #303030; selection-background-color: #4f7195; }"
        )

    def create_selector_controls(self):
        self.character_label = QtWidgets.QLabel("Character", self)
        self.character_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.character_label.setStyleSheet("color: #dddddd; background: transparent;")
        self.character_combo = QtWidgets.QComboBox(self)
        self.character_combo.setObjectName("character_selector")
        self.character_combo.setStyleSheet(self.combo_style())
        self.character_combo.setMaxVisibleItems(20)
        self.character_combo.currentIndexChanged.connect(self.on_character_combo_changed)

        self.source_label = QtWidgets.QLabel("Source", self)
        self.source_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.source_label.setStyleSheet("color: #dddddd; background: transparent;")
        self.source_combo = QtWidgets.QComboBox(self)
        self.source_combo.setObjectName("source_selector")
        self.source_combo.setStyleSheet(self.combo_style())
        self.source_combo.setMaxVisibleItems(24)
        self.source_combo.currentIndexChanged.connect(self.on_source_combo_changed)

        self.selector_toggle_button = PickerChevronButton(self)
        self.selector_toggle_button.setObjectName("picker_selector_area_toggle")
        self.selector_toggle_button.setToolTip("Hide Character and Source selectors")
        self.selector_toggle_button.setCollapsed(self.selector_area_collapsed)
        self.selector_toggle_button.clicked.connect(self.toggle_selector_area)

    def picker_ui_settings(self):
        return QtCore.QSettings(PICKER_UI_SETTINGS_ORGANIZATION, PICKER_UI_SETTINGS_APPLICATION)

    def load_picker_ui_settings(self):
        try:
            settings = self.picker_ui_settings()
            mode = str(settings.value("layoutMode", PICKER_UI_HORIZONTAL)).lower()
            if mode not in (PICKER_UI_HORIZONTAL, PICKER_UI_VERTICAL):
                mode = PICKER_UI_HORIZONTAL
            collapsed_value = settings.value("selectorAreaCollapsed", False)
            if isinstance(collapsed_value, str):
                collapsed = collapsed_value.strip().lower() in ("1", "true", "yes", "on")
            else:
                collapsed = bool(collapsed_value)
            self.ui_layout_mode = mode
            self.selector_area_collapsed = collapsed
        except Exception:
            self.ui_layout_mode = PICKER_UI_HORIZONTAL
            self.selector_area_collapsed = False

    def save_picker_ui_settings(self):
        try:
            settings = self.picker_ui_settings()
            settings.setValue("layoutMode", self.ui_layout_mode)
            settings.setValue("selectorAreaCollapsed", bool(self.selector_area_collapsed))
            settings.sync()
        except Exception:
            pass

    def picker_ui_is_vertical(self):
        return self.ui_layout_mode == PICKER_UI_VERTICAL

    def logical_tool_width(self):
        if self.picker_ui_is_vertical():
            return BACKGROUND_WIDTH + VERTICAL_TOOLBAR_WIDTH + VERTICAL_TOOLBAR_GAP
        return BACKGROUND_WIDTH

    def logical_bake_row_top(self):
        if self.selector_area_collapsed:
            return COLLAPSED_SELECTOR_HEIGHT + 3
        return BAKE_ROW_TOP

    def logical_toolbar_top(self):
        return self.logical_bake_row_top() + BAKE_ROW_HEIGHT + 5

    def logical_background_left(self):
        if self.picker_ui_is_vertical():
            return VERTICAL_TOOLBAR_WIDTH + VERTICAL_TOOLBAR_GAP
        return 0

    def logical_background_top(self):
        if self.picker_ui_is_vertical():
            return self.logical_bake_row_top() + BAKE_ROW_HEIGHT + 5
        return self.logical_toolbar_top() + TOOLBAR_HEIGHT + 5

    def logical_tool_height(self):
        return self.logical_background_top() + BACKGROUND_HEIGHT

    def sizeHint(self):
        return QtCore.QSize(int(round(self.logical_tool_width())), int(round(self.logical_tool_height())))

    def apply_picker_ui_layout(self, persist=True):
        selector_visible = not self.selector_area_collapsed
        for widget in (
            self.character_menu_button,
            self.character_label,
            self.character_combo,
            self.source_label,
            self.source_combo,
        ):
            if widget is not None:
                widget.setVisible(selector_visible)
        if self.selector_toggle_button is not None:
            self.selector_toggle_button.setCollapsed(self.selector_area_collapsed)
            self.selector_toggle_button.setToolTip(
                "Show Character and Source selectors" if self.selector_area_collapsed
                else "Hide Character and Source selectors"
            )
            self.selector_toggle_button.show()
        self.position_selector_controls()
        self.position_bake_controls()
        self.position_toolbar_controls()
        self.apply_embedded_ui_scale()
        self.updateGeometry()
        self.update()
        if persist:
            self.save_picker_ui_settings()

    def set_picker_ui_layout(self, mode):
        mode = str(mode).lower()
        if mode not in (PICKER_UI_HORIZONTAL, PICKER_UI_VERTICAL):
            return
        self.ui_layout_mode = mode
        self.apply_picker_ui_layout(True)
        self.refresh_independent_character_menu()

    def toggle_selector_area(self):
        self.selector_area_collapsed = not self.selector_area_collapsed
        self.apply_picker_ui_layout(True)

    def create_character_menu_button(self, resource_dir):
        self.character_menu_button = QtWidgets.QToolButton(self)
        self.character_menu_button.setObjectName("character_controls_native_menu")
        self.character_menu_button.setToolTip("Character Controls menu")
        self.character_menu_button.setAutoRaise(False)
        self.character_menu_button.setIcon(QtGui.QIcon(os.path.join(resource_dir, "HIKmenuButton.svg")))
        self.character_menu_button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
            "QToolButton:hover { background: #3f5968; border: 1px solid #7791a0; }"
            "QToolButton:pressed { background: #243844; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        self.character_menu_button.clicked.connect(self.open_native_character_menu)
        self.create_independent_character_menu()

    def character_menu_style(self):
        return (
            "QMenu { color: #eeeeee; background: #303030; border: 1px solid #666666; }"
            "QMenu::item { padding: 4px 24px 4px 8px; }"
            "QMenu::item:selected { background: #4f7195; }"
            "QMenu::item:disabled { color: #777777; }"
            "QMenu::separator { height: 1px; background: #555555; margin: 3px 5px; }"
        )

    def add_character_menu_action(self, menu, key, text, checkable=False, supported=True):
        # As with submenus, create a parented QObject explicitly.  The QAction
        # wrapper returned by QMenu.addAction(str) can outlive its C++ object in
        # MotionBuilder's PySide6 runtime.
        action = QtGui.QAction(str(text), menu)
        menu.addAction(action)
        action.setCheckable(checkable)
        action.setProperty("independent_supported", bool(supported))
        action.setEnabled(bool(supported))
        if not supported:
            action.setToolTip("This native-only command has no safe independent SDK equivalent.")
        else:
            action.triggered.connect(
                lambda checked=False, command_key=key: self.execute_character_menu_command(command_key, checked)
            )
        self.character_menu_actions[key] = action
        return action

    def add_character_submenu(self, parent, key, text):
        # Build the QMenu explicitly with a QObject parent.  MotionBuilder's
        # PySide6 binding can otherwise delete the C++ QMenu created by
        # addMenu(str) while the Python wrapper is still stored here.
        submenu = QtWidgets.QMenu(str(text), parent)
        submenu.setObjectName("independent_character_menu_%s" % key)
        submenu.setStyleSheet(self.character_menu_style())
        parent.addMenu(submenu)
        self.character_menu_sections[key] = submenu
        return submenu

    def create_independent_character_menu(self):
        old_root = self.native_character_root_menu
        if old_root is not None:
            try:
                if isValid(old_root):
                    old_root.hide()
                    old_root.deleteLater()
            except Exception:
                pass

        self.native_character_root_menu = None
        self.character_menu_actions = {}
        self.character_menu_sections = {}

        root = QtWidgets.QMenu(self)
        root.setObjectName("independent_character_controls_menu")
        root.setStyleSheet(self.character_menu_style())

        file_menu = self.add_character_submenu(root, "file", "File")
        self.add_character_menu_action(file_menu, "load_animation", "Load Character Animation...")
        self.add_character_menu_action(file_menu, "save_animation", "Save Character Animation...")

        create_menu = self.add_character_submenu(root, "create", "Create")
        self.add_character_menu_action(create_menu, "create_actor", "Actor")
        self.add_character_menu_action(create_menu, "create_control_rig", "Control Rig")

        define_menu = self.add_character_submenu(root, "define", "Define")
        self.add_character_menu_action(define_menu, "define_skeleton", "Skeleton")

        edit_menu = self.add_character_submenu(root, "edit", "Edit")
        actor_menu = self.add_character_submenu(edit_menu, "edit_actor", "Actor")
        self.add_character_menu_action(actor_menu, "actor_lock", "Lock", True)
        self.add_character_menu_action(actor_menu, "actor_ik_manip", "IK Manip", True)
        self.add_character_menu_action(actor_menu, "actor_symmetry_t", "Symmetry Edit (Translation)", True)
        self.add_character_menu_action(actor_menu, "actor_symmetry_r", "Symmetry Edit (Rotation)", True)
        self.add_character_menu_action(actor_menu, "actor_symmetry_s", "Symmetry Edit (Scaling)", True)
        actor_menu.addSeparator()
        self.add_character_menu_action(actor_menu, "actor_stance", "Stance Pose", supported=False)
        self.add_character_menu_action(actor_menu, "actor_collapse", "Collapse", supported=False)
        self.add_character_menu_action(actor_menu, "actor_reset_size", "Reset Size", supported=False)
        self.add_character_menu_action(actor_menu, "actor_find_size", "Find Size", supported=False)
        self.add_character_menu_action(actor_menu, "actor_reset_pivots", "Reset Pivot Points", supported=False)
        self.add_character_menu_action(actor_menu, "actor_reset_all", "Reset All", supported=False)
        actor_menu.addSeparator()
        self.add_character_menu_action(actor_menu, "actor_edit_properties", "Edit Properties", supported=False)
        actor_menu.addSeparator()
        self.add_character_menu_action(actor_menu, "switch_to_character", "Switch To Character")

        definition_menu = self.add_character_submenu(edit_menu, "edit_definition", "Definition")
        self.add_character_menu_action(definition_menu, "definition_lock", "Lock Definition", True)
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "definition_rename", "Rename")
        self.add_character_menu_action(definition_menu, "definition_delete", "Delete")
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "skeleton_lock_sel", "Skeleton Lock Sel", True)
        self.add_character_menu_action(definition_menu, "skeleton_lock_trs", "Skeleton Lock Trs", True)
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "definition_edit_properties", "Edit Properties", supported=False)
        self.add_character_menu_action(definition_menu, "definition_reset_properties", "Reset Properties")
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "mirror_matching", "Mirror Matching", True)
        self.add_character_menu_action(definition_menu, "configure_mirror", "Configure Mirror Matching...", supported=False)
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "load_definition", "Load Skeleton Definition...", supported=False)
        self.add_character_menu_action(definition_menu, "save_definition", "Save Skeleton Definition...", supported=False)
        definition_menu.addSeparator()
        self.add_character_menu_action(definition_menu, "switch_to_actor", "Switch To Actor")

        controls_menu = self.add_character_submenu(edit_menu, "edit_controls", "Controls")
        rig_look_menu = self.add_character_submenu(controls_menu, "rig_look", "Rig Look")
        self.add_character_menu_action(rig_look_menu, "rig_look_wire", "Wire", True, False)
        self.add_character_menu_action(rig_look_menu, "rig_look_stick", "Stick", True, False)
        self.add_character_menu_action(rig_look_menu, "rig_look_box", "Box", True, False)
        self.add_character_menu_action(controls_menu, "controls_stance", "Stance Pose")
        self.add_character_menu_action(controls_menu, "controls_retarget", "Retarget Rig")
        controls_menu.addSeparator()
        self.add_character_menu_action(controls_menu, "controls_rename", "Rename")
        self.add_character_menu_action(controls_menu, "controls_delete", "Delete")
        controls_menu.addSeparator()
        self.add_character_menu_action(controls_menu, "fk_lock_sel", "FK Lock Sel", True)
        self.add_character_menu_action(controls_menu, "fk_lock_trs", "FK Lock Trs", True)
        controls_menu.addSeparator()
        self.add_character_menu_action(controls_menu, "reach_override", "Reach Override", True)
        self.add_character_menu_action(controls_menu, "stiffness_override", "Stiffness Override", True)
        controls_menu.addSeparator()
        reconnect_menu = self.add_character_submenu(controls_menu, "rig_reconnect", "Rig Reconnect")
        self.add_character_menu_action(reconnect_menu, "attach_rig", "Attach Rig", supported=False)
        self.add_character_menu_action(reconnect_menu, "detach_rig", "Detach Rig", supported=False)
        controls_menu.addSeparator()
        self.add_character_menu_action(controls_menu, "load_ui_config", "Load UI Configuration...", supported=False)
        self.add_character_menu_action(controls_menu, "update_ui_config", "Update UI Configuration", supported=False)
        edit_menu.addSeparator()

        bake_menu = self.add_character_submenu(root, "bake", "Bake (Plot)")
        self.add_character_menu_action(bake_menu, "bake_skeleton", "Bake (plot) To Skeleton")
        self.add_character_menu_action(bake_menu, "bake_control_rig", "Bake (plot) To Control Rig")

        add_menu = self.add_character_submenu(root, "add_selection", "Add to Selection")
        self.add_character_menu_action(add_menu, "select_ik", "IK")
        self.add_character_menu_action(add_menu, "select_fk", "FK")
        self.add_character_menu_action(add_menu, "select_skeleton", "Skeleton")

        show_menu = self.add_character_submenu(root, "show_hide", "Show/Hide")
        self.add_character_menu_action(show_menu, "show_ik", "IK", True)
        self.add_character_menu_action(show_menu, "show_fk", "FK", True)
        self.add_character_menu_action(show_menu, "show_skeleton", "Skeleton", True)
        show_menu.addSeparator()
        self.add_character_menu_action(show_menu, "show_floor_contact", "Floor Contact", True)
        self.add_character_menu_action(show_menu, "show_finger_tips", "Finger Tips", True, False)
        show_menu.addSeparator()
        self.add_character_menu_action(show_menu, "show_actor_all", "Actor (All)", True)
        self.add_character_menu_action(show_menu, "show_actor_body", "Actor Body", True)
        self.add_character_menu_action(show_menu, "show_actor_skeleton", "Actor Skeleton", True)
        self.add_character_menu_action(show_menu, "show_marker_set", "Marker Set", True, False)
        self.add_character_menu_action(show_menu, "show_source_markers", "Source Markers", True, False)
        self.add_character_menu_action(show_menu, "show_pivot_points", "Pivot Points", True)

        root.addSeparator()
        picker_ui_menu = self.add_character_submenu(root, "picker_ui", "Picker UI")
        horizontal_action = self.add_character_menu_action(
            picker_ui_menu, "picker_ui_horizontal", "Horizontal Button Row", True
        )
        vertical_action = self.add_character_menu_action(
            picker_ui_menu, "picker_ui_vertical", "Vertical Buttons on Left", True
        )
        self.picker_ui_action_group = QtGui.QActionGroup(root)
        self.picker_ui_action_group.setExclusive(True)
        self.picker_ui_action_group.addAction(horizontal_action)
        self.picker_ui_action_group.addAction(vertical_action)

        root.aboutToShow.connect(self.refresh_independent_character_menu)
        self.native_character_root_menu = root

    def independent_character_menu_is_valid(self):
        try:
            if self.native_character_root_menu is None or not isValid(self.native_character_root_menu):
                return False
            for submenu in self.character_menu_sections.values():
                if submenu is None or not isValid(submenu):
                    return False
        except Exception:
            return False
        return True

    def open_native_character_menu(self):
        try:
            if not self.independent_character_menu_is_valid():
                self.create_independent_character_menu()
            menu = self.native_character_root_menu
            self.refresh_independent_character_menu()
            self.character_menu_window = self.window()
            self.character_menu_window_position = QtCore.QPoint(self.character_menu_window.pos())
            try:
                menu.aboutToHide.disconnect(self.restore_picker_window_position)
            except Exception:
                pass
            menu.aboutToHide.connect(self.restore_picker_window_position)
            target = self.character_menu_button.mapToGlobal(
                QtCore.QPoint(0, self.character_menu_button.height())
            )
            menu.popup(target)
            menu.move(target)
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def current_menu_actor(self):
        try:
            return FBApplication().CurrentActor
        except Exception:
            return None

    def component_boolean(self, component, names, default=False):
        if component is None:
            return bool(default)
        for name in names:
            try:
                return bool(getattr(component, name))
            except Exception:
                pass
            try:
                prop = component.PropertyList.Find(name)
                if prop is not None:
                    return bool(prop.Data)
            except Exception:
                pass
        return bool(default)

    def set_component_boolean(self, component, names, value):
        if component is None:
            return False
        for name in names:
            try:
                setattr(component, name, bool(value))
                return True
            except Exception:
                pass
            try:
                prop = component.PropertyList.Find(name)
                if prop is not None:
                    prop.Data = bool(value)
                    return True
            except Exception:
                pass
        return False

    def set_character_menu_checked(self, key, checked):
        action = self.character_menu_actions.get(key)
        if action is None or not action.isCheckable():
            return
        action.blockSignals(True)
        action.setChecked(bool(checked))
        action.blockSignals(False)

    def floor_contact_models(self, character):
        result = []
        if character is None:
            return result
        member_ids = []
        for name in (
            "FBLeftHandMemberIndex", "FBRightHandMemberIndex",
            "FBLeftFootMemberIndex", "FBRightFootMemberIndex",
        ):
            try:
                member_ids.append(getattr(FBFloorContactID, name))
            except Exception:
                pass
        for index in member_ids:
            try:
                model = character.GetFloorContactModel(index)
            except Exception:
                continue
            if model is not None and model not in result:
                result.append(model)
        return result

    def refresh_independent_character_menu(self):
        character = get_current_character()
        actor = self.current_menu_actor()
        control_set = get_current_control_set(character)
        section_states = {
            "file": character is not None,
            "create": True,
            "define": True,
            "edit": character is not None or actor is not None,
            "edit_actor": actor is not None,
            "edit_definition": character is not None,
            "edit_controls": control_set is not None,
            "rig_look": False,
            "rig_reconnect": False,
            "bake": character is not None,
            "add_selection": character is not None,
            "show_hide": character is not None or actor is not None,
            "picker_ui": True,
        }
        for key, menu in self.character_menu_sections.items():
            if key in section_states:
                menu.menuAction().setEnabled(bool(section_states[key]))

        contexts = {
            "load_animation": character is not None,
            "save_animation": character is not None,
            "create_actor": True,
            "create_control_rig": character is not None and control_set is None,
            "define_skeleton": True,
            "switch_to_character": actor is not None,
            "switch_to_actor": character is not None and bool(scene_actors()),
            "bake_skeleton": character is not None,
            "bake_control_rig": character is not None and control_set is not None,
            "select_ik": character is not None,
            "select_fk": character is not None,
            "select_skeleton": character is not None,
            "show_ik": character is not None,
            "show_fk": character is not None,
            "show_skeleton": character is not None,
            "show_floor_contact": character is not None,
            "show_actor_all": actor is not None,
            "show_actor_body": actor is not None,
            "show_actor_skeleton": actor is not None,
            "show_pivot_points": actor is not None,
        }
        for key, action in self.character_menu_actions.items():
            supported = bool(action.property("independent_supported"))
            enabled = contexts.get(key, True)
            if key.startswith("actor_"):
                enabled = actor is not None
            elif key.startswith("definition_") or key in ("skeleton_lock_sel", "skeleton_lock_trs", "mirror_matching"):
                enabled = character is not None
            elif key.startswith("controls_") or key in ("fk_lock_sel", "fk_lock_trs", "reach_override", "stiffness_override"):
                enabled = control_set is not None
            action.setEnabled(supported and bool(enabled))

        self.set_character_menu_checked("show_ik", character_visibility(character, "GetIKVisibility"))
        self.set_character_menu_checked("show_fk", character_visibility(character, "GetFKVisibility"))
        self.set_character_menu_checked("show_skeleton", character_visibility(character, "GetSkeletonVisibility"))
        floor_models = self.floor_contact_models(character)
        self.set_character_menu_checked(
            "show_floor_contact",
            bool(floor_models) and all(self.component_boolean(model, ("Show", "Visibility"), True) for model in floor_models),
        )
        self.set_character_menu_checked("actor_lock", self.component_boolean(actor, ("Lock", "Locked")))
        self.set_character_menu_checked("actor_ik_manip", self.component_boolean(actor, ("IKManip",)))
        self.set_character_menu_checked("actor_symmetry_t", self.component_boolean(actor, ("SymmetryEditTranslation",)))
        self.set_character_menu_checked("actor_symmetry_r", self.component_boolean(actor, ("SymmetryEditRotation",)))
        self.set_character_menu_checked("actor_symmetry_s", self.component_boolean(actor, ("SymmetryEditScaling",)))
        self.set_character_menu_checked("definition_lock", bool(character.GetCharacterize()) if character is not None else False)
        self.set_character_menu_checked("mirror_matching", self.component_boolean(character, ("MirrorMode",)))
        self.set_character_menu_checked("skeleton_lock_sel", self.component_boolean(character, ("Skeleton Lock Sel", "SkeletonLockSel")))
        self.set_character_menu_checked("skeleton_lock_trs", self.component_boolean(character, ("Skeleton Lock Trs", "SkeletonLockTrs")))
        self.set_character_menu_checked("fk_lock_sel", self.component_boolean(control_set, ("FK Lock Sel", "FKLockSel")))
        self.set_character_menu_checked("fk_lock_trs", self.component_boolean(control_set, ("FK Lock Trs", "FKLockTrs")))
        self.set_character_menu_checked("reach_override", self.component_boolean(control_set, ("Reach Override", "ReachOverride")))
        self.set_character_menu_checked("stiffness_override", self.component_boolean(control_set, ("Stiffness Override", "StiffnessOverride")))
        actor_visible = self.component_boolean(actor, ("Visibility",), True)
        actor_skeleton = self.component_boolean(actor, ("SkeletonVisibility",), True)
        self.set_character_menu_checked("show_actor_all", actor_visible and actor_skeleton)
        self.set_character_menu_checked("show_actor_body", actor_visible)
        self.set_character_menu_checked("show_actor_skeleton", actor_skeleton)
        self.set_character_menu_checked("show_pivot_points", self.component_boolean(actor, ("PivotPointsVisibility",)))
        self.set_character_menu_checked("picker_ui_horizontal", not self.picker_ui_is_vertical())
        self.set_character_menu_checked("picker_ui_vertical", self.picker_ui_is_vertical())

    def unique_scene_name(self, base_name, components):
        existing = {component_name(component).lower() for component in components}
        if base_name.lower() not in existing:
            return base_name
        index = 1
        while (base_name + str(index)).lower() in existing:
            index += 1
        return base_name + str(index)

    def rename_component_dialog(self, component, title):
        if component is None:
            return
        name, accepted = QtWidgets.QInputDialog.getText(
            self, title, "Name:", text=component_name(component)
        )
        name = str(name).strip()
        if accepted and name:
            try:
                component.Name = name
            except Exception:
                component.LongName = name

    def confirm_delete(self, label):
        result = QtWidgets.QMessageBox.question(
            self, TOOL_NAME, "Delete %s?" % label,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return result == QtWidgets.QMessageBox.Yes

    def execute_character_menu_command(self, key, checked=False):
        character = get_current_character()
        actor = self.current_menu_actor()
        control_set = get_current_control_set(character)
        try:
            if key == "picker_ui_horizontal":
                self.set_picker_ui_layout(PICKER_UI_HORIZONTAL)
            elif key == "picker_ui_vertical":
                self.set_picker_ui_layout(PICKER_UI_VERTICAL)
            elif key == "load_animation":
                filename, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Load Character Animation", "", "FBX Files (*.fbx)")
                if filename:
                    loaded = FBApplication().LoadAnimationOnCharacter(
                        str(filename), character, FBFbxOptions(True), FBPlotOptions()
                    )
                    if not loaded:
                        raise RuntimeError("MotionBuilder could not load the character animation.")
            elif key == "save_animation":
                filename, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Save Character Animation", "", "FBX Files (*.fbx)")
                if filename:
                    filename = str(filename)
                    if not filename.lower().endswith(".fbx"):
                        filename += ".fbx"
                    options = FBFbxOptions(False)
                    options.SaveCharacter = False
                    options.SaveControlSet = True
                    try:
                        options.SaveCharacterExtensions = True
                    except Exception:
                        pass
                    FBApplication().SaveCharacterRigAndAnimation(filename, character, options)
            elif key == "create_actor":
                actor = FBActor(self.unique_scene_name("Actor", scene_actors()))
                FBApplication().CurrentActor = actor
            elif key == "create_control_rig":
                if not bool(character.CreateControlRig(True)):
                    raise RuntimeError("MotionBuilder could not create the control rig.")
            elif key == "define_skeleton":
                character = FBCharacter(self.unique_scene_name("Character", scene_characters()))
                FBApplication().CurrentCharacter = character
            elif key == "actor_lock":
                self.set_component_boolean(actor, ("Lock", "Locked"), checked)
            elif key == "actor_ik_manip":
                self.set_component_boolean(actor, ("IKManip",), checked)
            elif key == "actor_symmetry_t":
                self.set_component_boolean(actor, ("SymmetryEditTranslation",), checked)
            elif key == "actor_symmetry_r":
                self.set_component_boolean(actor, ("SymmetryEditRotation",), checked)
            elif key == "actor_symmetry_s":
                self.set_component_boolean(actor, ("SymmetryEditScaling",), checked)
            elif key == "switch_to_character":
                target = next((item for item in scene_characters() if same_component(getattr(item, "InputActor", None), actor)), None)
                if target is not None:
                    FBApplication().CurrentCharacter = target
            elif key == "definition_lock":
                if checked:
                    if not bool(character.SetCharacterizeOn(True)):
                        raise RuntimeError(character.GetCharacterizeError())
                else:
                    character.SetCharacterizeOff()
            elif key == "definition_rename":
                self.rename_component_dialog(character, "Rename Character Definition")
            elif key == "definition_delete":
                if self.confirm_delete(component_name(character)):
                    character.FBDelete()
            elif key == "definition_reset_properties":
                character.ResetProperties(FBCharacterResetProperties.kFBCharacterResetPropertiesDefinition)
            elif key == "mirror_matching":
                self.set_component_boolean(character, ("MirrorMode",), checked)
            elif key == "skeleton_lock_sel":
                self.set_component_boolean(character, ("Skeleton Lock Sel", "SkeletonLockSel"), checked)
            elif key == "skeleton_lock_trs":
                self.set_component_boolean(character, ("Skeleton Lock Trs", "SkeletonLockTrs"), checked)
            elif key == "switch_to_actor":
                target = getattr(character, "InputActor", None) or (scene_actors()[0] if scene_actors() else None)
                if target is not None:
                    FBApplication().CurrentActor = target
            elif key == "controls_stance":
                character.GoToStancePose(True, True)
            elif key == "controls_retarget":
                character.Retarget(False)
            elif key == "controls_rename":
                self.rename_component_dialog(control_set, "Rename Control Rig")
            elif key == "controls_delete":
                if self.confirm_delete(component_name(control_set)):
                    character.DisconnectControlRig()
                    try:
                        control_set.FBDelete()
                    except Exception:
                        pass
            elif key == "fk_lock_sel":
                self.set_component_boolean(control_set, ("FK Lock Sel", "FKLockSel"), checked)
            elif key == "fk_lock_trs":
                self.set_component_boolean(control_set, ("FK Lock Trs", "FKLockTrs"), checked)
            elif key == "reach_override":
                self.set_component_boolean(control_set, ("Reach Override", "ReachOverride"), checked)
            elif key == "stiffness_override":
                self.set_component_boolean(control_set, ("Stiffness Override", "StiffnessOverride"), checked)
            elif key == "bake_skeleton":
                self.bake_to_skeleton()
            elif key == "bake_control_rig":
                self.bake_to_control_rig()
            elif key == "select_ik":
                select_items([item for item in self.items if item.get("kind") == "ik"], True)
            elif key == "select_fk":
                select_items([item for item in self.items if item.get("kind") == "fk"], True)
            elif key == "select_skeleton":
                character.SelectModels(True, True, False, False)
            elif key == "show_ik":
                set_character_visibility(character, "SetIKVisibility", checked)
            elif key == "show_fk":
                set_character_visibility(character, "SetFKVisibility", checked)
            elif key == "show_skeleton":
                set_character_visibility(character, "SetSkeletonVisibility", checked)
            elif key == "show_floor_contact":
                for model in self.floor_contact_models(character):
                    self.set_component_boolean(model, ("Show", "Visibility"), checked)
            elif key == "show_actor_all":
                self.set_component_boolean(actor, ("Visibility",), checked)
                self.set_component_boolean(actor, ("SkeletonVisibility",), checked)
            elif key == "show_actor_body":
                self.set_component_boolean(actor, ("Visibility",), checked)
            elif key == "show_actor_skeleton":
                self.set_component_boolean(actor, ("SkeletonVisibility",), checked)
            elif key == "show_pivot_points":
                self.set_component_boolean(actor, ("PivotPointsVisibility",), checked)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_selector_ui()
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.update()

    def restore_picker_window_position(self):
        window = self.character_menu_window
        position = self.character_menu_window_position
        self.character_menu_window = None
        self.character_menu_window_position = None
        if window is None or position is None:
            return
        try:
            if window.pos() != position:
                window.move(position)
        except Exception:
            pass

    def position_selector_controls(self):
        if self.character_combo is None or self.selector_toggle_button is None:
            return
        tool_width = self.logical_tool_width()
        if self.selector_area_collapsed:
            self.selector_toggle_button.setGeometry(
                self.logical_geometry(tool_width - SELECTOR_CHEVRON_WIDTH, 0, SELECTOR_CHEVRON_WIDTH, COLLAPSED_SELECTOR_HEIGHT)
            )
            return
        menu_width = 44
        right_left = menu_width + 4
        label_left = right_left
        combo_left = right_left + 61
        chevron_left = tool_width - SELECTOR_CHEVRON_WIDTH
        combo_width = max(30, chevron_left - combo_left - 2)
        self.character_menu_button.setGeometry(
            self.logical_geometry(0, SELECTOR_ROWS_TOP, menu_width, SELECTOR_ROW_HEIGHT * 2 - 4)
        )
        icon_size = max(8, int(round(42 * self.logical_scale())))
        self.character_menu_button.setIconSize(QtCore.QSize(icon_size, icon_size))
        self.character_label.setGeometry(self.logical_geometry(label_left, SELECTOR_ROWS_TOP, 58, 22))
        self.character_combo.setGeometry(self.logical_geometry(combo_left, SELECTOR_ROWS_TOP, combo_width, 22))
        source_top = SELECTOR_ROWS_TOP + SELECTOR_ROW_HEIGHT
        self.source_label.setGeometry(self.logical_geometry(label_left, source_top, 58, 22))
        self.source_combo.setGeometry(self.logical_geometry(combo_left, source_top, combo_width, 22))
        self.selector_toggle_button.setGeometry(
            self.logical_geometry(chevron_left, SELECTOR_ROWS_TOP, SELECTOR_CHEVRON_WIDTH, SELECTOR_ROW_HEIGHT * 2 - 4)
        )

    def bake_button_style(self):
        return (
            "QPushButton { color: #eeeeee; background: #3b3b3b; border: 1px solid #666666; padding: 2px 4px; }"
            "QPushButton:hover { background: #4b4b4b; border-color: #8d8d8d; }"
            "QPushButton:pressed { background: #252525; }"
            "QPushButton:disabled { color: #777777; background: #292929; border-color: #414141; }"
        )

    def create_bake_controls(self):
        skeleton_button = QtWidgets.QPushButton("Bake to Skeleton", self)
        skeleton_button.setObjectName("bake_to_skeleton")
        skeleton_button.setToolTip("Bake the current character animation to its skeleton")
        skeleton_button.setStyleSheet(self.bake_button_style())
        skeleton_button.clicked.connect(self.bake_to_skeleton)

        control_rig_button = QtWidgets.QPushButton("Bake Control Rig", self)
        control_rig_button.setObjectName("bake_to_control_rig")
        control_rig_button.setStyleSheet(self.bake_button_style())
        control_rig_button.clicked.connect(self.bake_to_control_rig)

        self.bake_buttons = {
            "skeleton": skeleton_button,
            "control_rig": control_rig_button,
        }

    def position_bake_controls(self):
        if not self.bake_buttons:
            return
        gap = 4
        tool_width = self.logical_tool_width()
        bake_top = self.logical_bake_row_top()
        button_width = (tool_width - gap) * 0.5
        self.bake_buttons["skeleton"].setGeometry(
            self.logical_geometry(0, bake_top, button_width, BAKE_ROW_HEIGHT)
        )
        self.bake_buttons["control_rig"].setGeometry(
            self.logical_geometry(button_width + gap, bake_top, button_width, BAKE_ROW_HEIGHT)
        )

    def refresh_bake_ui(self):
        character = get_current_character()
        skeleton_button = self.bake_buttons["skeleton"]
        control_rig_button = self.bake_buttons["control_rig"]
        if self.bake_in_progress:
            skeleton_button.setEnabled(False)
            control_rig_button.setEnabled(False)
            return

        has_character = character is not None
        skeleton_button.setEnabled(has_character)
        label = control_rig_bake_label(character)
        control_rig_button.setText(label)

        mode = current_character_keying_mode(character)
        scoped_mode = False
        try:
            scoped_mode = mode in (
                FBCharacterKeyingMode.kFBCharacterKeyingBodyPart,
                FBCharacterKeyingMode.kFBCharacterKeyingSelection,
            )
        except Exception:
            scoped_mode = False
        source_kind, _source_component = character_source_state(character) if has_character else ("none", None)
        has_control_rig = get_current_control_set(character) is not None if has_character else False
        has_scope_selection = bool(selected_picker_models(character)) if scoped_mode else True
        enabled = has_character and has_control_rig and has_scope_selection and (not scoped_mode or source_kind == "control_rig")
        control_rig_button.setEnabled(enabled)

        if label == "Bake Body Part":
            tooltip = "Bake only the selected Character Controls body part to the control rig"
        elif label == "Bake Selection":
            tooltip = "Bake only the selected control-rig bones"
        else:
            tooltip = "Bake the full character animation to the control rig"
        if scoped_mode and source_kind != "control_rig":
            tooltip += " (set Source to Control Rig for scoped baking)"
        elif scoped_mode and not has_scope_selection:
            tooltip += " (select a control first)"
        control_rig_button.setToolTip(tooltip)

    def run_character_bake(self, plot_where, plot_to_skeleton=False):
        global _LAST_UI_KEYING_MODE
        character = get_current_character()
        if character is None:
            return
        original_mode = current_character_keying_mode(character)
        self.bake_in_progress = True
        self.refresh_bake_ui()
        try:
            QtWidgets.QApplication.processEvents()
            baked = plot_current_character(plot_where, plot_to_skeleton)
            if not baked:
                FBMessageBox(TOOL_NAME, "MotionBuilder could not complete the bake.", "OK")
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        finally:
            if original_mode is not None:
                try:
                    character.KeyingMode = original_mode
                    _LAST_UI_KEYING_MODE = original_mode
                except Exception:
                    pass
            self.bake_in_progress = False
            evaluate_scene()
            self.refresh_selector_ui()
            self.refresh_bake_ui()
            self.refresh_toolbar_ui()
            self.refresh_slider_ui()
            self.update()

    def bake_to_skeleton(self):
        self.run_character_bake(FBCharacterPlotWhere.kFBCharacterPlotOnSkeleton, True)

    def bake_to_control_rig(self):
        character = get_current_character()
        if character is None:
            return
        mode = current_character_keying_mode(character)
        try:
            scoped_mode = mode in (
                FBCharacterKeyingMode.kFBCharacterKeyingBodyPart,
                FBCharacterKeyingMode.kFBCharacterKeyingSelection,
            )
        except Exception:
            scoped_mode = False
        source_kind, _source_component = character_source_state(character)
        if scoped_mode and (source_kind != "control_rig" or not selected_picker_models(character)):
            self.refresh_bake_ui()
            return
        self.run_character_bake(FBCharacterPlotWhere.kFBCharacterPlotOnControlRig, False)

    def toolbar_button_style(self):
        return (
            "QToolButton { background: #333333; border: 1px solid #555555; padding: 0px; }"
            "QToolButton:hover { background: #494949; border-color: #8a8a8a; }"
            "QToolButton:pressed { background: #202020; }"
            "QToolButton:checked { background: #3e6683; border-color: #86c9f5; }"
            "QToolButton#character_control_release_all_pins:checked { background: #9d2525; border-color: #ff6b6b; }"
            "QToolButton:disabled { background: #252525; border-color: #3b3b3b; }"
            "QToolButton::menu-indicator { image: none; }"
        )

    def create_toolbar_controls(self, resource_dir):
        checkable_names = {
            "ik_visibility", "fk_visibility", "skeleton_visibility",
            "key_full_body", "key_full_body_no_pull", "key_body_part", "key_selection",
            "pin_translation", "pin_rotation", "release_all_pins",
        }
        keying_names = {
            "key_full_body", "key_full_body_no_pull", "key_body_part", "key_selection",
        }
        for name, icon_filename, tooltip in TOOLBAR_BUTTON_SPECS:
            button = QtWidgets.QToolButton(self)
            button.setObjectName("character_control_" + name)
            button.setToolTip(tooltip)
            button.setAutoRaise(False)
            button.setCheckable(name in checkable_names)
            button.setStyleSheet(self.toolbar_button_style())
            button.setIcon(QtGui.QIcon(os.path.join(resource_dir, icon_filename)))
            if name in keying_names:
                self.keying_button_group.addButton(button)
            self.toolbar_buttons[name] = button

        self.toolbar_buttons["ik_visibility"].clicked.connect(
            lambda checked=False: self.on_visibility_clicked("SetIKVisibility", checked)
        )
        self.toolbar_buttons["fk_visibility"].clicked.connect(
            lambda checked=False: self.on_visibility_clicked("SetFKVisibility", checked)
        )
        self.toolbar_buttons["skeleton_visibility"].clicked.connect(
            lambda checked=False: self.on_visibility_clicked("SetSkeletonVisibility", checked)
        )
        self.toolbar_buttons["key_full_body"].clicked.connect(
            lambda checked=False: self.on_keying_mode_clicked("kFBCharacterKeyingFullBody")
        )
        self.toolbar_buttons["key_full_body_no_pull"].clicked.connect(
            lambda checked=False: self.on_keying_mode_clicked("kFBCharacterKeyingFullBodyNoPull")
        )
        self.toolbar_buttons["key_body_part"].clicked.connect(
            lambda checked=False: self.on_keying_mode_clicked("kFBCharacterKeyingBodyPart")
        )
        self.toolbar_buttons["key_selection"].clicked.connect(
            lambda checked=False: self.on_keying_mode_clicked("kFBCharacterKeyingSelection")
        )
        self.toolbar_buttons["pin_translation"].clicked.connect(
            lambda checked=False: self.on_pin_clicked(True)
        )
        self.toolbar_buttons["pin_rotation"].clicked.connect(
            lambda checked=False: self.on_pin_clicked(False)
        )
        self.toolbar_buttons["release_all_pins"].toggled.connect(self.on_pin_bypass_toggled)
        self.toolbar_buttons["stance_pose"].clicked.connect(self.go_to_stance_pose)

        self.pinning_preset_menu = QtWidgets.QMenu(self)
        self.pinning_preset_menu.setStyleSheet(
            "QMenu { color: #eeeeee; background: #303030; border: 1px solid #666; }"
            "QMenu::item:selected { background: #4f7195; }"
            "QMenu::item:disabled { color: #777777; }"
        )
        self.pinning_preset_menu.aboutToShow.connect(self.rebuild_pinning_preset_menu)
        preset_button = self.toolbar_buttons["pinning_presets"]
        preset_button.setMenu(self.pinning_preset_menu)
        preset_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)

    def position_toolbar_controls(self):
        vertical = self.picker_ui_is_vertical()
        count = max(1, len(TOOLBAR_BUTTON_SPECS))
        background_top = self.logical_background_top()
        for index, (name, _icon_filename, _tooltip) in enumerate(TOOLBAR_BUTTON_SPECS):
            button = self.toolbar_buttons.get(name)
            if button is None:
                continue
            if vertical:
                button_size = 22.0
                slot_height = float(BACKGROUND_HEIGHT) / float(count)
                left = (VERTICAL_TOOLBAR_WIDTH - button_size) * 0.5
                top = background_top + slot_height * (index + 0.5) - button_size * 0.5
                button.setGeometry(self.logical_geometry(left, top, button_size, button_size))
                logical_icon_size = 18
            else:
                button.setGeometry(self.logical_geometry(index * 21, self.logical_toolbar_top(), 19, TOOLBAR_HEIGHT))
                logical_icon_size = 17
            icon_size = max(6, int(round(logical_icon_size * self.logical_scale())))
            button.setIconSize(QtCore.QSize(icon_size, icon_size))

    def set_toolbar_checked(self, name, checked):
        button = self.toolbar_buttons[name]
        button.blockSignals(True)
        button.setChecked(bool(checked))
        button.blockSignals(False)

    def refresh_toolbar_ui(self):
        character = get_current_character()
        if self.pin_bypass_active and not same_component(character, self.pin_bypass_character):
            self.restore_pin_bypass()
        has_character = character is not None
        for button in self.toolbar_buttons.values():
            button.setEnabled(has_character)

        self.set_toolbar_checked("ik_visibility", character_visibility(character, "GetIKVisibility"))
        self.set_toolbar_checked("fk_visibility", character_visibility(character, "GetFKVisibility"))
        self.set_toolbar_checked("skeleton_visibility", character_visibility(character, "GetSkeletonVisibility"))
        bypassing_current_character = self.pin_bypass_active and same_component(character, self.pin_bypass_character)
        self.set_toolbar_checked("release_all_pins", bypassing_current_character)

        mode = current_character_keying_mode(character)
        if mode is None and character is not None:
            try:
                # Display MotionBuilder's normal initial state without calling
                # the native keying-mode getter, which initializes Character
                # Controls.  This is presentation-only; it does not write the
                # character until the user clicks a keying-mode button.
                mode = FBCharacterKeyingMode.kFBCharacterKeyingFullBody
            except Exception:
                pass
        mode_names = (
            ("key_full_body", "kFBCharacterKeyingFullBody"),
            ("key_full_body_no_pull", "kFBCharacterKeyingFullBodyNoPull"),
            ("key_body_part", "kFBCharacterKeyingBodyPart"),
            ("key_selection", "kFBCharacterKeyingSelection"),
        )
        for button_name, enum_name in mode_names:
            try:
                checked = mode == getattr(FBCharacterKeyingMode, enum_name)
            except Exception:
                checked = False
            self.set_toolbar_checked(button_name, checked)

        selected_ids = picker_effector_ids(character, True) if has_character else []
        for button_name, state_method in (
            ("pin_translation", "IsTranslationPin"),
            ("pin_rotation", "IsRotationPin"),
        ):
            button = self.toolbar_buttons[button_name]
            button.setEnabled(bool(selected_ids) and not bypassing_current_character)
            states = []
            for effector_id in selected_ids:
                try:
                    states.append(bool(getattr(character, state_method)(effector_id)))
                except Exception:
                    states.append(False)
            self.set_toolbar_checked(button_name, bool(states) and all(states))

    def on_visibility_clicked(self, setter_name, checked):
        try:
            set_character_visibility(get_current_character(), setter_name, checked)
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.update()

    def on_keying_mode_clicked(self, enum_name):
        global _LAST_UI_KEYING_MODE
        character = get_current_character()
        if character is None:
            return
        try:
            mode = getattr(FBCharacterKeyingMode, enum_name)
            character.KeyingMode = mode
            _LAST_UI_KEYING_MODE = mode
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.update()

    def on_pin_clicked(self, translation):
        character = get_current_character()
        effector_ids = picker_effector_ids(character, True)
        if character is None or not effector_ids:
            return
        state_method = "IsTranslationPin" if translation else "IsRotationPin"
        set_method = "SetTranslationPin" if translation else "SetRotationPin"
        try:
            current_states = [bool(getattr(character, state_method)(effector_id)) for effector_id in effector_ids]
            new_state = not all(current_states)
            for effector_id in effector_ids:
                getattr(character, set_method)(effector_id, new_state)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_toolbar_ui()
        self.update()

    def set_character_pinning_enabled(self, character, enabled):
        if character is None:
            return
        for effector_id in picker_effector_ids(character):
            character.SetTranslationPin(effector_id, bool(enabled))
            character.SetRotationPin(effector_id, bool(enabled))

    def restore_pin_bypass(self):
        if not self.pin_bypass_active:
            return
        character = self.pin_bypass_character
        snapshot = list(self.pin_bypass_snapshot)
        self.pin_bypass_active = False
        self.pin_bypass_character = None
        self.pin_bypass_snapshot = []
        try:
            if character is not None:
                for effector_id, translation_pinned, rotation_pinned in snapshot:
                    character.SetTranslationPin(effector_id, translation_pinned)
                    character.SetRotationPin(effector_id, rotation_pinned)
                evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def discard_pin_bypass(self):
        self.pin_bypass_active = False
        self.pin_bypass_character = None
        self.pin_bypass_snapshot = []
        if "release_all_pins" in self.toolbar_buttons:
            self.set_toolbar_checked("release_all_pins", False)

    def on_pin_bypass_toggled(self, checked):
        character = get_current_character()
        if checked and character is None:
            self.set_toolbar_checked("release_all_pins", False)
            return
        try:
            if checked:
                if self.pin_bypass_active:
                    self.restore_pin_bypass()
                snapshot = []
                for effector_id in picker_effector_ids(character):
                    snapshot.append((
                        effector_id,
                        bool(character.IsTranslationPin(effector_id)),
                        bool(character.IsRotationPin(effector_id)),
                    ))
                self.pin_bypass_character = character
                self.pin_bypass_snapshot = snapshot
                self.pin_bypass_active = True
                self.set_character_pinning_enabled(character, False)
            else:
                self.restore_pin_bypass()
            evaluate_scene()
        except Exception:
            self.restore_pin_bypass()
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_toolbar_ui()
        self.update()

    def permanently_release_all_pinning(self):
        character = get_current_character()
        if character is None:
            return
        try:
            if self.pin_bypass_active:
                if same_component(character, self.pin_bypass_character):
                    self.discard_pin_bypass()
                else:
                    self.restore_pin_bypass()
            self.set_character_pinning_enabled(character, False)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_toolbar_ui()
        self.update()

    def go_to_stance_pose(self):
        character = get_current_character()
        if character is None:
            return
        try:
            character.GoToStancePose(True, True)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.update()

    def rebuild_pinning_preset_menu(self):
        self.pinning_preset_menu.clear()
        names = saved_pinning_preset_names()
        if names:
            for name in names:
                action = self.pinning_preset_menu.addAction(name)
                action.triggered.connect(lambda checked=False, preset_name=name: self.load_pinning_preset(preset_name))
        else:
            empty_action = self.pinning_preset_menu.addAction("No saved presets")
            empty_action.setEnabled(False)
        self.pinning_preset_menu.addSeparator()
        self.pinning_preset_menu.addAction("Create Preset...").triggered.connect(self.create_pinning_preset)
        rename_action = self.pinning_preset_menu.addAction("Rename Preset...")
        rename_action.setEnabled(bool(names))
        rename_action.triggered.connect(self.rename_pinning_preset)
        delete_action = self.pinning_preset_menu.addAction("Delete Preset...")
        delete_action.setEnabled(bool(names))
        delete_action.triggered.connect(self.delete_pinning_preset)
        self.pinning_preset_menu.addSeparator()
        self.pinning_preset_menu.addAction("Release All Pinning").triggered.connect(
            self.permanently_release_all_pinning
        )

    def load_pinning_preset(self, preset_name):
        try:
            loaded = load_custom_pinning_preset(get_current_character(), preset_name)
            if not loaded:
                loaded = bool(FBLoadCharacterPinningPreset(str(preset_name)))
            if not loaded:
                raise RuntimeError("MotionBuilder could not load pinning preset: " + str(preset_name))
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_toolbar_ui()
        self.update()

    def create_pinning_preset(self):
        name, accepted = QtWidgets.QInputDialog.getText(self, "Create Pinning Preset", "Preset name:")
        name = str(name).strip()
        if not accepted or not name:
            return
        try:
            saved = bool(FBSaveCharacterPinningPreset(name, True))
            if not saved:
                saved = save_custom_pinning_preset(get_current_character(), name)
            if not saved:
                raise RuntimeError("MotionBuilder could not save the pinning preset.")
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def rename_pinning_preset(self):
        names = saved_pinning_preset_names()
        if not names:
            return
        old_name, accepted = QtWidgets.QInputDialog.getItem(
            self, "Rename Pinning Preset", "Preset:", names, 0, False
        )
        if not accepted:
            return
        old_name = str(old_name)
        new_name, accepted = QtWidgets.QInputDialog.getText(
            self, "Rename Pinning Preset", "New name:", text=old_name
        )
        new_name = str(new_name).strip()
        if not accepted or not new_name or new_name == old_name:
            return
        if any(name.lower() == new_name.lower() for name in names):
            FBMessageBox(TOOL_NAME, "A pinning preset named '%s' already exists." % new_name, "OK")
            return
        try:
            renamed = rename_pinning_preset(get_current_character(), old_name, new_name)
            if not renamed:
                raise RuntimeError("MotionBuilder could not rename pinning preset: " + old_name)
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def delete_pinning_preset(self):
        names = saved_pinning_preset_names()
        if not names:
            return
        name, accepted = QtWidgets.QInputDialog.getItem(
            self, "Delete Pinning Preset", "Preset:", names, 0, False
        )
        if not accepted:
            return
        try:
            deleted = delete_custom_pinning_preset(str(name))
            if not deleted:
                deleted = bool(FBDeleteCharacterPinningPreset(str(name)))
            if not deleted:
                raise RuntimeError("MotionBuilder could not delete pinning preset: " + str(name))
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def refresh_selector_ui(self):
        if self.updating_selector_ui:
            return
        self.updating_selector_ui = True
        try:
            current_character = get_current_character()
            character_options = scene_characters()
            current_index = -1
            for index, character in enumerate(character_options):
                if same_component(character, current_character):
                    current_index = index
            character_signature = (
                tuple(component_name(character) for character in character_options),
                component_name(current_character),
            )
            self.character_options = character_options
            if character_signature != self.character_selector_signature:
                self.character_selector_signature = character_signature
                self.character_combo.blockSignals(True)
                self.character_combo.clear()
                for character in self.character_options:
                    self.character_combo.addItem(component_name(character))
                if not self.character_options:
                    self.character_combo.addItem("No Character")
                    self.character_combo.setCurrentIndex(0)
                    self.character_combo.setEnabled(False)
                else:
                    self.character_combo.setEnabled(True)
                    self.character_combo.setCurrentIndex(max(0, current_index))
                self.character_combo.blockSignals(False)

            source_options = source_options_for_character(current_character) if current_character is not None else []
            source_kind, source_component = character_source_state(current_character)
            source_index = -1
            for index, (label, option_kind, option_component) in enumerate(source_options):
                if option_kind == source_kind and (
                    option_kind in ("none", "control_rig") or same_component(option_component, source_component)
                ):
                    source_index = index
            source_signature = (
                tuple((label, kind, component_name(component)) for label, kind, component in source_options),
                source_kind,
                component_name(source_component),
            )
            self.source_options = source_options
            if source_signature != self.source_selector_signature:
                self.source_selector_signature = source_signature
                self.source_combo.blockSignals(True)
                self.source_combo.clear()
                for label, _option_kind, _option_component in self.source_options:
                    self.source_combo.addItem(label)
                if not self.source_options:
                    self.source_combo.addItem("None")
                    self.source_combo.setCurrentIndex(0)
                    self.source_combo.setEnabled(False)
                else:
                    self.source_combo.setEnabled(True)
                    self.source_combo.setCurrentIndex(max(0, source_index))
                self.source_combo.blockSignals(False)
        finally:
            self.updating_selector_ui = False

    def on_character_combo_changed(self, index):
        global _FK_MODEL_CACHE
        if self.updating_selector_ui or index < 0 or index >= len(self.character_options):
            return
        try:
            self.restore_pin_bypass()
            FBApplication().CurrentCharacter = self.character_options[index]
            _FK_MODEL_CACHE = {"control_set": None, "models": {}}
            evaluate_scene()
            self.refresh_selector_ui()
            self.refresh_bake_ui()
            self.refresh_toolbar_ui()
            self.refresh_slider_ui()
            self.update()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def on_source_combo_changed(self, index):
        global _FK_MODEL_CACHE
        if self.updating_selector_ui or index < 0 or index >= len(self.source_options):
            return
        try:
            _label, source_kind, source_component = self.source_options[index]
            apply_character_source(get_current_character(), source_kind, source_component)
            _FK_MODEL_CACHE = {"control_set": None, "models": {}}
            self.refresh_selector_ui()
            self.refresh_bake_ui()
            self.refresh_toolbar_ui()
            self.refresh_slider_ui()
            self.update()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")

    def create_slider_controls(self):
        popup_scale = SLIDER_POPUP_SCALE
        scaled = lambda value: max(1, int(round(float(value) * popup_scale)))
        popup_flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
        self.slider_popup_menu = QtWidgets.QFrame(self, popup_flags)
        self.slider_popup_menu.setObjectName("ik_effector_slider_menu")
        self.slider_popup_menu.setStyleSheet(
            "QFrame#ik_effector_slider_menu { color: #eeeeee; background: #2b2b2b; border: 1px solid #666666; }"
        )
        self.slider_popup_menu.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

        self.slider_popup_widget = QtWidgets.QWidget(self.slider_popup_menu)
        self.slider_popup_widget.setObjectName("ik_effector_slider_widget")
        self.slider_popup_widget.setStyleSheet("background: #2b2b2b;")
        self.slider_key_context_menu = QtWidgets.QMenu(self)
        self.slider_key_context_menu.setObjectName("slider_key_context_menu")
        self.slider_key_context_menu.setStyleSheet(self.character_menu_style())
        self.slider_key_context_action = QtGui.QAction(
            "Remove All Keys in This Take", self.slider_key_context_menu
        )
        self.slider_key_context_menu.addAction(self.slider_key_context_action)
        self.slider_key_context_action.triggered.connect(self.remove_all_slider_property_keys)
        frame_layout = QtWidgets.QVBoxLayout(self.slider_popup_menu)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout = QtWidgets.QVBoxLayout(self.slider_popup_widget)
        popup_layout.setContentsMargins(scaled(8), scaled(6), scaled(8), scaled(7))
        popup_layout.setSpacing(scaled(4))
        frame_layout.addWidget(self.slider_popup_widget)

        self.slider_context_label = QtWidgets.QLabel("IK Effector", self.slider_popup_widget)
        self.slider_context_label.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_context_label.setStyleSheet(
            "color: #d9d9d9; background: transparent; font-size: %dpx;" % scaled(12)
        )
        self.slider_context_label.setMinimumHeight(scaled(18))
        popup_layout.addWidget(self.slider_context_label)

        for display_name, property_name in EFFECTOR_SLIDER_SPECS:
            row_widget = QtWidgets.QWidget(self.slider_popup_widget)
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(scaled(5))

            label = QtWidgets.QLabel(display_name, row_widget)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label.setStyleSheet(
                "color: #dddddd; background: transparent; font-size: %dpx;" % scaled(12)
            )
            label.setFixedWidth(scaled(70))

            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, row_widget)
            slider.setRange(0, SLIDER_STEPS)
            slider.setMinimumWidth(scaled(118))
            slider.setObjectName("effector_slider_" + property_name.replace(" ", "_"))
            slider.setToolTip(property_name + " for this IK effector")
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: %dpx; background: #343434; border: 1px solid #555; }"
                "QSlider::sub-page:horizontal { background: #518a58; }"
                "QSlider::handle:horizontal { width: %dpx; margin: -%dpx 0; border-radius: %dpx; "
                "background: #d7d7d7; border: 1px solid #111; }"
                "QSlider:disabled { color: #555; }"
                % (scaled(5), scaled(11), scaled(4), scaled(5))
            )
            slider.valueChanged.connect(lambda value, prop_name=property_name: self.on_slider_value_changed(prop_name, value))

            value_label = QtWidgets.QLabel("--", row_widget)
            value_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            value_label.setStyleSheet(
                "color: #cccccc; background: transparent; font-size: %dpx;" % scaled(12)
            )
            value_label.setFixedWidth(scaled(40))

            key_button = QtWidgets.QPushButton("K", row_widget)
            key_button.setFixedSize(scaled(28), scaled(22))
            key_button.setStyleSheet("font-size: %dpx; padding: 0px;" % scaled(12))
            key_button.setObjectName("effector_key_" + property_name.replace(" ", "_"))
            key_button.setToolTip(
                "LMB: toggle a keyframe at the current frame\n"
                "RMB: remove all keys from " + property_name + " in this take"
            )
            key_button.clicked.connect(lambda checked=False, prop_name=property_name: self.key_slider_property(prop_name))
            key_button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            key_button.customContextMenuRequested.connect(
                lambda point, prop_name=property_name, button=key_button:
                    self.show_slider_key_context_menu(prop_name, button, point)
            )

            row_layout.addWidget(label)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(value_label)
            row_layout.addWidget(key_button)
            popup_layout.addWidget(row_widget)

            self.slider_controls[property_name] = {
                "label": label,
                "slider": slider,
                "value": value_label,
                "key": key_button,
            }

        self.slider_popup_widget.setFixedWidth(scaled(300))
        # QWidget.adjustSize() imposes a 200 px minimum on expanding top-level
        # windows.  Pin the frame too so the half-sized popup has no blank area.
        self.slider_popup_menu.setFixedWidth(scaled(304))
        self.slider_popup_menu.adjustSize()
        self.slider_popup_menu.hide()

    def refresh_adaptive_picker_items(self):
        desired_items = picker_items_for_character(get_current_character())
        signature = tuple(
            item.get("tooltip") for item in desired_items
            if item.get("kind") == "fk" and item.get("tooltip") in ("Neck", "Neck1", "Neck2")
        )
        if signature == self.adaptive_neck_signature:
            return False
        self.items = desired_items
        self.adaptive_neck_signature = signature
        if self.hover_item is not None and self.hover_item.get("tooltip") in ("Neck", "Neck1", "Neck2"):
            self.hover_item = None
        if self.drag_press_item is not None and self.drag_press_item.get("tooltip") in ("Neck", "Neck1", "Neck2"):
            self.drag_press_item = None
        return True

    def auxiliary_marker_center(self, base_item, slot_index):
        base_x, base_y = base_item.get("center")
        try:
            numeric_id = int(base_item.get("id"))
        except Exception:
            numeric_id = -1
        first_offset = AUXILIARY_DISTANCE
        radius = AUXILIARY_SIZE * 0.5
        column_step = AUXILIARY_SIZE + AUXILIARY_GAP
        if numeric_id in CHEST_AUXILIARY_EFFECTOR_IDS:
            # Chest/Spine auxiliaries sit diagonally above-right so they clear
            # the spine, shoulders, and the main chest effector.
            direction_x = 2.0 ** -0.5
            direction_y = -(2.0 ** -0.5)
            available_columns = AUXILIARY_COLUMNS
        else:
            preferred_direction = -1.0 if base_x < BACKGROUND_WIDTH * 0.5 else 1.0
            preferred_space = base_x if preferred_direction < 0.0 else BACKGROUND_WIDTH - base_x
            opposite_space = BACKGROUND_WIDTH - base_x if preferred_direction < 0.0 else base_x
            direction_x = preferred_direction
            direction_y = 0.0
            minimum_space = first_offset + radius + 1.0
            if preferred_space < minimum_space and opposite_space > preferred_space:
                direction_x *= -1.0
                preferred_space = opposite_space
            extra_space = max(0.0, preferred_space - minimum_space)
            available_columns = min(AUXILIARY_COLUMNS, 1 + int(extra_space // column_step))

        available_columns = max(1, available_columns)
        column = slot_index % available_columns
        row = slot_index // available_columns
        primary_offset = first_offset + column * column_step
        if row == 0:
            perpendicular_offset = 0.0
        else:
            magnitude = (row + 1) // 2
            perpendicular_offset = magnitude * column_step
            if row % 2:
                perpendicular_offset *= -1.0

        perpendicular_x = -direction_y
        perpendicular_y = direction_x
        x = base_x + direction_x * primary_offset + perpendicular_x * perpendicular_offset
        y = base_y + direction_y * primary_offset + perpendicular_y * perpendicular_offset
        x = clamp(x, radius + 1.0, BACKGROUND_WIDTH - radius - 1.0)
        y = clamp(y, radius + 1.0, BACKGROUND_HEIGHT - radius - 1.0)
        return (x, y)

    def refresh_auxiliary_items(self):
        character = get_current_character()
        items = []
        seen = set()
        for base_item in self.items:
            if base_item.get("kind") != "ik":
                continue
            try:
                numeric_id = int(base_item.get("id"))
            except Exception:
                continue
            if numeric_id in seen:
                continue
            seen.add(numeric_id)
            models = auxiliary_models_for_effector(character, effector_id_from_int(numeric_id))
            for slot_index, (numeric_set_id, model, pivot) in enumerate(models):
                kind = "aux_pivot" if pivot else "aux_effector"
                label = "AUX Pivot" if pivot else "AUX Effector"
                items.append({
                    "kind": kind,
                    "id": numeric_id,
                    "effector_set_id": numeric_set_id,
                    "center": self.auxiliary_marker_center(base_item, slot_index),
                    "tooltip": "%s %s %d" % (base_item.get("tooltip", "IK"), label, numeric_set_id),
                    "base_item": base_item,
                    "model_name": component_name(model),
                })
        self.auxiliary_items_cache = items

    def all_picker_items(self, character=None):
        return list(self.items) + list(self.auxiliary_items_cache)

    def create_auxiliary_menu(self):
        self.auxiliary_menu = QtWidgets.QMenu(self)
        self.auxiliary_menu.setObjectName("ik_effector_auxiliary_menu")
        self.auxiliary_menu.setStyleSheet(self.character_menu_style())
        for key, text, pivot in (
            ("pivot", "Create AUX Pivot", True),
            ("effector", "Create AUX Effector", False),
        ):
            action = QtGui.QAction(text, self.auxiliary_menu)
            action.setObjectName("ik_effector_create_aux_" + key)
            action.triggered.connect(
                lambda checked=False, create_pivot=pivot: self.create_auxiliary_from_context(create_pivot)
            )
            self.auxiliary_menu.addAction(action)
            self.auxiliary_menu_actions[key] = action

    def show_auxiliary_menu(self, item, global_point):
        character = get_current_character()
        model = get_model_for_item(character, item)
        if character is None or model is None or item.get("kind") != "ik":
            return
        self.close_effector_slider_popup()
        if self.auxiliary_menu.isVisible():
            self.auxiliary_menu.hide()
        self.auxiliary_context_item = item
        enabled = callable(getattr(character, "CreateAuxiliary", None))
        for action in self.auxiliary_menu_actions.values():
            action.setEnabled(enabled)
        self.auxiliary_menu.popup(global_point)

    def create_auxiliary_from_context(self, pivot):
        item = self.auxiliary_context_item
        character = get_current_character()
        if character is None or item is None or item.get("kind") != "ik":
            return
        try:
            effector_id = effector_id_from_int(int(item.get("id")))
        except Exception:
            return
        character_controls_visibility = capture_character_controls_visibility()
        try:
            created = bool(character.CreateAuxiliary(effector_id, bool(pivot)))
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
            return
        finally:
            restore_character_controls_visibility(character_controls_visibility)
        if not created:
            label = "AUX Pivot" if pivot else "AUX Effector"
            FBMessageBox(TOOL_NAME, "MotionBuilder could not create the " + label + ".", "OK")
            return
        evaluate_scene()
        self.refresh_auxiliary_items()
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.refresh_slider_ui()
        self.update()

    def slider_popup_global_point(self, event):
        try:
            return event.globalPosition().toPoint()
        except Exception:
            try:
                return event.globalPos()
            except Exception:
                return self.mapToGlobal(event.pos())

    def show_effector_slider_popup(self, item, global_point):
        character = get_current_character()
        model = get_model_for_item(character, item)
        if model is None or item.get("kind") not in ("ik", "aux_effector", "aux_pivot"):
            return
        if self.auxiliary_menu is not None and self.auxiliary_menu.isVisible():
            self.auxiliary_menu.hide()
        if self.slider_key_context_menu is not None and self.slider_key_context_menu.isVisible():
            self.slider_key_context_menu.hide()
        self.slider_key_context_property = None
        if self.slider_popup_menu.isVisible():
            self.slider_popup_menu.hide()
        # RMB on one member of an existing IK selection must preserve the rest
        # of that selection so slider changes can fan out to every effector.
        if not is_model_selected(model):
            select_item(item, False)
        self.slider_context_item = item
        self.slider_context_model = model
        self.refresh_slider_ui()
        self.slider_popup_menu.adjustSize()
        self.slider_popup_menu.move(self.screen_safe_slider_popup_position(global_point))
        self.slider_popup_menu.show()
        self.slider_popup_menu.raise_()

    def screen_safe_slider_popup_position(self, cursor_point):
        try:
            screen = QtGui.QGuiApplication.screenAt(cursor_point)
        except Exception:
            screen = None
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()

        available = screen.availableGeometry()
        popup_size = self.slider_popup_menu.sizeHint().expandedTo(self.slider_popup_menu.minimumSizeHint())
        popup_width = max(1, popup_size.width())
        popup_height = max(1, popup_size.height())

        x = cursor_point.x()
        y = cursor_point.y()
        if x + popup_width > available.right() + 1:
            x = cursor_point.x() - popup_width
        x = max(available.left(), min(x, available.right() - popup_width + 1))
        y = max(available.top(), min(y, available.bottom() - popup_height + 1))
        return QtCore.QPoint(int(x), int(y))

    def close_effector_slider_popup(self):
        if self.slider_key_context_menu is not None and self.slider_key_context_menu.isVisible():
            self.slider_key_context_menu.hide()
        if self.slider_popup_menu is not None and self.slider_popup_menu.isVisible():
            self.slider_popup_menu.hide()
        self.slider_key_context_property = None
        self.slider_context_model = None
        self.slider_context_item = None

    def focus_widget_accepts_typed_input(self):
        focus_widget = QtWidgets.QApplication.focusWidget()
        if isinstance(
            focus_widget,
            (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox),
        ):
            return True
        return isinstance(focus_widget, QtWidgets.QComboBox) and focus_widget.isEditable()

    def apply_character_keying_shortcut(self, enum_name):
        global _LAST_UI_KEYING_MODE
        character = get_current_character()
        if character is None:
            return
        try:
            mode = normalize_keying_mode(getattr(FBCharacterKeyingMode, enum_name))
        except Exception:
            mode = None
        if mode is None:
            return
        # MotionBuilder has already handled the shortcut by the time this
        # zero-delay callback runs.  Cache the matching mode without reading
        # character.KeyingMode, whose passive getter initializes Character
        # Controls in a fresh session.
        _LAST_UI_KEYING_MODE = mode
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.update()

    def detect_character_keying_shortcut(self, event):
        if self.focus_widget_accepts_typed_input():
            return
        try:
            if event.isAutoRepeat():
                return
        except Exception:
            pass
        relevant_modifiers = (
            QtCore.Qt.ShiftModifier
            | QtCore.Qt.ControlModifier
            | QtCore.Qt.AltModifier
            | QtCore.Qt.MetaModifier
            | QtCore.Qt.KeypadModifier
        )
        event_modifiers = event.modifiers() & relevant_modifiers
        for (key, modifiers), enum_name in self.character_keying_shortcuts.items():
            if event.key() == key and event_modifiers == modifiers:
                QtCore.QTimer.singleShot(
                    0, lambda mode_name=enum_name: self.apply_character_keying_shortcut(mode_name)
                )
                return

    def eventFilter(self, watched, event):
        try:
            if event.type() == QtCore.QEvent.KeyPress:
                self.detect_character_keying_shortcut(event)
            if (
                self.slider_popup_menu is not None
                and self.slider_popup_menu.isVisible()
                and event.type() == QtCore.QEvent.MouseButtonPress
                and event.button() in (QtCore.Qt.LeftButton, QtCore.Qt.RightButton)
            ):
                target = watched if isinstance(watched, QtWidgets.QWidget) else None
                if target is None:
                    target = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
                inside_popup = target is self.slider_popup_menu or (
                    target is not None and self.slider_popup_menu.isAncestorOf(target)
                )
                inside_key_context = target is self.slider_key_context_menu or (
                    target is not None
                    and self.slider_key_context_menu is not None
                    and self.slider_key_context_menu.isAncestorOf(target)
                )
                inside_picker = target is self or (
                    target is not None and self.isAncestorOf(target)
                )
                if not inside_popup and not inside_key_context and not inside_picker:
                    self.close_effector_slider_popup()
        except Exception:
            pass
        return QtWidgets.QWidget.eventFilter(self, watched, event)

    def logical_geometry(self, left, top, width, height):
        scale = self.logical_scale()
        origin_x, origin_y = self.logical_origin()
        return QtCore.QRect(
            int(round(origin_x + left * scale)),
            int(round(origin_y + top * scale)),
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )

    def apply_embedded_ui_scale(self):
        scale = self.logical_scale()
        pixel_size = max(6, int(round(11.0 * scale)))
        text_widgets = [
            self.character_label,
            self.character_combo,
            self.source_label,
            self.source_combo,
        ] + list(self.bake_buttons.values())
        for widget in text_widgets:
            if widget is None:
                continue
            font = widget.font()
            font.setPixelSize(pixel_size)
            widget.setFont(font)
        for combo in (self.character_combo, self.source_combo):
            if combo is None:
                continue
            try:
                combo.view().setFont(combo.font())
            except Exception:
                pass

    def resizeEvent(self, event):
        self.position_selector_controls()
        self.position_bake_controls()
        self.position_toolbar_controls()
        self.apply_embedded_ui_scale()
        QtWidgets.QWidget.resizeEvent(self, event)

    def closeEvent(self, event):
        self.restore_pin_bypass()
        self.close_effector_slider_popup()
        try:
            QtWidgets.QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        QtWidgets.QWidget.closeEvent(self, event)

    def on_refresh_timer(self):
        adaptive_items_changed = self.refresh_adaptive_picker_items()
        self.auxiliary_refresh_counter = (self.auxiliary_refresh_counter + 1) % 3
        if adaptive_items_changed or self.auxiliary_refresh_counter == 0:
            self.refresh_auxiliary_items()
        self.refresh_selector_ui()
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.refresh_slider_ui()
        self.update()

    def slider_position_from_value(self, prop, value):
        min_value, max_value = property_range(prop)
        normalized = (clamp(value, min_value, max_value) - min_value) / (max_value - min_value)
        return int(round(normalized * SLIDER_STEPS))

    def property_value_from_slider(self, prop, slider_position):
        min_value, max_value = property_range(prop)
        normalized = float(slider_position) / float(SLIDER_STEPS)
        return min_value + normalized * (max_value - min_value)

    def set_key_button_state(self, button, keyed, enabled):
        button.setEnabled(enabled)
        if keyed and enabled:
            button.setStyleSheet("QPushButton { color: white; background: #b52a2a; border: 1px solid #ff9b9b; font-weight: bold; }")
        else:
            button.setStyleSheet("QPushButton { color: #eeeeee; background: #414141; border: 1px solid #666; font-weight: bold; } QPushButton:disabled { color: #777; background: #292929; }")

    def current_slider_context_model(self):
        model = self.slider_context_model
        item = self.slider_context_item
        character = get_current_character()
        if model is None or item is None or character is None:
            return None
        resolved_model = get_model_for_item(character, item)
        if not same_component(model, resolved_model) or not is_model_selected(model):
            return None
        return model

    def refresh_slider_ui(self):
        model = self.current_slider_context_model()
        if self.slider_context_model is not None and model is None:
            self.close_effector_slider_popup()
        props = get_effector_slider_properties(model)
        if model is None:
            context_text = "IK Effector"
        else:
            context_text = component_name(model).split(":")[-1]
        self.slider_context_label.setText(context_text)

        self.updating_slider_ui = True
        try:
            for _display_name, property_name in EFFECTOR_SLIDER_SPECS:
                controls = self.slider_controls[property_name]
                prop = props.get(property_name)
                enabled = prop is not None
                controls["label"].setEnabled(enabled)
                controls["slider"].setEnabled(enabled)
                controls["value"].setEnabled(enabled)
                if enabled:
                    value = property_float(prop)
                    controls["slider"].blockSignals(True)
                    controls["slider"].setValue(self.slider_position_from_value(prop, value))
                    controls["slider"].blockSignals(False)
                    controls["value"].setText("%0.1f" % value)
                    self.set_key_button_state(controls["key"], property_has_key_at_current_time(prop), True)
                else:
                    controls["slider"].blockSignals(True)
                    controls["slider"].setValue(0)
                    controls["slider"].blockSignals(False)
                    controls["value"].setText("--")
                    self.set_key_button_state(controls["key"], False, False)
        finally:
            self.updating_slider_ui = False

    def on_slider_value_changed(self, property_name, slider_position):
        if self.updating_slider_ui:
            return
        context_model = self.current_slider_context_model()
        context_prop = get_effector_slider_properties(context_model).get(property_name)
        if context_prop is None:
            self.refresh_slider_ui()
            return
        try:
            value = self.property_value_from_slider(context_prop, slider_position)
            target_models = selected_effector_slider_models(context_model)
            if not target_models and context_model is not None:
                target_models = [context_model]
            for target_model in target_models:
                target_prop = get_effector_slider_properties(target_model).get(property_name)
                if target_prop is None:
                    continue
                min_value, max_value = property_range(target_prop)
                target_prop.Data = clamp(value, min_value, max_value)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_slider_ui()
        self.update()

    def key_slider_property(self, property_name):
        model = self.current_slider_context_model()
        prop = get_effector_slider_properties(model).get(property_name)
        if prop is None:
            return
        try:
            if property_has_key_at_current_time(prop):
                remove_property_key_at_current_time(prop)
            else:
                prop.Key()
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_slider_ui()
        self.update()

    def show_slider_key_context_menu(self, property_name, button, local_point):
        model = self.current_slider_context_model()
        prop = get_effector_slider_properties(model).get(property_name)
        if prop is None or self.slider_key_context_menu is None:
            return
        if self.slider_key_context_menu.isVisible():
            self.slider_key_context_menu.hide()
        self.slider_key_context_property = property_name
        self.slider_key_context_action.setEnabled(property_key_count_in_current_take(prop) > 0)
        self.slider_key_context_menu.popup(button.mapToGlobal(local_point))

    def remove_all_slider_property_keys(self, checked=False):
        property_name = self.slider_key_context_property
        model = self.current_slider_context_model()
        prop = get_effector_slider_properties(model).get(property_name)
        if prop is None:
            return
        try:
            remove_all_property_keys_in_current_take(prop)
            evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.refresh_slider_ui()
        self.update()

    def logical_scale(self):
        return max(
            0.01,
            min(
                float(self.width()) / float(self.logical_tool_width()),
                float(self.height()) / float(self.logical_tool_height()),
            ),
        )

    def logical_scale_x(self):
        return self.logical_scale()

    def logical_scale_y(self):
        return self.logical_scale()

    def logical_origin(self):
        scale = self.logical_scale()
        return (
            (self.width() - self.logical_tool_width() * scale) * 0.5,
            (self.height() - self.logical_tool_height() * scale) * 0.5,
        )

    def event_point(self, event):
        try:
            point = event.position()
        except Exception:
            point = event.localPos() if hasattr(event, "localPos") else QtCore.QPointF(event.x(), event.y())
        scale = self.logical_scale()
        origin_x, origin_y = self.logical_origin()
        return QtCore.QPointF((point.x() - origin_x) / scale, (point.y() - origin_y) / scale)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor(18, 18, 18))
        origin_x, origin_y = self.logical_origin()
        painter.translate(origin_x, origin_y)
        painter.scale(self.logical_scale(), self.logical_scale())
        self.draw_selector_panel(painter)
        self.draw_bake_panel(painter)
        self.draw_toolbar_panel(painter)
        target = QtCore.QRectF(
            self.logical_background_left(), self.logical_background_top(), BACKGROUND_WIDTH, BACKGROUND_HEIGHT
        )
        if self.background_pixmap.isNull():
            painter.fillRect(target, QtGui.QColor(8, 8, 8))
        else:
            painter.drawPixmap(target.toRect(), self.background_pixmap)
        self.draw_items(painter)
        self.draw_box_selection(painter)
        painter.end()

    def draw_selector_panel(self, painter):
        if self.selector_area_collapsed:
            return
        panel_top = SELECTOR_ROWS_TOP - 3
        panel_height = SELECTOR_ROW_HEIGHT * 2 + 3
        panel_rect = QtCore.QRectF(0, panel_top, self.logical_tool_width(), panel_height)
        painter.fillRect(panel_rect, QtGui.QColor(27, 27, 27))
        painter.setPen(QtGui.QPen(QtGui.QColor(62, 62, 62), 1.0))
        painter.drawRect(panel_rect)

    def draw_bake_panel(self, painter):
        panel_rect = QtCore.QRectF(
            0, self.logical_bake_row_top() - 2, self.logical_tool_width(), BAKE_ROW_HEIGHT + 4
        )
        painter.fillRect(panel_rect, QtGui.QColor(27, 27, 27))
        painter.setPen(QtGui.QPen(QtGui.QColor(62, 62, 62), 1.0))
        painter.drawRect(panel_rect)

    def draw_toolbar_panel(self, painter):
        if self.picker_ui_is_vertical():
            panel_rect = QtCore.QRectF(0, self.logical_background_top(), VERTICAL_TOOLBAR_WIDTH, BACKGROUND_HEIGHT)
        else:
            panel_rect = QtCore.QRectF(0, self.logical_toolbar_top() - 2, BACKGROUND_WIDTH, TOOLBAR_HEIGHT + 4)
        painter.fillRect(panel_rect, QtGui.QColor(27, 27, 27))
        painter.setPen(QtGui.QPen(QtGui.QColor(62, 62, 62), 1.0))
        painter.drawRect(panel_rect)

    def draw_items(self, painter):
        character = get_current_character()
        for item in self.items:
            if item["kind"] == "fk":
                self.draw_fk(painter, item, character)
        for item in self.items:
            if item["kind"] != "fk":
                self.draw_ik(painter, item, character)
        for item in self.auxiliary_items_cache:
            self.draw_auxiliary(painter, item, character)

    def item_state(self, item, character):
        model = get_model_for_item(character, item)
        selected = is_model_selected(model)
        hovered = self.hover_item is item or self.item_in_box(item)
        return model, selected, hovered

    def draw_fk(self, painter, item, character):
        model, selected, hovered = self.item_state(item, character)
        shortened_start, shortened_end = shortened_fk_segment(item)
        background_left = self.logical_background_left()
        background_top = self.logical_background_top()
        start = QtCore.QPointF(background_left + shortened_start[0], background_top + shortened_start[1])
        end = QtCore.QPointF(background_left + shortened_end[0], background_top + shortened_end[1])
        alpha = 255 if model is not None else 70
        painter.setPen(QtGui.QPen(QtGui.QColor(5, 5, 5, alpha), 7.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        painter.drawLine(start, end)
        painter.setPen(QtGui.QPen(QtGui.QColor(105, 105, 105, alpha), 5.5, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        painter.drawLine(start, end)
        center_color = QtGui.QColor(70, 232, 248) if selected or hovered else QtGui.QColor(225, 225, 225, alpha)
        painter.setPen(QtGui.QPen(center_color, 2.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        painter.drawLine(start, end)

    def draw_ik(self, painter, item, character):
        model, selected, hovered = self.item_state(item, character)
        center = QtCore.QPointF(
            self.logical_background_left() + item["center"][0],
            self.logical_background_top() + item["center"][1],
        )
        diameter = IK_SMALL_SIZE if item.get("small") else IK_SIZE
        radius = diameter * 0.5
        alpha = 255 if model is not None else 70
        if item["kind"] == "reference":
            painter.setBrush(QtGui.QColor(80, 72, 112, alpha))
        else:
            gradient = QtGui.QRadialGradient(center.x() - 2, center.y() - 2, radius * 1.6)
            gradient.setColorAt(0.0, QtGui.QColor(250, 250, 250, alpha))
            gradient.setColorAt(0.65, QtGui.QColor(82, 82, 82, alpha))
            gradient.setColorAt(1.0, QtGui.QColor(155, 155, 155, alpha))
            painter.setBrush(gradient)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, alpha), 1.0))
        painter.drawEllipse(center, radius, radius)
        if item["kind"] == "ik" and model is not None:
            translation_ratio = normalized_effector_property_value(model, "IK Reach Translation")
            rotation_ratio = normalized_effector_property_value(model, "IK Reach Rotation")
            pull_ratio = normalized_effector_property_value(model, "IK Pull")
            fill_color = effector_fill_color(pull_ratio, alpha)
            self.draw_half_circle_fill(painter, center, radius, translation_ratio, False, fill_color)
            self.draw_half_circle_fill(painter, center, radius, rotation_ratio, True, fill_color)
            if translation_ratio > 0.0 or rotation_ratio > 0.0:
                painter.setPen(QtGui.QPen(QtGui.QColor(25, 25, 25, alpha), 0.65))
                painter.drawLine(QtCore.QPointF(center.x(), center.y() - radius + 0.8), QtCore.QPointF(center.x(), center.y() + radius - 0.8))
        if selected or hovered:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(70, 232, 248), 2.0))
            painter.drawEllipse(center, max(1.0, radius - 1.0), max(1.0, radius - 1.0))
        if item["kind"] == "ik" and model is not None:
            translation_pinned, rotation_pinned = effector_pin_states(character, item)
            self.draw_effector_pin_markers(painter, center, radius, translation_pinned, rotation_pinned)

    def draw_auxiliary(self, painter, item, character):
        model, selected, hovered = self.item_state(item, character)
        x, y = item.get("center")
        background_left = self.logical_background_left()
        background_top = self.logical_background_top()
        center = QtCore.QPointF(background_left + x, background_top + y)
        base_item = item.get("base_item") or {}
        base_x, base_y = base_item.get("center", (x, y))
        base_center = QtCore.QPointF(background_left + base_x, background_top + base_y)
        radius = AUXILIARY_SIZE * 0.5
        alpha = 255 if model is not None else 70

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(95, 95, 95, alpha), 1.0))
        dx = center.x() - base_center.x()
        dy = center.y() - base_center.y()
        distance = max(0.001, (dx * dx + dy * dy) ** 0.5)
        base_radius = (IK_SMALL_SIZE if base_item.get("small") else IK_SIZE) * 0.5
        line_start = QtCore.QPointF(
            base_center.x() + dx / distance * base_radius,
            base_center.y() + dy / distance * base_radius,
        )
        line_end = QtCore.QPointF(
            center.x() - dx / distance * radius,
            center.y() - dy / distance * radius,
        )
        painter.drawLine(line_start, line_end)

        if item.get("kind") == "aux_pivot":
            fill = QtGui.QColor(247, 171, 54, alpha)
        else:
            fill = QtGui.QColor(73, 187, 245, alpha)
        painter.setBrush(fill)
        painter.setPen(QtGui.QPen(QtGui.QColor(5, 5, 5, alpha), 1.0))
        painter.drawEllipse(center, radius, radius)

        if item.get("kind") == "aux_pivot":
            painter.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30, alpha), 0.9))
            arm = max(1.0, radius - 1.2)
            painter.drawLine(QtCore.QPointF(center.x() - arm, center.y()), QtCore.QPointF(center.x() + arm, center.y()))
            painter.drawLine(QtCore.QPointF(center.x(), center.y() - arm), QtCore.QPointF(center.x(), center.y() + arm))

        if selected or hovered:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(70, 232, 248), 1.5))
            painter.drawEllipse(center, max(1.0, radius - 0.5), max(1.0, radius - 0.5))

    def draw_effector_pin_markers(self, painter, center, radius, translation_pinned, rotation_pinned):
        if not translation_pinned and not rotation_pinned:
            return
        marker_width = max(15.0, radius * 2.8)
        marker_height = marker_width * (23.0 / 24.0)
        target = QtCore.QRectF(
            center.x() - marker_width * 0.5,
            center.y() - marker_height * 0.5,
            marker_width,
            marker_height,
        )
        if translation_pinned:
            self.draw_pin_icon(painter, self.translation_pin_icon, target, False)
        if rotation_pinned:
            self.draw_pin_icon(painter, self.rotation_pin_icon, target, True)

    def draw_pin_icon(self, painter, icon, target, right_side):
        if icon is not None and not icon.isNull():
            pixmap = icon.pixmap(48, 46)
            painter.drawPixmap(target.toRect(), pixmap)
            return
        marker_center_x = target.right() - 3.0 if right_side else target.left() + 3.0
        marker_center_y = target.top() + 3.0
        painter.setBrush(QtGui.QColor(70, 225, 82))
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 70, 24), 0.8))
        painter.drawEllipse(QtCore.QPointF(marker_center_x, marker_center_y), 2.1, 2.1)
        direction = -1.0 if right_side else 1.0
        painter.drawLine(
            QtCore.QPointF(marker_center_x, marker_center_y + 1.6),
            QtCore.QPointF(marker_center_x + direction * 3.5, marker_center_y + 5.2),
        )

    def draw_half_circle_fill(self, painter, center, radius, ratio, right_half, color):
        ratio = clamp(float(ratio), 0.0, 1.0)
        if ratio <= 0.0001:
            return
        circle_path = QtGui.QPainterPath()
        circle_path.addEllipse(center, radius - 0.7, radius - 0.7)
        if right_half:
            half_rect = QtCore.QRectF(center.x(), center.y() - radius, radius, radius * 2.0)
        else:
            half_rect = QtCore.QRectF(center.x() - radius, center.y() - radius, radius, radius * 2.0)
        half_path = QtGui.QPainterPath()
        half_path.addRect(half_rect)

        fill_height = radius * 2.0 * ratio
        fill_rect = QtCore.QRectF(
            half_rect.left(),
            center.y() + radius - fill_height,
            half_rect.width(),
            fill_height,
        )
        fill_path = QtGui.QPainterPath()
        fill_path.addRect(fill_rect)
        visible_path = circle_path.intersected(half_path).intersected(fill_path)
        painter.fillPath(visible_path, color)

    def current_box(self):
        if self.drag_start is None or self.drag_current is None:
            return None
        return QtCore.QRectF(self.drag_start, self.drag_current).normalized()

    def draw_box_selection(self, painter):
        rect = self.current_box()
        if not self.box_selecting or rect is None:
            return
        painter.setBrush(QtGui.QColor(70, 232, 248, 34))
        painter.setPen(QtGui.QPen(QtGui.QColor(70, 232, 248), 1.2, QtCore.Qt.DashLine))
        painter.drawRect(rect)

    def item_rect(self, item):
        background_left = self.logical_background_left()
        background_top = self.logical_background_top()
        if item["kind"] == "fk":
            (x1, y1), (x2, y2) = shortened_fk_segment(item)
            return QtCore.QRectF(
                QtCore.QPointF(background_left + x1, background_top + y1),
                QtCore.QPointF(background_left + x2, background_top + y2),
            ).normalized().adjusted(-4, -4, 4, 4)
        x, y = item["center"]
        if item.get("kind") in ("aux_effector", "aux_pivot"):
            radius = AUXILIARY_SIZE * 0.8
        else:
            radius = (IK_SMALL_SIZE if item.get("small") else IK_SIZE) * 0.7
        return QtCore.QRectF(background_left + x - radius, background_top + y - radius, radius * 2, radius * 2)

    def item_in_box(self, item):
        rect = self.current_box()
        return bool(self.box_selecting and rect is not None and rect.intersects(self.item_rect(item)))

    def hit_test(self, point):
        character = get_current_character()
        image_x = point.x() - self.logical_background_left()
        image_y = point.y() - self.logical_background_top()

        best_auxiliary = None
        best_auxiliary_distance = 99999.0
        for item in reversed(self.auxiliary_items_cache):
            if get_model_for_item(character, item) is None:
                continue
            x, y = item["center"]
            distance = ((image_x - x) ** 2 + (image_y - y) ** 2) ** 0.5
            threshold = AUXILIARY_SIZE * 0.9
            if distance <= threshold and distance < best_auxiliary_distance:
                best_auxiliary = item
                best_auxiliary_distance = distance
        if best_auxiliary is not None:
            return best_auxiliary

        best_ik = None
        best_ik_distance = 99999.0
        for item in reversed(self.items):
            if item["kind"] == "fk" or get_model_for_item(character, item) is None:
                continue
            x, y = item["center"]
            distance = ((image_x - x) ** 2 + (image_y - y) ** 2) ** 0.5
            threshold = (IK_SMALL_SIZE if item.get("small") else IK_SIZE) * 0.8
            if distance <= threshold and distance < best_ik_distance:
                best_ik = item
                best_ik_distance = distance
        if best_ik is not None:
            return best_ik

        best = None
        best_distance = 99999.0
        for item in reversed(self.items):
            if get_model_for_item(character, item) is None:
                continue
            if item["kind"] == "fk":
                shortened_start, shortened_end = shortened_fk_segment(item)
                distance = distance_to_segment(image_x, image_y, shortened_start, shortened_end)
                threshold = FK_HIT_WIDTH
            else:
                continue
            if distance <= threshold and distance < best_distance:
                best = item
                best_distance = distance
        return best

    def shift_pressed(self, event=None):
        try:
            if event is not None and event.modifiers() & QtCore.Qt.ShiftModifier:
                return True
        except Exception:
            pass
        try:
            return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier)
        except Exception:
            return False

    def point_in_bone_ui(self, point):
        return QtCore.QRectF(
            self.logical_background_left(), self.logical_background_top(), BACKGROUND_WIDTH, BACKGROUND_HEIGHT
        ).contains(point)

    def mouseMoveEvent(self, event):
        point = self.event_point(event)
        if self.drag_start is not None:
            try:
                left_down = bool(event.buttons() & QtCore.Qt.LeftButton)
            except Exception:
                left_down = False
            if left_down:
                self.drag_current = point
                dx = point.x() - self.drag_start.x()
                dy = point.y() - self.drag_start.y()
                if (dx * dx + dy * dy) ** 0.5 >= BOX_DRAG_THRESHOLD:
                    self.box_selecting = True
                    self.hover_item = None
                self.update()
                return
        item = self.hit_test(point)
        if item is not self.hover_item:
            self.hover_item = item
            self.update()

    def leaveEvent(self, event):
        self.hover_item = None
        self.update()

    def mousePressEvent(self, event):
        point = self.event_point(event)
        if event.button() == QtCore.Qt.MiddleButton:
            item = self.hit_test(point) if self.point_in_bone_ui(point) else None
            if item is not None and item.get("kind") == "ik":
                try:
                    self.show_auxiliary_menu(item, self.slider_popup_global_point(event))
                    event.accept()
                except Exception:
                    FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
            elif self.auxiliary_menu is not None and self.auxiliary_menu.isVisible():
                self.auxiliary_menu.hide()
            return
        if event.button() == QtCore.Qt.RightButton:
            item = self.hit_test(point) if self.point_in_bone_ui(point) else None
            if item is not None and item.get("kind") in ("ik", "aux_effector", "aux_pivot"):
                try:
                    self.show_effector_slider_popup(item, self.slider_popup_global_point(event))
                    self.refresh_bake_ui()
                    self.refresh_toolbar_ui()
                    self.update()
                    event.accept()
                except Exception:
                    FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
            elif self.point_in_bone_ui(point) and item is None:
                try:
                    self.close_effector_slider_popup()
                    select_items(self.all_picker_items(), False)
                    self.refresh_toolbar_ui()
                    self.refresh_slider_ui()
                    self.update()
                    event.accept()
                except Exception:
                    FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
            return
        if event.button() != QtCore.Qt.LeftButton or not self.point_in_bone_ui(point):
            return
        press_item = self.hit_test(point)
        if press_item is None:
            self.close_effector_slider_popup()
        self.drag_start = point
        self.drag_current = point
        self.drag_press_item = press_item
        self.drag_additive = self.shift_pressed(event)
        self.box_selecting = False

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or self.drag_start is None:
            return
        point = self.event_point(event)
        self.drag_current = point
        try:
            if self.box_selecting:
                rect = self.current_box()
                character = get_current_character()
                items = [
                    item for item in self.all_picker_items(character)
                    if rect.intersects(self.item_rect(item)) and get_model_for_item(character, item) is not None
                ]
                select_items(items, self.drag_additive)
            else:
                item = self.hit_test(point) or self.drag_press_item
                if item is not None:
                    select_item(item, self.drag_additive)
                elif self.point_in_bone_ui(point):
                    clear_model_selection()
                    evaluate_scene()
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.drag_start = None
        self.drag_current = None
        self.drag_press_item = None
        self.box_selecting = False
        self.refresh_bake_ui()
        self.refresh_toolbar_ui()
        self.refresh_slider_ui()
        self.update()


class FullBodyPickerWidgetHolder(FBWidgetHolder):
    def WidgetCreate(self, pWidgetParent):
        global _NATIVE_WIDGET
        parent = wrapInstance(pWidgetParent, QtWidgets.QWidget)
        self.native_widget = FullBodyPickerWidget(parent)
        _NATIVE_WIDGET = self.native_widget
        return getCppPointer(self.native_widget)[0]


def add_fill_region(tool, region_name, control):
    x = FBAddRegionParam(0, FBAttachType.kFBAttachLeft, "")
    y = FBAddRegionParam(0, FBAttachType.kFBAttachTop, "")
    w = FBAddRegionParam(0, FBAttachType.kFBAttachRight, "")
    h = FBAddRegionParam(0, FBAttachType.kFBAttachBottom, "")
    tool.AddRegion(region_name, region_name, x, y, w, h)
    tool.SetControl(region_name, control)


def dock_picker_at_viewer_right():
    widget = _NATIVE_WIDGET
    if widget is None:
        return False
    dock = widget.parentWidget()
    while dock is not None and not isinstance(dock, QtWidgets.QDockWidget):
        dock = dock.parentWidget()
    if dock is None:
        return False
    main_window = dock.parentWidget()
    while main_window is not None and not isinstance(main_window, QtWidgets.QMainWindow):
        main_window = main_window.parentWidget()
    if main_window is None:
        return False

    dock.setObjectName(DOCK_OBJECT_NAME)
    viewer_dock = None
    for candidate in main_window.findChildren(QtWidgets.QDockWidget):
        if candidate is not dock and candidate.windowTitle().strip().lower() == "viewer":
            viewer_dock = candidate
            break

    correctly_aligned = False
    if viewer_dock is not None and not dock.isFloating():
        viewer_rect = viewer_dock.geometry()
        dock_rect = dock.geometry()
        correctly_aligned = (
            dock_rect.x() >= viewer_rect.x() + viewer_rect.width() - 2
            and abs(dock_rect.y() - viewer_rect.y()) <= 3
            and abs(dock_rect.height() - viewer_rect.height()) <= 3
        )

    if not correctly_aligned:
        dock.setFloating(False)
        main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        if viewer_dock is not None:
            main_window.splitDockWidget(viewer_dock, dock, QtCore.Qt.Horizontal)

    if abs(dock.width() - DOCK_WIDTH) > 2:
        try:
            main_window.resizeDocks([dock], [DOCK_WIDTH + 1], QtCore.Qt.Horizontal)
        except Exception:
            pass
    dock.show()
    return True


def picker_dock_context():
    widget = _NATIVE_WIDGET
    if widget is None:
        return None, None
    dock = widget.parentWidget()
    while dock is not None and not isinstance(dock, QtWidgets.QDockWidget):
        dock = dock.parentWidget()
    if dock is None:
        return None, None
    main_window = dock.parentWidget()
    while main_window is not None and not isinstance(main_window, QtWidgets.QMainWindow):
        main_window = main_window.parentWidget()
    return dock, main_window


def dock_layout_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DOCK_LAYOUT_FILENAME)


def dock_reference_identity(dock):
    return {
        "object_name": str(dock.objectName() or ""),
        "title": str(dock.windowTitle() or ""),
    }


def adjacent_dock_reference(main_window, picker_dock):
    picker_rect = picker_dock.geometry()
    best = None
    for candidate in main_window.findChildren(QtWidgets.QDockWidget):
        if candidate is picker_dock or not candidate.isVisible() or candidate.isFloating():
            continue
        candidate_rect = candidate.geometry()
        vertical_overlap = max(
            0,
            min(picker_rect.bottom(), candidate_rect.bottom()) - max(picker_rect.top(), candidate_rect.top()) + 1,
        )
        horizontal_overlap = max(
            0,
            min(picker_rect.right(), candidate_rect.right()) - max(picker_rect.left(), candidate_rect.left()) + 1,
        )
        relations = []
        if vertical_overlap > 0:
            if picker_rect.left() >= candidate_rect.right():
                relations.append((picker_rect.left() - candidate_rect.right(), -vertical_overlap, "right"))
            if candidate_rect.left() >= picker_rect.right():
                relations.append((candidate_rect.left() - picker_rect.right(), -vertical_overlap, "left"))
        if horizontal_overlap > 0:
            if picker_rect.top() >= candidate_rect.bottom():
                relations.append((picker_rect.top() - candidate_rect.bottom(), -horizontal_overlap, "bottom"))
            if candidate_rect.top() >= picker_rect.bottom():
                relations.append((candidate_rect.top() - picker_rect.bottom(), -horizontal_overlap, "top"))
        for gap, negative_overlap, relation in relations:
            score = (gap, negative_overlap)
            if best is None or score < best[0]:
                best = (score, candidate, relation)
    if best is None:
        return None, None
    return best[1], best[2]


def save_current_picker_dock_layout():
    picker_dock, main_window = picker_dock_context()
    if picker_dock is None or main_window is None:
        raise RuntimeError("The full-body picker is not open.")
    if picker_dock.isFloating():
        raise RuntimeError("Dock the full-body picker before saving its position.")

    reference = None
    relation = None
    tabified = main_window.tabifiedDockWidgets(picker_dock)
    if tabified:
        reference = tabified[0]
        relation = "tab"
    else:
        reference, relation = adjacent_dock_reference(main_window, picker_dock)
    if reference is None or relation is None:
        raise RuntimeError("Could not determine the picker's dock relationship.")

    payload = {
        "version": 1,
        "reference": dock_reference_identity(reference),
        "relation": relation,
        "width": int(picker_dock.width()),
        "height": int(picker_dock.height()),
    }
    path = dock_layout_path()
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
    return path


def load_picker_dock_layout():
    path = dock_layout_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if int(payload.get("version", 0)) != 1:
            return None
        return payload
    except Exception:
        return None


def find_saved_reference_dock(main_window, identity):
    object_name = str((identity or {}).get("object_name", ""))
    title = str((identity or {}).get("title", ""))
    candidates = main_window.findChildren(QtWidgets.QDockWidget)
    if object_name:
        for candidate in candidates:
            if candidate.objectName() == object_name:
                return candidate
    if title:
        for candidate in candidates:
            if candidate.windowTitle() == title:
                return candidate
    return None


def dock_relation_matches(picker_dock, reference, relation):
    if picker_dock.isFloating():
        return False
    picker_rect = picker_dock.geometry()
    reference_rect = reference.geometry()
    if relation == "right":
        return picker_rect.left() >= reference_rect.right() and abs(picker_rect.top() - reference_rect.top()) <= 3
    if relation == "left":
        return reference_rect.left() >= picker_rect.right() and abs(picker_rect.top() - reference_rect.top()) <= 3
    if relation == "bottom":
        return picker_rect.top() >= reference_rect.bottom() and abs(picker_rect.left() - reference_rect.left()) <= 3
    if relation == "top":
        return reference_rect.top() >= picker_rect.bottom() and abs(picker_rect.left() - reference_rect.left()) <= 3
    return False


def restore_picker_dock_layout():
    layout = load_picker_dock_layout()
    if not layout:
        return dock_picker_at_viewer_right()
    picker_dock, main_window = picker_dock_context()
    if picker_dock is None or main_window is None:
        return False
    reference = find_saved_reference_dock(main_window, layout.get("reference"))
    relation = str(layout.get("relation", ""))
    if reference is None or relation not in ("left", "right", "top", "bottom", "tab"):
        return dock_picker_at_viewer_right()

    picker_dock.setObjectName(DOCK_OBJECT_NAME)
    picker_dock.setFloating(False)
    if relation == "tab":
        if picker_dock not in main_window.tabifiedDockWidgets(reference):
            main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, picker_dock)
            main_window.tabifyDockWidget(reference, picker_dock)
        picker_dock.raise_()
    elif not dock_relation_matches(picker_dock, reference, relation):
        main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, picker_dock)
        orientation = QtCore.Qt.Horizontal if relation in ("left", "right") else QtCore.Qt.Vertical
        if relation in ("right", "bottom"):
            main_window.splitDockWidget(reference, picker_dock, orientation)
        else:
            main_window.splitDockWidget(picker_dock, reference, orientation)

    target = int(layout.get("width", DOCK_WIDTH)) if relation in ("left", "right", "tab") else int(layout.get("height", 519))
    orientation = QtCore.Qt.Horizontal if relation in ("left", "right", "tab") else QtCore.Qt.Vertical
    try:
        main_window.resizeDocks([picker_dock], [max(50, target + 1)], orientation)
    except Exception:
        pass
    picker_dock.show()
    return True


def create_tool():
    global _TOOL
    picker_data()
    remove_custom_selection_keying_groups()
    _TOOL = FBCreateUniqueTool(TOOL_NAME)
    _TOOL.StartSizeX = 297
    _TOOL.StartSizeY = 590
    holder = FullBodyPickerWidgetHolder()
    add_fill_region(_TOOL, "main", holder)
    ShowTool(_TOOL)
    restore_picker_dock_layout()
    QtCore.QTimer.singleShot(0, restore_picker_dock_layout)
    QtCore.QTimer.singleShot(250, restore_picker_dock_layout)
    QtCore.QTimer.singleShot(1000, restore_picker_dock_layout)


def run_with_error_dialog():
    try:
        create_tool()
    except Exception:
        FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")


run_with_error_dialog()
