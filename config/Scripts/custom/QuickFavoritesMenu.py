"""Context-sensitive quick favorites popup for MotionBuilder 2026.

Assign this script to a MotionBuilder keyboard shortcut.  The favorites shown
depend on the editor under the mouse when the shortcut is pressed.
"""

from __future__ import print_function

import builtins
import ctypes
import os
import re
import sys
import traceback

from PySide6 import QtCore, QtGui, QtWidgets
from pyfbsdk import FBActionManager, FBMessageBox, FBSystem


TOOL_NAME = "Quick Favorites"
STATE_NAME = "_motionbuilder_quick_favorites_menu"
PENDING_STATE_NAME = "_motionbuilder_quick_favorites_pending"
NATIVE_ACTION_STATE_NAME = "_motionbuilder_quick_favorites_native_action"
NATIVE_ACTION_TEMP_KEYS = (
    (b"F11", 0x7A),
    (b"F10", 0x79),
    (b"F9", 0x78),
    (b"F12", 0x7B),
)

CONTEXT_VIEWER = "viewer"
CONTEXT_FCURVES = "fcurves"
CONTEXT_OTHER = "other"


def script(label, filename):
    """Create a favorite that runs a complete Python script."""
    return {
        "kind": "script",
        "label": label,
        "filename": filename,
    }


def function(label, filename, function_name):
    """Create a favorite that loads a file and calls one named function."""
    return {
        "kind": "function",
        "label": label,
        "filename": filename,
        "function": function_name,
    }


def callback(label, callable_object):
    """Create a favorite that calls an already available Python callable."""
    return {
        "kind": "callback",
        "label": label,
        "callback": callable_object,
    }


def action(label, action_name):
    """Create a favorite that runs a native MotionBuilder action."""
    return {
        "kind": "action",
        "label": label,
        "action": action_name,
    }


def separator():
    return {"kind": "separator"}


# ---------------------------------------------------------------------------
# Favorites configuration
#
# Add a whole script:
#     script("My Tool", "MyTool.py"),
#
# Call a named function from an import-safe script:
#     function("My Command", "MyLibrary.py", "my_command"),
#
# Call an already available Python callable:
#     callback("Select All", select_all),
#
# Run a native MotionBuilder keyboard-map action:
#     action("Object Mode", "action.viewer.pick_mode_object"),
# ---------------------------------------------------------------------------

FAVORITES = {
    CONTEXT_VIEWER: [
        action("Hide Gizmo", "action.viewer.pick_mode_object"),
        separator(),
        script("Camera Follow Selected", "LockCameraToSelected.py"),
    ],
    CONTEXT_FCURVES: [
        script("Select FCurve", "SelectFCurve.py"),
        action("Add Key", "action.fcurve.insert_key"),
        separator(),
        script("Apply Filter", "ApplyFilterToSelectedFCurves.py"),
        script(
            "Set Loop",
            "SetSelectedFCurvesInfiniteRepetition.py",
        ),
    ],
    CONTEXT_OTHER: [
        script("Duplicate", "Duplicate.py"),
        script("Rename Selected...", "RenameSelected.py"),
        separator(),
        script("Set Namespace...", "SetNamespace.py"),
        script("Remove Namespace...", "RemoveNamespace.py"),
        separator(),
        script("Bake Story Clips to Takes...", "BakeStoryClipsToTakes.py"),
        script("Export Custom...", "ExportCustom.py"),
    ],
}


CONTEXT_TITLES = {
    CONTEXT_VIEWER: "3D Viewer Favorites",
    CONTEXT_FCURVES: "FCurves Favorites",
    CONTEXT_OTHER: "General Favorites",
}

FCURVE_TOKENS = (
    "fcurvelayerview",
    "fcurvepropertyview",
    "fcurves",
    "curvelayout",
)

VIEWER_TOKENS = (
    "viewerwithrightbar",
    "toolindex_1 viewer",
)


