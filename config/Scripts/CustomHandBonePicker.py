from pyfbsdk import *
from pyfbsdk_additions import *
import ctypes
import os
import tempfile
import traceback

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import getCppPointer, wrapInstance
except Exception:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import getCppPointer, wrapInstance


TOOL_NAME = "Custom Hand Bone Picker"

HAND_SIDES = (
    ("Left", "L"),
    ("Right", "R"),
)

FINGER_ROWS = (
    ("Thumb", "Thumb"),
    ("Index", "Index"),
    ("Middle", "Middle"),
    ("Ring", "Ring"),
    ("Pinky", "Pinky"),
    ("Extra", "ExtraFinger"),
)

FINGER_SEGMENTS = (
    ("In", "In"),
    ("A", "A"),
    ("B", "B"),
    ("C", "C"),
    ("D", "D"),
)

BACKGROUND_IMAGE_RELATIVE_PATH = os.path.join("custom", "icons", "Hands_UI.png")
BACKGROUND_IMAGE_FALLBACK_PATH = r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts\custom\icons\Hands_UI.png"
CHARACTER_CONTROLS_IMAGE_DIR = r"C:\Program Files\Autodesk\MotionBuilder 2026\bin\system\CharacterControls\DefaultImages"

MARGIN = 12
TITLE_TOP = 6
BACKGROUND_LEFT = 12
BACKGROUND_TOP = 30
BACKGROUND_WIDTH = 495
BACKGROUND_HEIGHT = 379
STATUS_TOP = BACKGROUND_TOP + BACKGROUND_HEIGHT + 8
TOOL_WIDTH = BACKGROUND_LEFT + BACKGROUND_WIDTH + MARGIN
TOOL_HEIGHT = STATUS_TOP + 38

FK_LINE_PADDING = 8
FK_LINE_STROKE_WIDTH = 9
IK_BUTTON_SIZE = 24
BOX_SELECT_DRAG_THRESHOLD = 5
BOX_SELECT_FK_PADDING = 8
BOX_SELECT_IK_PADDING = 2
MIN_TOOL_WIDTH = 140
MIN_TOOL_HEIGHT = 120

_TOOL = None
_BUTTONS = {}
_BUTTON_ITEMS = {}
_LABELS = []
_UI_CONTROLS = []
_STATUS_LABEL = None
_CALLBACKS = []
_SELECTION_KEYING_GROUP = None
_ASSET_FILES = []
_BACKGROUND_IMAGE_CONTROL = None
_LAST_UI_KEYING_MODE = None

SELECTION_KEYING_GROUP_NAME = "CustomHandPickerSelectionTRS"
SELECTION_KEYING_PROPERTY_NAMES = (
    "Translation (Lcl)",
    "Rotation (Lcl)",
    "Scaling (Lcl)",
)


def get_side_prefix(side_name):
    return "Left" if side_name == "Left" else "Right"


def finger_node_name(side_name, finger_token, segment_token):
    return "kFB%s%s%sNodeId" % (get_side_prefix(side_name), finger_token, segment_token)


def body_node_name(side_name, token):
    return "kFB%s%sNodeId" % (get_side_prefix(side_name), token)


def effector_name(side_name, token):
    return "kFB%s%sEffectorId" % (get_side_prefix(side_name), token)


def hand_effector_name(side_name, token):
    return "kFB%sHand%sEffectorId" % (get_side_prefix(side_name), token)


def mirror_point(point):
    x, y = point
    return (BACKGROUND_WIDTH - x, y)


LEFT_FK_SPECIAL_POINTS = {
    "Wrist": ((55, 328), (67, 286)),
    "Hand": ((71, 271), (79, 244)),
}

LEFT_IK_SPECIAL_POINTS = {
    "Wrist": (50, 342),
    "Hand": (67, 286),
}

LEFT_FK_FINGER_POINTS = {
    "Thumb": [(118, 326), (169, 300), (206, 266), (226, 244), (237, 234)],
    "Index": [(142, 204), (171, 156), (190, 123), (204, 98), (210, 84)],
    "Middle": [(111, 188), (126, 142), (138, 104), (150, 64), (154, 48)],
    "Ring": [(81, 179), (87, 133), (92, 98), (95, 70), (96, 53)],
    "Pinky": [(49, 175), (50, 137), (51, 111), (52, 89), (52, 77)],
    "Extra": [(26, 175), (26, 137), (27, 110), (27, 89), (27, 77)],
}

LEFT_FK_FINGER_ROOT_POINTS = {
    "Thumb": (81, 340),
    "Index": (120, 262),
    "Middle": (96, 257),
    "Ring": (73, 253),
    "Pinky": (49, 253),
    "Extra": (30, 253),
}

LEFT_IK_FINGER_POINTS = {
    "Thumb": (237, 234),
    "Index": (210, 83),
    "Middle": (154, 48),
    "Ring": (96, 53),
    "Pinky": (52, 77),
    "Extra": (26, 77),
}


def point_for_side(side_name, point):
    if side_name == "Left":
        return point
    return mirror_point(point)


def segment_for_side(side_name, segment):
    start, end = segment
    return point_for_side(side_name, start), point_for_side(side_name, end)


def item_key(side_name, mode, label):
    safe_label = label.replace(" ", "_").replace("/", "_")
    return "%s_%s_%s" % (side_name, mode, safe_label)


def make_fk_item(side_name, label, node_name, segment):
    start, end = segment_for_side(side_name, segment)
    return {
        "key": item_key(side_name, "FK", label),
        "side": side_name,
        "mode": "FK",
        "visual": "fk",
        "label": label,
        "node_name": node_name,
        "target_type": "body_node",
        "line_start": start,
        "line_end": end,
        "center": ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5),
    }


def make_ik_item(side_name, label, effector_name_value, point):
    return {
        "key": item_key(side_name, "IK", label),
        "side": side_name,
        "mode": "IK",
        "visual": "ik",
        "label": label,
        "effector_name": effector_name_value,
        "target_type": "effector",
        "center": point_for_side(side_name, point),
    }


