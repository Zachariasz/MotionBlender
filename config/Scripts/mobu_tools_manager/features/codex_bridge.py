"""Manager-owned main-thread execution bridge with a Viewer status badge."""

from __future__ import absolute_import

import builtins
import contextlib
import io
import json
import os
import shutil
import time
import traceback


FEATURE_ID = "developer.codex_bridge"
FEATURE_NAME = "Codex MotionBuilder Bridge"
LEGACY_SERVICE_ATTR = "_codex_motionbuilder_bridge_service"
LEGACY_CONTROLLER_ATTR = "_codex_motionbuilder_bridge_tool_controller"
LEGACY_TOOL_NAME = "Start Codex MotionBuilder Bridge"
POLL_INTERVAL_MS = 250
HEARTBEAT_INTERVAL_SECONDS = 2.0
BADGE_OBJECT_NAME = "MobuCodexBridgeDebugBadge"
BADGE_WIDTH = 104
BADGE_HEIGHT = 26
BADGE_MARGIN = 12

SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
BRIDGE_ROOT = os.path.join(SCRIPTS_ROOT, ".codex_mobu_bridge")
COMMANDS_DIR = os.path.join(BRIDGE_ROOT, "commands")
RUNNING_DIR = os.path.join(BRIDGE_ROOT, "running")
DONE_DIR = os.path.join(BRIDGE_ROOT, "done")
RESULTS_DIR = os.path.join(BRIDGE_ROOT, "results")
LOGS_DIR = os.path.join(BRIDGE_ROOT, "logs")
STATUS_PATH = os.path.join(BRIDGE_ROOT, "status.json")
HEARTBEAT_PATH = os.path.join(BRIDGE_ROOT, "heartbeat.txt")
LOG_PATH = os.path.join(LOGS_DIR, "bridge.log")

_SERVICE = None


def _qt_modules():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets


def _qt_enum(QtCore, group_name, value_name):
    group = getattr(QtCore.Qt, group_name, None)
    if group is not None and hasattr(group, value_name):
        return getattr(group, value_name)
    return getattr(QtCore.Qt, value_name)


def _event_value(QtCore, name):
    group = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    value = getattr(QtCore.QEvent, name, None)
    return value if value is not None else getattr(group, name, None)


def _safe(callback, default=None):
    try:
        return callback()
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError):
        return default


def _is_valid_qobject(value):
    if value is None:
        return False
    try:
        try:
            import shiboken6 as shiboken
        except ImportError:
            import shiboken2 as shiboken
        return bool(shiboken.isValid(value))
    except Exception:
        return _safe(lambda: value.metaObject() is not None, False)


def _timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _ensure_directory(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _ensure_bridge_directories():
    for path in (
        BRIDGE_ROOT,
        COMMANDS_DIR,
        RUNNING_DIR,
        DONE_DIR,
        RESULTS_DIR,
        LOGS_DIR,
    ):
        _ensure_directory(path)


def _replace_file(source_path, target_path):
    os.replace(source_path, target_path)


def _safe_write_text(path, text):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as output_file:
        output_file.write(text)
    _replace_file(temp_path, path)


def _safe_write_json(path, data):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, indent=2, sort_keys=True)
    _replace_file(temp_path, path)


def _move_file(source_path, target_path):
    if os.path.exists(target_path):
        root, extension = os.path.splitext(target_path)
        target_path = root + "_" + str(int(time.time() * 1000)) + extension
    shutil.move(source_path, target_path)
    return target_path


def _append_log(message):
    try:
        _ensure_directory(LOGS_DIR)
        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write("[%s] %s\n" % (_timestamp(), message))
    except OSError:
        pass


def _json_friendly(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError, OverflowError):
        return {"__repr__": repr(value), "__type__": type(value).__name__}


