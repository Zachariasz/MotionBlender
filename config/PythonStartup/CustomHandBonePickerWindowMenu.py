from pyfbsdk import *
from pyfbsdk_additions import *
import os
import traceback


PICKER_TOOL_NAME = "Custom Hand Bone Picker"
PICKER_SCRIPT_NAME = "CustomHandBonePicker.py"
MENU_PATH = "Window"
MENU_ITEM_NAME = "Custom Hand Bone Picker"
MENU_ITEM_ID = 95260602
AUTO_OPEN_PROPERTY_NAME = "AutoOpenHandPicker"

_APP = FBApplication()
_MENU_CALLBACKS = []
_FILE_CALLBACKS = []
_PICKER_NAMESPACES = []


def add_config_candidate(candidates, path):
    if not path:
        return
    try:
        path = os.path.normpath(str(path))
    except Exception:
        return
    if path and path not in candidates:
        candidates.append(path)


def get_config_dir():
    candidates = []

    try:
        startup_dir = os.path.dirname(os.path.abspath(__file__))
        add_config_candidate(candidates, os.path.dirname(startup_dir))
    except Exception:
        pass

    try:
        add_config_candidate(candidates, FBSystem().UserConfigPath)
    except Exception:
        pass

    try:
        add_config_candidate(candidates, FBSystem().ConfigPath)
    except Exception:
        pass

    try:
        startup_paths = FBSystem().GetPythonStartupPath()
        for startup_path in startup_paths:
            startup_dir = os.path.normpath(str(startup_path))
            add_config_candidate(candidates, os.path.dirname(startup_dir))
    except Exception:
        pass

    for config_dir in candidates:
        if os.path.isfile(os.path.join(config_dir, "Scripts", PICKER_SCRIPT_NAME)):
            return config_dir

    for config_dir in candidates:
        if os.path.isdir(os.path.join(config_dir, "Scripts")):
            return config_dir

    if candidates:
        return candidates[0]

    return os.getcwd()


def get_picker_script_path():
    return os.path.join(get_config_dir(), "Scripts", PICKER_SCRIPT_NAME)


def show_existing_picker():
    if PICKER_TOOL_NAME in FBToolList:
        ShowTool(FBToolList[PICKER_TOOL_NAME])
        return True
    return False


def destroy_existing_picker():
    try:
        FBDestroyToolByName(PICKER_TOOL_NAME)
    except Exception:
        try:
            if PICKER_TOOL_NAME in FBToolList:
                del FBToolList[PICKER_TOOL_NAME]
        except Exception:
            pass


def run_picker_script():
    destroy_existing_picker()
    script_path = get_picker_script_path()
    if not os.path.isfile(script_path):
        FBMessageBox(
            PICKER_TOOL_NAME,
            "Could not find picker script:\n" + script_path + "\n\nCopy " + PICKER_SCRIPT_NAME + " into the Scripts folder.",
            "OK",
        )
        return

    namespace = {
        "__file__": script_path,
        "__name__": "__custom_hand_bone_picker_exec__",
    }
    with open(script_path, "r", encoding="utf-8-sig") as stream:
        code = compile(stream.read(), script_path, "exec")
    exec(code, namespace)
    _PICKER_NAMESPACES.append(namespace)


def value_is_truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def property_is_truthy(prop):
    try:
        return value_is_truthy(prop.Data)
    except Exception:
        return False


def scene_has_auto_open_property():
    scene = FBSystem().Scene
    for component in scene.Components:
        try:
            prop = component.PropertyList.Find(AUTO_OPEN_PROPERTY_NAME)
        except Exception:
            prop = None

        if prop is not None and property_is_truthy(prop):
            return True

    return False


def auto_open_picker_if_requested():
    if scene_has_auto_open_property():
        run_picker_script()


def on_file_open_completed(control, event):
    try:
        auto_open_picker_if_requested()
    except Exception:
        FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")


def on_menu_activate(control, event):
    try:
        if event.Id == MENU_ITEM_ID:
            run_picker_script()
    except Exception:
        FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")


def register_window_menu_item():
    menu_manager = FBMenuManager()
    window_menu = menu_manager.GetMenu(MENU_PATH)
    if window_menu is None:
        FBMessageBox(PICKER_TOOL_NAME, "Could not find MotionBuilder menu: " + MENU_PATH, "OK")
        return

    existing_item = window_menu.GetItem(MENU_ITEM_ID)
    if existing_item is not None:
        window_menu.DeleteItem(existing_item)

    window_menu.InsertLast(MENU_ITEM_NAME, MENU_ITEM_ID)
    window_menu.OnMenuActivate.Add(on_menu_activate)
    _MENU_CALLBACKS.append(on_menu_activate)


def register_file_open_handler():
    _APP.OnFileOpenCompleted.Add(on_file_open_completed)
    _FILE_CALLBACKS.append(on_file_open_completed)


try:
    register_window_menu_item()
    register_file_open_handler()
    auto_open_picker_if_requested()
except Exception:
    FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")
