"""Viewer-only display and picking-mode menu."""

from __future__ import absolute_import


FEATURE_ID = "viewer.display_mode_menu"
MENU_TITLE = "Viewer Display"
CURSOR_MENU_X_FRACTION = 5.0 / 6.0
LAST_OPTION_ATTR = "_mobu_tools_manager_viewer_display_menu_last_option"
ACTION_OPTIONS = (
    ("toggle_overlays", "Toggle Overlays", "action.viewer.cycle_picking_mode"),
    ("solid", "Solid", "action.viewer.shade.shaders"),
    ("wire", "Wire", "action.viewer.shade.wire"),
    ("toggle_x_ray", "Toggle X-Ray", "action.viewer.cycle_picking_mode"),
)
_ACTION_BY_ID = dict(
    (option_id, (label, action_name))
    for option_id, label, action_name in ACTION_OPTIONS
)
_ACTIVE_MENU = None
_SERVICE = None


def _qt_modules():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets


def _manager(context):
    manager = getattr(context, "manager", None)
    if manager is not None:
        return manager
    from mobu_tools_manager import get_manager

    return get_manager()


def _native_action_available(context, option_id):
    _label, action_name = _ACTION_BY_ID[option_id]
    exists = getattr(_manager(context), "native_action_exists", None)
    try:
        return not callable(exists) or bool(exists(action_name))
    except Exception:
        return False


def dispatch_action(context, option_id, manager=None):
    """Dispatch one declared action through MotionBuilder's 3D Renderer."""
    if option_id not in _ACTION_BY_ID:
        raise ValueError("Unknown Viewer display option: " + str(option_id))
    label, action_name = _ACTION_BY_ID[option_id]
    manager = manager or _manager(context)
    if manager is None:
        raise RuntimeError("MotionBuilder Tools Manager is unavailable")
    exists = getattr(manager, "native_action_exists", None)
    if callable(exists) and not exists(action_name):
        raise RuntimeError("Viewer action is unavailable: " + action_name)
    dispatch = getattr(manager, "dispatch_viewer_native_action", None)
    if not callable(dispatch):
        raise RuntimeError("Viewer native action dispatch is unavailable")
    dispatch(action_name)

    diagnostics = getattr(context, "diagnostics", None)
    record = getattr(diagnostics, "record", None)
    if callable(record):
        record(
            "viewer_display_menu_action_dispatched",
            FEATURE_ID,
            option=option_id,
            label=label,
            action=action_name,
            source="renderer_keyboard_input",
        )
    return {
        "option": option_id,
        "label": label,
        "action": action_name,
        "source": "renderer_keyboard_input",
    }


def _record_action_error(context, option_id, error):
    diagnostics = getattr(context, "diagnostics", None)
    record = getattr(diagnostics, "record", None)
    if callable(record):
        record(
            "viewer_display_menu_action_failed",
            FEATURE_ID,
            option=option_id,
            error=str(error),
        )


def _dispatch_safely(context, option_id):
    try:
        dispatch_action(context, option_id)
    except Exception as error:
        # Deferred callbacks must not escape through MotionBuilder's Qt loop.
        _record_action_error(context, option_id, error)


def last_option_id(context):
    """Return the last menu option selected during this manager session."""
    option_id = getattr(_manager(context), LAST_OPTION_ATTR, None)
    if option_id in _ACTION_BY_ID:
        return option_id
    return None


def remember_option(context, option_id):
    """Remember an option so it is centered under the next Z-menu cursor."""
    if option_id not in _ACTION_BY_ID:
        raise ValueError("Unknown Viewer display option: " + str(option_id))
    setattr(_manager(context), LAST_OPTION_ATTR, option_id)


