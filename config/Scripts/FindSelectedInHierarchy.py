"""
Find Selected in Hierarchy (MotionBuilder Script)
-------------------------------------------------
Unrolls / expands the Scene Browser tree to locate the selected object in the hierarchy.
"""

import os
import sys

# Ensure custom scripts directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
custom_dir = os.path.join(script_dir, "custom")
if custom_dir not in sys.path:
    sys.path.insert(0, custom_dir)

try:
    import FindSelectedInHierarchy
    if sys.version_info[0] >= 3:
        import importlib
        importlib.reload(FindSelectedInHierarchy)
    else:
        reload(FindSelectedInHierarchy)
    FindSelectedInHierarchy.run_with_error_dialog()
except Exception:
    import pyfbsdk, traceback
    pyfbsdk.FBMessageBox("Error", traceback.format_exc(), "OK")