def _make_badge_class(QtCore, QtGui, QtWidgets):
    class DebugBadge(QtWidgets.QWidget):
        def __init__(self, parent):
            super(DebugBadge, self).__init__(parent)
            self.setObjectName(BADGE_OBJECT_NAME)
            self.setFixedSize(BADGE_WIDTH, BADGE_HEIGHT)
            self.setAttribute(
                _qt_enum(
                    QtCore,
                    "WidgetAttribute",
                    "WA_TransparentForMouseEvents",
                ),
                True,
            )
            self.setAttribute(
                _qt_enum(
                    QtCore,
                    "WidgetAttribute",
                    "WA_TranslucentBackground",
                ),
                True,
            )
            self.setAttribute(
                _qt_enum(
                    QtCore,
                    "WidgetAttribute",
                    "WA_ShowWithoutActivating",
                ),
                True,
            )
            self.setFocusPolicy(
                _qt_enum(QtCore, "FocusPolicy", "NoFocus")
            )

        def paintEvent(self, event):
            del event
            painter = QtGui.QPainter(self)
            try:
                hint_group = getattr(
                    QtGui.QPainter,
                    "RenderHint",
                    QtGui.QPainter,
                )
                painter.setRenderHint(getattr(hint_group, "Antialiasing"), True)
                painter.setPen(_qt_enum(QtCore, "PenStyle", "NoPen"))
                painter.setBrush(QtGui.QColor(18, 22, 20, 210))
                painter.drawRoundedRect(self.rect(), 5.0, 5.0)
                painter.setBrush(QtGui.QColor(68, 214, 112))
                painter.drawEllipse(QtCore.QPointF(13.0, 13.0), 4.5, 4.5)
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QtGui.QColor(184, 245, 202))
                painter.drawText(
                    QtCore.QRect(24, 0, BADGE_WIDTH - 28, BADGE_HEIGHT),
                    _qt_enum(QtCore, "AlignmentFlag", "AlignVCenter")
                    | _qt_enum(QtCore, "AlignmentFlag", "AlignLeft"),
                    "Debug On",
                )
            finally:
                painter.end()

    return DebugBadge


class ViewportDebugIndicator(object):
    """Positions one input-transparent badge from manager UI geometry events."""

    def __init__(self, context, qt_modules=None, badge_factory=None):
        self.context = context
        self.QtCore, self.QtGui, self.QtWidgets = qt_modules or _qt_modules()
        self._badge_factory = badge_factory
        self._badge_class = None
        self.badge = None
        self.running = False
        self.geometry = None
        self._observer = self._observe_ui_event
        self._timer = self.QtCore.QTimer(context.qt_application)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh_now)
        self._activation_events = set(
            value
            for value in (
                _event_value(self.QtCore, "ApplicationActivate"),
                _event_value(self.QtCore, "WindowActivate"),
            )
            if value is not None
        )
        self._deactivation_events = set(
            value
            for value in (
                _event_value(self.QtCore, "ApplicationDeactivate"),
                _event_value(self.QtCore, "WindowDeactivate"),
            )
            if value is not None
        )
        self._geometry_events = set(
            value
            for value in (
                _event_value(self.QtCore, "Resize"),
                _event_value(self.QtCore, "Move"),
                _event_value(self.QtCore, "Show"),
                _event_value(self.QtCore, "Hide"),
                _event_value(self.QtCore, "LayoutRequest"),
            )
            if value is not None
        )

    def start(self):
        if self.running:
            return self
        self.context.add_ui_event_observer(self._observer)
        self.running = True
        self._schedule()
        return self

    def stop(self):
        if self.context is not None:
            self.context.remove_ui_event_observer(self._observer)
        self.running = False
        self._timer.stop()
        self._destroy_badge()

    def close(self):
        self.stop()
        try:
            self._timer.timeout.disconnect(self._refresh_now)
        except (RuntimeError, TypeError):
            pass
        self._timer.deleteLater()

    def _schedule(self, delay_ms=0):
        if self.running and not self._timer.isActive():
            self._timer.start(max(0, int(delay_ms)))

    def _create_badge(self, parent):
        if _is_valid_qobject(self.badge):
            return self.badge
        if self._badge_factory is not None:
            self.badge = self._badge_factory(parent)
        else:
            if self._badge_class is None:
                self._badge_class = _make_badge_class(
                    self.QtCore,
                    self.QtGui,
                    self.QtWidgets,
                )
            self.badge = self._badge_class(parent)
        return self.badge

    def _destroy_badge(self):
        badge = self.badge
        self.badge = None
        self.geometry = None
        if badge is None:
            return
        _safe(badge.hide)
        _safe(lambda: badge.setParent(None))
        _safe(badge.close)
        _safe(badge.deleteLater)

    def _interaction_active(self):
        input_router = getattr(self.context, "input", None)
        return getattr(input_router, "owner", None) is not None

    def _refresh_now(self):
        if not self.running or self._interaction_active():
            return
        attachment = _safe(
            lambda: self.context.find_ui_surface_attachment("viewer"),
            None,
        )
        try:
            host, geometry = attachment
            x, y, width, height = tuple(geometry)
            geometry = (int(x), int(y), int(width), int(height))
            if not _is_valid_qobject(host):
                raise ValueError("invalid viewer host")
        except (TypeError, ValueError):
            self.geometry = None
            _safe(lambda: self.badge.hide())
            return
        if geometry[2] <= BADGE_WIDTH or geometry[3] <= BADGE_HEIGHT:
            self.geometry = None
            _safe(lambda: self.badge.hide())
            return
        if _is_valid_qobject(self.badge):
            same_parent = _safe(
                lambda: self.badge.parentWidget() == host,
                False,
            )
            if not same_parent:
                self._destroy_badge()
        self.geometry = geometry
        badge = self._create_badge(host)
        badge.move(x + BADGE_MARGIN, y + BADGE_MARGIN)
        badge.show()
        badge.raise_()

    def _observe_ui_event(self, watched, event):
        if not self.running or watched is self.badge:
            return False
        if self._interaction_active():
            return False
        event_type = _safe(event.type, None)
        if (
            event_type in self._activation_events
            or event_type in self._deactivation_events
        ):
            self._schedule(50)
        elif event_type in self._geometry_events:
            self._schedule(0)
        return False


