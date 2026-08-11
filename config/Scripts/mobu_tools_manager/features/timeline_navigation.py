"""Manager-owned commands for navigating the current take timeline."""

from __future__ import absolute_import


TAKE_NAVIGATION_LABEL = "Timeline Navigation"

FEATURE_ID = "input.timeline_navigation_hotkeys"
HOTKEY_FEATURES = {
    (True, False, "UP"): "animation.timeline_step_forward_10_frames",
    (True, False, "DOWN"): "animation.timeline_step_backward_10_frames",
    (True, False, "LEFT"): "animation.timeline_go_to_take_start",
    (True, False, "RIGHT"): "animation.timeline_go_to_take_end",
    (False, True, "UP"): "animation.timeline_step_forward_fps",
    (False, True, "DOWN"): "animation.timeline_step_backward_fps",
    (False, True, "LEFT"): "animation.timeline_previous_marker",
    (False, True, "RIGHT"): "animation.timeline_next_marker",
}

_SERVICE = None


def _sdk_module():
    import pyfbsdk

    return pyfbsdk


def _frame_bounds(take, time_mode):
    """Return inclusive current-take frame bounds, or raise a useful error."""
    if take is None:
        raise RuntimeError("No current take.")
    try:
        span = take.LocalTimeSpan
        first = int(span.GetStart().GetFrame(time_mode))
        last = int(span.GetStop().GetFrame(time_mode))
    except Exception as error:
        raise RuntimeError("Could not read the current take frame range.") from error
    if last < first:
        raise RuntimeError("The current take has an invalid frame range.")
    return first, last


def _goto_frame(player, sdk, frame, time_mode):
    target = sdk.FBTime(0)
    target.SetFrame(int(frame), time_mode)
    player.Goto(target)
    return target


def _current_frame(system, time_mode):
    try:
        return int(system.LocalTime.GetFrame(time_mode))
    except Exception as error:
        raise RuntimeError("Could not read the current timeline frame.") from error


def _report(kind, source_frame, target_frame, **details):
    result = {
        "ok": True,
        "kind": kind,
        "source_frame": int(source_frame),
        "target_frame": int(target_frame),
    }
    result.update(details)
    return result


def jump_by_frames(context, frame_delta, sdk=None):
    """Move by an integer number of frames without leaving the current take."""
    sdk = sdk or _sdk_module()
    player = context.player_control
    time_mode = player.GetTransportFps()
    first, last = _frame_bounds(context.take, time_mode)
    source = _current_frame(context.system, time_mode)
    target = max(first, min(last, source + int(frame_delta)))
    _goto_frame(player, sdk, target, time_mode)
    return _report(
        "frame_step",
        source,
        target,
        frame_delta=int(frame_delta),
        clamped=target != source + int(frame_delta),
    )


def jump_to_take_boundary(context, first, sdk=None):
    """Move to the inclusive first or last frame of the current take."""
    sdk = sdk or _sdk_module()
    player = context.player_control
    time_mode = player.GetTransportFps()
    start, end = _frame_bounds(context.take, time_mode)
    source = _current_frame(context.system, time_mode)
    target = start if first else end
    _goto_frame(player, sdk, target, time_mode)
    return _report(
        "take_start" if first else "take_end",
        source,
        target,
    )


def _transport_fps_frame_count(player, time_mode):
    try:
        value = float(player.GetTransportFpsValue(time_mode))
    except Exception as error:
        raise RuntimeError("Could not read the current transport frame rate.") from error
    frames = int(round(value))
    if frames <= 0:
        raise RuntimeError("The current transport frame rate is invalid.")
    return frames


def jump_by_transport_second(context, direction, sdk=None):
    """Move by the nearest whole-frame equivalent of one transport second."""
    player = context.player_control
    time_mode = player.GetTransportFps()
    frames = _transport_fps_frame_count(player, time_mode)
    direction = 1 if int(direction) >= 0 else -1
    report = jump_by_frames(context, direction * frames, sdk=sdk)
    report["kind"] = "transport_second_step"
    report["frame_delta"] = direction * frames
    report["transport_fps"] = frames
    return report


