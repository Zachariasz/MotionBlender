"""Per-take alternate Timeline range command and Timeline RMB context menu integration.

The command is exposed through Timeline Quick Favorites and the Timeline RMB
context menu. The current and alternate ``FBTake.LocalTimeSpan`` values live in
one custom string property on the take, so the per-take state follows the source
FBX.
"""

from __future__ import absolute_import

import json

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import getCppPointer as _get_cpp_pointer
    from shiboken6 import isValid as _is_valid
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        from shiboken2 import getCppPointer as _get_cpp_pointer
        from shiboken2 import isValid as _is_valid
    except ImportError:
        QtCore = None
        QtGui = None
        QtWidgets = None
        _get_cpp_pointer = None
        _is_valid = None


FEATURE_ID = "animation.timeline_toggle_alt_range"
PROPERTY_NAME = "MTM Timeline Alternate Range"
PROPERTY_VERSION = 1
MAIN_SLOT = "main"
ALT_SLOT = "alternate"
ACTION_OBJECT_NAME = "mobu_tools_manager_timeline_toggle_alt_range"
ACTION_LABEL = "Toggle Alternate Range"

_SERVICE = None


def _qt_modules():
    global QtCore, QtGui, QtWidgets
    if QtCore is None or QtGui is None or QtWidgets is None:
        try:
            from PySide6 import QtCore as _QtCore, QtGui as _QtGui, QtWidgets as _QtWidgets
        except ImportError:
            try:
                from PySide2 import QtCore as _QtCore, QtGui as _QtGui, QtWidgets as _QtWidgets
            except ImportError:
                _QtCore = _QtGui = _QtWidgets = None
        QtCore, QtGui, QtWidgets = _QtCore, _QtGui, _QtWidgets
    return QtCore, QtGui, QtWidgets


def _sdk_module():
    import pyfbsdk

    return pyfbsdk


def _safe(callback, default=None):
    try:
        return callback()
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError):
        return default


def _is_valid_qobject(value):
    if value is None:
        return False
    if _is_valid is not None:
        try:
            return bool(_is_valid(value))
        except Exception:
            pass
    try:
        return bool(_safe(lambda: value.metaObject() is not None, False) or hasattr(value, "objectName"))
    except Exception:
        return False


def _native_pointer(widget):
    if widget is None or _get_cpp_pointer is None:
        return None
    try:
        return int(_get_cpp_pointer(widget)[0])
    except Exception:
        return None


def _event_value(QtCoreModule, name):
    qevent = getattr(QtCoreModule, "QEvent", None)
    if qevent is None:
        return None
    scoped = getattr(qevent, "Type", qevent)
    value = getattr(qevent, name, None)
    if value is None:
        value = getattr(scoped, name, None)
    return value


def _time_range(take):
    """Return the current local range as immutable FBTime ticks."""
    if take is None:
        raise RuntimeError("No current take.")
    try:
        span = take.LocalTimeSpan
        start = int(span.GetStart().Get())
        stop = int(span.GetStop().Get())
    except Exception as error:
        raise RuntimeError("Could not read the current take Timeline range.") from error
    if stop < start:
        raise RuntimeError("The current take has an invalid Timeline range.")
    return start, stop


