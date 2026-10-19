from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "transform.reset_scale"
TOOL_NAME = "Reset Local Scale"

def _show_error(details):
    # Print error details to console
    print("[{}] Error:".format(TOOL_NAME))
    print(details)

def reset_local_scale():
    from mobu_tools_manager import dispatch
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        reset_local_scale()
    except Exception as e:
        details = "{}\n{}".format(e, traceback.format_exc())
        _show_error(details)

if globals().get("RESET_LOCAL_SCALE_AUTORUN", True):
    run_with_error_dialog()
