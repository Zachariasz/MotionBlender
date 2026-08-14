"""Open MotionBuilder's Navigator and synchronize its selected model."""

from __future__ import absolute_import


TOOL_NAME = "Find Selected in Hierarchy"
MAX_TREE_NODES = 20000
SCENE_BROWSER_TERMS = ("navigator", "scene browser")
EXPAND_TO_SELECTION_TEXT = "expand to selection"
MAX_NATIVE_MENU_ATTEMPTS = 8
NATIVE_MENU_POLL_MS = 50
NAVIGATOR_TREE_X_RATIO = 0.052
NAVIGATOR_TREE_Y_RATIO = 0.77

_PENDING_TIMER = None
_PENDING_ATTEMPTS = 0
_LAST_EXPAND_RESULT = None


def _qt_modules():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


def _enum(container, nested_name, name):
    nested = getattr(container, nested_name, container)
    return getattr(nested, name)


def _normalize_text(value):
    return " ".join(str(value or "").split()).casefold()


def _name_variants(component):
    """Return exact labels used by the native hierarchy tree."""
    names = set()
    for attribute in ("LongName", "Name"):
        try:
            value = str(getattr(component, attribute) or "").strip()
        except Exception:
            value = ""
        if not value:
            continue
        names.add(_normalize_text(value))
        if ":" in value:
            names.add(_normalize_text(value.rsplit(":", 1)[-1]))
    names.discard("")
    return names


def _ancestor_names(targets):
    names = set()
    for target in targets:
        current = target
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            names.update(_name_variants(current))
            try:
                current = current.Parent
            except Exception:
                current = None
    return names


def _widget_description(widget):
    parts = []
    current = widget
    while current is not None:
        for attribute in ("objectName", "windowTitle", "accessibleName"):
            try:
                value = getattr(current, attribute)()
            except Exception:
                value = ""
            if value:
                parts.append(str(value))
        try:
            parts.append(str(current.metaObject().className()))
        except Exception:
            pass
        try:
            current = current.parentWidget()
        except Exception:
            current = None
    return _normalize_text(" ".join(parts))


def _valid_widget(widget):
    if widget is None:
        return False
    try:
        try:
            import shiboken6 as shiboken
        except ImportError:
            import shiboken2 as shiboken
        return bool(shiboken.isValid(widget))
    except Exception:
        try:
            widget.metaObject()
            return True
        except (AttributeError, RuntimeError, ReferenceError):
            return False


def _is_tree_view(widget, QtWidgets):
    tree_classes = tuple(
        candidate
        for candidate in (
            getattr(QtWidgets, "QTreeView", None),
            getattr(QtWidgets, "QTreeWidget", None),
        )
        if isinstance(candidate, type)
    )
    if tree_classes and isinstance(widget, tree_classes):
        return True
    try:
        return bool(
            widget.inherits("QTreeView")
            or widget.inherits("QAbstractItemView")
        )
    except Exception:
        return False


def _scene_browser_trees(application, QtWidgets):
    try:
        widgets = tuple(application.allWidgets())
    except Exception:
        return ()
    trees = []
    fallback = []
    for widget in widgets:
        if not _valid_widget(widget) or not _is_tree_view(widget, QtWidgets):
            continue
        try:
            if not widget.isVisible() or widget.model() is None:
                continue
        except Exception:
            continue
        fallback.append(widget)
        description = _widget_description(widget)
        if any(term in description for term in SCENE_BROWSER_TERMS):
            trees.append(widget)
    return tuple(trees or fallback)


def _index_key(index):
    try:
        return (int(index.internalId()), int(index.row()), int(index.column()))
    except Exception:
        return (id(index),)


def _index_names(model, index, QtCore):
    display_role = _enum(QtCore.Qt, "ItemDataRole", "DisplayRole")
    tooltip_role = _enum(QtCore.Qt, "ItemDataRole", "ToolTipRole")
    names = set()
    for role in (display_role, tooltip_role):
        try:
            value = model.data(index, role)
        except Exception:
            value = None
        normalized = _normalize_text(value)
        if normalized:
            names.add(normalized)
            if ":" in normalized:
                names.add(normalized.rsplit(":", 1)[-1])
    return names


def _expand_ancestors(tree, index):
    current = index
    while True:
        try:
            current = current.parent()
        except Exception:
            return
        try:
            if not current.isValid():
                return
            tree.expand(current)
        except Exception:
            return