def _script_directory():
    # MotionBuilder's shortcut runner compiles scripts with the correct source
    # filename, but it does not always add ``__file__`` to the global namespace.
    # The function code object keeps that filename (it is also what appears in
    # tracebacks), so use it as the host-safe fallback.
    candidates = [globals().get("__file__")]
    code = getattr(_script_directory, "__code__", None)
    if code is not None:
        candidates.append(getattr(code, "co_filename", None))

    for candidate in candidates:
        if not candidate or str(candidate).startswith("<"):
            continue
        source_path = os.path.abspath(str(candidate))
        source_directory = os.path.dirname(source_path)
        if os.path.isdir(source_directory):
            return source_directory

    # Last resort for hosts that compile with a synthetic filename: search the
    # Python paths MotionBuilder registered for this exact launcher file.
    for search_directory in sys.path:
        if not search_directory:
            continue
        for candidate in (
            os.path.join(search_directory, "QuickFavoritesMenu.py"),
            os.path.join(search_directory, "custom", "QuickFavoritesMenu.py"),
        ):
            if os.path.isfile(candidate):
                return os.path.dirname(os.path.abspath(candidate))

    raise RuntimeError("Could not locate the Quick Favorites script folder.")


def _widget_description(widget):
    parts = []
    seen = set()
    current = widget

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            meta = current.metaObject()
            if meta is not None:
                parts.append(str(meta.className()))
        except Exception:
            parts.append(type(current).__name__)

        for getter_name in (
            "objectName",
            "accessibleName",
            "windowTitle",
            "toolTip",
        ):
            try:
                value = getattr(current, getter_name)()
            except Exception:
                value = ""
            if value:
                parts.append(str(value))

        try:
            current = current.parentWidget()
        except Exception:
            current = None

    return " ".join(parts).lower()


def context_for_widget(widget):
    description = _widget_description(widget)

    if any(token in description for token in FCURVE_TOKENS):
        return CONTEXT_FCURVES

    if any(token in description for token in VIEWER_TOKENS):
        return CONTEXT_VIEWER

    return CONTEXT_OTHER


def _visible_editor_match(app, global_position):
    matches = []
    for widget in app.allWidgets():
        try:
            if not widget.isVisible():
                continue
            context = context_for_widget(widget)
            if context == CONTEXT_OTHER:
                continue
            top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
            global_rect = QtCore.QRect(top_left, widget.size())
            if global_rect.contains(global_position):
                matches.append(
                    (
                        global_rect.width() * global_rect.height(),
                        widget,
                        context,
                    )
                )
        except Exception:
            pass

    if matches:
        # The smallest matching editor surface is the most specific one.
        matches.sort(key=lambda match: match[0])
        return matches[0]
    return None


def _context_from_visible_editor_geometry(app, global_position):
    match = _visible_editor_match(app, global_position)
    if match is not None:
        return match[2]
    return CONTEXT_OTHER


def _focus_target_for_context(app, global_position, context):
    focused_widget = app.focusWidget()
    if focused_widget is not None:
        if context == CONTEXT_OTHER or context_for_widget(focused_widget) == context:
            return focused_widget

    match = _visible_editor_match(app, global_position)
    if match is not None and match[2] == context:
        return match[1]

    widget = app.widgetAt(global_position)
    if widget is not None:
        return widget
    return focused_widget


