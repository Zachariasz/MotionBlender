from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "scene.grid_axis_lines"
TOOL_NAME = "Grid Axis Lines Auto Start"

def _show_error(details):
    """Display error details."""
    print("Error in {}:".format(TOOL_NAME))
    if isinstance(details, Exception):
        traceback.print_exc()
    else:
        print(details)

def install_autostart_service():
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def stop_autostart_service():
    from mobu_tools_manager import disable
    return disable(FEATURE_ID)

def run_with_error_dialog():
    try:
        install_autostart_service()
    except Exception as e:
        _show_error(e)

if globals().get("GRID_AXIS_LINES_AUTOSTART_AUTORUN", True):
    run_with_error_dialog()