def build_items():
    items = []
    for side_name, short_name in HAND_SIDES:
        items.append(make_fk_item(side_name, "Wrist", body_node_name(side_name, "Wrist"), LEFT_FK_SPECIAL_POINTS["Wrist"]))
        items.append(make_fk_item(side_name, "Hand", body_node_name(side_name, "Hand"), LEFT_FK_SPECIAL_POINTS["Hand"]))
        items.append(make_ik_item(side_name, "Wrist", effector_name(side_name, "Wrist"), LEFT_IK_SPECIAL_POINTS["Wrist"]))
        items.append(make_ik_item(side_name, "Hand", effector_name(side_name, "Hand"), LEFT_IK_SPECIAL_POINTS["Hand"]))
        for finger_label, finger_token in FINGER_ROWS:
            finger_points = LEFT_FK_FINGER_POINTS[finger_label]
            previous_point = LEFT_FK_FINGER_ROOT_POINTS[finger_label]
            for segment_index, (segment_label, segment_token) in enumerate(FINGER_SEGMENTS):
                label = "%s %s" % (finger_label, segment_label)
                current_point = finger_points[segment_index]
                item = make_fk_item(
                    side_name,
                    label,
                    finger_node_name(side_name, finger_token, segment_token),
                    (previous_point, current_point),
                )
                item["finger_label"] = finger_label
                item["segment_label"] = segment_label
                items.append(item)
                previous_point = current_point
            ik_item = make_ik_item(
                side_name,
                "%s Tip" % finger_label,
                hand_effector_name(side_name, finger_token),
                LEFT_IK_FINGER_POINTS[finger_label],
            )
            ik_item["finger_label"] = finger_label
            items.append(ik_item)
    return items


HAND_ITEMS = build_items()


def get_script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def get_background_image_path():
    candidate = os.path.join(get_script_dir(), BACKGROUND_IMAGE_RELATIVE_PATH)
    if os.path.isfile(candidate):
        return candidate
    return BACKGROUND_IMAGE_FALLBACK_PATH


def write_text_file(path, text):
    with open(path, "w", encoding="utf-8") as output_file:
        output_file.write(text)


def get_character_controls_image(name):
    path = os.path.join(CHARACTER_CONTROLS_IMAGE_DIR, name)
    if os.path.isfile(path):
        return path
    return None


def fk_line_geometry(item):
    x1, y1 = item["line_start"]
    x2, y2 = item["line_end"]
    left = int(round(min(x1, x2) - FK_LINE_PADDING))
    top = int(round(min(y1, y2) - FK_LINE_PADDING))
    width = int(round(abs(x2 - x1) + (FK_LINE_PADDING * 2)))
    height = int(round(abs(y2 - y1) + (FK_LINE_PADDING * 2)))
    return left, top, max(width, 1), max(height, 1), x1 - left, y1 - top, x2 - left, y2 - top


def fk_line_svg(item, selected=False):
    left, top, width, height, x1, y1, x2, y2 = fk_line_geometry(item)
    if selected:
        return """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%(width)d\" height=\"%(height)d\" viewBox=\"0 0 %(width)d %(height)d\" fill=\"none\" style=\"background:transparent\">\n<rect x=\"0\" y=\"0\" width=\"%(width)d\" height=\"%(height)d\" fill=\"none\" fill-opacity=\"0\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#46E8F8\" stroke-width=\"12\" stroke-linecap=\"round\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#252525\" stroke-width=\"9\" stroke-linecap=\"round\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#8c8c8c\" stroke-width=\"6\" stroke-linecap=\"round\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#f0f0f0\" stroke-width=\"2\" stroke-linecap=\"round\" opacity=\"0.55\"/>\n</svg>\n""" % {
            "width": width,
            "height": height,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
        }
    return """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"%(width)d\" height=\"%(height)d\" viewBox=\"0 0 %(width)d %(height)d\" fill=\"none\" style=\"background:transparent\">\n<rect x=\"0\" y=\"0\" width=\"%(width)d\" height=\"%(height)d\" fill=\"none\" fill-opacity=\"0\"/>\n<defs>\n<linearGradient id=\"fk_bevel\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">\n<stop offset=\"0\" stop-color=\"#f3f3f3\"/>\n<stop offset=\"0.34\" stop-color=\"#9a9a9a\"/>\n<stop offset=\"0.72\" stop-color=\"#3f3f3f\"/>\n<stop offset=\"1\" stop-color=\"#bdbdbd\"/>\n</linearGradient>\n</defs>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#080808\" stroke-width=\"11\" stroke-linecap=\"round\" opacity=\"0.95\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"url(#fk_bevel)\" stroke-width=\"8\" stroke-linecap=\"round\"/>\n<line x1=\"%(x1).3f\" y1=\"%(y1).3f\" x2=\"%(x2).3f\" y2=\"%(y2).3f\" stroke=\"#ffffff\" stroke-width=\"2\" stroke-linecap=\"round\" opacity=\"0.42\"/>\n</svg>\n""" % {
        "width": width,
        "height": height,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }


