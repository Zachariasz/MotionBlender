"""Compatibility launcher for the manager-owned Quick Favorites feature.

Configure menu entries from MotionBuilder Tools Manager -> Quick Favorites.
The implementation, UI context, input pairing, native-action dispatch, and
lifecycle are owned by ``mobu_tools_manager``.
"""

from __future__ import absolute_import, print_function

import traceback

from mobu_tools_manager import dispatch


FEATURE_ID = "ui.quick_favorites"


def show_quick_favorites(global_position=None):
    """Dispatch the managed feature; position is retained for compatibility."""
    del global_position
    return dispatch(FEATURE_ID)


def run_with_error_dialog():
    try:
        return show_quick_favorites()
    except Exception:
        details = traceback.format_exc()
        try:
            from pyfbsdk import FBMessageBox

            FBMessageBox("Quick Favorites", details, "OK")
        except Exception:
            print(details)
        return None


if globals().get("QUICK_FAVORITES_AUTORUN", True):
    run_with_error_dialog()