def jump_to_marker(context, direction, sdk=None):
    """Move to the next or previous time mark on the current take.

    This intentionally uses take-local marks, rather than global marks, so
    marker navigation always follows the active take.
    """
    sdk = sdk or _sdk_module()
    take = context.take
    if take is None:
        raise RuntimeError("No current take.")
    player = context.player_control
    time_mode = player.GetTransportFps()
    source = _current_frame(context.system, time_mode)
    method_name = (
        "GetNextTimeMarkIndex"
        if int(direction) >= 0
        else "GetPreviousTimeMarkIndex"
    )
    try:
        marker_index = int(getattr(take, method_name)())
    except Exception as error:
        raise RuntimeError("Could not find a marker on the current take.") from error
    if marker_index < 0:
        return {
            "ok": False,
            "kind": "next_marker" if int(direction) >= 0 else "previous_marker",
            "source_frame": source,
            "message": "No %s marker on the current take."
            % ("next" if int(direction) >= 0 else "previous"),
        }
    try:
        marker_time = take.GetTimeMarkTime(marker_index)
        target = int(marker_time.GetFrame(time_mode))
        player.Goto(sdk.FBTime(int(marker_time.Get())))
    except Exception as error:
        raise RuntimeError("Could not jump to the current take marker.") from error
    return _report(
        "next_marker" if int(direction) >= 0 else "previous_marker",
        source,
        target,
        marker_index=marker_index,
    )


def jump_forward_10_frames(context):
    return jump_by_frames(context, 10)


def jump_backward_10_frames(context):
    return jump_by_frames(context, -10)


def jump_to_take_start(context):
    return jump_to_take_boundary(context, True)


def jump_to_take_end(context):
    return jump_to_take_boundary(context, False)


def jump_forward_transport_second(context):
    return jump_by_transport_second(context, 1)


def jump_backward_transport_second(context):
    return jump_by_transport_second(context, -1)


def jump_to_next_marker(context):
    return jump_to_marker(context, 1)


def jump_to_previous_marker(context):
    return jump_to_marker(context, -1)


class TimelineNavigationHotkeyService(object):
    """Route modifier-arrow navigation through the shared Qt input boundary."""

    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_feature_id = None
        self.last_error = None

    def start(self):
        if self.running:
            return self
        self.context.input.configure_timeline_navigation_launcher(
            self._callback,
        )
        self.running = True
        return self

    def stop(self):
        if self.context is not None:
            try:
                self.context.input.clear_timeline_navigation_launcher(
                    self._callback,
                )
            except Exception:
                pass
        self.running = False

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        callback = getattr(diagnostics, "record", None)
        if callable(callback):
            try:
                callback(event, FEATURE_ID, **data)
            except Exception:
                pass

    def handle_key(self, payload):
        if not self.running:
            return False
        payload = dict(payload or {})
        feature_id = HOTKEY_FEATURES.get(
            (
                bool(payload.get("shift")),
                bool(payload.get("control")),
                str(payload.get("key") or "").upper(),
            )
        )
        if feature_id is None:
            return False
        try:
            from mobu_tools_manager import dispatch

            dispatch(feature_id)
        except Exception as error:
            self.last_error = str(error)
            self._record(
                "timeline_navigation_hotkey_error",
                feature_id=feature_id,
                error=self.last_error,
            )
            return False
        self.last_feature_id = feature_id
        self.last_error = None
        self._record(
            "timeline_navigation_hotkey_dispatched",
            feature_id=feature_id,
        )
        return True

    def status(self):
        return {
            "running": self.running,
            "bindings": dict(
                (
                    "%s+%s" % (
                        "Shift" if shift else "Ctrl",
                        key.title(),
                    ),
                    feature_id,
                )
                for (shift, _control, key), feature_id in HOTKEY_FEATURES.items()
            ),
            "last_feature_id": self.last_feature_id,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = TimelineNavigationHotkeyService(context)
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
