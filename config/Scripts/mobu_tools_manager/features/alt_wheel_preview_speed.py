"""Alt+wheel playback speed control managed by the shared runtime."""

from __future__ import absolute_import


FEATURE_ID = "input.alt_wheel_preview_speed"
TOOL_NAME = "Alt Wheel Preview Speed"
OVERLAY_OBJECT_NAME = "MobuAltWheelPreviewSpeedOverlay"
OVERLAY_HOLD_MS = 1100
OVERLAY_BOTTOM_MARGIN = 24
DEFAULT_OVERLAY_WIDTH = 132
DEFAULT_OVERLAY_HEIGHT = 30
VK_LMENU = 0xA4
SPEED_EPSILON = 0.005

# Change this to True if you want wheel scrolling to use custom smooth values
# instead of the discrete transport speed steps below.
USE_SMOOTH_SPEED = False
SMOOTH_SPEED_STEP = 0.10
SMOOTH_MIN_SPEED = 0.10
SMOOTH_MAX_SPEED = 4.00

SPEEDS = (
    (0.10, "0.1x"),
    (0.20, "0.2x"),
    (0.25, "0.25x"),
    (0.33, "0.33x"),
    (0.50, "0.5x"),
    (1.00, "1x"),
    (1.50, "1.5x"),
    (2.00, "2x"),
    (2.50, "2.5x"),
    (3.00, "3x"),
    (3.50, "3.5x"),
    (4.00, "4x"),
)

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


def _clamp(value, minimum, maximum):
    if maximum < minimum:
        return minimum
    return max(minimum, min(maximum, value))


def _speed_label(speed):
    for candidate, label in SPEEDS:
        if abs(candidate - float(speed)) < SPEED_EPSILON:
            return label
    return ("%.2f" % float(speed)).rstrip("0").rstrip(".") + "x"


def _wheel_delta(event):
    try:
        delta = event.angleDelta().y()
        if delta:
            return int(delta)
    except Exception:
        pass

    try:
        delta = event.delta()
        if delta:
            return int(delta)
    except Exception:
        pass

    try:
        delta = event.pixelDelta().y()
        if delta:
            return int(delta)
    except Exception:
        pass

    return 0


def _make_overlay_class(QtCore, QtWidgets):
    class SpeedOverlay(QtWidgets.QLabel):
        def __init__(self, parent):
            QtWidgets.QLabel.__init__(self, parent)
            self.setObjectName(OVERLAY_OBJECT_NAME)
            self.setAlignment(
                _qt_enum(QtCore, "AlignmentFlag", "AlignCenter")
            )
            self.setMinimumWidth(DEFAULT_OVERLAY_WIDTH)
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
                    "WA_ShowWithoutActivating",
                ),
                True,
            )
            self.setFocusPolicy(_qt_enum(QtCore, "FocusPolicy", "NoFocus"))
            self.setStyleSheet(
                "QLabel {"
                "background-color: rgba(18, 18, 18, 205);"
                "color: white;"
                "border: 1px solid rgba(255, 255, 255, 95);"
                "border-radius: 4px;"
                "padding: 6px 10px;"
                "font-size: 13px;"
                "}"
            )

    return SpeedOverlay