class BridgeCommandContext(object):
    def __init__(self, service, command_name):
        self.service = service
        self.command_name = command_name
        self.result = None
        self.result_was_set = False
        self.logs = []

    def set_result(self, value):
        self.result = value
        self.result_was_set = True

    def log(self, *values):
        text = " ".join(str(value) for value in values)
        self.logs.append(text)
        print(text)

    def stop(self):
        self.service.stop_requested = True

    def bridge_root(self):
        return BRIDGE_ROOT


class CodexMotionBuilderBridgeService(object):
    def __init__(
        self,
        context,
        qt_modules=None,
        indicator_factory=None,
    ):
        self.context = context
        modules = qt_modules or _qt_modules()
        self.QtCore, self.QtGui, self.QtWidgets = modules
        self.timer = self.QtCore.QTimer(context.qt_application)
        self.timer.timeout.connect(self._tick)
        try:
            self.timer.setTimerType(
                _qt_enum(self.QtCore, "TimerType", "PreciseTimer")
            )
        except (AttributeError, TypeError):
            pass
        self.indicator = (
            indicator_factory(context)
            if indicator_factory is not None
            else ViewportDebugIndicator(context, qt_modules=modules)
        )
        self.started_at = None
        self.processed_count = 0
        self.last_command = None
        self.last_result_path = None
        self.last_error = None
        self.last_heartbeat_time = 0.0
        self.busy = False
        self.running = False
        self.stop_requested = False

    def start(self):
        if self.running:
            return self
        _ensure_bridge_directories()
        self.started_at = _timestamp()
        self.stop_requested = False
        self.running = True
        self.indicator.start()
        self._write_status("running")
        self._write_heartbeat(force=True)
        self.timer.start(POLL_INTERVAL_MS)
        _append_log("bridge started")
        self._record("codex_bridge_started")
        return self

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.timer.stop()
        self.indicator.stop()
        self._write_status("stopped")
        _append_log("bridge stopped")
        self._record("codex_bridge_stopped")

    def close(self):
        self.stop()
        try:
            self.timer.timeout.disconnect(self._tick)
        except (RuntimeError, TypeError):
            pass
        self.timer.deleteLater()
        self.indicator.close()

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        callback = getattr(diagnostics, "record", None)
        if callable(callback):
            callback(event, FEATURE_ID, **data)

    def _write_heartbeat(self, force=False):
        now = time.time()
        if not force and now - self.last_heartbeat_time < HEARTBEAT_INTERVAL_SECONDS:
            return
        self.last_heartbeat_time = now
        _safe_write_text(HEARTBEAT_PATH, "%s\n" % _timestamp())

    def _write_status(self, state):
        _safe_write_json(
            STATUS_PATH,
            {
                "state": state,
                "bridge_root": BRIDGE_ROOT,
                "commands_dir": COMMANDS_DIR,
                "results_dir": RESULTS_DIR,
                "started_at": self.started_at,
                "updated_at": _timestamp(),
                "processed_count": self.processed_count,
                "last_command": self.last_command,
                "last_result_path": self.last_result_path,
                "last_error": self.last_error,
                "busy": self.busy,
            },
        )

    def _next_command_path(self):
        try:
            names = sorted(os.listdir(COMMANDS_DIR))
        except OSError:
            return None
        for name in names:
            if (
                not name.startswith(".")
                and not name.endswith(".tmp")
                and name.lower().endswith(".py")
            ):
                return os.path.join(COMMANDS_DIR, name)
        return None

    @staticmethod
    def _claim_command(command_path):
        return _move_file(
            command_path,
            os.path.join(RUNNING_DIR, os.path.basename(command_path)),
        )

    @staticmethod
    def _result_path_for(command_path):
        name = os.path.basename(command_path)
        root, _extension = os.path.splitext(name)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        return os.path.join(RESULTS_DIR, "%s_%s.json" % (root, stamp))

    def _execute_command(self, running_path):
        command_name = os.path.basename(running_path)
        bridge_context = BridgeCommandContext(self, command_name)
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        started = time.time()
        result = {
            "ok": False,
            "command": command_name,
            "command_path": running_path,
            "started_at": _timestamp(),
            "ended_at": None,
            "duration_ms": None,
            "stdout": "",
            "stderr": "",
            "bridge_logs": [],
            "result": None,
            "error": None,
        }
        try:
            with open(running_path, "r", encoding="utf-8-sig") as command_file:
                source = command_file.read()
            namespace = {
                "__builtins__": builtins,
                "__file__": running_path,
                "__name__": "__codex_mobu_command__",
                "BRIDGE": bridge_context,
                "bridge": bridge_context,
                "set_result": bridge_context.set_result,
                "bridge_log": bridge_context.log,
            }
            with contextlib.redirect_stdout(stdout_buffer):
                with contextlib.redirect_stderr(stderr_buffer):
                    exec(compile(source, running_path, "exec"), namespace, namespace)
            if bridge_context.result_was_set:
                result["result"] = _json_friendly(bridge_context.result)
            elif "RESULT" in namespace:
                result["result"] = _json_friendly(namespace["RESULT"])
            result["ok"] = True
            self.last_error = None
        except Exception:
            result["error"] = traceback.format_exc()
            self.last_error = result["error"]

        result["ended_at"] = _timestamp()
        result["duration_ms"] = int((time.time() - started) * 1000.0)
        result["stdout"] = stdout_buffer.getvalue()
        result["stderr"] = stderr_buffer.getvalue()
        result["bridge_logs"] = list(bridge_context.logs)
        result_path = self._result_path_for(running_path)
        _safe_write_json(result_path, result)
        suffix = ".done.py" if result["ok"] else ".error.py"
        _move_file(running_path, os.path.join(DONE_DIR, command_name + suffix))
        self.processed_count += 1
        self.last_command = command_name
        self.last_result_path = result_path
        self._write_status("running")
        _append_log(
            "command ok: %s" % command_name
            if result["ok"]
            else "command error: %s" % command_name
        )

    def _tick(self):
        if not self.running or self.busy:
            return
        self._write_heartbeat()
        if self.stop_requested:
            self.stop()
            return
        command_path = self._next_command_path()
        if command_path is None:
            return
        self.busy = True
        self._write_status("busy")
        try:
            self._execute_command(self._claim_command(command_path))
        except Exception:
            self.last_error = traceback.format_exc()
            _append_log("bridge internal error: %s" % self.last_error)
            self._record("codex_bridge_internal_error", error=self.last_error)
        finally:
            self.busy = False
            if self.running:
                self._write_status("running")

    def status(self):
        return {
            "running": bool(self.running and self.timer.isActive()),
            "indicator_visible": bool(
                _safe(lambda: self.indicator.badge.isVisible(), False)
            ),
            "processed_count": int(self.processed_count),
            "last_command": self.last_command,
            "last_result_path": self.last_result_path,
            "last_error": self.last_error,
        }