def _valid_range(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        start, stop = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None
    return (start, stop) if stop >= start else None


def _state_from_data(value):
    try:
        state = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    try:
        version = int(state.get("version", 0))
    except (TypeError, ValueError):
        return None
    if version != PROPERTY_VERSION:
        return None
    main_range = _valid_range(state.get(MAIN_SLOT))
    alt_range = _valid_range(state.get(ALT_SLOT))
    if main_range is None or alt_range is None:
        return None
    active = state.get("active")
    if active not in (MAIN_SLOT, ALT_SLOT):
        return None
    return {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: main_range,
        ALT_SLOT: alt_range,
        "active": active,
    }


def _state_property(take, sdk, create=False):
    try:
        property_list = take.PropertyList
        prop = property_list.Find(PROPERTY_NAME)
    except Exception as error:
        raise RuntimeError("Could not access the current take properties.") from error
    if prop is not None or not create:
        return prop
    try:
        prop = take.PropertyCreate(
            PROPERTY_NAME,
            sdk.FBPropertyType.kFBPT_charptr,
            "String",
            False,
            True,
            None,
        )
    except Exception as error:
        raise RuntimeError("Could not create the alternate range property.") from error
    if prop is None:
        raise RuntimeError("Could not create the alternate range property.")
    return prop


def read_state(take, sdk):
    """Read validated persisted state, or ``None`` for a new/corrupt take."""
    prop = _state_property(take, sdk, create=False)
    return None if prop is None else _state_from_data(_safe(lambda: prop.Data, ""))


def is_alternate_active(take, sdk=None):
    """Return whether ``take`` is currently showing its alternate range."""
    if take is None:
        return False
    state = read_state(take, sdk or _sdk_module())
    return bool(state and state["active"] == ALT_SLOT)


def quick_favorite_checked(context, sdk=None):
    """Provide the checked state when this command appears in Quick Favorites."""
    take = getattr(context, "take", None)
    return is_alternate_active(take, sdk=sdk)


def _new_state(current_range):
    return {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: tuple(current_range),
        ALT_SLOT: tuple(current_range),
        "active": MAIN_SLOT,
    }


def _write_state(take, sdk, state, prop=None):
    prop = prop or _state_property(take, sdk, create=True)
    payload = {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: list(state[MAIN_SLOT]),
        ALT_SLOT: list(state[ALT_SLOT]),
        "active": state["active"],
    }
    try:
        prop.Data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception as error:
        raise RuntimeError("Could not save the alternate Timeline range.") from error


def _set_time_range(take, sdk, time_range):
    start, stop = _valid_range(time_range) or (None, None)
    if start is None:
        raise RuntimeError("The saved alternate Timeline range is invalid.")
    try:
        take.LocalTimeSpan = sdk.FBTimeSpan(sdk.FBTime(start), sdk.FBTime(stop))
    except Exception as error:
        raise RuntimeError("Could not set the current take Timeline range.") from error


def _local_time_span_property(take):
    return _safe(lambda: take.PropertyList.Find("LocalTimeSpan"), None)


def toggle_alt_range(context, sdk=None):
    """Save edits to the active side, then swap to the other saved range.

    The first invocation initializes both sides from the current range and
    enters alternate mode without changing the visible range. The user can then
    edit Timeline start/end normally; the next invocation captures those edits
    and restores the original main range.
    """
    sdk = sdk or _sdk_module()
    take = getattr(context, "take", None)
    current_range = _time_range(take)
    state = read_state(take, sdk) or _new_state(current_range)
    active = state["active"]
    target = ALT_SLOT if active == MAIN_SLOT else MAIN_SLOT
    state_prop = _state_property(take, sdk, create=True)

    def swap():
        state[active] = current_range
        _set_time_range(take, sdk, state[target])
        state["active"] = target
        _write_state(take, sdk, state, prop=state_prop)

    undo_helper = getattr(context, "undo", None)
    if undo_helper is not None and hasattr(undo_helper, "begin"):
        transaction = undo_helper.begin("Toggle Timeline Alternate Range")
        transaction.add_property(_local_time_span_property(take))
        transaction.add_property(state_prop)
        try:
            swap()
        except Exception:
            transaction.cancel()
            raise
        else:
            transaction.commit()
    elif undo_helper is not None and hasattr(undo_helper, "scope"):
        with undo_helper.scope("Toggle Timeline Alternate Range"):
            swap()
    else:
        swap()

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None and hasattr(evaluation, "request"):
        evaluation.request()
    return {
        "ok": True,
        "kind": "timeline_alt_range_toggle",
        "active": target,
        "saved_range": tuple(current_range),
        "applied_range": tuple(state[target]),
    }


execute = toggle_alt_range


class TimelineAltRangeService(object):
    """Resident service that extends the Timeline RMB context menu.

    Observes UI events via the manager's single application filter and inserts
    a checkable action into MotionBuilder's native Timeline context menu.
    """

    def __init__(self, context, qt_modules=None):
        self.context = context
        modules = qt_modules or _qt_modules()
        self.QtCore, self.QtGui, self.QtWidgets = modules
        self._observer = self._observe_ui_event
        self.running = False
        self.context_menu_pending = False
        self.last_error = None
        self.context_menu = None
        self.context_action = None
        self.context_separator = None
        if self.QtCore is not None and hasattr(self.QtCore, "QTimer"):
            app = getattr(context, "qt_application", None)
            self._expiry_timer = self.QtCore.QTimer(app) if app is not None else self.QtCore.QTimer()
            self._expiry_timer.setSingleShot(True)
            self._expiry_timer.timeout.connect(self._expire_context_menu_request)
        else:
            self._expiry_timer = None

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
        if hasattr(self.context, "add_ui_event_observer"):
            self.context.add_ui_event_observer(self._observer)
        self.running = True
        self._record("timeline_alt_range_service_started")
        return self

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.context_menu_pending = False
        if hasattr(self.context, "remove_ui_event_observer"):
            try:
                self.context.remove_ui_event_observer(self._observer)
            except Exception:
                pass
        if self._expiry_timer is not None:
            try:
                self._expiry_timer.stop()
            except Exception:
                pass
        self._release_context_menu(remove_actions=True)
        self._record("timeline_alt_range_service_stopped")

    def execute(self):
        return toggle_alt_range(self.context, sdk=self._sdk())

    def toggle(self):
        return self.execute()

    def is_alternate_active(self):
        take = getattr(self.context, "take", None)
        return is_alternate_active(take, sdk=self._sdk())

    def _sdk(self):
        return getattr(self.context, "sdk", None) or _sdk_module()

    def _is_enabled(self):
        manager = getattr(self.context, "manager", None)
        if manager is not None and hasattr(manager, "is_enabled"):
            try:
                return bool(manager.is_enabled(FEATURE_ID))
            except Exception:
                return True
        return True

    def _expire_context_menu_request(self):
        self.context_menu_pending = False

    def _is_cursor_over_timeline(self):
        if self.QtGui is None:
            return False
        try:
            cursor_pos = self.QtGui.QCursor.pos()
        except Exception:
            return False

        # 1. Check current surface geometry from context
        geom_fn = getattr(self.context, "current_ui_surface_geometry", None)
        if callable(geom_fn):
            try:
                rect = geom_fn("timeline")
                if rect and len(rect) == 4:
                    rx, ry, rw, rh = rect
                    if rx <= cursor_pos.x() <= rx + rw and ry <= cursor_pos.y() <= ry + rh:
                        return True
            except Exception:
                pass

        # 2. Check surface attachment
        attach_fn = getattr(self.context, "find_ui_surface_attachment", None)
        if callable(attach_fn):
            try:
                attach = attach_fn("timeline")
                if attach is not None:
                    host, rect = attach
                    if _is_valid_qobject(host) and rect and len(rect) == 4:
                        top_left = host.mapToGlobal(self.QtCore.QPoint(int(rect[0]), int(rect[1])))
                        if (
                            top_left.x() <= cursor_pos.x() <= top_left.x() + int(rect[2])
                            and top_left.y() <= cursor_pos.y() <= top_left.y() + int(rect[3])
                        ):
                            return True
            except Exception:
                pass

        # 3. Check ui_context snapshot
        ui_ctx = getattr(self.context, "ui_context", None)
        if isinstance(ui_ctx, dict):
            hovered = str(ui_ctx.get("hovered") or "").lower()
            active = str(ui_ctx.get("active") or "").lower()
            if hovered == "timeline" or active == "timeline":
                return True

        # 4. Check widget at cursor
        if self.QtWidgets is not None and hasattr(self.QtWidgets, "QApplication"):
            try:
                app = self.QtWidgets.QApplication.instance()
                if app is not None:
                    widget_at = app.widgetAt(cursor_pos)
                    if self._is_timeline_widget(widget_at):
                        return True
            except Exception:
                pass

        return False

    def _is_timeline_widget(self, widget):
        if not _is_valid_qobject(widget):
            return False

        attachment_fn = getattr(self.context, "find_ui_surface_attachment", None)
        if callable(attachment_fn):
            try:
                attachment = attachment_fn("timeline")
                if attachment is not None:
                    host = attachment[0]
                    if _is_valid_qobject(host):
                        if widget is host:
                            return True
                        host_ptr = _native_pointer(host)
                        if host_ptr is not None and _native_pointer(widget) == host_ptr:
                            return True
                        try:
                            if host.isAncestorOf(widget):
                                return True
                        except Exception:
                            pass
            except Exception:
                pass

        current = widget
        while current is not None:
            parts = []
            for name in ("objectName", "windowTitle", "accessibleName"):
                try:
                    val = getattr(current, name)()
                    if val:
                        parts.append(str(val))
                except Exception:
                    pass
            try:
                parts.append(current.metaObject().className())
            except Exception:
                parts.append(type(current).__name__)
            desc = " ".join(parts).lower()
            if any(
                key in desc
                for key in (
                    "timeline",
                    "transport",
                    "timecursor",
                    "time cursor",
                    "fptime",
                    "timebar",
                    "ruler",
                    "time_slider",
                    "timeslider",
                )
            ):
                return True
            try:
                current = current.parentWidget()
            except Exception:
                break

        return False

    def _observe_ui_event(self, watched, event):
        if self.QtCore is None:
            return False
        try:
            event_type = event.type()
        except Exception:
            return False

        context_menu_event = _event_value(self.QtCore, "ContextMenu")
        mouse_press_event = _event_value(self.QtCore, "MouseButtonPress")
        mouse_release_event = _event_value(self.QtCore, "MouseButtonRelease")
        show_event = _event_value(self.QtCore, "Show")

        right_click = False
        if event_type in (mouse_press_event, mouse_release_event):
            try:
                right_button = getattr(
                    getattr(self.QtCore.Qt, "MouseButton", self.QtCore.Qt),
                    "RightButton",
                )
                right_click = (event.button() == right_button)
            except Exception:
                right_click = False

        if (
            (event_type == context_menu_event or right_click)
            and (self._is_timeline_widget(watched) or self._is_cursor_over_timeline())
        ):
            self.context_menu_pending = True
            if self._expiry_timer is not None:
                self._expiry_timer.start(1000)
        elif (
            event_type == show_event
            and self.QtWidgets is not None
            and isinstance(watched, self.QtWidgets.QMenu)
        ):
            if (
                self.context_menu_pending
                or self._is_cursor_over_timeline()
                or self._is_timeline_widget(watched.parentWidget())
            ):
                self._extend_timeline_context_menu(watched)

        return False

    def _extend_timeline_context_menu(self, menu):
        self.context_menu_pending = False
        if self._expiry_timer is not None:
            try:
                self._expiry_timer.stop()
            except Exception:
                pass

        stale_actions = []
        try:
            for existing in menu.actions():
                if existing.objectName() == ACTION_OBJECT_NAME:
                    stale_actions.append(existing)
        except Exception:
            return

        self._release_context_menu(remove_actions=True)
        try:
            for stale in stale_actions:
                try:
                    menu.removeAction(stale)
                except Exception:
                    pass
                try:
                    stale.deleteLater()
                except Exception:
                    pass

            native_actions = list(menu.actions())
            first_native_action = native_actions[0] if native_actions else None

            action = menu.addAction(ACTION_LABEL)
            action.setObjectName(ACTION_OBJECT_NAME)
            action.setCheckable(True)
            checked = self.is_alternate_active()
            action.setChecked(checked)
            action.setToolTip(
                "Toggle between main and alternate Timeline start/end ranges for the current take."
            )
            action.setStatusTip(
                "Toggle between main and alternate Timeline start/end ranges for the current take."
            )
            action.setEnabled(self._is_enabled())
            action.triggered.connect(self._on_action_triggered)

            separator = menu.addSeparator()
            if first_native_action is not None:
                menu.insertAction(first_native_action, action)
                menu.insertAction(first_native_action, separator)

            menu.aboutToHide.connect(self._on_context_menu_hidden)
            self.context_menu = menu
            self.context_action = action
            self.context_separator = separator
        except Exception as error:
            self.last_error = str(error)
            self._release_context_menu(remove_actions=True)

    def _on_action_triggered(self, checked=False):
        del checked
        if not self.running:
            return
        manager = getattr(self.context, "manager", None)
        if manager is not None and hasattr(manager, "dispatch"):
            try:
                manager.dispatch(FEATURE_ID)
                return
            except Exception:
                pass
        self.execute()

    def _on_context_menu_hidden(self):
        self._release_context_menu(remove_actions=True)

    def _release_context_menu(self, remove_actions=False):
        menu = self.context_menu
        action = self.context_action
        separator = self.context_separator
        self.context_menu = None
        self.context_action = None
        self.context_separator = None

        if not _is_valid_qobject(menu):
            return

        try:
            menu.aboutToHide.disconnect(self._on_context_menu_hidden)
        except Exception:
            pass

        if not remove_actions:
            return

        for owned in (action, separator):
            if not _is_valid_qobject(owned):
                continue
            try:
                menu.removeAction(owned)
            except Exception:
                pass
            try:
                owned.deleteLater()
            except Exception:
                pass

    def status(self):
        return {
            "running": self.running,
            "active": self.is_alternate_active(),
            "last_error": self.last_error,
        }


def start(context, qt_modules=None):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = TimelineAltRangeService(context, qt_modules=qt_modules)
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