def ensure_shape_assets():
    asset_dir = os.path.join(tempfile.gettempdir(), "Codex_CustomHandBonePicker")
    if not os.path.isdir(asset_dir):
        os.makedirs(asset_dir)

    assets = {}
    ik_off = get_character_controls_image("Effector.svg")
    ik_on = get_character_controls_image("Effector_sel.svg")
    if ik_off is None:
        ik_off = os.path.join(asset_dir, "ik_off.svg")
        write_text_file(ik_off, """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" style=\"background:transparent\">\n<rect x=\"0\" y=\"0\" width=\"24\" height=\"24\" fill=\"none\" fill-opacity=\"0\"/>\n<circle cx=\"12\" cy=\"12\" r=\"11.4\" fill=\"#606060\" stroke=\"black\"/>\n<circle cx=\"9\" cy=\"7\" r=\"4\" fill=\"#eeeeee\" opacity=\"0.55\"/>\n</svg>\n""")
    if ik_on is None:
        ik_on = os.path.join(asset_dir, "ik_on.svg")
        write_text_file(ik_on, """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" style=\"background:transparent\">\n<rect x=\"0\" y=\"0\" width=\"24\" height=\"24\" fill=\"none\" fill-opacity=\"0\"/>\n<circle cx=\"12\" cy=\"12\" r=\"10\" stroke=\"#46E8F8\" stroke-width=\"2.5\"/>\n<circle cx=\"12\" cy=\"12\" r=\"8\" stroke=\"#544C4B\" stroke-width=\"1.25\"/>\n</svg>\n""")
    assets["ik_off.svg"] = ik_off
    assets["ik_on.svg"] = ik_on

    for item in HAND_ITEMS:
        if item.get("visual") != "fk":
            continue
        off_name = item["key"] + "_off.svg"
        on_name = item["key"] + "_on.svg"
        off_path = os.path.join(asset_dir, off_name)
        on_path = os.path.join(asset_dir, on_name)
        write_text_file(off_path, fk_line_svg(item, False))
        write_text_file(on_path, fk_line_svg(item, True))
        assets[off_name] = off_path
        assets[on_name] = on_path
        if off_path not in _ASSET_FILES:
            _ASSET_FILES.append(off_path)
        if on_path not in _ASSET_FILES:
            _ASSET_FILES.append(on_path)
    return assets


def add_region(tool, region_name, control, left, top, width, height):
    x = FBAddRegionParam(left, FBAttachType.kFBAttachLeft, "")
    y = FBAddRegionParam(top, FBAttachType.kFBAttachTop, "")
    w = FBAddRegionParam(width, FBAttachType.kFBAttachNone, "")
    h = FBAddRegionParam(height, FBAttachType.kFBAttachNone, "")
    tool.AddRegion(region_name, region_name, x, y, w, h)
    tool.SetControl(region_name, control)
    _UI_CONTROLS.append(control)


def add_fill_region(tool, region_name, control, left=0, top=0, right=0, bottom=0):
    x = FBAddRegionParam(left, FBAttachType.kFBAttachLeft, "")
    y = FBAddRegionParam(top, FBAttachType.kFBAttachTop, "")
    w = FBAddRegionParam(right, FBAttachType.kFBAttachRight, "")
    h = FBAddRegionParam(bottom, FBAttachType.kFBAttachBottom, "")
    tool.AddRegion(region_name, region_name, x, y, w, h)
    tool.SetControl(region_name, control)
    _UI_CONTROLS.append(control)


def add_label(tool, region_name, caption, left, top, width, height, justify=FBTextJustify.kFBTextJustifyLeft):
    label = FBLabel()
    label.Caption = caption
    label.Justify = justify
    add_region(tool, region_name, label, left, top, width, height)
    _LABELS.append(label)
    return label


def set_hint(control, text):
    for attr_name in ("Hint", "CaptionHint", "ToolTip"):
        try:
            setattr(control, attr_name, text)
            return
        except Exception:
            pass


def set_enabled(control, enabled):
    for attr_name in ("Enabled", "Enable"):
        try:
            setattr(control, attr_name, bool(enabled))
            return
        except Exception:
            pass


def get_current_character():
    app = FBApplication()
    try:
        if app.CurrentCharacter is not None:
            return app.CurrentCharacter
    except Exception:
        pass

    characters = []
    try:
        for character in FBSystem().Scene.Characters:
            characters.append(character)
    except Exception:
        characters = []

    if len(characters) == 1:
        return characters[0]
    return None


def get_body_node_id(node_name):
    try:
        return getattr(FBBodyNodeId, node_name)
    except Exception:
        return None


def get_effector_id(effector_name_value):
    try:
        return getattr(FBEffectorId, effector_name_value)
    except Exception:
        return None


def get_character_model_for_node(character, node_name):
    node_id = get_body_node_id(node_name)
    if character is None or node_id is None:
        return None

    for method_name in ("GetCtrlRigModel", "GetModel", "GetGoalModel"):
        try:
            method = getattr(character, method_name)
        except Exception:
            continue

        try:
            model = method(node_id)
        except Exception:
            model = None

        if model is not None:
            return model

    return None


def get_character_effector_model(character, effector_name_value):
    effector_id = get_effector_id(effector_name_value)
    if character is None or effector_id is None:
        return None

    try:
        return character.GetEffectorModel(effector_id, FBEffectorSetID.FBEffectorSetDefault)
    except Exception:
        pass

    try:
        return character.GetEffectorModel(effector_id)
    except Exception:
        return None


def get_character_model_for_item(character, item):
    if item is None:
        return None
    if item.get("target_type") == "effector":
        return get_character_effector_model(character, item.get("effector_name"))
    return get_character_model_for_node(character, item.get("node_name"))


def is_item_available_for_character(character, item):
    return get_character_model_for_item(character, item) is not None


def get_item_model(item):
    return get_character_model_for_item(get_current_character(), item)


def is_model_selected(model):
    try:
        return model is not None and bool(model.Selected)
    except Exception:
        return False


def make_model_transformable(model):
    if model is None:
        return
    try:
        model.Transformable = True
    except Exception:
        pass


def hard_select_model(model):
    if model is None:
        return
    try:
        model.HardSelect()
    except Exception:
        pass


def clear_model_selection():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, False)
    for selected_model in selected_models:
        selected_model.Selected = False


def evaluate_scene():
    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass


def make_model_last_selected(model):
    if model is None:
        return

    make_model_transformable(model)

    try:
        FBSetLastSelectedModel(model)
    except Exception:
        try:
            model.Selected = True
        except Exception:
            pass

    hard_select_model(model)