class AltWheelPreviewSpeedService(object):
    def __init__(
        self,
        context,
        qt_modules=None,
        overlay_factory=None,
        alt_state_callback=None,
        use_smooth_speed=None,
    ):
        self.context = context
        modules = qt_modules or _qt_modules()
        self.QtCore, self.QtGui, self.QtWidgets = modules
        self._overlay_factory = overlay_factory
        self._overlay_class = None
        self._alt_state_callback = alt_state_callback
        self.use_smooth_speed = (
            bool(USE_SMOOTH_SPEED)
            if use_smooth_speed is None
            else bool(use_smooth_speed)
        )
        self._observer = self._observe_ui_event
        self._hide_timer = self.QtCore.QTimer(context.qt_application)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_status)
        self._wheel_event = _event_value(self.QtCore, "Wheel")
        self._geometry_events = set(
            value
            for value in (
                _event_value(self.QtCore, "Resize"),
                _event_value(self.QtCore, "Move"),
                _event_value(self.QtCore, "Show"),
                _event_value(self.QtCore, "LayoutRequest"),
                _event_value(self.QtCore, "WindowActivate"),
                _event_value(self.QtCore, "ApplicationActivate"),
            )
            if value is not None
        )
        self.overlay = None
        self.geometry = None
        self.running = False
        self.last_speed = None
        self.last_direction = None
        self.last_steps = 0
        self.last_error = None
        self._last_status_text = None

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        callback = getattr(diagnostics, "record", None)
        if callable(callback):
            try:
                callback(event, FEATURE_ID, **data)
            except Exception:
                pass

    def start(self):
        if self.running:
            return self
        self.context.add_ui_event_observer(self._observer)
        self.running = True
        try:
            self.set_speed(1.0, show_status=False)
        except Exception as error:
            self.last_error = str(error)
            self._record("alt_wheel_preview_speed_start_error", error=str(error))
        self.hide_status()
        self._record("alt_wheel_preview_speed_started")
        return self

    def stop(self):
        if self.context is not None:
            try:
                self.context.remove_ui_event_observer(self._observer)
            except Exception:
                pass
        try:
            self._hide_timer.stop()
        except Exception:
            pass
        try:
            self._hide_timer.timeout.disconnect(self.hide_status)
        except Exception:
            pass
        self._destroy_overlay()
        try:
            self._hide_timer.deleteLater()
        except Exception:
            pass
        self.running = False
        self._record("alt_wheel_preview_speed_stopped")

    def _create_overlay(self, parent):
        if _is_valid_qobject(self.overlay):
            return self.overlay
        if self._overlay_factory is not None:
            self.overlay = self._overlay_factory(parent)
        else:
            if self._overlay_class is None:
                self._overlay_class = _make_overlay_class(
                    self.QtCore,
                    self.QtWidgets,
                )
            self.overlay = self._overlay_class(parent)
        if _is_valid_qobject(self.overlay):
            same_parent = _safe(
                lambda: self.overlay.parentWidget() == parent,
                False,
            )
            if not same_parent:
                _safe(lambda: self.overlay.setParent(parent))
        return self.overlay

    def _destroy_overlay(self):
        overlay = self.overlay
        self.overlay = None
        self.geometry = None
        self._last_status_text = None
        if overlay is None:
            return
        _safe(overlay.hide)
        _safe(lambda: overlay.setParent(None))
        _safe(overlay.close)
        _safe(overlay.deleteLater)

    def _sync_attachment(self):
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
            _safe(lambda: self.overlay.hide())
            return False
        if (
            geometry[2] <= DEFAULT_OVERLAY_WIDTH
            or geometry[3] <= DEFAULT_OVERLAY_HEIGHT
        ):
            self.geometry = None
            _safe(lambda: self.overlay.hide())
            return False
        if _is_valid_qobject(self.overlay):
            same_parent = _safe(
                lambda: self.overlay.parentWidget() == host,
                False,
            )
            if not same_parent:
                self._destroy_overlay()
        self.geometry = geometry
        return _is_valid_qobject(self._create_overlay(host))

    def _overlay_size(self):
        width = int(_safe(lambda: self.overlay.width(), 0) or 0)
        height = int(_safe(lambda: self.overlay.height(), 0) or 0)
        if width <= 0:
            width = DEFAULT_OVERLAY_WIDTH
        if height <= 0:
            height = DEFAULT_OVERLAY_HEIGHT
        return width, height

    def _position_status_text(self, text):
        if not self._sync_attachment():
            return False
        overlay = self.overlay
        _safe(lambda: overlay.setText(text))
        _safe(overlay.adjustSize)
        width, height = self._overlay_size()
        x, y, viewport_width, viewport_height = self.geometry
        left = x + int((viewport_width - width) * 0.5)
        top = y + viewport_height - height - OVERLAY_BOTTOM_MARGIN
        left = _clamp(left, x, x + viewport_width - width)
        top = _clamp(top, y, y + viewport_height - height)
        _safe(lambda: overlay.move(left, top))
        _safe(overlay.show)
        _safe(overlay.raise_)
        return True

    def _overlay_visible(self):
        return _is_valid_qobject(self.overlay) and bool(
            _safe(lambda: self.overlay.isVisible(), False)
        )

    def _left_alt_down(self):
        if callable(self._alt_state_callback):
            return bool(self._alt_state_callback())
        input_router = getattr(self.context, "input", None)
        callback = getattr(input_router, "virtual_keys_are_down", None)
        if callable(callback):
            try:
                return bool(callback((VK_LMENU,)))
            except Exception:
                pass
        try:
            modifiers = self.QtWidgets.QApplication.keyboardModifiers()
            alt = _qt_enum(self.QtCore, "KeyboardModifier", "AltModifier")
            return bool(modifiers & alt)
        except Exception:
            return False

    def _current_speed(self):
        try:
            return float(self.context.player_control.GetPlaySpeed())
        except Exception:
            return 1.0

    def _next_discrete_speed(self, direction):
        current_speed = self._current_speed()
        if direction > 0:
            for speed, _label in SPEEDS:
                if speed > current_speed + SPEED_EPSILON:
                    return speed
            return SPEEDS[-1][0]
        for speed, _label in reversed(SPEEDS):
            if speed < current_speed - SPEED_EPSILON:
                return speed
        return SPEEDS[0][0]

    def _next_smooth_speed(self, direction):
        current_speed = self._current_speed()
        next_speed = current_speed + (SMOOTH_SPEED_STEP * direction)
        next_speed = _clamp(next_speed, SMOOTH_MIN_SPEED, SMOOTH_MAX_SPEED)
        return round(next_speed, 2)

    def _speed_for_wheel_direction(self, direction):
        if self.use_smooth_speed:
            return self._next_smooth_speed(direction)
        return self._next_discrete_speed(direction)

    def set_speed(self, speed, show_status=False):
        self.context.player_control.SetPlaySpeed(float(speed))
        applied_speed = self._current_speed()
        self.last_speed = applied_speed
        self.last_error = None
        if show_status:
            self._show_status(applied_speed)
        return applied_speed

    def _show_status(self, speed=None):
        if speed is None:
            speed = self._current_speed()
        text = "Preview speed %s" % _speed_label(speed)
        self._last_status_text = text
        if self._position_status_text(text):
            self._hide_timer.start(OVERLAY_HOLD_MS)

    def hide_status(self):
        _safe(lambda: self.overlay.hide())

    def change_by_wheel_delta(self, delta):
        if not self.running or not delta:
            return False
        steps = max(1, int(abs(delta) / 120))
        direction = 1 if delta > 0 else -1
        applied_speed = None
        try:
            for _index in range(steps):
                applied_speed = self.set_speed(
                    self._speed_for_wheel_direction(direction),
                    show_status=False,
                )
            if applied_speed is not None:
                self.last_direction = direction
                self.last_steps = steps
                self._show_status(applied_speed)
                self._record(
                    "alt_wheel_preview_speed_changed",
                    speed=applied_speed,
                    direction=direction,
                    steps=steps,
                    smooth=bool(self.use_smooth_speed),
                )
                return True
        except Exception as error:
            self.last_error = str(error)
            self._record(
                "alt_wheel_preview_speed_change_error",
                error=str(error),
            )
        return False

    def _observe_ui_event(self, watched, event):
        if not self.running or watched is self.overlay:
            return False
        event_type = _safe(event.type, None)
        if event_type == self._wheel_event:
            if not self._left_alt_down():
                return False
            delta = _wheel_delta(event)
            if not delta:
                return False
            consumed = self.change_by_wheel_delta(delta)
            if consumed:
                _safe(event.accept)
            return consumed
        if event_type in self._geometry_events and self._overlay_visible():
            self._position_status_text(self._last_status_text or "")
        return False

    def status(self):
        return {
            "running": bool(self.running),
            "current_speed": self._current_speed(),
            "use_smooth_speed": bool(self.use_smooth_speed),
            "viewer_attached": bool(
                self.geometry is not None and _is_valid_qobject(self.overlay)
            ),
            "overlay_visible": bool(self._overlay_visible()),
            "last_direction": self.last_direction,
            "last_steps": self.last_steps,
            "last_error": self.last_error,
        }

    status_payload = status


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = AltWheelPreviewSpeedService(context)
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