def detect_context(global_position=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return CONTEXT_OTHER

    if global_position is None:
        global_position = QtGui.QCursor.pos()

    widget = app.widgetAt(global_position)
    if widget is not None:
        context = context_for_widget(widget)
        if context != CONTEXT_OTHER:
            return context

    # MotionBuilder's native OpenGL surfaces can be visible while widgetAt()
    # returns None.  Their Qt geometry is still reliable.
    context = _context_from_visible_editor_geometry(app, global_position)
    if context != CONTEXT_OTHER:
        return context

    if widget is not None:
        return CONTEXT_OTHER

    # Some native child surfaces do not resolve through widgetAt().  Focus is
    # the last fallback when neither widget lookup nor editor geometry matched.
    return context_for_widget(app.focusWidget())


def _target_path(entry):
    return os.path.normpath(os.path.join(_script_directory(), entry["filename"]))


def _keyboard_map_path_and_manager():
    manager = FBActionManager()
    interaction_mode = str(manager.CurrentInteractionMode)
    if not interaction_mode:
        raise RuntimeError("MotionBuilder has no active interaction mode.")
    path = os.path.join(
        str(FBSystem().UserConfigPath),
        "Keyboard",
        interaction_mode + ".txt",
    )
    return path, manager


def _native_action_line_pattern(action_name):
    try:
        encoded_name = action_name.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeError(
            "MotionBuilder action names must contain ASCII characters only."
        )
    return re.compile(
        rb"(?m)^" + re.escape(encoded_name) + rb"[ \t]*=.*(?:\r?\n|$)"
    )


def _native_action_exists(action_name):
    try:
        path, _manager = _keyboard_map_path_and_manager()
        with open(path, "rb") as keyboard_file:
            return bool(_native_action_line_pattern(action_name).search(
                keyboard_file.read()
            ))
    except Exception:
        return False


def _write_keyboard_map(path, contents):
    with open(path, "wb") as keyboard_file:
        keyboard_file.write(contents)
        keyboard_file.flush()
        os.fsync(keyboard_file.fileno())


class DeferredNativeAction(object):
    """Dispatch one action after Python returns to MotionBuilder's event loop."""

    def __init__(self, action_name):
        self.action_name = action_name
        self.path = ""
        self.manager = None
        self.original_contents = b""
        self.bound_contents = b""
        self.original_line = b""
        self.bound_line = b""
        self.virtual_key = 0
        self.active = False
        self.restore_attempts = 0

    def start(self):
        previous = getattr(builtins, NATIVE_ACTION_STATE_NAME, None)
        if previous is not None:
            try:
                previous.restore()
            except Exception:
                pass

        self.path, self.manager = _keyboard_map_path_and_manager()
        with open(self.path, "rb") as keyboard_file:
            self.original_contents = keyboard_file.read()

        pattern = _native_action_line_pattern(self.action_name)
        match = pattern.search(self.original_contents)
        if match is None:
            raise RuntimeError(
                "MotionBuilder action is not present in the active keyboard map:\n"
                + self.action_name
            )

        self.original_line = match.group(0)
        if self.original_line.endswith(b"\r\n"):
            newline = b"\r\n"
        elif self.original_line.endswith(b"\n"):
            newline = b"\n"
        else:
            newline = b""

        other_action_lines = (
            self.original_contents[:match.start()]
            + self.original_contents[match.end():]
        )
        temporary_key_name = b""
        for candidate_name, candidate_virtual_key in NATIVE_ACTION_TEMP_KEYS:
            candidate_binding = (
                b"{NONE:" + candidate_name + b"*DN}"
            )
            if candidate_binding not in other_action_lines:
                temporary_key_name = candidate_name
                self.virtual_key = candidate_virtual_key
                break
        if not temporary_key_name:
            raise RuntimeError(
                "Quick Favorites could not find an unused temporary function key."
            )

        self.bound_line = (
            self.action_name.encode("ascii")
            + b" = {NONE:"
            + temporary_key_name
            + b"*DN}"
            + newline
        )
        self.bound_contents = (
            self.original_contents[:match.start()]
            + self.bound_line
            + self.original_contents[match.end():]
        )

        try:
            _write_keyboard_map(self.path, self.bound_contents)
            if not self.manager.RescanCurrentInteractionModeShortcuts():
                raise RuntimeError(
                    "MotionBuilder did not accept the temporary action binding."
                )
        except Exception:
            _write_keyboard_map(self.path, self.original_contents)
            self.manager.RescanCurrentInteractionModeShortcuts()
            raise

        self.active = True
        builtins.__dict__[NATIVE_ACTION_STATE_NAME] = self

        # The input must be queued only after this Python callback returns.
        # MotionBuilder's native action manager does not process it inside a
        # nested Python/Qt event loop.
        QtCore.QTimer.singleShot(0, self._send_key_pair)
        # Recovery timer in case the send callback itself is interrupted.
        QtCore.QTimer.singleShot(2000, self.restore)
        return self

    def _send_key_pair(self):
        if not self.active:
            return
        user32 = ctypes.windll.user32
        key_event_key_up = 0x0002
        try:
            user32.keybd_event(self.virtual_key, 0, 0, 0)
        finally:
            # Always deliver the matching release; a press-only shortcut is the
            # source of the stuck mouse/editor states this tool must avoid.
            user32.keybd_event(
                self.virtual_key,
                0,
                key_event_key_up,
                0,
            )
        QtCore.QTimer.singleShot(300, self.restore)

    def restore(self):
        if not self.active:
            return True

        try:
            with open(self.path, "rb") as keyboard_file:
                current_contents = keyboard_file.read()

            if current_contents == self.bound_contents:
                restored_contents = self.original_contents
            else:
                # Preserve any unrelated edit made during the short dispatch
                # window, and only undo our own still-present action line.
                pattern = _native_action_line_pattern(self.action_name)
                current_match = pattern.search(current_contents)
                if current_match is None or current_match.group(0) != self.bound_line:
                    restored_contents = current_contents
                else:
                    restored_contents = (
                        current_contents[:current_match.start()]
                        + self.original_line
                        + current_contents[current_match.end():]
                    )

            if restored_contents != current_contents:
                _write_keyboard_map(self.path, restored_contents)
            self.manager.RescanCurrentInteractionModeShortcuts()
        except Exception:
            self.restore_attempts += 1
            if self.restore_attempts < 3:
                QtCore.QTimer.singleShot(250, self.restore)
            return False

        self.active = False
        if getattr(builtins, NATIVE_ACTION_STATE_NAME, None) is self:
            builtins.__dict__[NATIVE_ACTION_STATE_NAME] = None
        return True


def _run_native_action(action_name):
    return DeferredNativeAction(action_name).start()


def _favorite_availability(entry):
    kind = entry["kind"]
    if kind in ("script", "function"):
        path = _target_path(entry)
        if os.path.isfile(path):
            return True, ""
        return False, "Missing: {0}".format(entry["filename"])

    if kind == "callback":
        if callable(entry.get("callback")):
            return True, ""
        return False, "Python callback is not callable"

    if kind == "action":
        action_name = entry.get("action", "")
        if _native_action_exists(action_name):
            return True, action_name
        return False, "Unknown native action: {0}".format(action_name)

    return False, "Unknown favorite kind: {0}".format(kind)


def _execute_source(path, module_name):
    with open(path, "r", encoding="utf-8-sig") as source_file:
        source = source_file.read()

    namespace = {
        "__file__": path,
        "__name__": module_name,
        "__package__": None,
        "__builtins__": __builtins__,
    }

    script_directory = os.path.dirname(path)
    added_to_path = script_directory not in sys.path
    if added_to_path:
        sys.path.insert(0, script_directory)

    try:
        exec(compile(source, path, "exec"), namespace, namespace)
    finally:
        if added_to_path:
            try:
                sys.path.remove(script_directory)
            except ValueError:
                pass

    return namespace


def run_favorite(entry):
    kind = entry["kind"]

    if kind == "script":
        path = _target_path(entry)
        if not os.path.isfile(path):
            raise RuntimeError("Favorite script does not exist:\n{0}".format(path))
        _execute_source(path, "__main__")
        return

    if kind == "function":
        path = _target_path(entry)
        if not os.path.isfile(path):
            raise RuntimeError("Favorite script does not exist:\n{0}".format(path))
        namespace = _execute_source(path, "_quick_favorites_target_")
        function_name = entry["function"]
        callback = namespace.get(function_name)
        if not callable(callback):
            raise RuntimeError(
                "'{0}' does not define a callable named '{1}'.".format(
                    entry["filename"], function_name
                )
            )
        callback()
        return

    if kind == "callback":
        callback_object = entry.get("callback")
        if not callable(callback_object):
            raise RuntimeError("Quick Favorite Python callback is not callable.")
        callback_object()
        return

    if kind == "action":
        return _run_native_action(entry["action"])

    raise RuntimeError("Unknown favorite kind: {0}".format(kind))


def _run_favorite_with_error_dialog(entry):
    try:
        run_favorite(entry)
    except Exception:
        FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")


def _event_global_position(event):
    try:
        return event.globalPosition().toPoint()
    except Exception:
        pass

    try:
        return event.globalPos()
    except Exception:
        return QtGui.QCursor.pos()


def _pressed_virtual_keys():
    if os.name != "nt":
        return []

    user32 = ctypes.windll.user32
    # Mouse buttons are handled by the popup itself.  This guard is only for
    # keyboard shortcuts that execute on key-down, such as Script37 on Q.
    mouse_virtual_keys = {0x01, 0x02, 0x04, 0x05, 0x06}
    return [
        virtual_key
        for virtual_key in range(0x08, 0xFF)
        if virtual_key not in mouse_virtual_keys
        and user32.GetAsyncKeyState(virtual_key) & 0x8000
    ]


def _virtual_keys_are_down(virtual_keys):
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    return any(
        user32.GetAsyncKeyState(virtual_key) & 0x8000
        for virtual_key in virtual_keys
    )


class DeferredQuickFavoritesPopup(QtCore.QObject):
    """Wait for the shortcut key-up before allowing the popup to take focus."""

    def __init__(
        self,
        app,
        global_position,
        pressed_virtual_keys,
        key_state_reader=None,
    ):
        super(DeferredQuickFavoritesPopup, self).__init__(app)
        self.app = app
        self.global_position = QtCore.QPoint(global_position)
        self.pressed_virtual_keys = tuple(pressed_virtual_keys)
        self.key_state_reader = key_state_reader or _virtual_keys_are_down
        self.open_scheduled = False
        self.cancelled = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._poll)

    def start(self):
        self.app.installEventFilter(self)
        self.timer.start()
        return self

    def cancel(self):
        if self.cancelled:
            return
        self.cancelled = True
        self.timer.stop()
        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass
        self.deleteLater()

    def _keys_are_down(self):
        try:
            return bool(self.key_state_reader(self.pressed_virtual_keys))
        except Exception:
            return False

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyRelease:
            # Returning False lets the original Viewer/FCurves widget receive
            # the release.  Open on the next event-loop turn, after it has done
            # so, instead of leaving MotionBuilder with a key-down-only state.
            QtCore.QTimer.singleShot(0, self._schedule_if_released)
        return False

    def _poll(self):
        if not self._keys_are_down():
            # Polling is a fallback for hosts that consume the Qt release event.
            # A small delay lets any queued native key-up finish dispatching.
            self.timer.stop()
            QtCore.QTimer.singleShot(30, self._open)

    def _schedule_if_released(self):
        if not self._keys_are_down():
            self._open()

    def _open(self):
        if self.cancelled or self.open_scheduled:
            return
        self.open_scheduled = True
        self.timer.stop()
        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass
        if getattr(builtins, PENDING_STATE_NAME, None) is self:
            builtins.__dict__[PENDING_STATE_NAME] = None
        _show_quick_favorites_now(self.global_position)
        self.deleteLater()


