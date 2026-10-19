from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "scene.grid_axis_lines"
TOOL_NAME = "Grid Axis Lines Auto Start"

def _show_error(details):
    # Print error details to console
    print("{}:".format(TOOL_NAME))
    print(details)

def run_service_script():
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        run_service_script()
    except Exception as e:
        details = traceback.format_exc()
        _show_error(details)

if globals().get("GRID_AXIS_LINES_AUTOSTART_LAUNCHER_AUTORUN", True):
    run_with_error_dialog()
