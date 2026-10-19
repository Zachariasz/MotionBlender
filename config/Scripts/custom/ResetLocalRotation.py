from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "transform.reset_rotation"
TOOL_NAME = "Reset Local Rotation"

def _show_error(details):
    try:
        from mobu_tools_manager import show_error_dialog
        show_error_dialog(TOOL_NAME, details)
    except Exception as e:
        print("Error showing error dialog:", e)

def reset_local_rotation():
    from mobu_tools_manager import dispatch
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        reset_local_rotation()
    except Exception as exc:
        tb = traceback.format_exc()
        _show_error(f"{exc}\n{tb}")

if globals().get("RESET_LOCAL_ROTATION_AUTORUN", True):
    run_with_error_dialog()
