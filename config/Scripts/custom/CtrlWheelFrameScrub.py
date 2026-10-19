from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "input.ctrl_wheel_frame_scrub"
TOOL_NAME = "Ctrl Wheel Frame Scrub"

def _show_error(details):
    try:
        from pyfbsdk import FBMessageBox
        FBMessageBox(TOOL_NAME + " Error", details[-1800:], "OK")
    except Exception:
        print(details)

def start_ctrl_wheel_frame_scrub():
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def stop_ctrl_wheel_frame_scrub():
    from mobu_tools_manager import disable
    return disable(FEATURE_ID)

def status_payload():
    from mobu_tools_manager import dispatch
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        start_ctrl_wheel_frame_scrub()
    except Exception:
        _show_error(traceback.format_exc())

if globals().get("CTRL_WHEEL_FRAME_SCRUB_AUTORUN", True):
    run_with_error_dialog()
