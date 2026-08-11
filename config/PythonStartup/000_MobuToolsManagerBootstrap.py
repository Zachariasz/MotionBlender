"""Source copied to PythonStartup/000_MobuToolsManagerBootstrap.py."""

from __future__ import absolute_import

import os
import sys
import traceback


def _scripts_root():
    startup = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(startup, os.pardir, "Scripts"))


try:
    root = _scripts_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from mobu_tools_manager.bootstrap import bootstrap

    bootstrap()
except Exception:
    details = traceback.format_exc()
    try:
        from pyfbsdk import FBMessageBox

        FBMessageBox("MotionBuilder Tools Manager Startup Error", details[-2500:], "OK")
    except Exception:
        print(details)
