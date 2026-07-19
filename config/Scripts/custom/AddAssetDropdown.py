import builtins
import ctypes
import os
import traceback

from pyfbsdk import (
    FBActor,
    FBActorFace,
    FBCamera,
    FBCharacter,
    FBCharacterExtension,
    FBCharacterFace,
    FBConstraintManager,
    FBCreateObject,
    FBMessageBox,
    FBModelCube,
    FBModelMarker,
    FBModelNull,
    FBModelPlane,
    FBModelRoot,
    FBModelSkeleton,
    FBSystem,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Add Asset Dropdown"
STATE_NAME = "_codex_add_asset_dropdown_popup"
PENDING_STATE_NAME = "_codex_add_asset_dropdown_pending"

PRIMITIVE_TEMPLATE_PATH = "Browsing/Templates/Elements/Primitives"
ELEMENT_TEMPLATE_PATHS = (
    "Browsing/Templates/Elements",
    "Browsing/Templates/Elements/Primitives",
)
CHARACTER_TEMPLATE_PATHS = (
    "Browsing/Templates/Characters",
    "Browsing/Templates/Elements",
)
CONSTRAINT_TEMPLATE_PATHS = (
    "Browsing/Templates/Constraints",
    "Browsing/Templates/Elements/Constraints",
)

TOP_LEVEL_ITEMS = (
    {
        "label": "Null",
        "kind": "template_or_class",
        "paths": ELEMENT_TEMPLATE_PATHS,
        "entry": "Null",
        "class": FBModelNull,
    },
    {
        "label": "Camera",
        "kind": "template_or_class",
        "paths": ELEMENT_TEMPLATE_PATHS,
        "entry": "Camera",
        "class": FBCamera,
    },
)

TAB_ITEMS = (
    (
        "Character",
        (
            {
                "label": "Actor",
                "kind": "template_or_class",
                "paths": CHARACTER_TEMPLATE_PATHS,
                "entry": "Actor",
                "class": FBActor,
            },
            {
                "label": "Actor face",
                "kind": "template_or_class",
                "paths": CHARACTER_TEMPLATE_PATHS,
                "entry": "Actor Face",
                "class": FBActorFace,
            },
            {
                "label": "Character",
                "kind": "template_or_class",
                "paths": CHARACTER_TEMPLATE_PATHS,
                "entry": "Character",
                "class": FBCharacter,
            },
            {
                "label": "Character Extension",
                "kind": "template_or_class",
                "paths": CHARACTER_TEMPLATE_PATHS,
                "entry": "Character Extension",
                "class": FBCharacterExtension,
            },
            {
                "label": "Character face",
                "kind": "template_or_class",
                "paths": CHARACTER_TEMPLATE_PATHS,
                "entry": "Character Face",
                "class": FBCharacterFace,
            },
        ),
    ),
    (
        "Mesh",
        (
            {
                "label": "Cube",
                "kind": "primitive",
                "entry": "Cube",
                "class": FBModelCube,
            },
            {
                "label": "Plane",
                "kind": "primitive",
                "entry": "Plane",
                "class": FBModelPlane,
            },
            {"label": "Sphere", "kind": "primitive", "entry": "Sphere"},
            {"label": "Cone", "kind": "primitive", "entry": "Cone"},
            {"label": "Cylinder", "kind": "primitive", "entry": "Cylinder"},
            {"label": "Torus", "kind": "primitive", "entry": "Torus"},
            {"label": "Disc", "kind": "primitive", "entry": "Disc"},
            {"label": "polySphere", "kind": "primitive", "entry": "polySphere"},
        ),
    ),
    (
        "Skeleton",
        (
            {
                "label": "Skeleton node",
                "kind": "template_or_class",
                "paths": ELEMENT_TEMPLATE_PATHS,
                "entry": "Skeleton Node",
                "class": FBModelSkeleton,
            },
            {
                "label": "Skeleton root",
                "kind": "template_or_class",
                "paths": ELEMENT_TEMPLATE_PATHS,
                "entry": "Skeleton Root",
                "class": FBModelRoot,
            },
            {
                "label": "Marker",
                "kind": "template_or_class",
                "paths": ELEMENT_TEMPLATE_PATHS,
                "entry": "Marker",
                "class": FBModelMarker,
            },
        ),
    ),
    (
        "Constraint",
        (
            {"label": "3 Points", "kind": "constraint", "aliases": ("3 Points", "3-Points", "Three Points")},
            {
                "label": "Multi Reference",
                "kind": "constraint",
                "aliases": (
                    "Multi Reference",
                    "Multi-Reference",
                    "Multi Referential",
                    "Multi-Referential",
                ),
            },
            {"label": "Relation", "kind": "constraint", "aliases": ("Relation", "Relations")},
            {"label": "Aim", "kind": "constraint"},
            {"label": "Parent/Child", "kind": "constraint", "aliases": ("Parent/Child", "Parent-Child")},
            {"label": "Rigid Body", "kind": "constraint"},
            {"label": "Chain IK", "kind": "constraint", "aliases": ("Chain IK", "ChainIK")},
            {"label": "Path", "kind": "constraint"},
            {"label": "Rotation", "kind": "constraint"},
            {"label": "Expression", "kind": "constraint"},
            {"label": "Position", "kind": "constraint"},
            {"label": "Scale", "kind": "constraint"},
            {"label": "Mapping", "kind": "constraint", "aliases": ("Mapping", "Simple Mapping")},
            {"label": "Range", "kind": "constraint"},
            {"label": "Spline IK", "kind": "constraint", "aliases": ("Spline IK", "SplineIK")},
        ),
    ),
)


def _norm(text):
    return "".join(ch.lower() for ch in str(text) if ch.isalnum())


def _clear_selection():
    for component in FBSystem().Scene.Components:
        try:
            component.Selected = False
        except Exception:
            pass


def _select_created(created):
    _clear_selection()
    if isinstance(created, (list, tuple)):
        created_items = created
    else:
        created_items = (created,)

    for item in created_items:
        try:
            item.Selected = True
        except Exception:
            pass


def _show_component(component):
    for attr_name in ("Show", "Visible", "Visibility"):
        try:
            setattr(component, attr_name, True)
        except Exception:
            pass


def _evaluate_scene():
    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass


def _create_from_template(paths, entry, object_name=None):
    object_name = object_name or entry
    for path in paths:
        try:
            component = FBCreateObject(path, entry, object_name)
        except Exception:
            component = None

        if component is not None:
            return component

    return None


def _create_with_class(spec):
    cls = spec.get("class")
    if cls is None:
        return None
    return cls(spec["label"])


def _create_template_or_class(spec):
    component = _create_from_template(
        spec.get("paths", ()),
        spec.get("entry", spec["label"]),
        spec["label"],
    )
    if component is None:
        component = _create_with_class(spec)
    return component


def _create_primitive(spec):
    entry = spec.get("entry", spec["label"])

    # MotionBuilder's sample notes that primitives must use their entry name as
    # the object name when created through the Asset Browser template API.
    component = _create_from_template((PRIMITIVE_TEMPLATE_PATH,), entry, entry)
    if component is None:
        component = _create_with_class(spec)
    return component


def _constraint_type_map(manager):
    type_map = {}
    type_names = []
    for index in range(manager.TypeGetCount()):
        try:
            type_name = manager.TypeGetName(index)
        except Exception:
            continue
        type_names.append(type_name)
        type_map[_norm(type_name)] = (index, type_name)
    return type_map, type_names


def _create_constraint_from_manager(spec):
    manager = FBConstraintManager()
    type_map, type_names = _constraint_type_map(manager)
    candidates = [spec["label"]]
    candidates.extend(spec.get("aliases", ()))

    for candidate in candidates:
        match = type_map.get(_norm(candidate))
        if match is not None:
            constraint = manager.TypeCreateConstraint(match[0])
            if constraint is not None:
                constraint.Name = spec["label"]
                return constraint, type_names

    for candidate in candidates:
        try:
            constraint = manager.TypeCreateConstraint(candidate)
        except Exception:
            constraint = None
        if constraint is not None:
            constraint.Name = spec["label"]
            return constraint, type_names

    return None, type_names


def _create_constraint(spec):
    constraint, type_names = _create_constraint_from_manager(spec)
    if constraint is not None:
        return constraint

    candidates = [spec["label"]]
    candidates.extend(spec.get("aliases", ()))
    for candidate in candidates:
        component = _create_from_template(CONSTRAINT_TEMPLATE_PATHS, candidate, spec["label"])
        if component is not None:
            return component

    raise RuntimeError(
        "Could not find a MotionBuilder constraint type for '{0}'.\n\nAvailable constraint types:\n{1}".format(
            spec["label"],
            "\n".join(type_names),
        )
    )


def create_asset(spec):
    kind = spec.get("kind")
    if kind == "class":
        component = _create_with_class(spec)
    elif kind == "template_or_class":
        component = _create_template_or_class(spec)
    elif kind == "primitive":
        component = _create_primitive(spec)
    elif kind == "constraint":
        component = _create_constraint(spec)
    else:
        raise RuntimeError("Unknown asset type: {0}".format(kind))

    if component is None:
        raise RuntimeError("MotionBuilder returned no object for '{0}'.".format(spec["label"]))

    _show_component(component)
    _select_created(component)
    _evaluate_scene()
    print("{0}: created {1}".format(TOOL_NAME, spec["label"]))
    return component


def _run_asset_with_error_dialog(spec):
    try:
        create_asset(spec)
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


def _pressed_virtual_inputs():
    if os.name != "nt":
        return []

    user32 = ctypes.windll.user32
    return [
        virtual_key
        for virtual_key in range(0x01, 0xFF)
        if user32.GetAsyncKeyState(virtual_key) & 0x8000
    ]


def _virtual_inputs_are_down(virtual_keys):
    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    return any(
        user32.GetAsyncKeyState(virtual_key) & 0x8000
        for virtual_key in virtual_keys
    )


def _qt_event_type(name):
    event_types = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    return getattr(event_types, name)


def _qt_mouse_button(name):
    mouse_buttons = getattr(QtCore.Qt, "MouseButton", QtCore.Qt)
    return getattr(mouse_buttons, name)


def _qt_focus_reason(name):
    focus_reasons = getattr(QtCore.Qt, "FocusReason", QtCore.Qt)
    return getattr(focus_reasons, name)


class DeferredAssetDropdownPopup(QtCore.QObject):
    """Open only after the input that launched the script is released."""

    def __init__(self, app, global_position, pressed_virtual_inputs):
        QtCore.QObject.__init__(self, app)
        self.app = app
        self.global_position = QtCore.QPoint(global_position)
        self.pressed_virtual_inputs = tuple(pressed_virtual_inputs)
        self.cancelled = False
        self.open_scheduled = False
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
        if getattr(builtins, PENDING_STATE_NAME, None) is self:
            builtins.__dict__[PENDING_STATE_NAME] = None
        self.deleteLater()

    def _inputs_are_down(self):
        try:
            return _virtual_inputs_are_down(self.pressed_virtual_inputs)
        except Exception:
            return False

    def eventFilter(self, watched, event):
        release_types = (
            _qt_event_type("KeyRelease"),
            _qt_event_type("MouseButtonRelease"),
        )
        if event.type() in release_types:
            # Let MotionBuilder receive the matching release before the popup
            # takes focus and starts its own mouse grab.
            QtCore.QTimer.singleShot(0, self._schedule_if_released)
        return False

    def _poll(self):
        if not self._inputs_are_down():
            self.timer.stop()
            QtCore.QTimer.singleShot(30, self._open)

    def _schedule_if_released(self):
        if not self._inputs_are_down():
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
        _show_dropdown_now(self.global_position)
        self.deleteLater()


class AddAssetDropdown(QtWidgets.QMenu):
    def __init__(self, parent=None, focus_target=None):
        QtWidgets.QMenu.__init__(self, parent)
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
        self._launching_asset = False
        self._outside_dismiss_button = _qt_mouse_button("NoButton")
        self.setObjectName("AddAssetDropdown")
        self.setWindowTitle(TOOL_NAME)
        self.setTearOffEnabled(False)

        for category_name, specs in TAB_ITEMS:
            submenu = QtWidgets.QMenu(category_name, self)
            submenu.setTearOffEnabled(False)
            self.addMenu(submenu)
            for spec in specs:
                action = submenu.addAction(spec["label"])
                action.triggered.connect(
                    lambda _checked=False, s=spec: self._add_asset(s)
                )

        self.addSeparator()
        for spec in TOP_LEVEL_ITEMS:
            action = self.addAction(spec["label"])
            action.triggered.connect(
                lambda _checked=False, s=spec: self._add_asset(s)
            )

        self.aboutToShow.connect(self._install_outside_click_filter)
        self.aboutToHide.connect(self._on_hidden)

    def _add_asset(self, spec):
        self._launching_asset = True
        self.cancel_focus_restore()
        self._restore_source_focus(force=True)
        self.close()
        # Return to MotionBuilder before creating the SDK object so QMenu can
        # release its popup and mouse grabs completely.
        QtCore.QTimer.singleShot(
            0,
            lambda asset_spec=spec: _run_asset_with_error_dialog(asset_spec),
        )

    def _install_outside_click_filter(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    def _on_hidden(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

        if self._launching_asset:
            self.cancel_focus_restore()
        else:
            self._schedule_focus_restore()

        QtCore.QTimer.singleShot(0, self._dispose)

    def _dispose(self):
        if getattr(builtins, STATE_NAME, None) is self:
            builtins.__dict__[STATE_NAME] = None
        self.deleteLater()

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

        if self._focus_window is not None:
            try:
                if self._focus_window.isVisible():
                    self._focus_window.activateWindow()
            except Exception:
                pass

        if self._focus_target is not None:
            try:
                if (
                    self._focus_target.isVisible()
                    and self._focus_target.isEnabled()
                ):
                    self._focus_target.setFocus(_qt_focus_reason("PopupFocusReason"))
                    return self._focus_target.hasFocus()
            except Exception:
                pass
        return False

    def _is_inside_menu_tree(self, global_position):
        menus = [self]
        menus.extend(self.findChildren(QtWidgets.QMenu))
        for menu in menus:
            try:
                if menu.isVisible() and menu.frameGeometry().contains(global_position):
                    return True
            except Exception:
                pass
        return False

    def _begin_outside_dismiss(self, event):
        global_position = _event_global_position(event)
        if self.isVisible() and not self._is_inside_menu_tree(global_position):
            self._outside_dismiss_button = event.button()
            event.accept()
            return True
        return False

    def _finish_outside_dismiss(self, event):
        if self._outside_dismiss_button == _qt_mouse_button("NoButton"):
            return False

        event.accept()
        if event.button() == self._outside_dismiss_button:
            self._outside_dismiss_button = _qt_mouse_button("NoButton")
            self.close()
        return True

    def eventFilter(self, watched, event):
        event_type = event.type()
        mouse_press_types = (
            _qt_event_type("MouseButtonPress"),
            _qt_event_type("MouseButtonDblClick"),
            _qt_event_type("NonClientAreaMouseButtonPress"),
        )
        if event_type in mouse_press_types:
            if self._begin_outside_dismiss(event):
                return True
        elif event_type == _qt_event_type("MouseButtonRelease"):
            if self._finish_outside_dismiss(event):
                return True
        return QtCore.QObject.eventFilter(self, watched, event)


def _show_dropdown_now(global_position):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    previous_popup = getattr(builtins, STATE_NAME, None)
    focus_target = None
    if previous_popup is not None:
        try:
            focus_target = getattr(previous_popup, "_focus_target", None)
        except Exception:
            pass
        try:
            previous_popup.cancel_focus_restore()
        except Exception:
            pass
        try:
            previous_popup.close()
        except Exception:
            pass

    if focus_target is None:
        try:
            focus_target = app.widgetAt(global_position)
        except Exception:
            focus_target = None
    if focus_target is None:
        focus_target = app.focusWidget()

    parent = None
    if focus_target is not None:
        try:
            parent = focus_target.window()
        except Exception:
            pass
    if parent is None:
        parent = app.activeWindow()

    popup = AddAssetDropdown(parent, focus_target)
    builtins.__dict__[STATE_NAME] = popup
    popup.popup(global_position)
    return popup


def show_dropdown(global_position=None):
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

    pressed_virtual_inputs = _pressed_virtual_inputs()
    if pressed_virtual_inputs:
        pending = DeferredAssetDropdownPopup(
            app,
            global_position,
            pressed_virtual_inputs,
        ).start()
        builtins.__dict__[PENDING_STATE_NAME] = pending
        return pending

    return _show_dropdown_now(global_position)


def run_with_error_dialog():
    try:
        show_dropdown()
    except Exception:
        FBMessageBox(TOOL_NAME, traceback.format_exc(), "OK")


run_with_error_dialog()