def _retire_legacy_resources():
    legacy_service = getattr(builtins, LEGACY_SERVICE_ATTR, None)
    if legacy_service is not None:
        _safe(legacy_service.stop)
    controller = getattr(builtins, LEGACY_CONTROLLER_ATTR, None)
    tool = getattr(controller, "tool", None)
    if tool is not None:
        for event_name, callback_name in (
            ("OnPreShow", "on_pre_show"),
            ("OnShow", "on_show"),
        ):
            callback = getattr(controller, callback_name, None)
            if callback is not None:
                _safe(lambda: getattr(tool, event_name).Remove(callback))
        _safe(lambda: setattr(tool, "Visible", False))
    try:
        import pyfbsdk_additions

        tool_manager = pyfbsdk_additions.FBToolManager
        entry = tool_manager.tools.get(LEGACY_TOOL_NAME)
        if entry is not None:
            menu_item = getattr(entry, "menuitem", None)
            if menu_item is not None:
                tool_manager.menu.DeleteItem(menu_item)
            tool_manager.tools.pop(LEGACY_TOOL_NAME, None)
    except (AttributeError, KeyError, RuntimeError, TypeError):
        _append_log("could not remove retired bridge Python Tools item")
    setattr(builtins, LEGACY_SERVICE_ATTR, None)
    setattr(builtins, LEGACY_CONTROLLER_ATTR, None)


def start(context):
    global _SERVICE
    _retire_legacy_resources()
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.close()
    _SERVICE = CodexMotionBuilderBridgeService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.close()
    _SERVICE = None


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
