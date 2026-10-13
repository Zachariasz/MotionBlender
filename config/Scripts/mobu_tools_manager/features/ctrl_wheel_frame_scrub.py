"""Ctrl+wheel timeline frame scrubbing managed by the shared runtime.

Replaces the legacy ``custom/CtrlWheelFrameScrub.py`` controller, which
installed its own ``WH_MOUSE_LL`` hook, a 15 ms polling timer, and a builtins
singleton. This service uses the runtime's shared native wheel capture and the
single shared Qt application event filter.
"""

from __future__ import absolute_import
import time

# Constants
FEATURE_ID = "input.ctrl_wheel_frame_scrub"
VK_LCONTROL = 0xA2
CTRL_VIRTUAL_KEYS = (VK_LCONTROL,)
MOUSE_BUTTON_VIRTUAL_KEYS = (0x01, 0x02, 0x04)
INVERT_WHEEL_DIRECTION = False
FRAMES_PER_WHEEL_STEP = 1
STOP_PLAYBACK_WHEN_SCRUBBING = True
QT_DEDUP_SECONDS = 0.08
_SERVICE = None


def _qt_modules():
    """Return (QtCore, QtWidgets) preferring PySide6, falling back to PySide2."""
    try:
        from PySide6 import QtCore, QtWidgets
        return QtCore, QtWidgets
    except ImportError:
        pass
    try:
        from PySide2 import QtCore, QtWidgets
        return QtCore, QtWidgets
    except ImportError:
        raise ImportError("CtrlWheelFrameScrubService requires PySide6 or PySide2")


def _event_value(QtCore, name):
    """Get event type value from QtCore.QEvent.Type or QtCore.QEvent."""
    group = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    value = getattr(group, name, None)
    if value is not None:
        return value
    return getattr(QtCore.QEvent, name, None)


def _wheel_delta(event):
    """Extract wheel delta from event, trying angleDelta().y(), delta(), pixelDelta().y()."""
    for method in ("angleDelta", "delta", "pixelDelta"):
        try:
            delta_val = getattr(event, method)()
            if hasattr(delta_val, "y"):
                y_val = delta_val.y()
                if y_val != 0:
                    return int(y_val)
            else:
                if delta_val != 0:
                    return int(delta_val)
        except Exception:
            continue
    return 0


class CtrlWheelFrameScrubService(object):
    def __init__(self, context):
        self.context = context
        self.running = False
        self._native_wheel_token = None
        self._last_native_time = 0.0
        self.last_moved = 0
        self.last_error = None
        QtCore, _ = _qt_modules()
        self._wheel_event = _event_value(QtCore, "Wheel")

    def _record(self, event, **data):
        try:
            self.context.diagnostics.record(event, FEATURE_ID, **data)
        except Exception:
            pass

    def start(self):
        if self.running:
            return self
        try:
            self.context.add_ui_event_observer(self._observe_ui_event)
        except Exception as e:
            self._record("ctrl_wheel_frame_scrub_observer_error", error=str(e))
        try:
            self._native_wheel_token = self.context.input.add_native_wheel_observer(
                self._observe_native_wheel, CTRL_VIRTUAL_KEYS
            )
        except Exception as e:
            self.last_error = str(e)
            self._record("ctrl_wheel_frame_scrub_native_capture_error", error=str(e))
        self.running = True
        self._record("ctrl_wheel_frame_scrub_started")
        return self

    def stop(self):
        try:
            self.context.remove_ui_event_observer(self._observe_ui_event)
        except Exception:
            pass
        if self._native_wheel_token is not None:
            try:
                self.context.input.remove_native_wheel_observer(self._native_wheel_token)
            except Exception:
                pass
            self._native_wheel_token = None
        self.running = False
        self._record("ctrl_wheel_frame_scrub_stopped")

    def _mouse_button_down(self):
        try:
            for vk in MOUSE_BUTTON_VIRTUAL_KEYS:
                if self.context.input.virtual_keys_are_down((vk,)):
                    return True
            return False
        except Exception:
            return False

    def scrub_by_wheel_delta(self, delta):
        if not self.running or not delta or self._mouse_button_down():
            return False
        notches = max(1, abs(int(delta)) // 120)
        steps = notches * max(1, int(FRAMES_PER_WHEEL_STEP))
        direction = 1 if delta > 0 else -1
        if INVERT_WHEEL_DIRECTION:
            direction = -direction
        try:
            player = self.context.player_control
            if STOP_PLAYBACK_WHEN_SCRUBBING and player.IsPlaying:
                player.Stop()
            moved = 0
            for _ in range(steps):
                if direction > 0:
                    ok = player.StepForward()
                else:
                    ok = player.StepBackward()
                if ok is False:
                    break
                moved += direction
            self.last_moved = moved
            self.last_error = None
            return True
        except Exception as error:
            self.last_error = str(error)
            self._record("ctrl_wheel_frame_scrub_error", error=str(error))
            return False

    def _observe_native_wheel(self, delta):
        self._last_native_time = time.perf_counter()
        return self.scrub_by_wheel_delta(delta)

    def _observe_ui_event(self, watched, event):
        try:
            if not self.running or self._wheel_event is None:
                return False
            if event.type() != self._wheel_event:
                return False
            if not self.context.input.virtual_keys_are_down(CTRL_VIRTUAL_KEYS):
                return False
            if time.perf_counter() - self._last_native_time < QT_DEDUP_SECONDS:
                event.accept()
                return True
            consumed = self.scrub_by_wheel_delta(_wheel_delta(event))
            if consumed:
                event.accept()
            return consumed
        except Exception:
            return False

    def status(self):
        return {
            "running": self.running,
            "native_wheel_registered": self._native_wheel_token is not None,
            "last_moved": self.last_moved,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = CtrlWheelFrameScrubService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.stop()
    _SERVICE = None


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
