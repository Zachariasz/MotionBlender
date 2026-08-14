"""Manager-owned Antigravity main-thread execution bridge with diagnostic tools and Viewport HUD."""

from __future__ import absolute_import

import builtins
import contextlib
import io
import json
import os
import shutil
import time
import traceback


FEATURE_ID = "developer.antigravity_bridge"
FEATURE_NAME = "Antigravity MotionBuilder Bridge"
POLL_INTERVAL_MS = 200
HEARTBEAT_INTERVAL_SECONDS = 2.0
BADGE_OBJECT_NAME = "MobuAntigravityBridgeDebugBadge"
BADGE_WIDTH = 136
BADGE_HEIGHT = 26
BADGE_MARGIN = 12

SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
BRIDGE_ROOT = os.path.join(SCRIPTS_ROOT, ".antigravity_mobu_bridge")
COMMANDS_DIR = os.path.join(BRIDGE_ROOT, "commands")
RUNNING_DIR = os.path.join(BRIDGE_ROOT, "running")
DONE_DIR = os.path.join(BRIDGE_ROOT, "done")
RESULTS_DIR = os.path.join(BRIDGE_ROOT, "results")
CAPTURES_DIR = os.path.join(BRIDGE_ROOT, "captures")
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


def _stamp_id():
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


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
        CAPTURES_DIR,
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
    class AntigravityBadge(QtWidgets.QWidget):
        def __init__(self, parent):
            super(AntigravityBadge, self).__init__(parent)
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
                # Modern sleek dark pill background
                painter.setBrush(QtGui.QColor(16, 24, 32, 220))
                painter.drawRoundedRect(self.rect(), 6.0, 6.0)

                # Antigravity Cyan/Emerald glowing status indicator dot
                painter.setBrush(QtGui.QColor(0, 229, 255))
                painter.drawEllipse(QtCore.QPointF(14.0, 13.0), 4.5, 4.5)

                # Crisp typography
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QtGui.QColor(224, 247, 250))
                painter.drawText(
                    QtCore.QRect(26, 0, BADGE_WIDTH - 30, BADGE_HEIGHT),
                    _qt_enum(QtCore, "AlignmentFlag", "AlignVCenter")
                    | _qt_enum(QtCore, "AlignmentFlag", "AlignLeft"),
                    "Antigravity Bridge",
                )
            finally:
                painter.end()

    return AntigravityBadge


class ViewportAntigravityIndicator(object):
    """Positions one input-transparent Antigravity badge from manager UI geometry events."""

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


