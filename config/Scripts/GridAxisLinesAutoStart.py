import os
import traceback

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

from pyfbsdk import FBApplication, FBMessageBox


TOOL_NAME = "Grid Axis Lines Auto Start"
SERVICE_ATTR = "_grid_axis_lines_autostart_service"
AXIS_SCRIPT_NAME = "CreateGridAxisLines.py"


def script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return r"C:\Users\zacha\OneDrive\Documents\MB\2026\config\Scripts"


def axis_script_path():
    return os.path.join(script_dir(), AXIS_SCRIPT_NAME)


def run_axis_script():
    path = axis_script_path()
    if not os.path.isfile(path):
        raise RuntimeError("Could not find axis-line script: " + path)

    namespace = {
        "__file__": path,
        "__name__": "__grid_axis_lines_exec__",
    }

    with open(path, "r", encoding="utf-8-sig") as stream:
        code = compile(stream.read(), path, "exec")

    exec(code, namespace, namespace)


class GridAxisLinesAutoStartService(object):
    def __init__(self):
        self.app = FBApplication()
        self.started = False
        self.run_count = 0
        self.last_reason = None
        self.last_error = None
        self._open_callback = self.on_file_open_completed
        self._new_callback = self.on_file_new_completed

    def start(self):
        if self.started:
            return

        self.app.OnFileOpenCompleted.Add(self._open_callback)
        self.app.OnFileNewCompleted.Add(self._new_callback)
        self.started = True
        self.run("startup")

    def stop(self):
        if not self.started:
            return

        try:
            self.app.OnFileOpenCompleted.Remove(self._open_callback)
        except Exception:
            pass

        try:
            self.app.OnFileNewCompleted.Remove(self._new_callback)
        except Exception:
            pass

        self.started = False

    def run(self, reason):
        try:
            run_axis_script()
            self.run_count += 1
            self.last_reason = reason
            self.last_error = None
        except Exception:
            self.last_error = traceback.format_exc()
            FBMessageBox(TOOL_NAME + " Error", self.last_error[-1800:], "OK")

    def on_file_open_completed(self, control, event):
        self.run("file_open_completed")

    def on_file_new_completed(self, control, event):
        self.run("file_new_completed")


def install_autostart_service():
    old_service = getattr(builtins, SERVICE_ATTR, None)
    if old_service is not None:
        try:
            old_service.stop()
        except Exception:
            pass

    service = GridAxisLinesAutoStartService()
    setattr(builtins, SERVICE_ATTR, service)
    service.start()
    return service


try:
    install_autostart_service()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")