def refresh_model_selection_for_character_controls(model):
    if model is None:
        return

    try:
        model.Selected = False
        evaluate_scene()
    except Exception:
        pass

    try:
        model.Selected = True
        make_model_transformable(model)
        FBSetLastSelectedModel(model)
    except Exception:
        try:
            model.Selected = True
        except Exception:
            pass

    hard_select_model(model)


def get_selection_keying_group():
    global _SELECTION_KEYING_GROUP
    if _SELECTION_KEYING_GROUP is None:
        _SELECTION_KEYING_GROUP = find_existing_selection_keying_group()
    return _SELECTION_KEYING_GROUP


def component_matches_target_name(component, target_name):
    for attr_name in ("Name", "LongName"):
        try:
            value = getattr(component, attr_name)
            if value == target_name or str(value).endswith("::" + target_name):
                return True
        except Exception:
            pass
    return False


def find_existing_selection_keying_group():
    try:
        for component in FBSystem().Scene.Components:
            try:
                if not component_matches_target_name(component, SELECTION_KEYING_GROUP_NAME):
                    continue
                if hasattr(component, "AddProperty") and hasattr(component, "ClearAllItems"):
                    return component
            except Exception:
                pass
    except Exception:
        pass
    return None


def clear_selection_keying_group_items(group):
    if group is None:
        return
    try:
        group.ClearAllItems()
        return
    except Exception:
        pass
    for method_name in ("RemoveAllProperties", "RemoveAllObjectDependency", "RemoveAllSubKeyingGroup"):
        try:
            getattr(group, method_name)()
        except Exception:
            pass


def iter_model_selection_keying_properties(model):
    if model is None:
        return
    for prop_name in SELECTION_KEYING_PROPERTY_NAMES:
        try:
            prop = model.PropertyList.Find(prop_name)
        except Exception:
            prop = None
        if prop is None:
            continue
        try:
            prop.SetAnimated(True)
        except Exception:
            pass
        yield prop


def activate_selection_keying_group(model):
    deactivate_selection_keying_group(True)


def model_identity(model):
    if model is None:
        return ""
    for attr_name in ("LongName", "Name"):
        try:
            value = getattr(model, attr_name)
            if value:
                return str(value)
        except Exception:
            pass
    return str(model)


def unique_models(models):
    unique = []
    seen = set()
    for model in models:
        if model is None:
            continue
        key = model_identity(model)
        if key in seen:
            continue
        seen.add(key)
        unique.append(model)
    return unique


def get_selected_picker_models(character):
    selected_models = []
    for item in HAND_ITEMS:
        model = get_character_model_for_item(character, item)
        if is_model_selected(model):
            selected_models.append(model)
    return unique_models(selected_models)


def activate_selection_keying_group_for_models(models):
    deactivate_selection_keying_group(True)


def deactivate_selection_keying_group(clear_items=False):
    global _SELECTION_KEYING_GROUP
    if _SELECTION_KEYING_GROUP is None:
        _SELECTION_KEYING_GROUP = find_existing_selection_keying_group()
    if _SELECTION_KEYING_GROUP is None:
        return
    try:
        _SELECTION_KEYING_GROUP.SetActive(False)
    except Exception:
        pass
    if clear_items:
        clear_selection_keying_group_items(_SELECTION_KEYING_GROUP)


def remove_custom_selection_keying_groups():
    global _SELECTION_KEYING_GROUP
    groups = []
    try:
        for component in FBSystem().Scene.Components:
            try:
                if component_matches_target_name(component, SELECTION_KEYING_GROUP_NAME):
                    groups.append(component)
            except Exception:
                pass
    except Exception:
        groups = []

    removed_count = 0
    for group in groups:
        try:
            group.SetActive(False)
        except Exception:
            pass
        clear_selection_keying_group_items(group)
        try:
            group.FBDelete()
            removed_count += 1
        except Exception:
            pass

    _SELECTION_KEYING_GROUP = None
    return removed_count


def keying_mode_candidates():
    candidates = []
    for attr_name in (
        "kFBCharacterKeyingFullBody",
        "kFBCharacterKeyingFullBodyNoPull",
        "kFBCharacterKeyingBodyPart",
        "kFBCharacterKeyingSelection",
    ):
        try:
            candidates.append(getattr(FBCharacterKeyingMode, attr_name))
        except Exception:
            pass
    return candidates


def is_full_body_keying_mode(keying_mode):
    try:
        if keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingFullBody:
            return True
    except Exception:
        pass
    try:
        if keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingFullBodyNoPull:
            return True
    except Exception:
        pass
    return False


def is_body_part_keying_mode(keying_mode):
    try:
        return keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingBodyPart
    except Exception:
        return False


def is_selection_keying_mode(keying_mode):
    try:
        return keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingSelection
    except Exception:
        return False


def normalize_character_keying_mode(keying_mode):
    if is_full_body_keying_mode(keying_mode):
        return keying_mode
    if is_body_part_keying_mode(keying_mode):
        return FBCharacterKeyingMode.kFBCharacterKeyingBodyPart
    if is_selection_keying_mode(keying_mode):
        return FBCharacterKeyingMode.kFBCharacterKeyingSelection
    return None


def qt_text_parts(obj):
    parts = []
    for attr_name in ("text", "toolTip", "statusTip", "whatsThis", "accessibleName", "accessibleDescription", "objectName", "windowTitle"):
        try:
            attr = getattr(obj, attr_name)
        except Exception:
            attr = None
        if attr is None:
            continue
        try:
            value = attr()
        except Exception:
            value = attr
        if value:
            parts.append(str(value))
    return parts


def qt_text_blob(obj):
    return " ".join(qt_text_parts(obj)).lower()


def qt_ancestor_text_blob(widget):
    parts = []
    current = widget
    guard = 0
    while current is not None and guard < 32:
        parts.extend(qt_text_parts(current))
        try:
            current = current.parentWidget()
        except Exception:
            current = None
        guard += 1
    return " ".join(parts).lower()


