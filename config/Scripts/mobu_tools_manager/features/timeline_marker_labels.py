"""Names above the current take's time marks in the main Timeline.

This is a manager-native resident service.  It observes MotionBuilder UI events
through the manager's single application event filter and owns only one
transparent child overlay plus one coalescing, single-shot timer.
"""

from __future__ import absolute_import


FEATURE_ID = "animation.timeline_marker_labels"
OVERLAY_OBJECT_NAME = "MobuTimelineMarkerLabelsOverlay"
MAX_LABEL_WIDTH = 180
LABEL_PADDING_X = 4
LABEL_GAP = 4
MARKER_EDIT_SETTLE_MS = 250
MARKER_CENTER_OFFSET_X = 3.0

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
    qevent = QtCore.QEvent
    group = getattr(qevent, "Type", qevent)
    value = getattr(qevent, name, None)
    if value is None:
        value = getattr(group, name, None)
    return value


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


def _time_ticks(value):
    """Convert an FBTime-like value to integer SDK ticks."""
    if value is None:
        return None
    result = _safe(value.Get, None)
    if result is None:
        result = _safe(lambda: int(value), None)
    try:
        return int(result)
    except (TypeError, ValueError):
        return None


def _color_components(value):
    components = []
    for index in range(3):
        component = _safe(lambda index=index: value[index], 1.0)
        try:
            component = float(component)
        except (TypeError, ValueError):
            component = 1.0
        if component <= 1.0:
            component *= 255.0
        components.append(max(0, min(255, int(round(component)))))
    return tuple(components)


def _collect_marker_snapshot(take):
    """Read a take once and retain only immutable marker primitives."""
    if take is None:
        return ()
    count = _safe(take.GetTimeMarkCount, 0)
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        count = 0
    markers = []
    for index in range(count):
        ticks = _time_ticks(
            _safe(lambda index=index: take.GetTimeMarkTime(index), None)
        )
        if ticks is None:
            continue
        name = _safe(lambda index=index: take.GetTimeMarkName(index), "")
        name = " ".join(str(name or "").split())
        if not name:
            continue
        color = _color_components(
            _safe(lambda index=index: take.GetTimeMarkColor(index), None)
        )
        markers.append((ticks, name, color))
    markers.sort(key=lambda item: item[0])
    return tuple(markers)


def _collect_global_marker_snapshot(player):
    """Read global marks from FBPlayerControl into immutable primitives."""
    if player is None:
        return ()
    count = _safe(player.GetGlobalTimeMarkCount, 0)
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        count = 0
    markers = []
    for index in range(count):
        ticks = _time_ticks(
            _safe(lambda index=index: player.GetGlobalTimeMarkTime(index), None)
        )
        if ticks is None:
            continue
        name = _safe(
            lambda index=index: player.GetGlobalTimeMarkName(index),
            "",
        )
        name = " ".join(str(name or "").split())
        if not name:
            continue
        color = _color_components(
            _safe(
                lambda index=index: player.GetGlobalTimeMarkColor(index),
                None,
            )
        )
        markers.append((ticks, name, color))
    markers.sort(key=lambda item: item[0])
    return tuple(markers)


def _time_to_x(ticks, start_ticks, stop_ticks, width):
    """Map timeline ticks into the canonical TimeCursor surface."""
    try:
        span = float(stop_ticks - start_ticks)
        width = float(width)
    except (TypeError, ValueError):
        return None
    if span <= 0.0 or width <= 1.0:
        return None
    ratio = float(ticks - start_ticks) / span
    if ratio < 0.0 or ratio > 1.0:
        return None
    return ratio * (width - 1.0)


def _marker_center_x(ticks, start_ticks, stop_ticks, width):
    """Map time to the visual center of MotionBuilder's native mark icon."""
    marker_x = _time_to_x(ticks, start_ticks, stop_ticks, width)
    if marker_x is None:
        return None
    return max(
        0.0,
        min(float(width) - 1.0, marker_x + MARKER_CENTER_OFFSET_X),
    )