class QuickFavoritesMenu(QtWidgets.QMenu):
    def __init__(self, context, parent=None, focus_target=None):
        QtWidgets.QMenu.__init__(self, parent)
        self.context = context
        self._focus_target = focus_target
        self._focus_window = None
        if focus_target is not None:
            try:
                self._focus_window = focus_target.window()
            except Exception:
                pass
        if self._focus_window is None:
            self._focus_window = parent
        self._focus_restore_generation = 0
        self._launching_favorite = False
        self._outside_dismiss_button = QtCore.Qt.MouseButton.NoButton
        self.setObjectName("QuickFavoritesMenu")
        self.setWindowTitle(TOOL_NAME)
        self.setTearOffEnabled(False)

        title_action = self.addAction(CONTEXT_TITLES[context])
        title_action.setEnabled(False)
        self.addSeparator()

        entries = FAVORITES.get(context, [])
        for entry in entries:
            if entry["kind"] == "separator":
                self.addSeparator()
                continue

            menu_action = self.addAction(entry["label"])
            available, tool_tip = _favorite_availability(entry)
            menu_action.setEnabled(available)
            if tool_tip:
                menu_action.setToolTip(tool_tip)
            menu_action.triggered.connect(
                lambda _checked=False, favorite=entry: self._run(favorite)
            )

        if not entries:
            empty_action = self.addAction("No favorites configured")
            empty_action.setEnabled(False)

        self.aboutToShow.connect(self._install_outside_click_filter)
        self.aboutToHide.connect(self._remove_outside_click_filter)

    def _run(self, entry):
        # Restore the source editor before starting the target.  If the target
        # opens another popup (for example Apply Filter), that new popup then
        # becomes active normally and is not overridden by a late restore.
        self._launching_favorite = True
        self.cancel_focus_restore()
        self._restore_source_focus(force=True)
        if entry["kind"] == "action":
            # Let QMenu release its popup/mouse grab first. The native action
            # dispatcher then queues a complete shortcut pair on the following
            # host event-loop turn.
            self.close()
            QtCore.QTimer.singleShot(
                0,
                lambda favorite=entry: _run_favorite_with_error_dialog(
                    favorite
                ),
            )
            return

        _run_favorite_with_error_dialog(entry)

    def _install_outside_click_filter(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    def _remove_outside_click_filter(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._launching_favorite:
            self.cancel_focus_restore()
        else:
            self._schedule_focus_restore()

    def cancel_focus_restore(self):
        self._focus_restore_generation += 1

    def _schedule_focus_restore(self):
        self._focus_restore_generation += 1
        generation = self._focus_restore_generation
        QtCore.QTimer.singleShot(
            0,
            lambda expected=generation: self._restore_source_focus(expected),
        )

    def _restore_source_focus(self, expected_generation=None, force=False):
        if (
            expected_generation is not None
            and expected_generation != self._focus_restore_generation
        ):
            return False

        app = QtWidgets.QApplication.instance()
        if app is None:
            return False

        active_popup = app.activePopupWidget()
        if not force and active_popup is not None and active_popup is not self:
            return False

        window = self._focus_window
        if window is not None:
            try:
                if window.isVisible():
                    window.activateWindow()
            except Exception:
                pass

        target = self._focus_target
        if target is not None:
            try:
                if target.isVisible() and target.isEnabled():
                    target.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)
                    return target.hasFocus()
            except Exception:
                pass
        return False

    def _is_outside(self, event):
        return not self.frameGeometry().contains(_event_global_position(event))

    def _begin_outside_dismiss(self, event):
        if self.isVisible() and self._is_outside(event):
            # Consume the press and keep the popup grab until the same physical
            # button is released.  Closing on press can leak half a gesture to
            # MotionBuilder and leave FCurves in its MMB key-offset state.
            self._outside_dismiss_button = event.button()
            event.accept()
            return True
        return False

    def _finish_outside_dismiss(self, event):
        if self._outside_dismiss_button == QtCore.Qt.MouseButton.NoButton:
            return False

        event.accept()
        if event.button() == self._outside_dismiss_button:
            self._outside_dismiss_button = QtCore.Qt.MouseButton.NoButton
            self.close()
        return True

    def dismiss_if_outside(self, global_position):
        # Retained as a small programmatic helper; physical mouse events use
        # the paired press/release path above.
        if self.isVisible() and not self.frameGeometry().contains(global_position):
            self.close()
            return True
        return False

    def eventFilter(self, watched, event):
        event_type = event.type()
        mouse_press_types = (
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonDblClick,
            QtCore.QEvent.Type.NonClientAreaMouseButtonPress,
        )
        if event_type in mouse_press_types:
            if self._begin_outside_dismiss(event):
                return True
        elif event_type == QtCore.QEvent.Type.MouseButtonRelease:
            if self._finish_outside_dismiss(event):
                return True
        return QtCore.QObject.eventFilter(self, watched, event)

    def mousePressEvent(self, event):
        if self._begin_outside_dismiss(event):
            return
        QtWidgets.QMenu.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        if self._finish_outside_dismiss(event):
            return
        QtWidgets.QMenu.mouseReleaseEvent(self, event)


def _show_quick_favorites_now(global_position=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    if global_position is None:
        global_position = QtGui.QCursor.pos()

    previous_menu = getattr(builtins, STATE_NAME, None)
    if previous_menu is not None:
        try:
            previous_menu.cancel_focus_restore()
            previous_menu.close()
        except Exception:
            pass

    context = detect_context(global_position)
    focus_target = _focus_target_for_context(app, global_position, context)
    parent = None
    if focus_target is not None:
        try:
            parent = focus_target.window()
        except Exception:
            pass
    if parent is None:
        parent = app.activeWindow()

    menu = QuickFavoritesMenu(context, parent, focus_target)
    builtins.__dict__[STATE_NAME] = menu
    menu.popup(global_position)
    return menu


def show_quick_favorites(global_position=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    if global_position is None:
        global_position = QtGui.QCursor.pos()

    previous_pending = getattr(builtins, PENDING_STATE_NAME, None)
    if previous_pending is not None:
        try:
            previous_pending.cancel()
        except Exception:
            pass

    pressed_virtual_keys = _pressed_virtual_keys()
    if pressed_virtual_keys:
        pending = DeferredQuickFavoritesPopup(
            app,
            global_position,
            pressed_virtual_keys,
        )
        builtins.__dict__[PENDING_STATE_NAME] = pending
        return pending.start()

    return _show_quick_favorites_now(global_position)


def run_with_error_dialog():
    try:
        return show_quick_favorites()
    except Exception:
        FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")
        return None


if globals().get("QUICK_FAVORITES_AUTORUN", True):
    run_with_error_dialog()
