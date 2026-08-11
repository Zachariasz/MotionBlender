"""Manager-owned Fast Render button for MotionBuilder's Viewer toolbar."""

from __future__ import absolute_import

import re

try:
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import isValid as _is_valid
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from shiboken2 import isValid as _is_valid


FEATURE_ID = "animation.render_side_front"
ROW_ACCESSIBLE_NAME = "ButtonBarWithRightBar"
CONTAINER_OBJECT_NAME = "mobu_tools_manager_fast_render_container"
BUTTON_OBJECT_NAME = "mobu_tools_manager_fast_render"
BUTTON_TEXT = "Fast Render"
BUTTON_WIDTH = 78
BUTTON_GAP = 14
RETRY_INTERVAL_MS = 500
BUTTON_STYLE = (
    "QToolButton {"
    " background-color: #5c5c5c;"
    " border: 1px solid transparent;"
    " }"
    " QToolButton:hover {"
    " border-color: palette(highlight);"
    " }"
)
_SPACE = re.compile(r"\s+")


def _event_value(name):
    qevent = QtCore.QEvent
    scoped = getattr(qevent, "Type", qevent)
    value = getattr(qevent, name, None)
    if value is None:
        value = getattr(scoped, name, None)
    return value


def _normalized(value):
    value = str(value or "").replace("&", "").strip().casefold()
    return _SPACE.sub(" ", value).strip(" :")


def _widget_values(widget):
    values = []
    for getter_name in (
        "currentText",
        "text",
        "accessibleName",
        "windowTitle",
        "toolTip",
        "objectName",
    ):
        try:
            value = str(getattr(widget, getter_name)() or "").strip()
        except Exception:
            value = ""
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _has_exact_label(widget, label):
    expected = _normalized(label)
    return any(_normalized(value) == expected for value in _widget_values(widget))


def _valid(widget):
    if widget is None:
        return False
    try:
        return bool(_is_valid(widget))
    except Exception:
        try:
            widget.objectName()
            return True
        except Exception:
            return False


def _visible(widget):
    if not _valid(widget):
        return False
    try:
        return bool(widget.isVisible())
    except Exception:
        return False


def _widgets_below(widget):
    if not _valid(widget):
        return ()
    try:
        return tuple(widget.findChildren(QtWidgets.QWidget))
    except Exception:
        return ()


def _direct_widget_children(widget):
    if not _valid(widget):
        return ()
    try:
        return tuple(
            child
            for child in widget.children()
            if isinstance(child, QtWidgets.QWidget)
        )
    except Exception:
        return ()


def _first_labeled_widget(widgets, label):
    for widget in widgets:
        if _visible(widget) and _has_exact_label(widget, label):
            return widget
    return None


def _camera_aliases(camera_name):
    normalized = _normalized(camera_name)
    aliases = {normalized}
    producer_prefix = "producer "
    if normalized.startswith(producer_prefix):
        aliases.add(normalized[len(producer_prefix):])
    return aliases


def _camera_name_from_viewer(host, camera_names):
    aliases = {}
    for camera_name in camera_names:
        for alias in _camera_aliases(camera_name):
            aliases.setdefault(alias, camera_name)
    matches = []
    for widget in _widgets_below(host):
        if not _visible(widget):
            continue
        for priority, getter_name in enumerate(("currentText", "text", "accessibleName")):
            try:
                value = _normalized(getattr(widget, getter_name)())
            except Exception:
                continue
            camera_name = aliases.get(value)
            if camera_name:
                matches.append((priority, camera_name))
                break
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