def _reveal_matches(tree, target_names, ancestor_names, QtCore, QtWidgets):
    """Expand matching branches and return the hierarchy indexes found."""
    try:
        model = tree.model()
        root = QtCore.QModelIndex()
    except Exception:
        return ()
    found = []
    pending = [root]
    visited = set()
    processed = 0
    while pending and processed < MAX_TREE_NODES:
        parent = pending.pop()
        try:
            if parent.isValid():
                key = _index_key(parent)
                if key in visited:
                    continue
                visited.add(key)
                if model.canFetchMore(parent):
                    model.fetchMore(parent)
            row_count = int(model.rowCount(parent))
        except Exception:
            continue
        for row in range(max(0, row_count)):
            if processed >= MAX_TREE_NODES:
                break
            processed += 1
            try:
                index = model.index(row, 0, parent)
                if not index.isValid():
                    continue
            except Exception:
                continue
            names = _index_names(model, index, QtCore)
            if names.intersection(target_names):
                _expand_ancestors(tree, index)
                try:
                    tree.expand(index)
                except Exception:
                    pass
                found.append(index)
            elif names.intersection(ancestor_names):
                try:
                    tree.expand(index)
                except Exception:
                    pass
            pending.append(index)

    if not found:
        return ()
    first = found[0]
    try:
        selection = tree.selectionModel()
        if selection is not None:
            selection_flag = _enum(
                QtCore.QItemSelectionModel,
                "SelectionFlag",
                "ClearAndSelect",
            )
            row_flag = _enum(
                QtCore.QItemSelectionModel,
                "SelectionFlag",
                "Rows",
            )
            selection.select(first, selection_flag | row_flag)
    except Exception:
        pass
    try:
        tree.setCurrentIndex(first)
    except Exception:
        pass
    try:
        position = _enum(
            QtWidgets.QAbstractItemView,
            "ScrollHint",
            "PositionAtCenter",
        )
        tree.scrollTo(first, position)
    except Exception:
        pass
    return tuple(found)


def _update_status(application, message):
    try:
        application.UpdateStatusBar(message)
    except Exception:
        pass


def _open_navigator(qt_application):
    """Open the built-in Navigator through MotionBuilder's own window action."""
    try:
        QtGui = _qt_gui_module()
        windows = tuple(qt_application.topLevelWidgets())
    except Exception:
        return False

    for window in windows:
        if not _valid_widget(window):
            continue
        try:
            if not window.isVisible() or not window.inherits("QMainWindow"):
                continue
            actions = tuple(window.findChildren(QtGui.QAction))
        except Exception:
            continue
        for action in actions:
            try:
                text = str(action.text()).replace("&", "").strip()
                if text != "Navigator":
                    continue
                if action.isCheckable() and action.isChecked():
                    return True
                action.trigger()
                return True
            except (AttributeError, RuntimeError, ReferenceError, TypeError):
                continue
    return False


def _qt_gui_module():
    try:
        from PySide6 import QtGui
    except ImportError:
        from PySide2 import QtGui
    return QtGui


def _request_native_selection_update(targets):
    """Tell MotionBuilder's native browser UI about the current selection.

    The Navigator's BrowsingTree is a proprietary C++ control, rather than a
    Qt item view, so it does not expose a model or an expansion API to Python.
    ``HardSelect`` refreshes the host selection UI after the Navigator has
    been opened through MotionBuilder's own window action.
    """
    try:
        from pyfbsdk import FBSetLastSelectedModel
    except ImportError:
        FBSetLastSelectedModel = None

    if FBSetLastSelectedModel is not None:
        try:
            FBSetLastSelectedModel(targets[-1])
        except (AttributeError, RuntimeError, ReferenceError, TypeError):
            pass

    notified = 0
    for target in targets:
        try:
            target.HardSelect()
            notified += 1
        except (AttributeError, RuntimeError, ReferenceError, TypeError):
            continue
    return notified


def _action_text(action):
    try:
        return str(action.text()).replace("&", "").strip().casefold()
    except (AttributeError, RuntimeError, ReferenceError, TypeError):
        return ""


def _trigger_expand_to_selection(qt_application):
    """Trigger Navigator's native Expand To Selection popup action."""
    try:
        popups = tuple(qt_application.topLevelWidgets())
    except Exception:
        return False
    for popup in popups:
        if not _valid_widget(popup):
            continue
        try:
            if not popup.isVisible():
                continue
            actions = tuple(popup.actions())
        except Exception:
            continue
        for action in actions:
            if _action_text(action) != EXPAND_TO_SELECTION_TEXT:
                continue
            try:
                if not action.isEnabled():
                    continue
                action.trigger()
                popup.hide()
                return True
            except (AttributeError, RuntimeError, ReferenceError, TypeError):
                continue
    return False


def _main_window(qt_application):
    try:
        windows = tuple(qt_application.topLevelWidgets())
    except Exception:
        return None
    for window in windows:
        if not _valid_widget(window):
            continue
        try:
            if window.isVisible() and window.inherits("QMainWindow"):
                return window
        except Exception:
            continue
    return None