def _label_lanes(entries, width, lane_count, gap=LABEL_GAP):
    """Lay out ``(x, label_width, payload)`` entries with minimal overlap."""
    width = max(1.0, float(width))
    lane_count = max(1, int(lane_count))
    right_edges = [-float("inf")] * lane_count
    result = []
    for marker_x, label_width, payload in sorted(entries, key=lambda item: item[0]):
        label_width = min(max(1.0, float(label_width)), width)
        ideal_left = max(
            0.0,
            min(float(marker_x) - label_width * 0.5, width - label_width),
        )
        choices = []
        for lane, right_edge in enumerate(right_edges):
            left = max(ideal_left, right_edge + float(gap))
            if left + label_width <= width:
                choices.append((abs(left - ideal_left), lane, left))
        if choices:
            _distance, lane, left = min(choices)
        else:
            lane = min(range(lane_count), key=lambda item: right_edges[item])
            left = ideal_left
        right_edges[lane] = left + label_width
        result.append((float(marker_x), left, label_width, lane, payload))
    return tuple(result)


def _make_overlay_class(QtCore, QtGui, QtWidgets):
    transparent_mouse = _qt_enum(
        QtCore, "WidgetAttribute", "WA_TransparentForMouseEvents"
    )
    translucent_background = _qt_enum(
        QtCore, "WidgetAttribute", "WA_TranslucentBackground"
    )
    no_system_background = _qt_enum(
        QtCore, "WidgetAttribute", "WA_NoSystemBackground"
    )
    show_without_activating = _qt_enum(
        QtCore, "WidgetAttribute", "WA_ShowWithoutActivating"
    )
    no_focus = _qt_enum(QtCore, "FocusPolicy", "NoFocus")
    align_center = _qt_enum(QtCore, "AlignmentFlag", "AlignCenter")
    antialiasing = getattr(
        getattr(QtGui.QPainter, "RenderHint", QtGui.QPainter),
        "Antialiasing",
    )

    class TimelineMarkerLabelsOverlay(QtWidgets.QWidget):
        def __init__(self, parent):
            super(TimelineMarkerLabelsOverlay, self).__init__(parent)
            self.setObjectName(OVERLAY_OBJECT_NAME)
            self.setAttribute(transparent_mouse, True)
            self.setAttribute(translucent_background, True)
            self.setAttribute(no_system_background, True)
            self.setAttribute(show_without_activating, True)
            self.setFocusPolicy(no_focus)
            self._state = (None, None, ())

        def set_state(self, start_ticks, stop_ticks, markers):
            state = (start_ticks, stop_ticks, tuple(markers))
            if state == self._state:
                return False
            self._state = state
            self.update()
            return True

        def clear(self):
            return self.set_state(None, None, ())

        def paintEvent(self, event):
            del event
            start_ticks, stop_ticks, markers = self._state
            if start_ticks is None or stop_ticks is None or not markers:
                return
            width = int(self.width())
            height = int(self.height())
            if width <= 1 or height <= 8:
                return

            painter = QtGui.QPainter(self)
            try:
                painter.setRenderHint(antialiasing, True)
                font = painter.font()
                point_size = _safe(font.pointSizeF, -1.0)
                if point_size and point_size > 8.0:
                    font.setPointSizeF(max(8.0, point_size - 1.0))
                painter.setFont(font)
                metrics = QtGui.QFontMetrics(font)
                text_height = max(10, int(metrics.height()))
                label_height = text_height + 4
                lane_count = max(1, min(2, (height - 4) // (label_height + 2)))
                entries = []
                for ticks, name, color in markers:
                    marker_x = _marker_center_x(
                        ticks, start_ticks, stop_ticks, width
                    )
                    if marker_x is None:
                        continue
                    text = metrics.elidedText(
                        name,
                        _qt_enum(QtCore, "TextElideMode", "ElideRight"),
                        MAX_LABEL_WIDTH - (2 * LABEL_PADDING_X),
                    )
                    text_width = _safe(
                        lambda: metrics.horizontalAdvance(text),
                        _safe(lambda: metrics.width(text), 1),
                    )
                    entries.append(
                        (
                            marker_x,
                            min(
                                MAX_LABEL_WIDTH,
                                int(text_width) + 2 * LABEL_PADDING_X,
                            ),
                            (text, color),
                        )
                    )

                for marker_x, left, label_width, lane, payload in _label_lanes(
                    entries, width, lane_count
                ):
                    text, color = payload
                    top = 2 + lane * (label_height + 2)
                    rect = QtCore.QRectF(
                        left,
                        float(top),
                        label_width,
                        float(label_height),
                    )
                    marker_color = QtGui.QColor(*color)
                    display_color = marker_color
                    if display_color.lightness() < 100:
                        display_color = marker_color.lighter(500)
                    if display_color.lightness() < 100:
                        display_color = QtGui.QColor(150, 150, 150)
                    text_color = QtGui.QColor(245, 245, 245)
                    painter.setPen(QtGui.QPen(display_color, 1.0))
                    painter.setBrush(QtGui.QColor(20, 20, 20, 210))
                    painter.drawRoundedRect(rect, 3.0, 3.0)
                    painter.setPen(text_color)
                    painter.drawText(rect, align_center, text)
                    painter.setPen(QtGui.QPen(display_color, 1.0))
                    anchor_y = min(float(height - 1), rect.bottom() + 3.0)
                    painter.drawLine(
                        QtCore.QPointF(marker_x, rect.bottom()),
                        QtCore.QPointF(marker_x, anchor_y),
                    )
            finally:
                painter.end()

    return TimelineMarkerLabelsOverlay


class TimelineMarkerLabelService(object):
    def __init__(self, context, qt_modules=None, overlay_factory=None):
        self.context = context
        modules = qt_modules or _qt_modules()
        self.QtCore, self.QtGui, self.QtWidgets = modules
        self._overlay_factory = overlay_factory
        self._overlay_class = None
        self._observer = self._observe_ui_event
        self._timer = self.QtCore.QTimer(context.qt_application)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh_now)
        self._hide_event = _event_value(self.QtCore, "Hide")
        self._show_event = _event_value(self.QtCore, "Show")
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
                _event_value(self.QtCore, "Show"),
                _event_value(self.QtCore, "LayoutRequest"),
            )
            if value is not None
        )
        self._refresh_events = set(
            value
            for value in (
                _event_value(self.QtCore, "Wheel"),
                _event_value(self.QtCore, "MouseButtonRelease"),
            )
            if value is not None
        )
        self._discovery_events = set(self._activation_events)
        show_event = _event_value(self.QtCore, "Show")
        if show_event is not None:
            self._discovery_events.add(show_event)
        self.geometry = None
        self.overlay = None
        self.running = False
        self._discover_pending = False
        self.last_marker_count = 0
        self.last_take_marker_count = 0
        self.last_global_marker_count = 0
        self.last_error = None

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
        self._schedule(discover=True)
        self._record("timeline_marker_labels_started")
        return self

    def stop(self):
        if self.context is not None:
            try:
                self.context.remove_ui_event_observer(self._observer)
            except Exception:
                pass
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            self._timer.timeout.disconnect(self._refresh_now)
        except Exception:
            pass
        self._destroy_overlay()
        try:
            self._timer.deleteLater()
        except Exception:
            pass
        self.running = False
        self._record("timeline_marker_labels_stopped")

    def _schedule(self, discover=False, delay_ms=0):
        if not self.running:
            return
        self._discover_pending = self._discover_pending or bool(discover)
        try:
            delay_ms = max(0, int(delay_ms))
            if delay_ms > 0:
                self._timer.start(delay_ms)
            elif not self._timer.isActive():
                self._timer.start(0)
        except Exception:
            self._record("timeline_marker_labels_schedule_error")

    def _create_overlay(self, parent):
        if _is_valid_qobject(self.overlay):
            return self.overlay
        # Own a sibling of TimeCursor on its stable Transport Controls pane.
        # Never retain or parent directly to the volatile QOpenGLWidget.
        if self._overlay_factory is not None:
            overlay = self._overlay_factory(parent)
        else:
            if self._overlay_class is None:
                self._overlay_class = _make_overlay_class(
                    self.QtCore,
                    self.QtGui,
                    self.QtWidgets,
                )
            overlay = self._overlay_class(parent)
        self.overlay = overlay
        return overlay

    def _destroy_overlay(self):
        overlay = self.overlay
        self.overlay = None
        self.geometry = None
        if overlay is None:
            return
        _safe(overlay.clear)
        _safe(overlay.hide)
        _safe(lambda: overlay.setParent(None))
        _safe(overlay.close)
        _safe(overlay.deleteLater)

    def _sync_geometry(self):
        attachment = _safe(
            lambda: self.context.find_ui_surface_attachment("timeline"),
            None,
        )
        try:
            host, geometry = attachment
            x, y, width, height = tuple(geometry)
            geometry = (int(x), int(y), int(width), int(height))
            if not _is_valid_qobject(host):
                raise ValueError("invalid timeline host")
        except (TypeError, ValueError):
            self.geometry = None
            _safe(lambda: self.overlay.hide())
            return False
        if geometry[2] <= 20 or geometry[3] <= 10:
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
        overlay = self._create_overlay(host)
        if not _is_valid_qobject(overlay):
            return False
        rect = self.QtCore.QRect(*geometry)
        _safe(lambda: self.overlay.setGeometry(rect))
        return True

    def _sync_visibility(self):
        if not _is_valid_qobject(self.overlay):
            return False
        visible = self.geometry is not None
        if visible:
            _safe(self.overlay.show)
            _safe(self.overlay.raise_)
        else:
            _safe(self.overlay.hide)
        return visible

    def _interaction_active(self):
        input_router = getattr(self.context, "input", None)
        return getattr(input_router, "owner", None) is not None

    def _observe_ui_event(self, watched, event):
        if not self.running or watched is self.overlay:
            return False
        if self._interaction_active():
            return False
        event_type = _safe(event.type, None)
        if (
            event_type in self._activation_events
            or event_type in self._deactivation_events
        ):
            self._schedule(discover=True, delay_ms=50)

        if event_type in self._geometry_events or event_type in self._refresh_events:
            self._schedule(delay_ms=50)

        if event_type == self._hide_event:
            try:
                is_popup = isinstance(
                    watched,
                    (self.QtWidgets.QMenu, self.QtWidgets.QDialog),
                )
            except Exception:
                is_popup = False
            if is_popup:
                self._schedule(discover=True, delay_ms=MARKER_EDIT_SETTLE_MS)
        return False

    @staticmethod
    def _fallback_time_span(take):
        span = _safe(lambda: take.LocalTimeSpan, None)
        if span is None:
            return None, None
        start = _safe(span.GetStart, _safe(lambda: span.Start, None))
        stop = _safe(span.GetStop, _safe(lambda: span.Stop, None))
        return _time_ticks(start), _time_ticks(stop)

    def _refresh_now(self):
        if not self.running or self._interaction_active():
            return
        self._discover_pending = False
        if not self._sync_geometry() or self.overlay is None:
            return
        try:
            take = self.context.take
            player = self.context.player_control
            take_markers = _collect_marker_snapshot(take)
            global_markers = _collect_global_marker_snapshot(player)
            markers = tuple(
                sorted(
                    take_markers + global_markers,
                    key=lambda item: item[0],
                )
            )
            start_ticks = _time_ticks(player.ZoomWindowStart)
            stop_ticks = _time_ticks(player.ZoomWindowStop)
            if (
                start_ticks is None
                or stop_ticks is None
                or stop_ticks <= start_ticks
            ):
                start_ticks, stop_ticks = self._fallback_time_span(take)
            self.overlay.set_state(start_ticks, stop_ticks, markers)
            self._sync_visibility()
            self.last_marker_count = len(markers)
            self.last_take_marker_count = len(take_markers)
            self.last_global_marker_count = len(global_markers)
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)
            self.last_marker_count = 0
            self.last_take_marker_count = 0
            self.last_global_marker_count = 0
            _safe(self.overlay.clear)
            self._record(
                "timeline_marker_labels_refresh_error",
                error=self.last_error,
            )

    def status(self):
        return {
            "running": bool(self.running),
            "surface_attached": bool(
                self.geometry is not None and _is_valid_qobject(self.overlay)
            ),
            "marker_count": int(self.last_marker_count),
            "take_marker_count": int(self.last_take_marker_count),
            "global_marker_count": int(self.last_global_marker_count),
            "timer_active": bool(_safe(self._timer.isActive, False)),
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = TimelineMarkerLabelService(context)
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
