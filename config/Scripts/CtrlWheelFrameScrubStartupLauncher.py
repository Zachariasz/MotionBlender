from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "input.ctrl_wheel_frame_scrub"
TOOL_NAME = "Ctrl Wheel Frame Scrub Startup"

def _show_error(details):
    from mobu_tools_manager import show_error_dialog
    show_error_dialog(TOOL_NAME, details)

def start_ctrl_wheel_frame_scrub():
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        start_ctrl_wheel_frame_scrub()
    except Exception as e:
        _show_error(traceback.format_exc())

if globals().get("CTRL_WHEEL_FRAME_SCRUB_STARTUP_AUTORUN", True):
    run_with_error_dialog()
