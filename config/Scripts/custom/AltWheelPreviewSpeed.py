"""Compatibility launcher for the manager-owned Alt+Wheel speed service."""

from __future__ import absolute_import, print_function

import traceback


FEATURE_ID = "input.alt_wheel_preview_speed"
TOOL_NAME = "Alt Wheel Preview Speed"


def _show_error(details):
    try:
        from pyfbsdk import FBMessageBox

        FBMessageBox(TOOL_NAME + " Error", details[-1800:], "OK")
    except Exception:
        print(details)


def start_alt_wheel_preview_speed():
    from mobu_tools_manager import dispatch, enable

    enable(FEATURE_ID)
    return dispatch(FEATURE_ID)


def stop_alt_wheel_preview_speed():
    from mobu_tools_manager import disable

    return disable(FEATURE_ID)


def status_payload():
    from mobu_tools_manager import dispatch

    return dispatch(FEATURE_ID)


def run_with_error_dialog():
    try:
        return start_alt_wheel_preview_speed()
    except Exception:
        _show_error(traceback.format_exc())
        return None


if globals().get("ALT_WHEEL_PREVIEW_SPEED_AUTORUN", True):
    run_with_error_dialog()
