from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "input.block_alt_menu_focus"
TOOL_NAME = "Block Alt Menu Focus Startup"

def _show_error(details):
    try:
        from mobu_tools_manager import show_dialog
        show_dialog(title=TOOL_NAME, message=details)
    except Exception:
        # Fallback to console output if dialog is unavailable
        print("{}\n{}".format(TOOL_NAME, details))

def start_block_alt_menu_focus():
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        start_block_alt_menu_focus()
    except Exception as e:
        details = "{}\n{}".format(e, traceback.format_exc())
        _show_error(details)

if globals().get("BLOCK_ALT_MENU_FOCUS_STARTUP_AUTORUN", True):
    run_with_error_dialog()
