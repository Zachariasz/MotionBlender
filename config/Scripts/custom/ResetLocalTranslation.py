from __future__ import absolute_import, print_function

import traceback

FEATURE_ID = "transform.reset_translation"
TOOL_NAME = "Reset Local Translation"

def _show_error(details):
    # Print error details to console and optionally show a dialog
    print("Error in {}:".format(TOOL_NAME))
    print(details)

def reset_local_translation():
    from mobu_tools_manager import dispatch
    return dispatch(FEATURE_ID)

def run_with_error_dialog():
    try:
        reset_local_translation()
    except Exception as e:
        details = traceback.format_exc()
        _show_error(details)

if globals().get("RESET_LOCAL_TRANSLATION_AUTORUN", True):
    run_with_error_dialog()
