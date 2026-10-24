"""Ctrl + RMB drag smooth timeline scrubbing with subframe precision.

Managed resident service that allows scrubbing the MotionBuilder timeline
by holding Ctrl and dragging horizontally with the Right Mouse Button (RMB).
Holding Shift scales scrubbing speed down by 10x for ultra-fine subframe adjustments.
Pressing Escape while dragging cancels and restores the original transport time.
"""

from __future__ import absolute_import

import time


FEATURE_ID = "input.ctrl_rmb_drag_scrub"
SERVICE_NAME = "Ctrl + RMB Drag Smooth Scrub"

VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
CTRL_VIRTUAL_KEYS = (VK_CONTROL, VK_LCONTROL, VK_RCONTROL)

VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
SHIFT_VIRTUAL_KEYS = (VK_SHIFT, VK_LSHIFT, VK_RSHIFT)

MOUSE_BUTTON_RIGHT = 0x02

PIXELS_PER_FRAME = 10.0
FINE_TUNE_MULTIPLIER = 0.1
DRAG_THRESHOLD = 3

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
        raise ImportError("CtrlRmbDragScrubService requires PySide6 or PySide2")


def _sdk_module():
    """Import pyfbsdk safely."""
    import pyfbsdk
    return pyfbsdk


def _event_value(QtCore, name):
    """Get event type integer value from QtCore.QEvent.Type or QtCore.QEvent."""
    group = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    value = getattr(group, name, None)
    if value is not None:
        return value
    return getattr(QtCore.QEvent, name, None)


def _extract_x(event):
    """Extract global horizontal X coordinate from QMouseEvent."""
    try:
        if hasattr(event, "globalPosition"):
            return float(event.globalPosition().toPoint().x())
    except Exception:
        pass
    try:
        if hasattr(event, "globalPos"):
            return float(event.globalPos().x())
    except Exception:
        pass
    try:
        if hasattr(event, "pos"):
            return float(event.pos().x())
    except Exception:
        pass
    return 0.0


