import os
import traceback

from pyfbsdk import FBMessageBox, FBSystem


TOOL_NAME = "Block Alt Menu Focus"
SERVICE_SCRIPT_NAME = os.path.join("custom", "BlockAltMenuFocus.py")


def add_candidate(candidates, path):
    if not path:
        return

    try:
        path = os.path.normpath(str(path))
    except Exception:
        return

    if path and path not in candidates:
        candidates.append(path)


def get_config_dir():
    candidates = []

    try:
        startup_dir = os.path.dirname(os.path.abspath(__file__))
        add_candidate(candidates, os.path.dirname(startup_dir))
    except Exception:
        pass

    try:
        add_candidate(candidates, FBSystem().UserConfigPath)
    except Exception:
        pass

    try:
        add_candidate(candidates, FBSystem().ConfigPath)
    except Exception:
        pass

    try:
        for startup_path in FBSystem().GetPythonStartupPath():
            add_candidate(candidates, os.path.dirname(os.path.normpath(str(startup_path))))
    except Exception:
        pass

    for config_dir in candidates:
        if os.path.isfile(os.path.join(config_dir, "Scripts", SERVICE_SCRIPT_NAME)):
            return config_dir

    for config_dir in candidates:
        if os.path.isdir(os.path.join(config_dir, "Scripts")):
            return config_dir

    if candidates:
        return candidates[0]

    return os.getcwd()


def run_service_script():
    script_path = os.path.join(get_config_dir(), "Scripts", SERVICE_SCRIPT_NAME)
    if not os.path.isfile(script_path):
        FBMessageBox(TOOL_NAME, "Could not find startup service:\n" + script_path, "OK")
        return

    namespace = {
        "__file__": script_path,
        "__name__": "__block_alt_menu_focus_startup__",
    }

    with open(script_path, "r", encoding="utf-8-sig") as stream:
        code = compile(stream.read(), script_path, "exec")

    exec(code, namespace, namespace)


try:
    run_service_script()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
