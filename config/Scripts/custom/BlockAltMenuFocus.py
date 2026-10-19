from __future__ import absolute_import, print_function
import traceback

FEATURE_ID = "input.block_alt_menu_focus"
TOOL_NAME = "Block Alt Menu Focus"

def _show_error(details):
    """Display error details."""
    try:
        from mobu_tools_manager import show_error_dialog
        show_error_dialog(TOOL_NAME, details)
    except Exception:
        # Fallback to console output if dialog not available
        print("[{}] Error:".format(TOOL_NAME))
        print(details)

def start_block_alt_menu_focus():
    """Start the Block Alt Menu Focus feature."""
    from mobu_tools_manager import dispatch, enable
    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)

def stop_existing_controller():
    """Stop any existing controller for this feature."""
    from mobu_tools_manager import disable
    return disable(FEATURE_ID)

def get_block_alt_menu_focus_controller():
    """Retrieve the service controller for Block Alt Menu Focus."""
    from mobu_tools_manager.features.block_alt_menu_focus import _SERVICE
    return _SERVICE

def run_with_error_dialog():
    """Run the feature with error handling."""
    try:
        start_block_alt_menu_focus()
    except Exception as e:
        details = traceback.format_exc()
        _show_error(details)

# Auto-run if enabled in globals
if globals().get("BLOCK_ALT_MENU_FOCUS_AUTORUN", True):
    run_with_error_dialog()