def text_matches_keying_mode(text_blob, keying_mode):
    if is_full_body_keying_mode(keying_mode):
        return "full body" in text_blob or "fullbody" in text_blob
    if is_body_part_keying_mode(keying_mode):
        return "body part" in text_blob or "bodypart" in text_blob
    if is_selection_keying_mode(keying_mode):
        if "selected properties" in text_blob:
            return False
        return "selection" in text_blob
    return False


def read_character_controls_keying_mode_from_ui():
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    if app is None:
        return None

    try:
        widgets = list(app.allWidgets())
    except Exception:
        try:
            widgets = list(QtWidgets.QApplication.allWidgets())
        except Exception:
            widgets = []

    for widget in widgets:
        try:
            if not isinstance(widget, QtWidgets.QAbstractButton):
                continue
            if not widget.isChecked():
                continue
        except Exception:
            continue

        ancestor_text = qt_ancestor_text_blob(widget)
        if "character controls" not in ancestor_text and "charactercontrols" not in ancestor_text:
            continue

        own_text = qt_text_blob(widget)
        for mode in keying_mode_candidates():
            if text_matches_keying_mode(own_text, mode):
                return normalize_character_keying_mode(mode)

    return None


def refresh_cached_character_controls_keying_mode():
    global _LAST_UI_KEYING_MODE
    keying_mode = normalize_character_keying_mode(read_character_controls_keying_mode_from_ui())
    if keying_mode is not None:
        _LAST_UI_KEYING_MODE = keying_mode
    return keying_mode


def read_global_character_keying_mode():
    try:
        return FBGetCharactersKeyingMode()
    except Exception:
        return None


def read_character_keying_mode(character=None):
    try:
        current_character = FBApplication().CurrentCharacter
    except Exception:
        current_character = None

    for candidate in (current_character, character):
        if candidate is None:
            continue
        try:
            return candidate.KeyingMode
        except Exception:
            pass

    return None


def get_character_controls_keying_mode(character=None):
    ui_keying_mode = refresh_cached_character_controls_keying_mode()
    if ui_keying_mode is not None:
        return ui_keying_mode
    if _LAST_UI_KEYING_MODE is not None:
        return _LAST_UI_KEYING_MODE

    global_keying_mode = normalize_character_keying_mode(read_global_character_keying_mode())
    if global_keying_mode is not None:
        return global_keying_mode

    character_keying_mode = normalize_character_keying_mode(read_character_keying_mode(character))
    if character_keying_mode is not None:
        return character_keying_mode

    return None


def apply_character_keying_mode(character, keying_mode):
    if character is None or keying_mode is None:
        return
    try:
        character.KeyingMode = keying_mode
    except Exception:
        pass


def keying_mode_name(keying_mode):
    if is_full_body_keying_mode(keying_mode):
        try:
            if keying_mode == FBCharacterKeyingMode.kFBCharacterKeyingFullBodyNoPull:
                return "FullBodyNoPull"
        except Exception:
            pass
        return "FullBody"
    if is_body_part_keying_mode(keying_mode):
        return "BodyPart"
    if is_selection_keying_mode(keying_mode):
        return "Selection"
    if keying_mode is None:
        return "None"
    try:
        return str(keying_mode)
    except Exception:
        return "Unknown"


def sync_character_keying_after_picker_selection(character, fallback_model=None, keying_mode=None):
    if keying_mode is None:
        keying_mode = get_character_controls_keying_mode(character)

    remove_custom_selection_keying_groups()
    apply_character_keying_mode(character, keying_mode)


def event_value_is_shift(value):
    if value is None:
        return False

    try:
        if value == FBInputModifier.kFBKeyShift:
            return True
    except Exception:
        pass

    try:
        shift_value = int(FBInputModifier.kFBKeyShift)
        input_value = int(value)
        if input_value & shift_value:
            return True
    except Exception:
        pass

    try:
        return "shift" in str(value).lower()
    except Exception:
        return False


def is_shift_pressed():
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
    except Exception:
        return False


def event_has_shift(event):
    if is_shift_pressed():
        return True

    for attr_name in ("Modifier", "Modifiers", "KeyModifier", "KeyModifiers", "InputModifier", "Key"):
        try:
            if event_value_is_shift(getattr(event, attr_name)):
                return True
        except Exception:
            pass

    return False


def select_item(item, additive=False):
    character = get_current_character()
    if character is None:
        FBMessageBox(TOOL_NAME, "No current character found.", "OK")
        refresh_button_states()
        return

    model = get_character_model_for_item(character, item)
    if model is None:
        FBMessageBox(TOOL_NAME, "Could not find Character Controls model:\n%s %s %s" % (item["side"], item["mode"], item["label"]), "OK")
        refresh_button_states()
        return

    keying_mode = get_character_controls_keying_mode(character)
    try:
        FBApplication().CurrentCharacter = character
    except Exception:
        pass
    make_model_transformable(model)

    if additive:
        should_select = not is_model_selected(model)
        model.Selected = should_select
        if should_select:
            make_model_last_selected(model)
            refresh_model_selection_for_character_controls(model)
    else:
        clear_model_selection()
        model.Selected = True
        make_model_last_selected(model)
        refresh_model_selection_for_character_controls(model)

    sync_character_keying_after_picker_selection(character, model, keying_mode)

    refresh_button_states()
    evaluate_scene()


def select_items(items, additive=False):
    character = get_current_character()
    if character is None:
        FBMessageBox(TOOL_NAME, "No current character found.", "OK")
        refresh_button_states()
        return

    keying_mode = get_character_controls_keying_mode(character)
    models = []
    for item in items:
        model = get_character_model_for_item(character, item)
        if model is not None:
            models.append(model)

    models = unique_models(models)
    if not models:
        if not additive:
            clear_model_selection()
            sync_character_keying_after_picker_selection(character, None, keying_mode)
        refresh_button_states()
        evaluate_scene()
        return

    try:
        FBApplication().CurrentCharacter = character
    except Exception:
        pass

    if not additive:
        clear_model_selection()

    for model in models:
        make_model_transformable(model)
        try:
            model.Selected = True
        except Exception:
            pass

    last_model = models[-1]
    make_model_last_selected(last_model)
    refresh_model_selection_for_character_controls(last_model)
    sync_character_keying_after_picker_selection(character, last_model, keying_mode)

    refresh_button_states()
    evaluate_scene()


