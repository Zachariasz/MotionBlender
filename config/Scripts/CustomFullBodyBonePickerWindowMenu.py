from pyfbsdk import *
import os
import traceback

try:
    from PySide6 import QtCore, QtWidgets
except Exception:
    from PySide2 import QtCore, QtWidgets


PICKER_TOOL_NAME = "Custom Full Body Bone Picker"
PICKER_SCRIPT_NAME = "CustomFullBodyBonePicker.py"
MENU_PATH = "Window"
MENU_ITEM_NAME = "Custom Full Body Bone Picker"
MENU_ITEM_ID = 95260603
LAYOUT_MENU_PATH = "Layout"
LAYOUT_MENU_ITEM_NAME = "Save/Update Full Body Picker Position"
LAYOUT_MENU_ITEM_ID = 95260604
AUTO_OPEN_PROPERTY_NAME = "AutoOpenFullBodyPicker"

_APP = FBApplication()
_MENU_CALLBACKS = []
_FILE_CALLBACKS = []
_PICKER_NAMESPACES = []
_STARTUP_TIMER = None


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
        for startup_path in FBSystem().GetPythonStartupPath():
            add_config_candidate(candidates, os.path.dirname(os.path.normpath(str(startup_path))))
    except Exception:
        pass
    for config_dir in candidates:
        if os.path.isfile(os.path.join(config_dir, "Scripts", PICKER_SCRIPT_NAME)):
            return config_dir
    for config_dir in candidates:
        if os.path.isdir(os.path.join(config_dir, "Scripts")):
            return config_dir
    return candidates[0] if candidates else os.getcwd()


def get_picker_script_path():
    return os.path.join(get_config_dir(), "Scripts", PICKER_SCRIPT_NAME)


def destroy_existing_picker():
    try:
        FBDestroyToolByName(PICKER_TOOL_NAME)
    except Exception:
        pass


def run_picker_script():
    destroy_existing_picker()
    script_path = get_picker_script_path()
    if not os.path.isfile(script_path):
        FBMessageBox(PICKER_TOOL_NAME, "Could not find picker script:\n" + script_path, "OK")
        return
    namespace = {"__file__": script_path, "__name__": "__custom_full_body_bone_picker_exec__"}
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


def scene_requests_auto_open():
    for component in FBSystem().Scene.Components:
        try:
            prop = component.PropertyList.Find(AUTO_OPEN_PROPERTY_NAME)
        except Exception:
            prop = None
        if prop is not None:
            try:
                if value_is_truthy(prop.Data):
                    return True
            except Exception:
                pass
    return False


def auto_open_picker_if_requested():
    if scene_requests_auto_open():
        run_picker_script()


def delayed_startup_open():
    global _STARTUP_TIMER
    try:
        run_picker_script()
    except Exception:
        FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")
    finally:
        _STARTUP_TIMER = None


def schedule_startup_open():
    global _STARTUP_TIMER
    application = QtWidgets.QApplication.instance()
    if application is None:
        raise RuntimeError("MotionBuilder Qt application is not available.")
    _STARTUP_TIMER = QtCore.QTimer(application)
    _STARTUP_TIMER.setSingleShot(True)
    _STARTUP_TIMER.timeout.connect(delayed_startup_open)
    _STARTUP_TIMER.start(5000)


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


def live_picker_namespace():
    for namespace in reversed(_PICKER_NAMESPACES):
        widget = namespace.get("_NATIVE_WIDGET")
        try:
            if widget is not None and widget.parentWidget() is not None:
                return namespace
        except Exception:
            pass
    application = QtWidgets.QApplication.instance()
    if application is None:
        return None
    selector = next(
        (widget for widget in application.allWidgets() if widget.objectName() == "character_selector"),
        None,
    )
    picker = selector
    while picker is not None:
        method = getattr(picker, "refresh_toolbar_ui", None)
        function = getattr(method, "__func__", None)
        namespace = getattr(function, "__globals__", None)
        if isinstance(namespace, dict) and "save_current_picker_dock_layout" in namespace:
            return namespace
        picker = picker.parentWidget()
    return None


def on_layout_menu_activate(control, event):
    try:
        if event.Id != LAYOUT_MENU_ITEM_ID:
            return
        namespace = live_picker_namespace()
        if namespace is None:
            raise RuntimeError("Open the full-body picker before saving its dock position.")
        path = namespace["save_current_picker_dock_layout"]()
        FBMessageBox(PICKER_TOOL_NAME, "Picker dock position saved.\n\n" + path, "OK")
    except Exception:
        FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")


def register_window_menu_item():
    window_menu = FBMenuManager().GetMenu(MENU_PATH)
    if window_menu is None:
        FBMessageBox(PICKER_TOOL_NAME, "Could not find MotionBuilder menu: " + MENU_PATH, "OK")
        return
    existing_item = window_menu.GetItem(MENU_ITEM_ID)
    if existing_item is not None:
        window_menu.DeleteItem(existing_item)
    window_menu.InsertLast(MENU_ITEM_NAME, MENU_ITEM_ID)
    window_menu.OnMenuActivate.Add(on_menu_activate)
    _MENU_CALLBACKS.append(on_menu_activate)


def register_layout_menu_item():
    layout_menu = FBMenuManager().GetMenu(LAYOUT_MENU_PATH)
    if layout_menu is None:
        FBMessageBox(PICKER_TOOL_NAME, "Could not find MotionBuilder menu: " + LAYOUT_MENU_PATH, "OK")
        return
    existing_item = layout_menu.GetItem(LAYOUT_MENU_ITEM_ID)
    if existing_item is not None:
        layout_menu.DeleteItem(existing_item)
    layout_menu.InsertLast(LAYOUT_MENU_ITEM_NAME, LAYOUT_MENU_ITEM_ID)
    layout_menu.OnMenuActivate.Add(on_layout_menu_activate)
    _MENU_CALLBACKS.append(on_layout_menu_activate)


def register_file_open_handler():
    _APP.OnFileOpenCompleted.Add(on_file_open_completed)
    _FILE_CALLBACKS.append(on_file_open_completed)


try:
    register_window_menu_item()
    register_layout_menu_item()
    register_file_open_handler()
    schedule_startup_open()
except Exception:
    FBMessageBox(PICKER_TOOL_NAME, traceback.format_exc(), "OK")