def _post_navigator_context_menu(qt_application):
    """Focus the Navigator tree and open its context menu on Windows."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    window = _main_window(qt_application)
    if window is None:
        return False
    try:
        hwnd = int(window.winId())
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError):
        return False

    user32 = ctypes.windll.user32
    rectangle = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rectangle)):
        return False
    width = max(1, int(rectangle.right - rectangle.left))
    height = max(1, int(rectangle.bottom - rectangle.top))
    x = max(8, min(width - 8, int(width * NAVIGATOR_TREE_X_RATIO)))
    y = max(8, min(height - 8, int(height * NAVIGATOR_TREE_Y_RATIO)))
    position = (y << 16) | (x & 0xFFFF)

    messages = (
        (0x0204, 0x0002, position),  # WM_RBUTTONDOWN / MK_RBUTTON
        (0x0205, 0, position),       # WM_RBUTTONUP
        (0x0100, 0x5D, 0),           # WM_KEYDOWN / VK_APPS
        (0x0101, 0x5D, 0xC0000001),  # WM_KEYUP / VK_APPS
    )
    return all(
        bool(user32.PostMessageW(hwnd, message, wparam, lparam))
        for message, wparam, lparam in messages
    )


def _clear_pending_timer():
    global _PENDING_TIMER, _PENDING_ATTEMPTS
    timer = _PENDING_TIMER
    _PENDING_TIMER = None
    _PENDING_ATTEMPTS = 0
    if timer is None:
        return
    try:
        timer.stop()
    except Exception:
        pass
    try:
        timer.timeout.disconnect(_poll_expand_action)
    except Exception:
        pass
    try:
        timer.deleteLater()
    except Exception:
        pass


def _poll_expand_action():
    global _LAST_EXPAND_RESULT, _PENDING_ATTEMPTS
    QtCore, QtWidgets = _qt_modules()
    del QtCore
    application = QtWidgets.QApplication.instance()
    if application is not None and _trigger_expand_to_selection(application):
        _LAST_EXPAND_RESULT = True
        _clear_pending_timer()
        return
    _PENDING_ATTEMPTS += 1
    if _PENDING_ATTEMPTS >= MAX_NATIVE_MENU_ATTEMPTS:
        _LAST_EXPAND_RESULT = False
        _clear_pending_timer()


def _schedule_expand_action(qt_application):
    global _LAST_EXPAND_RESULT, _PENDING_TIMER, _PENDING_ATTEMPTS
    _clear_pending_timer()
    QtCore, unused_widgets = _qt_modules()
    del unused_widgets
    timer = QtCore.QTimer(qt_application)
    timer.setInterval(NATIVE_MENU_POLL_MS)
    timer.timeout.connect(_poll_expand_action)
    _PENDING_TIMER = timer
    _PENDING_ATTEMPTS = 0
    _LAST_EXPAND_RESULT = None
    timer.start()
    return True


def close():
    """Cancel the short-lived native menu poll during reload or shutdown."""
    _clear_pending_timer()


def execute(context):
    """Run Navigator's native Expand To Selection operation."""
    targets = tuple(context.selection)
    if not targets:
        message = "Find in Hierarchy: No object selected."
        _update_status(context.application, message)
        return {"found": 0, "message": message}

    navigator_opened = _open_navigator(context.qt_application)
    native_count = _request_native_selection_update(targets)

    if _trigger_expand_to_selection(context.qt_application):
        message = "Find in Hierarchy: Expanded Navigator to selection."
        _update_status(context.application, message)
        return {
            "found": native_count,
            "message": message,
            "method": "expand_to_selection",
        }

    menu_posted = _post_navigator_context_menu(context.qt_application)
    if navigator_opened and menu_posted:
        _schedule_expand_action(context.qt_application)
        message = "Find in Hierarchy: Expanding Navigator to selection."
        _update_status(context.application, message)
        return {
            "found": native_count,
            "message": message,
            "method": "expand_to_selection_scheduled",
        }

    # Retain the standard Qt-tree implementation as a compatibility fallback
    # for host versions or custom browsers that do expose a tree model.
    QtCore, QtWidgets = _qt_modules()
    trees = _scene_browser_trees(context.qt_application, QtWidgets)
    if not trees:
        if navigator_opened and native_count:
            message = (
                "Find in Hierarchy: Navigator opened and selection synchronized."
            )
        elif navigator_opened:
            message = "Find in Hierarchy: Navigator opened."
        else:
            message = "Find in Hierarchy: Could not open Navigator."
        _update_status(context.application, message)
        return {
            "found": 0,
            "message": message,
            "navigator_opened": navigator_opened,
            "selection_updated": native_count,
        }

    target_names = set()
    for target in targets:
        target_names.update(_name_variants(target))
    if not target_names:
        message = "Find in Hierarchy: Selected object has no hierarchy name."
        _update_status(context.application, message)
        return {"found": 0, "message": message}

    ancestor_names = _ancestor_names(targets)
    found = []
    for tree in trees:
        found.extend(
            _reveal_matches(
                tree,
                target_names,
                ancestor_names,
                QtCore,
                QtWidgets,
            )
        )
    message = "Find in Hierarchy: Revealed %d selected object(s)." % len(found)
    _update_status(context.application, message)
    return {
        "found": len(found),
        "message": message,
        "navigator_opened": navigator_opened,
        "selection_updated": native_count,
    }