class CtrlRmbDragScrubService(object):
    def __init__(self, context, sdk=None):
        self.context = context
        self._sdk = sdk
        self.running = False

        self._active = False
        self._is_dragging = False
        self._just_scrubbed = False

        self._start_x = 0.0
        self._start_ticks = 0
        self._start_time = None
        self._original_snap_mode = None
        self._last_ticks = None

        self.last_moved_frames = 0.0
        self.last_error = None

        QtCore, QtWidgets = _qt_modules()
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets

        self._mouse_press_event = _event_value(QtCore, "MouseButtonPress")
        self._mouse_move_event = _event_value(QtCore, "MouseMove")
        self._mouse_release_event = _event_value(QtCore, "MouseButtonRelease")
        self._context_menu_event = _event_value(QtCore, "ContextMenu")
        self._key_press_event = _event_value(QtCore, "KeyPress")

    def _get_sdk(self):
        if self._sdk is not None:
            return self._sdk
        return _sdk_module()

    def _record(self, event, **data):
        try:
            diagnostics = getattr(self.context, "diagnostics", None)
            if diagnostics and hasattr(diagnostics, "record"):
                diagnostics.record(event, FEATURE_ID, **data)
        except Exception:
            pass

    def start(self):
        if self.running:
            return self
        try:
            self.context.add_ui_event_observer(self._observe_ui_event)
            self.running = True
            self._record("ctrl_rmb_drag_scrub_started")
        except Exception as error:
            self.last_error = str(error)
            self._record("ctrl_rmb_drag_scrub_start_error", error=str(error))
        return self

    def stop(self):
        if not self.running:
            return
        try:
            self.context.remove_ui_event_observer(self._observe_ui_event)
        except Exception:
            pass
        self._cancel_active_drag()
        self.running = False
        self._record("ctrl_rmb_drag_scrub_stopped")

    def _is_ctrl_down(self, event=None):
        """Check if Ctrl is pressed via Qt modifiers or native virtual key state."""
        try:
            if event is not None and hasattr(event, "modifiers"):
                control_modifier = getattr(
                    getattr(self.QtCore.Qt, "KeyboardModifier", self.QtCore.Qt),
                    "ControlModifier",
                    None,
                )
                if control_modifier is not None and (event.modifiers() & control_modifier):
                    return True
        except Exception:
            pass
        try:
            input_router = getattr(self.context, "input", None)
            if input_router and hasattr(input_router, "virtual_keys_are_down"):
                if input_router.virtual_keys_are_down(CTRL_VIRTUAL_KEYS):
                    return True
        except Exception:
            pass
        return False

    def _is_shift_down(self, event=None):
        """Check if Shift is pressed via Qt modifiers or native virtual key state."""
        try:
            if event is not None and hasattr(event, "modifiers"):
                shift_modifier = getattr(
                    getattr(self.QtCore.Qt, "KeyboardModifier", self.QtCore.Qt),
                    "ShiftModifier",
                    None,
                )
                if shift_modifier is not None and (event.modifiers() & shift_modifier):
                    return True
        except Exception:
            pass
        try:
            input_router = getattr(self.context, "input", None)
            if input_router and hasattr(input_router, "virtual_keys_are_down"):
                if input_router.virtual_keys_are_down(SHIFT_VIRTUAL_KEYS):
                    return True
        except Exception:
            pass
        return False

    def _is_right_button(self, event):
        try:
            right_button = getattr(
                getattr(self.QtCore.Qt, "MouseButton", self.QtCore.Qt),
                "RightButton",
                None,
            )
            if right_button is not None and hasattr(event, "button"):
                return event.button() == right_button
        except Exception:
            pass
        return False

    def _ticks_per_frame(self, player, sdk):
        """Calculate ticks per single frame based on transport FPS."""
        try:
            time_mode = player.GetTransportFps()
            return abs(int(sdk.FBTime(0, 0, 0, 1, 0, time_mode).Get()))
        except Exception:
            pass
        try:
            return abs(int(sdk.FBTime(0, 0, 0, 1).Get()))
        except Exception:
            return 1537622000

    def _take_bounds_ticks(self, context, sdk):
        """Return (start_ticks, stop_ticks) for current take or None."""
        try:
            take = getattr(context, "take", None)
            if take is None:
                system = getattr(context, "system", None)
                if system and hasattr(system, "CurrentTake"):
                    take = system.CurrentTake
            if take is not None and hasattr(take, "LocalTimeSpan"):
                span = take.LocalTimeSpan
                return int(span.GetStart().Get()), int(span.GetStop().Get())
        except Exception:
            pass
        return None

    def _no_snap_enum(self, sdk):
        for candidate in ("kFBTransportSnapModeNoSnap", "SnapModeNoSnap"):
            if hasattr(sdk, candidate):
                return getattr(sdk, candidate)
        enum_type = getattr(sdk, "FBTransportSnapMode", None)
        if enum_type and hasattr(enum_type, "kFBTransportSnapModeNoSnap"):
            return getattr(enum_type, "kFBTransportSnapModeNoSnap")
        return None

    def _start_drag(self, event):
        sdk = self._get_sdk()
        player = getattr(self.context, "player_control", None)
        system = getattr(self.context, "system", None)

        self._active = True
        self._is_dragging = False
        self._just_scrubbed = False
        self._start_x = _extract_x(event)
        self.last_moved_frames = 0.0

        if player and getattr(player, "IsPlaying", False):
            try:
                player.Stop()
            except Exception:
                pass

        # Preserve and temporarily set SnapMode to No Snap for subframe precision
        self._original_snap_mode = getattr(player, "SnapMode", None) if player else None
        no_snap = self._no_snap_enum(sdk)
        if player and no_snap is not None and hasattr(player, "SnapMode"):
            try:
                player.SnapMode = no_snap
            except Exception:
                pass

        try:
            if system and hasattr(system, "LocalTime"):
                self._start_time = sdk.FBTime(system.LocalTime)
                self._start_ticks = int(self._start_time.Get())
            else:
                self._start_time = None
                self._start_ticks = 0
        except Exception:
            self._start_time = None
            self._start_ticks = 0

        self._last_ticks = self._start_ticks

    def _update_drag(self, event):
        if not self._active:
            return False

        current_x = _extract_x(event)
        dx = current_x - self._start_x

        if not self._is_dragging:
            if abs(dx) >= DRAG_THRESHOLD:
                self._is_dragging = True
            else:
                return True

        shift_held = self._is_shift_down(event)
        multiplier = FINE_TUNE_MULTIPLIER if shift_held else 1.0

        delta_frames = (dx / PIXELS_PER_FRAME) * multiplier
        self.last_moved_frames = delta_frames

        sdk = self._get_sdk()
        player = getattr(self.context, "player_control", None)
        system = getattr(self.context, "system", None)

        if player is None or sdk is None:
            return True

        ticks_per_frame = self._ticks_per_frame(player, sdk)
        delta_ticks = int(round(delta_frames * ticks_per_frame))
        target_ticks = self._start_ticks + delta_ticks

        bounds = self._take_bounds_ticks(self.context, sdk)
        if bounds is not None:
            start_bound, stop_bound = bounds
            target_ticks = max(start_bound, min(stop_bound, target_ticks))

        if target_ticks != self._last_ticks:
            self._last_ticks = target_ticks
            try:
                player.Goto(sdk.FBTime(target_ticks))
            except Exception as error:
                self.last_error = str(error)
                self._record("ctrl_rmb_drag_scrub_goto_error", error=str(error))
            try:
                if system and hasattr(system, "Scene") and hasattr(system.Scene, "Evaluate"):
                    system.Scene.Evaluate()
            except Exception:
                pass

        return True

    def _finish_drag(self):
        player = getattr(self.context, "player_control", None)
        if self._original_snap_mode is not None and player and hasattr(player, "SnapMode"):
            try:
                player.SnapMode = self._original_snap_mode
            except Exception:
                pass

        if self._is_dragging:
            self._just_scrubbed = True

        self._active = False
        self._is_dragging = False
        self._original_snap_mode = None

    def _cancel_active_drag(self):
        player = getattr(self.context, "player_control", None)
        if self._active and self._start_time is not None and player:
            try:
                player.Goto(self._start_time)
            except Exception:
                pass

        if self._original_snap_mode is not None and player and hasattr(player, "SnapMode"):
            try:
                player.SnapMode = self._original_snap_mode
            except Exception:
                pass

        self._active = False
        self._is_dragging = False
        self._original_snap_mode = None
        self._start_time = None

    def _observe_ui_event(self, watched, event):
        if not self.running or event is None:
            return False

        try:
            event_type = event.type()
        except Exception:
            return False

        # 1. Mouse Button Press
        if event_type == self._mouse_press_event:
            if self._is_right_button(event) and self._is_ctrl_down(event):
                self._start_drag(event)
                try:
                    event.accept()
                except Exception:
                    pass
                return True

        # 2. Mouse Move
        elif event_type == self._mouse_move_event:
            if self._active:
                handled = self._update_drag(event)
                if handled:
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return True

        # 3. Mouse Button Release
        elif event_type == self._mouse_release_event:
            if self._active and self._is_right_button(event):
                self._finish_drag()
                try:
                    event.accept()
                except Exception:
                    pass
                return True

        # 4. Context Menu Event (suppress RMB menu immediately after scrubbing)
        elif event_type == self._context_menu_event:
            if self._active or self._just_scrubbed:
                self._just_scrubbed = False
                try:
                    event.accept()
                except Exception:
                    pass
                return True

        # 5. Key Press (Escape cancels active drag)
        elif event_type == self._key_press_event:
            if self._active:
                try:
                    escape_key = getattr(
                        getattr(self.QtCore.Qt, "Key", self.QtCore.Qt),
                        "Key_Escape",
                        0x01000000,
                    )
                    if hasattr(event, "key") and event.key() == escape_key:
                        self._cancel_active_drag()
                        try:
                            event.accept()
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass

        return False

    def status(self):
        return {
            "running": self.running,
            "active": self._active,
            "is_dragging": self._is_dragging,
            "last_moved_frames": self.last_moved_frames,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = CtrlRmbDragScrubService(context)
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