class AntigravityCommandContext(object):
    """Rich development, introspection, and debugging helpers passed to bridge commands."""

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

    def get_sdk(self):
        try:
            import pyfbsdk

            return pyfbsdk
        except ImportError:
            return None

    def evaluate_scene(self):
        sdk = self.get_sdk()
        if sdk is not None:
            sdk.FBSystem().Scene.Evaluate()

    @contextlib.contextmanager
    def undo_transaction(self, name="Antigravity Action"):
        sdk = self.get_sdk()
        if sdk is not None:
            sdk.FBSystem().Scene.TransactionBegin(name)
        try:
            yield
        finally:
            if sdk is not None:
                sdk.FBSystem().Scene.TransactionEnd()

    def get_scene_summary(self):
        sdk = self.get_sdk()
        if sdk is None:
            return {"error": "pyfbsdk not available"}
        system = sdk.FBSystem()
        scene = system.Scene
        take = system.CurrentTake
        take_name = str(take.Name) if take is not None else None
        time_mode = sdk.FBTimeMode.kFBTimeModeDefault
        start_frame = None
        stop_frame = None
        fps = None
        if take is not None:
            try:
                time_span = take.LocalTimeSpan
                start_frame = int(time_span.GetStart().GetFrame(time_mode))
                stop_frame = int(time_span.GetStop().GetFrame(time_mode))
            except Exception:
                pass
        try:
            fps = float(system.CurrentTake.LocalTimeSpan.GetStop().GetFPS())
        except Exception:
            pass

        selected_models = []
        try:
            for component in scene.Components:
                if getattr(component, "Selected", False):
                    selected_models.append(
                        {
                            "name": str(getattr(component, "Name", "")),
                            "long_name": str(getattr(component, "LongName", "")),
                            "type": type(component).__name__,
                        }
                    )
        except Exception:
            pass

        cameras = []
        try:
            for cam in scene.Cameras:
                cameras.append(str(cam.Name))
        except Exception:
            pass

        return {
            "take": take_name,
            "start_frame": start_frame,
            "stop_frame": stop_frame,
            "fps": fps,
            "component_count": len(scene.Components) if scene.Components else 0,
            "selected_count": len(selected_models),
            "selected_models": selected_models,
            "cameras": cameras,
            "characters": [str(c.Name) for c in scene.Characters] if scene.Characters else [],
        }

    def get_selected_transforms(self):
        sdk = self.get_sdk()
        if sdk is None:
            return []
        system = sdk.FBSystem()
        results = []
        for component in system.Scene.Components:
            if not getattr(component, "Selected", False):
                continue
            item = {
                "name": str(getattr(component, "Name", "")),
                "long_name": str(getattr(component, "LongName", "")),
                "type": type(component).__name__,
            }
            if hasattr(component, "Translation"):
                try:
                    t = component.Translation
                    item["translation"] = [float(t[0]), float(t[1]), float(t[2])]
                except Exception:
                    pass
            if hasattr(component, "Rotation"):
                try:
                    r = component.Rotation
                    item["rotation"] = [float(r[0]), float(r[1]), float(r[2])]
                except Exception:
                    pass
            if hasattr(component, "Scaling"):
                try:
                    s = component.Scaling
                    item["scaling"] = [float(s[0]), float(s[1]), float(s[2])]
                except Exception:
                    pass
            results.append(item)
        return results

    def get_fcurve_summary(self, property_name=None):
        sdk = self.get_sdk()
        if sdk is None:
            return []
        system = sdk.FBSystem()
        results = []
        for component in system.Scene.Components:
            if not getattr(component, "Selected", False):
                continue
            anim_node = getattr(component, "AnimationNode", None)
            if anim_node is None:
                continue
            comp_info = {"name": str(component.Name), "nodes": []}
            for node in anim_node.Nodes:
                node_name = str(node.Name)
                if property_name and property_name.lower() not in node_name.lower():
                    continue
                node_info = {"name": node_name, "channels": []}
                for sub_node in node.Nodes:
                    fcurve = getattr(sub_node, "FCurve", None)
                    key_count = len(fcurve.Keys) if fcurve is not None else 0
                    node_info["channels"].append(
                        {
                            "name": str(sub_node.Name),
                            "key_count": key_count,
                        }
                    )
                comp_info["nodes"].append(node_info)
            results.append(comp_info)
        return results

    def capture_viewport(self, output_path=None, width=1920, height=1080):
        """Captures active MotionBuilder viewport snapshot and writes to PNG."""
        _ensure_directory(CAPTURES_DIR)
        if output_path is None:
            output_path = os.path.join(
                CAPTURES_DIR, "viewport_%s.png" % _stamp_id()
            )
        output_path = os.path.abspath(output_path)

        sdk = self.get_sdk()
        # Method 1: Try Qt widget grab from viewer attachment
        grabbed_via_qt = False
        try:
            attachment = self.service.context.find_ui_surface_attachment("viewer")
            if attachment is not None:
                host, _ = attachment
                if _is_valid_qobject(host) and hasattr(host, "grab"):
                    pixmap = host.grab()
                    if pixmap is not None and not pixmap.isNull():
                        pixmap.save(output_path, "PNG")
                        grabbed_via_qt = os.path.isfile(output_path)
        except Exception:
            pass

        # Method 2: If Qt grab didn't run, use FBVideoGrabber
        if not grabbed_via_qt and sdk is not None:
            try:
                grabber = sdk.FBVideoGrabber()
                image = grabber.RenderSnapshot(
                    int(width),
                    int(height),
                    False,
                    True,
                    False,
                    False,
                    False,
                    True,
                    True,
                )
                if image is not None:
                    tif_path = output_path + ".tif"
                    try:
                        if image.WriteToTif(tif_path, "", True):
                            try:
                                _QtCore, QtGui, _QtWidgets = _qt_modules()
                                qimg = QtGui.QImage(tif_path)
                                if not qimg.isNull():
                                    qimg.save(output_path, "PNG")
                                    try:
                                        os.remove(tif_path)
                                    except OSError:
                                        pass
                                else:
                                    output_path = tif_path
                            except Exception:
                                output_path = tif_path
                    finally:
                        image.FBDelete()
            except Exception as e:
                self.log("FBVideoGrabber capture error:", e)

        if os.path.isfile(output_path):
            file_size = os.path.getsize(output_path)
            self.log("Viewport captured to:", output_path, "(%d bytes)" % file_size)
            return {
                "ok": True,
                "path": output_path,
                "size_bytes": file_size,
                "timestamp": _timestamp(),
            }
        return {
            "ok": False,
            "error": "Failed to capture viewport snapshot",
            "path": output_path,
        }


class AntigravityMotionBuilderBridgeService(object):
    """Main-thread bridge service executing file payloads with full environment helpers."""

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
            else ViewportAntigravityIndicator(context, qt_modules=modules)
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
        _append_log("antigravity bridge started")
        self._record("antigravity_bridge_started")
        return self

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.timer.stop()
        self.indicator.stop()
        self._write_status("stopped")
        _append_log("antigravity bridge stopped")
        self._record("antigravity_bridge_stopped")

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
                "version": "1.0.0",
                "bridge_root": BRIDGE_ROOT,
                "commands_dir": COMMANDS_DIR,
                "results_dir": RESULTS_DIR,
                "captures_dir": CAPTURES_DIR,
                "logs_dir": LOGS_DIR,
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
        stamp = _stamp_id()
        return os.path.join(RESULTS_DIR, "%s_%s.json" % (root, stamp))

    def _execute_command(self, running_path):
        command_name = os.path.basename(running_path)
        bridge_context = AntigravityCommandContext(self, command_name)
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
                "__name__": "__antigravity_mobu_command__",
                "BRIDGE": bridge_context,
                "bridge": bridge_context,
                "set_result": bridge_context.set_result,
                "bridge_log": bridge_context.log,
                "capture_viewport": bridge_context.capture_viewport,
                "get_scene_summary": bridge_context.get_scene_summary,
                "get_selected_transforms": bridge_context.get_selected_transforms,
                "get_fcurve_summary": bridge_context.get_fcurve_summary,
                "evaluate_scene": bridge_context.evaluate_scene,
                "undo_transaction": bridge_context.undo_transaction,
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
            _append_log("antigravity bridge internal error: %s" % self.last_error)
            self._record("antigravity_bridge_internal_error", error=self.last_error)
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


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.close()
    _SERVICE = AntigravityMotionBuilderBridgeService(context)
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
