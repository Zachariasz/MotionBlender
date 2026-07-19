WARMUP_DISABLED = True
import os

from pyfbsdk import FBToolLayoutManager


_config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_restore_marker = os.path.join(_config_dir, "Scripts", "CustomFullBodyPickerLayoutRestored.once")
if not os.path.isfile(_restore_marker):
    try:
        _layout_manager = FBToolLayoutManager()
        _custom_names = [
            str(_layout_manager.GetLayoutName(index))
            for index in range(_layout_manager.GetCustomLayoutCount())
        ]
        if "FB Picker" in _custom_names and _layout_manager.SetCurrentLayout("FB Picker"):
            with open(_restore_marker, "w", encoding="utf-8") as _stream:
                _stream.write("restored\n")
    except Exception:
        pass

_RETIRED_WARMUP_SOURCE = r'''
import builtins

from pyfbsdk import FBToolLayoutManager

try:
    from PySide6 import QtCore, QtWidgets
except Exception:
    from PySide2 import QtCore, QtWidgets


STATE_NAME = "_custom_full_body_picker_character_menu_warmed"


def native_character_menu_exists():
    application = QtWidgets.QApplication.instance()
    if application is None:
        return False
    expected = (
        "File", "Create", "Define", "Edit", "Bake (Plot)", "Add to Selection", "Show/Hide",
    )
    for widget in application.allWidgets():
        if not isinstance(widget, QtWidgets.QMenu):
            continue
        try:
            actions = tuple(str(action.text()).strip() for action in widget.actions())
        except Exception:
            continue
        if actions == expected:
            return True
    return False


def wait_for_ui_events(milliseconds):
    event_loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(max(0, int(milliseconds)), event_loop.quit)
    try:
        event_loop.exec()
    except AttributeError:
        event_loop.exec_()


def warmup_native_character_menu():
    if native_character_menu_exists():
        return True
    application = QtWidgets.QApplication.instance()
    if application is None:
        return False

    visible_windows = [widget for widget in application.topLevelWidgets() if widget.isVisible()]
    for widget in visible_windows:
        widget.setUpdatesEnabled(False)

    manager = FBToolLayoutManager()
    original_index = int(manager.GetCurrentLayoutIdx())
    original_name = str(manager.GetCurrentLayoutName())
    restored = False
    try:
        if original_index == -1:
            if not manager.SetCurrentLayout(-2):
                return False
            wait_for_ui_events(120)
            if not manager.SetCurrentLayout(-1):
                return False
            restored = True
        else:
            if not manager.SetCurrentLayout(-1):
                return False
            wait_for_ui_events(180)
            restore_target = original_name if original_index >= 0 else original_index
            if not manager.SetCurrentLayout(restore_target):
                return False
            restored = True
        wait_for_ui_events(280)
        return native_character_menu_exists()
    finally:
        if not restored:
            try:
                restore_target = original_name if original_index >= 0 else original_index
                manager.SetCurrentLayout(restore_target)
                wait_for_ui_events(200)
            except Exception:
                pass
        for widget in visible_windows:
            try:
                widget.setUpdatesEnabled(True)
                widget.update()
            except Exception:
                pass


if not bool(getattr(builtins, STATE_NAME, False)):
    try:
        setattr(builtins, STATE_NAME, bool(warmup_native_character_menu()))
    except Exception:
        setattr(builtins, STATE_NAME, False)
'''