class ViewerDisplayMenu(object):
    """Transient menu that applies Viewer state after it has closed."""

    def __init__(self, context, snapshot=None, parent=None):
        QtCore, QtGui, QtWidgets = _qt_modules()
        self.context = context
        self.QtCore = QtCore
        self.QtGui = QtGui
        snapshot = dict(snapshot or getattr(context, "ui_context", {}) or {})
        self.source_surface = (
            snapshot.get("surface")
            or snapshot.get("active_surface")
            or snapshot.get("hovered_widget")
            or snapshot.get("active_widget")
        )
        self.source_widget = (
            snapshot.get("hovered_widget") or snapshot.get("active_widget")
        )
        self.menu = QtWidgets.QMenu(parent)
        self.menu.setObjectName("motionbuilder_viewer_display_menu")
        self.menu.setWindowTitle(MENU_TITLE)
        self._actions = {}
        self._popup_anchor = None
        for option_id, label, action_name in ACTION_OPTIONS:
            action = self.menu.addAction(label)
            action.setEnabled(_native_action_available(context, option_id))
            action.triggered.connect(
                lambda _checked=False, selected=option_id: self._select(selected)
            )
            self._actions[option_id] = action
        self.menu.aboutToHide.connect(self._finish_hide)

    def popup(self):
        self._popup_anchor = self.QtCore.QPoint(self.QtGui.QCursor.pos())
        self.menu.popup(
            self._constrain_position(
                self._position_for_anchor(self._popup_anchor),
                self._popup_anchor,
            )
        )
        self.QtCore.QTimer.singleShot(0, self._realign)
        return self

    def close_safely(self):
        try:
            self.menu.close()
        except RuntimeError:
            pass

    def _select(self, option_id):
        remember_option(self.context, option_id)
        try:
            self.context.restore_editor_focus(
                self.source_surface,
                self.source_widget,
            )
        except Exception:
            pass
        # Queue from the action callback itself. QMenu can emit aboutToHide
        # before QAction.triggered, so aboutToHide must never own dispatch.
        self.close_safely()
        context = self.context
        self.QtCore.QTimer.singleShot(
            0,
            lambda: _dispatch_safely(context, option_id),
        )

    def _last_action(self):
        return self._actions.get(last_option_id(self.context))

    def _position_for_anchor(self, anchor):
        anchor = self.QtCore.QPoint(anchor)
        target = self._last_action()
        if target is None:
            return anchor
        self.menu.ensurePolished()
        self.menu.adjustSize()
        size = self.menu.sizeHint().expandedTo(self.menu.size())
        row = self.menu.actionGeometry(target)
        if row.height() <= 0 or size.width() <= 0:
            return anchor
        return self.QtCore.QPoint(
            int(round(anchor.x() - size.width() * CURSOR_MENU_X_FRACTION)),
            int(round(anchor.y() - row.center().y())),
        )

    def _constrain_position(self, position, anchor):
        screen = self.QtGui.QGuiApplication.screenAt(anchor)
        if screen is None:
            screen = self.QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return self.QtCore.QPoint(position)
        available = screen.availableGeometry()
        size = self.menu.sizeHint().expandedTo(self.menu.size())
        maximum_x = max(
            available.left(),
            available.right() - size.width() + 1,
        )
        maximum_y = max(
            available.top(),
            available.bottom() - size.height() + 1,
        )
        return self.QtCore.QPoint(
            max(available.left(), min(position.x(), maximum_x)),
            max(available.top(), min(position.y(), maximum_y)),
        )

    def _realign(self):
        if self._popup_anchor is None:
            return
        try:
            if not self.menu.isVisible():
                return
            position = self._constrain_position(
                self._position_for_anchor(self._popup_anchor),
                self._popup_anchor,
            )
            if self.menu.pos() != position:
                self.menu.move(position)
        except RuntimeError:
            # The popup may have closed before its single-shot realignment.
            return

    def _finish_hide(self):
        global _ACTIVE_MENU
        if _ACTIVE_MENU is self:
            _ACTIVE_MENU = None
        self._popup_anchor = None
        menu = self.menu

        def finish():
            try:
                menu.deleteLater()
            except RuntimeError:
                pass

        self.QtCore.QTimer.singleShot(0, finish)


def show(context):
    """Open the Viewer display menu at the cursor."""
    global _ACTIVE_MENU
    close()
    _QtCore, _QtGui, QtWidgets = _qt_modules()
    snapshot = dict(getattr(context, "ui_context", {}) or {})
    application = getattr(context, "qt_application", None)
    parent = None
    source_widget = snapshot.get("hovered_widget") or snapshot.get(
        "active_widget"
    )
    if source_widget is not None:
        try:
            parent = source_widget.window()
        except Exception:
            pass
    if application is not None:
        if parent is None:
            try:
                parent = application.activeWindow()
            except Exception:
                pass
    if parent is None:
        try:
            parent = QtWidgets.QApplication.activeWindow()
        except Exception:
            pass
    _ACTIVE_MENU = ViewerDisplayMenu(context, snapshot, parent)
    return _ACTIVE_MENU.popup()


def close():
    """Close the one transient menu, if it exists."""
    global _ACTIVE_MENU
    menu, _ACTIVE_MENU = _ACTIVE_MENU, None
    if menu is not None:
        menu.close_safely()


class ViewerDisplayMenuHotkeyService(object):
    """Own the Viewer-only Z binding through the shared input router."""

    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_error = None
        self._show_token = 0

    def start(self):
        if self.running:
            return self
        self.context.input.configure_viewer_display_menu_launcher(self._callback)
        self.running = True
        return self

    def stop(self):
        self._show_token += 1
        if self.context is not None:
            try:
                self.context.input.clear_viewer_display_menu_launcher(self._callback)
            except Exception:
                pass
        close()
        self.running = False

    def handle_key(self, _payload=None):
        if not self.running:
            return False
        snapshot = dict(getattr(self.context, "ui_context", {}) or {})
        if str(snapshot.get("hovered") or "").lower() != "viewer":
            return False
        self._show_token += 1
        token = self._show_token
        try:
            self.context.input.QtCore.QTimer.singleShot(
                0,
                lambda: self._show_after_key(token),
            )
        except Exception as error:
            self.last_error = str(error)
            return False
        return True

    def _show_after_key(self, token):
        if not self.running or token != self._show_token:
            return
        try:
            show(self.context)
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)

    def status(self):
        return {
            "running": self.running,
            "binding": "Z",
            "surface": "viewer",
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = ViewerDisplayMenuHotkeyService(context)
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
