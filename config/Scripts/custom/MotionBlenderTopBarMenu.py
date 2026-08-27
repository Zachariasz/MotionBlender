"""Native Launcher for Motion Blender top-level menu tab.

Creates the 'Motion Blender' tab on MotionBuilder's main menu bar (topbar)
directly next to the 'Help' option using MotionBuilder SDK FBMenuManager.
"""

from __future__ import absolute_import, print_function

import traceback


def install_motion_blender_menu():
    try:
        from mobu_tools_manager.features.motion_blender_menu import start
        start()
        print("Installed 'Motion Blender' topbar menu successfully.")
    except Exception:
        details = traceback.format_exc()
        try:
            from pyfbsdk import FBMessageBox
            FBMessageBox("Motion Blender Menu", details, "OK")
        except Exception:
            print(details)


if __name__ == "__main__" or globals().get("MOTION_BLENDER_MENU_AUTORUN", True):
    install_motion_blender_menu()