def make_select_callback(item):
    def callback(control, event):
        try:
            select_item(item, event_has_shift(event))
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
    return callback


def get_character_display_name(character):
    if character is None:
        return "None"
    try:
        return character.Name
    except Exception:
        return str(character)


def refresh_button_states():
    character = get_current_character()

    if _STATUS_LABEL is not None:
        _STATUS_LABEL.Caption = "Character: " + get_character_display_name(character)

    for key, button in _BUTTONS.items():
        item = _BUTTON_ITEMS[key]
        model = get_character_model_for_item(character, item)
        button.State = 1 if is_model_selected(model) else 0
        set_enabled(button, model is not None)
        if model is not None:
            set_hint(button, "%s %s %s" % (item["side"], item["mode"], item["label"]))
        else:
            set_hint(button, "%s %s %s missing" % (item["side"], item["mode"], item["label"]))


def idle_callback(control, event):
    try:
        refresh_button_states()
    except Exception:
        pass


def button_geometry_for_item(item):
    if item.get("visual") == "ik":
        center_x, center_y = item["center"]
        return (
            int(round(BACKGROUND_LEFT + center_x - (IK_BUTTON_SIZE // 2))),
            int(round(BACKGROUND_TOP + center_y - (IK_BUTTON_SIZE // 2))),
            IK_BUTTON_SIZE,
            IK_BUTTON_SIZE,
        )
    left, top, width, height, _x1, _y1, _x2, _y2 = fk_line_geometry(item)
    return BACKGROUND_LEFT + left, BACKGROUND_TOP + top, width, height


def button_images_for_item(item, assets):
    if item.get("visual") == "ik":
        return assets["ik_off.svg"], assets["ik_on.svg"]
    return assets[item["key"] + "_off.svg"], assets[item["key"] + "_on.svg"]


def set_button_character_controls_look(button):
    for attr_name, value in (
        ("UseTransparentBackground", True),
        ("Transparent", True),
        ("Border", False),
    ):
        try:
            setattr(button, attr_name, value)
        except Exception:
            pass
    try:
        button.Look = FBButtonLook.kFBLookAlphaBackground
    except Exception:
        pass
    try:
        button.Look = FBButtonLook.kFBLookFlat
    except Exception:
        pass


def add_bone_button(tool, item, assets):
    left, top, width, height = button_geometry_for_item(item)

    button = FBButton()
    button.Caption = ""
    button.Style = FBButtonStyle.kFBBitmap2States
    button.Justify = FBTextJustify.kFBTextJustifyCenter
    button.State = 0
    up_image, down_image = button_images_for_item(item, assets)
    button.SetImageFileNames(up_image, down_image)
    set_button_character_controls_look(button)
    set_hint(button, "%s %s %s" % (item["side"], item["mode"], item["label"]))

    callback = make_select_callback(item)
    button.OnClick.Add(callback)

    region_name = "btn_" + item["key"]
    add_region(tool, region_name, button, left, top, width, height)
    _BUTTONS[item["key"]] = button
    _BUTTON_ITEMS[item["key"]] = item
    _CALLBACKS.append(callback)
    return button


def add_background_image(tool):
    global _BACKGROUND_IMAGE_CONTROL
    image_path = get_background_image_path()
    if not os.path.isfile(image_path):
        return None

    image = FBImageContainer()
    image.Filename = image_path
    try:
        image.UseTransparentBackground = False
    except Exception:
        pass
    add_region(tool, "hands_background", image, BACKGROUND_LEFT, BACKGROUND_TOP, BACKGROUND_WIDTH, BACKGROUND_HEIGHT)
    _BACKGROUND_IMAGE_CONTROL = image
    return image


def add_overlay_labels(tool):
    add_label(
        tool,
        "title_left",
        "Left Hand",
        BACKGROUND_LEFT,
        TITLE_TOP,
        BACKGROUND_WIDTH // 2,
        22,
        FBTextJustify.kFBTextJustifyCenter,
    )
    add_label(
        tool,
        "title_right",
        "Right Hand",
        BACKGROUND_LEFT + (BACKGROUND_WIDTH // 2),
        TITLE_TOP,
        BACKGROUND_WIDTH // 2,
        22,
        FBTextJustify.kFBTextJustifyCenter,
    )
    add_label(tool, "legend_fk", "FK", BACKGROUND_LEFT + 8, BACKGROUND_TOP + 8, 28, 18, FBTextJustify.kFBTextJustifyCenter)
    add_label(tool, "legend_ik", "IK", BACKGROUND_LEFT + 42, BACKGROUND_TOP + 8, 28, 18, FBTextJustify.kFBTextJustifyCenter)


def add_hand_buttons(tool, assets):
    for item in HAND_ITEMS:
        add_bone_button(tool, item, assets)


def distance_to_segment(point_x, point_y, start, end):
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length_squared = (dx * dx) + (dy * dy)
    if length_squared <= 0.0001:
        return ((point_x - x1) ** 2 + (point_y - y1) ** 2) ** 0.5

    t = ((point_x - x1) * dx + (point_y - y1) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    nearest_x = x1 + (t * dx)
    nearest_y = y1 + (t * dy)
    return ((point_x - nearest_x) ** 2 + (point_y - nearest_y) ** 2) ** 0.5


class HandPickerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setMinimumSize(MIN_TOOL_WIDTH, MIN_TOOL_HEIGHT)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.background_pixmap = QtGui.QPixmap(get_background_image_path())
        self.hover_item = None
        self.drag_start_point = None
        self.drag_current_point = None
        self.drag_press_item = None
        self.drag_additive = False
        self.box_selecting = False
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.timeout.connect(self.update)
        self.refresh_timer.start(150)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor(18, 18, 18))
        painter.save()
        self.apply_logical_transform(painter)
        self.draw_titles(painter)
        self.draw_background(painter)
        self.draw_fk_items(painter)
        self.draw_ik_items(painter)
        self.draw_box_selection(painter)
        self.draw_status(painter)
        painter.restore()
        painter.end()

    def logical_scale(self):
        width = max(1.0, float(self.width()))
        height = max(1.0, float(self.height()))
        return max(0.01, min(width / float(TOOL_WIDTH), height / float(TOOL_HEIGHT)))

    def logical_origin(self):
        scale = self.logical_scale()
        origin_x = (float(self.width()) - (float(TOOL_WIDTH) * scale)) * 0.5
        origin_y = (float(self.height()) - (float(TOOL_HEIGHT) * scale)) * 0.5
        return origin_x, origin_y

    def apply_logical_transform(self, painter):
        scale = self.logical_scale()
        origin_x, origin_y = self.logical_origin()
        painter.translate(origin_x, origin_y)
        painter.scale(scale, scale)

    def screen_to_logical_point(self, point):
        scale = self.logical_scale()
        origin_x, origin_y = self.logical_origin()
        return QtCore.QPointF((point.x() - origin_x) / scale, (point.y() - origin_y) / scale)

    def draw_titles(self, painter):
        painter.setPen(QtGui.QColor(235, 235, 235))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(BACKGROUND_LEFT, TITLE_TOP, BACKGROUND_WIDTH // 2, 20), QtCore.Qt.AlignCenter, "Left Hand")
        painter.drawText(QtCore.QRect(BACKGROUND_LEFT + (BACKGROUND_WIDTH // 2), TITLE_TOP, BACKGROUND_WIDTH // 2, 20), QtCore.Qt.AlignCenter, "Right Hand")
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QtCore.QRect(BACKGROUND_LEFT + 8, BACKGROUND_TOP + 6, 30, 18), QtCore.Qt.AlignCenter, "FK")
        painter.drawText(QtCore.QRect(BACKGROUND_LEFT + 42, BACKGROUND_TOP + 6, 30, 18), QtCore.Qt.AlignCenter, "IK")

    def draw_background(self, painter):
        target = QtCore.QRect(BACKGROUND_LEFT, BACKGROUND_TOP, BACKGROUND_WIDTH, BACKGROUND_HEIGHT)
        if not self.background_pixmap.isNull():
            painter.drawPixmap(target, self.background_pixmap)
        else:
            painter.fillRect(target, QtGui.QColor(8, 8, 8))

    def iter_visible_items(self, visual=None):
        character = get_current_character()
        if character is None:
            return
        for item in HAND_ITEMS:
            if visual is not None and item.get("visual") != visual:
                continue
            model = get_character_model_for_item(character, item)
            if model is None:
                continue
            yield item, model

    def item_is_selected(self, item):
        try:
            model = get_character_model_for_item(get_current_character(), item)
            return is_model_selected(model)
        except Exception:
            return False

    def draw_fk_items(self, painter):
        for item, model in self.iter_visible_items("fk"):
            selected = is_model_selected(model)
            hovered = self.hover_item is item or self.item_is_box_previewed(item)
            self.draw_fk_line(painter, item, selected, hovered)

    def draw_fk_line(self, painter, item, selected=False, hovered=False):
        x1, y1 = item["line_start"]
        x2, y2 = item["line_end"]
        start = QtCore.QPointF(BACKGROUND_LEFT + x1, BACKGROUND_TOP + y1)
        end = QtCore.QPointF(BACKGROUND_LEFT + x2, BACKGROUND_TOP + y2)

        if selected or hovered:
            pen = QtGui.QPen(QtGui.QColor(70, 232, 248), 13, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(start, end)

        painter.setPen(QtGui.QPen(QtGui.QColor(8, 8, 8), 11, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(start, end)
        painter.setPen(QtGui.QPen(QtGui.QColor(82, 82, 82), 9, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(start, end)
        painter.setPen(QtGui.QPen(QtGui.QColor(164, 164, 164), 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(start, end)
        painter.setPen(QtGui.QPen(QtGui.QColor(238, 238, 238, 145), 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(start, end)

    def draw_ik_items(self, painter):
        for item, model in self.iter_visible_items("ik"):
            selected = is_model_selected(model)
            hovered = self.hover_item is item or self.item_is_box_previewed(item)
            self.draw_ik_circle(painter, item, selected, hovered)

    def draw_ik_circle(self, painter, item, selected=False, hovered=False):
        center_x, center_y = item["center"]
        center = QtCore.QPointF(BACKGROUND_LEFT + center_x, BACKGROUND_TOP + center_y)
        radius = IK_BUTTON_SIZE * 0.48
        gradient = QtGui.QRadialGradient(center.x() - 3, center.y() - 4, radius * 1.55)
        gradient.setColorAt(0.0, QtGui.QColor(250, 250, 250))
        gradient.setColorAt(0.62, QtGui.QColor(82, 82, 82))
        gradient.setColorAt(1.0, QtGui.QColor(160, 160, 160))
        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 1.2))
        painter.drawEllipse(center, radius, radius)

        if selected or hovered:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(70, 232, 248), 2.5))
            painter.drawEllipse(center, radius - 1.5, radius - 1.5)
            painter.setPen(QtGui.QPen(QtGui.QColor(84, 76, 75), 1.25))
            painter.drawEllipse(center, radius - 4.0, radius - 4.0)

    def draw_status(self, painter):
        painter.setPen(QtGui.QColor(220, 220, 220))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        text = "Character: " + get_character_display_name(get_current_character())
        painter.drawText(QtCore.QRect(MARGIN, STATUS_TOP, TOOL_WIDTH - (MARGIN * 2), 22), QtCore.Qt.AlignCenter, text)

    def draw_box_selection(self, painter):
        rect = self.current_selection_rect()
        if rect is None or not self.box_selecting:
            return
        painter.setBrush(QtGui.QColor(70, 232, 248, 34))
        painter.setPen(QtGui.QPen(QtGui.QColor(70, 232, 248), 1.4, QtCore.Qt.DashLine))
        painter.drawRect(rect)

    def mouseMoveEvent(self, event):
        point = self.event_point(event)
        if self.drag_start_point is not None and self.left_button_is_down(event):
            self.drag_current_point = point
            if not self.box_selecting and self.drag_distance(point) >= self.logical_drag_threshold():
                self.box_selecting = True
                self.hover_item = None
            if self.box_selecting:
                self.update()
                return

        item = self.hit_test(point.x(), point.y())
        if item is not self.hover_item:
            self.hover_item = item
            self.update()

    def leaveEvent(self, event):
        if self.drag_start_point is not None:
            return
        self.hover_item = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        point = self.event_point(event)
        self.drag_start_point = point
        self.drag_current_point = point
        self.drag_press_item = self.hit_test(point.x(), point.y())
        self.drag_additive = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        self.box_selecting = False
        self.hover_item = self.drag_press_item
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        point = self.event_point(event)
        press_item = self.drag_press_item
        additive = self.drag_additive or bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        box_selecting = self.box_selecting
        selection_rect = self.current_selection_rect()
        self.reset_drag_state()

        try:
            if box_selecting and selection_rect is not None:
                select_items(self.items_in_selection_rect(selection_rect), additive)
            else:
                item = self.hit_test(point.x(), point.y())
                if item is None:
                    item = press_item
                if item is not None:
                    select_item(item, additive)
        except Exception:
            FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        self.update()

    def reset_drag_state(self):
        self.drag_start_point = None
        self.drag_current_point = None
        self.drag_press_item = None
        self.drag_additive = False
        self.box_selecting = False

    def event_x(self, event):
        try:
            return event.position().x()
        except Exception:
            return event.x()

    def event_y(self, event):
        try:
            return event.position().y()
        except Exception:
            return event.y()

    def event_point(self, event):
        return self.screen_to_logical_point(QtCore.QPointF(self.event_x(event), self.event_y(event)))

    def left_button_is_down(self, event):
        try:
            return bool(event.buttons() & QtCore.Qt.LeftButton)
        except Exception:
            return False

    def drag_distance(self, point):
        if self.drag_start_point is None:
            return 0.0
        dx = point.x() - self.drag_start_point.x()
        dy = point.y() - self.drag_start_point.y()
        return ((dx * dx) + (dy * dy)) ** 0.5

    def logical_drag_threshold(self):
        return float(BOX_SELECT_DRAG_THRESHOLD) / self.logical_scale()

    def current_selection_rect(self):
        if self.drag_start_point is None or self.drag_current_point is None:
            return None
        return QtCore.QRectF(self.drag_start_point, self.drag_current_point).normalized()

    def item_is_box_previewed(self, item):
        if not self.box_selecting:
            return False
        rect = self.current_selection_rect()
        if rect is None:
            return False
        return self.item_intersects_selection_rect(item, rect)

    def items_in_selection_rect(self, rect):
        items = []
        for item, _model in self.iter_visible_items():
            if self.item_intersects_selection_rect(item, rect):
                items.append(item)
        return items

    def item_intersects_selection_rect(self, item, rect):
        if item.get("visual") == "ik":
            center_x, center_y = item["center"]
            radius = (IK_BUTTON_SIZE * 0.5) + BOX_SELECT_IK_PADDING
            item_rect = QtCore.QRectF(
                BACKGROUND_LEFT + center_x - radius,
                BACKGROUND_TOP + center_y - radius,
                radius * 2.0,
                radius * 2.0,
            )
            return rect.intersects(item_rect) or rect.contains(item_rect.center())

        x1, y1 = item["line_start"]
        x2, y2 = item["line_end"]
        item_rect = QtCore.QRectF(
            QtCore.QPointF(BACKGROUND_LEFT + x1, BACKGROUND_TOP + y1),
            QtCore.QPointF(BACKGROUND_LEFT + x2, BACKGROUND_TOP + y2),
        ).normalized().adjusted(
            -BOX_SELECT_FK_PADDING,
            -BOX_SELECT_FK_PADDING,
            BOX_SELECT_FK_PADDING,
            BOX_SELECT_FK_PADDING,
        )
        return rect.intersects(item_rect) or rect.contains(item_rect.center())

    def hit_test(self, widget_x, widget_y):
        image_x = widget_x - BACKGROUND_LEFT
        image_y = widget_y - BACKGROUND_TOP
        best_item = None
        best_distance = 9999.0
        for item, _model in self.iter_visible_items():
            if item.get("visual") == "ik":
                center_x, center_y = item["center"]
                dist = ((image_x - center_x) ** 2 + (image_y - center_y) ** 2) ** 0.5
                threshold = (IK_BUTTON_SIZE * 0.58)
            else:
                dist = distance_to_segment(image_x, image_y, item["line_start"], item["line_end"])
                threshold = 8.0
            if dist <= threshold and dist < best_distance:
                best_item = item
                best_distance = dist
        return best_item


class HandPickerWidgetHolder(FBWidgetHolder):
    def WidgetCreate(self, pWidgetParent):
        parent = wrapInstance(pWidgetParent, QtWidgets.QWidget)
        self.native_widget = HandPickerWidget(parent)
        return getCppPointer(self.native_widget)[0]


def create_tool():
    global _TOOL
    remove_custom_selection_keying_groups()
    _TOOL = FBCreateUniqueTool(TOOL_NAME)
    _TOOL.StartSizeX = TOOL_WIDTH
    _TOOL.StartSizeY = TOOL_HEIGHT
    holder = HandPickerWidgetHolder()
    add_fill_region(_TOOL, "main", holder)
    ShowTool(_TOOL)


def run_with_error_dialog():
    try:
        create_tool()
    except Exception:
        FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")


run_with_error_dialog()