class ViewerToolbarController(QtCore.QObject):
    """Own one reload-safe Fast Render control beside native Renderer."""

    REFRESH_EVENTS = tuple(
        value
        for value in (
            _event_value("FocusIn"),
            _event_value("WindowActivate"),
            _event_value("Show"),
            _event_value("Hide"),
            _event_value("Resize"),
            _event_value("ChildAdded"),
            _event_value("ChildRemoved"),
            _event_value("LayoutRequest"),
        )
        if value is not None
    )

    def __init__(self, manager, ui_context):
        QtCore.QObject.__init__(self)
        self.manager = manager
        self.ui_context = ui_context
        self.container = None
        self.button = None
        self.viewer_host = None
        self.refresh_pending = False
        self.started = False
        self.retry_timer = QtCore.QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._refresh)

    def start(self):
        if self.started:
            return self
        self.started = True
        self.ui_context.add_event_observer(self._on_ui_event)
        self._schedule_refresh()
        return self

    def stop(self):
        if not self.started:
            return
        self.started = False
        self.refresh_pending = False
        self.retry_timer.stop()
        self.ui_context.remove_event_observer(self._on_ui_event)
        self._detach_controls()
        self.viewer_host = None

    def refresh(self):
        self._schedule_refresh()

    def _schedule_refresh(self):
        if not self.started or self.refresh_pending:
            return
        self.refresh_pending = True
        QtCore.QTimer.singleShot(0, self._refresh)

    def _schedule_retry(self):
        if not self.started or self.retry_timer.isActive():
            return
        self.retry_timer.start(RETRY_INTERVAL_MS)

    def _on_ui_event(self, watched, event):
        del watched
        try:
            if event.type() in self.REFRESH_EVENTS:
                self._schedule_refresh()
        except Exception:
            pass
        return False

    def _find_viewer_toolbar(self):
        app = self.ui_context.app
        if app is None:
            return None
        try:
            top_levels = tuple(app.topLevelWidgets())
        except Exception:
            return None
        for top_level in top_levels:
            for row in (top_level,) + _widgets_below(top_level):
                if not _visible(row):
                    continue
                if not _has_exact_label(row, ROW_ACCESSIBLE_NAME):
                    continue
                children = _direct_widget_children(row)
                view_control = _first_labeled_widget(children, "View")
                display_control = _first_labeled_widget(children, "Display")
                renderer_control = _first_labeled_widget(children, "Renderer")
                if (
                    view_control is None
                    or display_control is None
                    or renderer_control is None
                ):
                    continue
                try:
                    host = row.parentWidget()
                    if not _valid(host):
                        continue
                    row_geometry = row.geometry()
                    renderer_geometry = renderer_control.geometry()
                    toolbar_snapshot = {
                        "x": int(row_geometry.x()),
                        "y": int(row_geometry.y()) + int(renderer_geometry.y()),
                        "renderer_right": int(renderer_geometry.right()) + 1,
                        "renderer_height": int(renderer_geometry.height()),
                        "host_width": int(host.width()),
                    }
                    if not _valid(self.container):
                        self._attach_controls(
                            host,
                            toolbar_snapshot["renderer_height"],
                        )
                    self.viewer_host = host
                except RuntimeError:
                    self._detach_controls()
                    continue
                return toolbar_snapshot
        return None

    def _current_viewer_host(self):
        # Reacquire the stable Viewer pane from our owned child. MotionBuilder
        # may replace the native toolbar and invalidate its Python wrapper.
        if _valid(self.container):
            try:
                host = self.container.parentWidget()
            except Exception:
                host = None
            if _valid(host):
                self.viewer_host = host
                return host
        if _valid(self.viewer_host):
            return self.viewer_host
        self.viewer_host = None
        self._find_viewer_toolbar()
        if _valid(self.container):
            try:
                host = self.container.parentWidget()
            except Exception:
                host = None
            if _valid(host):
                self.viewer_host = host
                return host
        return self.viewer_host if _valid(self.viewer_host) else None

    def _detach_controls(self):
        container = self.container
        self.container = None
        self.button = None
        if not _valid(container):
            return
        try:
            container.hide()
            container.setParent(None)
            container.deleteLater()
        except Exception:
            pass

    def _attach_controls(self, host, height):
        self._detach_controls()
        control_height = max(20, int(height))
        container = QtWidgets.QWidget(host)
        container.setObjectName(CONTAINER_OBJECT_NAME)
        container.setAccessibleName("Managed Fast Render command")
        container.setFixedSize(BUTTON_WIDTH, control_height)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        button = QtWidgets.QToolButton(container)
        button.setObjectName(BUTTON_OBJECT_NAME)
        button.setAccessibleName(BUTTON_TEXT)
        button.setText(BUTTON_TEXT)
        button.setAutoRaise(True)
        button.setFixedSize(BUTTON_WIDTH, control_height)
        button.setStyleSheet(BUTTON_STYLE)
        button.setToolTip(
            "Render the current take from the active Viewer camera to "
            "<take>_<camera>.mov using QuickTime Animation."
        )
        button.clicked.connect(self._run_fast_render)
        layout.addWidget(button)

        self.container = container
        self.button = button

    def _position_controls(self, toolbar_snapshot):
        if not _valid(self.container):
            return
        try:
            x_position = (
                int(toolbar_snapshot["x"])
                + int(toolbar_snapshot["renderer_right"])
                + BUTTON_GAP
            )
            maximum_x = max(
                0,
                int(toolbar_snapshot["host_width"])
                - int(self.container.width())
                - 2,
            )
            self.container.move(
                min(x_position, maximum_x),
                int(toolbar_snapshot["y"]),
            )
            self.container.raise_()
        except Exception:
            pass

    def _refresh(self):
        self.refresh_pending = False
        if not self.started:
            return
        toolbar_snapshot = self._find_viewer_toolbar()
        if toolbar_snapshot is None:
            self.viewer_host = None
            self._detach_controls()
            self._schedule_retry()
            return
        self.retry_timer.stop()
        self._position_controls(toolbar_snapshot)
        if not _valid(self.container) or not _valid(self.button):
            self._schedule_retry()
            return
        try:
            self.button.setEnabled(self.manager.is_enabled(FEATURE_ID))
            self.container.show()
            self.container.raise_()
        except RuntimeError:
            self._detach_controls()
            self._schedule_retry()

    def _scene_camera_names(self):
        names = []
        try:
            cameras = self.manager.runtime.scene.Cameras
        except Exception:
            cameras = ()
        for camera in cameras:
            try:
                name = str(camera.Name or "").strip()
            except Exception:
                name = ""
            if name and name not in names:
                names.append(name)
        return tuple(names)

    def _switcher_camera_name(self):
        try:
            renderer = self.manager.runtime.scene.Renderer
            if not bool(renderer.IsCameraSwitcherInPane(0)):
                return None
            camera = self.manager._sdk().FBCameraSwitcher().CurrentCamera
            return str(camera.Name or "").strip() if camera is not None else None
        except Exception:
            return None

    def _active_camera_name(self):
        camera_name = _camera_name_from_viewer(
            self._current_viewer_host(),
            self._scene_camera_names(),
        )
        return camera_name or self._switcher_camera_name()

    def _run_fast_render(self):
        camera_name = self._active_camera_name()
        invocation = {"camera_name": camera_name} if camera_name else {}
        try:
            self.button.setEnabled(False)
        except Exception:
            pass
        try:
            self.manager.dispatch(
                FEATURE_ID,
                invocation=invocation,
            )
        finally:
            self._schedule_refresh()
