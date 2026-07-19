"""Context-only tangent menu for selected keys in MotionBuilder FCurves."""

from __future__ import print_function

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

import ctypes
import os
import traceback

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from pyfbsdk import (
    FBFCurveEditorUtility,
    FBPlayerControl,
    FBSystem,
    FBTangentMode,
    FBTangentWeightMode,
    FBTime,
    FBUndoManager,
)


TOOL_NAME = "Selected Key Tangents"
STATE_NAME = "_motionbuilder_selected_key_tangents_menu"
PENDING_STATE_NAME = "_motionbuilder_selected_key_tangents_pending"
LAST_ACTION_STATE_NAME = "_motionbuilder_selected_key_tangents_last_action"
AUTORUN_NAME = "SELECTED_KEY_TANGENTS_MENU_AUTORUN"


def _widget_text(widget):
    parts = []
    seen = set()
    current = widget

    while current is not None and id(current) not in seen:
        seen.add(id(current))
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


def _is_fcurve_widget(widget):
    if widget is None:
        return False

    description = _widget_text(widget)
    if "fcurvelayerview" in description and not any(
        token in description
        for token in ("fcurvepropertyview", "curvelayout")
    ):
        return False

    if any(
        token in description
        for token in ("fcurvepropertyview", "curvelayout", "fcurves window")
    ):
        return True

    current = widget
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            if str(current.accessibleName() or "").strip().lower() == "fcurve":
                return True
            current = current.parentWidget()
        except Exception:
            current = None
    return False


def _widget_global_rect(widget):
    top_left = widget.mapToGlobal(QtCore.QPoint(0, 0))
    return QtCore.QRect(top_left, widget.size())


def _fcurve_widget_at(global_position):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    try:
        widget = app.widgetAt(global_position)
    except Exception:
        widget = None

    if widget is not None and _is_fcurve_widget(widget):
        return widget

    matches = []
    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []

    for candidate in widgets:
        try:
            if not candidate.isVisible() or not _is_fcurve_widget(candidate):
                continue
            rect = _widget_global_rect(candidate)
            if rect.contains(global_position):
                matches.append((rect.width() * rect.height(), candidate))
        except Exception:
            pass

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _add_curve(registry, fcurve, prop):
    if fcurve is None:
        return
    try:
        if len(fcurve.Keys) <= 0:
            return
    except Exception:
        return

    if fcurve not in registry:
        registry[fcurve] = prop
    elif registry[fcurve] is None and prop is not None:
        registry[fcurve] = prop


def _scan_animation_node(registry, animation_node, layer_index, prop):
    if animation_node is None:
        return

    try:
        _add_curve(
            registry,
            animation_node.GetFCurve(layer_index),
            prop,
        )
    except Exception:
        pass

    try:
        _add_curve(registry, animation_node.FCurve, prop)
    except Exception:
        pass

    try:
        children = list(animation_node.Nodes)
    except Exception:
        children = []

    for child in children:
        _scan_animation_node(registry, child, layer_index, prop)


def _displayed_curves():
    properties = []
    registry = {}
    system = FBSystem()

    try:
        FBFCurveEditorUtility().GetProperties(properties, False)
    except Exception:
        return registry

    try:
        layer_index = int(system.CurrentTake.GetCurrentLayer())
    except Exception:
        layer_index = 0

    for prop in properties:
        try:
            if prop.IsAnimated():
                _scan_animation_node(
                    registry,
                    prop.GetAnimationNode(),
                    layer_index,
                    prop,
                )
        except Exception:
            pass

    return registry


def _key_is_selected(fcurve, index):
    try:
        if bool(fcurve.KeyGetSelected(index)):
            return True
    except Exception:
        pass

    try:
        if bool(fcurve.Keys[index].Selected):
            return True
    except Exception:
        pass

    try:
        if bool(fcurve.KeyGetMarkedForManipulation(index)):
            return True
    except Exception:
        pass

    try:
        return bool(fcurve.Keys[index].MarkedForManipulation)
    except Exception:
        return False


def _weight_mode_sides(weight_mode):
    """Return the right and next-key-left flags stored on one key."""
    if weight_mode == FBTangentWeightMode.kFBTangentWeightModeBoth:
        return True, True
    if weight_mode == FBTangentWeightMode.kFBTangentWeightModeRight:
        return True, False
    if weight_mode == FBTangentWeightMode.kFBTangentWeightModeNextLeft:
        return False, True
    return False, False


def _weight_mode_from_sides(right_active, next_left_active):
    if right_active and next_left_active:
        return FBTangentWeightMode.kFBTangentWeightModeBoth
    if right_active:
        return FBTangentWeightMode.kFBTangentWeightModeRight
    if next_left_active:
        return FBTangentWeightMode.kFBTangentWeightModeNextLeft
    return FBTangentWeightMode.kFBTangentWeightModeNone


def _key_has_weighted_tangent(fcurve, index):
    """Test both actual tangents of a key, not its storage record alone."""
    try:
        key_count = len(fcurve.Keys)
        mode = fcurve.KeyGetTangentWeightMode(index)
    except Exception:
        return False

    right_active, _unused_next_left = _weight_mode_sides(mode)
    left_active = False
    if index > 0:
        try:
            _unused_right, left_active = _weight_mode_sides(
                fcurve.KeyGetTangentWeightMode(index - 1)
            )
        except Exception:
            pass

    if index >= key_count - 1:
        right_active = False
    return left_active or right_active


def _selected_keys():
    selected = []

    for fcurve, prop in _displayed_curves().items():
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        for index in range(key_count):
            if not _key_is_selected(fcurve, index):
                continue
            try:
                selected.append(
                    {
                        "curve": fcurve,
                        "index": index,
                        "property": prop,
                        "broken": (
                            bool(fcurve.KeyGetTangentBreak(index))
                            or fcurve.KeyGetTangentMode(index)
                            == FBTangentMode.kFBTangentModeBreak
                        ),
                        "weighted": _key_has_weighted_tangent(fcurve, index),
                    }
                )
            except Exception:
                pass

    return selected


def _unique_properties(selected_keys):
    properties = []
    seen = set()

    for key in selected_keys:
        prop = key.get("property")
        if prop is None:
            continue
        try:
            identity = hash(prop)
        except Exception:
            identity = id(prop)
        if identity in seen:
            continue
        seen.add(identity)
        properties.append(prop)

    return properties


def _begin_undo(label, selected_keys):
    manager = FBUndoManager()
    owns_transaction = False

    try:
        if not manager.TransactionIsOpen():
            owns_transaction = bool(manager.TransactionBegin(label))
        for prop in _unique_properties(selected_keys):
            try:
                manager.TransactionAddProperty(prop)
            except Exception:
                pass
    except Exception:
        if owns_transaction:
            try:
                manager.TransactionEnd()
            except Exception:
                pass
        raise

    return manager, owns_transaction


def _end_undo(manager, owns_transaction):
    if owns_transaction:
        try:
            manager.TransactionEnd()
        except Exception:
            pass


def _frame_ticks():
    try:
        frames_per_second = float(FBPlayerControl().GetTransportFps())
    except Exception:
        frames_per_second = 0.0

    if frames_per_second <= 0.000001:
        return max(1, int(FBTime(0, 0, 0, 1).Get()))

    return max(1, int(round(float(FBTime.OneSecond.Get()) / frames_per_second)))


def _refresh_scene_after_fcurve_edit():
    """Force current-time properties to resolve after an FCurve edit."""
    system = FBSystem()
    current_time = FBTime(system.LocalTime.Get())
    current_ticks = int(current_time.Get())
    frame_ticks = _frame_ticks()
    refresh_ticks = current_ticks + frame_ticks

    try:
        take = system.CurrentTake
        time_span = take.LocalTimeSpan if take is not None else None
        start_ticks = int(time_span.GetStart().Get())
        stop_ticks = int(time_span.GetStop().Get())
        if refresh_ticks > stop_ticks and current_ticks - frame_ticks >= start_ticks:
            refresh_ticks = current_ticks - frame_ticks
    except Exception:
        pass

    try:
        player = FBPlayerControl()
        refresh_succeeded = bool(player.Goto(FBTime(refresh_ticks)))
        restore_succeeded = bool(player.Goto(current_time))
        if refresh_succeeded and restore_succeeded:
            return True
    except Exception:
        pass

    try:
        return bool(system.Scene.Evaluate())
    except Exception:
        return False


def _refresh_fcurves():
    try:
        _refresh_scene_after_fcurve_edit()
    except Exception:
        pass

    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []
    for widget in widgets:
        try:
            if str(widget.accessibleName() or "").strip().lower() == "fcurve":
                widget.update()
        except Exception:
            pass


def set_tangents_broken(selected_keys, broken):
    if not selected_keys:
        return 0

    label = "Break Tangents" if broken else "Unbreak Tangents"
    undo_manager, owns_transaction = _begin_undo(label, selected_keys)
    changed = 0

    try:
        for key in selected_keys:
            fcurve = key["curve"]
            index = key["index"]

            if broken:
                fcurve.KeySetTangentMode(
                    index,
                    FBTangentMode.kFBTangentModeBreak,
                )
                fcurve.KeySetTangentBreak(index, True)
            else:
                # MotionBuilder's Unify Tangents uses the incoming tangent as
                # the shared slope, then switches the key to User tangents.
                derivative = float(fcurve.KeyGetLeftDerivative(index))
                fcurve.KeySetTangentMode(
                    index,
                    FBTangentMode.kFBTangentModeUser,
                )
                fcurve.KeySetTangentBreak(index, False)
                fcurve.KeySetLeftDerivative(index, derivative)
                fcurve.KeySetRightDerivative(index, derivative)
            changed += 1
    finally:
        _end_undo(undo_manager, owns_transaction)

    _refresh_fcurves()
    return changed


def set_tangents_weighted(selected_keys, weighted):
    if not selected_keys:
        return 0

    label = "Weighted Tangents" if weighted else "Unweighted Tangents"
    undo_manager, owns_transaction = _begin_undo(label, selected_keys)
    changed = 0

    try:
        changed = _set_selected_tangent_weight_sides(selected_keys, weighted)
    finally:
        _end_undo(undo_manager, owns_transaction)

    _refresh_fcurves()
    return changed


def _set_selected_tangent_weight_sides(selected_keys, weighted):
    """Enable or disable the actual left and right sides of selected keys.

    MotionBuilder stores a key's right flag on that key, but its left flag as
    ``NextLeft`` on the previous key. Updating both records is required for a
    true Weighted/Unweighted Tangents command.
    """
    updates = {}

    def update_for(fcurve, index):
        token = (id(fcurve), index)
        update = updates.get(token)
        if update is None:
            right_active, next_left_active = _weight_mode_sides(
                fcurve.KeyGetTangentWeightMode(index)
            )
            update = {
                "curve": fcurve,
                "index": index,
                "right_active": right_active,
                "next_left_active": next_left_active,
            }
            updates[token] = update
        return update

    for key in selected_keys:
        fcurve = key["curve"]
        index = key["index"]
        try:
            key_count = len(fcurve.Keys)
        except Exception:
            continue

        if index < key_count - 1:
            update_for(fcurve, index)["right_active"] = bool(weighted)
        if index > 0:
            update_for(fcurve, index - 1)["next_left_active"] = bool(weighted)

    for update in updates.values():
        update["curve"].KeySetTangentWeightMode(
            update["index"],
            _weight_mode_from_sides(
                update["right_active"],
                update["next_left_active"],
            ),
        )

    return len(selected_keys)


def _key_time_seconds(fcurve, index):
    return float(fcurve.Keys[index].Time.GetSecondDouble())


def _key_value(fcurve, index):
    try:
        return float(fcurve.Keys[index].Value)
    except Exception:
        return float(fcurve.KeyGetValue(index))


def _neighbor_slopes(fcurve, index):
    key_count = len(fcurve.Keys)
    current_time = _key_time_seconds(fcurve, index)
    current_value = _key_value(fcurve, index)
    left_slope = None
    right_slope = None

    if index > 0:
        previous_time = _key_time_seconds(fcurve, index - 1)
        delta_time = current_time - previous_time
        if abs(delta_time) > 0.000000000001:
            left_slope = (
                current_value - _key_value(fcurve, index - 1)
            ) / delta_time

    if index + 1 < key_count:
        next_time = _key_time_seconds(fcurve, index + 1)
        delta_time = next_time - current_time
        if abs(delta_time) > 0.000000000001:
            right_slope = (
                _key_value(fcurve, index + 1) - current_value
            ) / delta_time

    return left_slope, right_slope


def set_discontinuity_tangent(selected_keys, side):
    if not selected_keys:
        return 0
    if side not in ("left", "right"):
        raise ValueError("Tangent side must be 'left' or 'right'.")

    label = "Align Left Tangent" if side == "left" else "Align Right Tangent"
    slopes = []
    for key in selected_keys:
        try:
            left_slope, right_slope = _neighbor_slopes(
                key["curve"],
                key["index"],
            )
            slopes.append((key, left_slope, right_slope))
        except Exception:
            pass

    undo_manager, owns_transaction = _begin_undo(label, selected_keys)
    changed = 0
    try:
        for key, left_slope, right_slope in slopes:
            fcurve = key["curve"]
            index = key["index"]
            was_broken = (
                bool(fcurve.KeyGetTangentBreak(index))
                or fcurve.KeyGetTangentMode(index)
                == FBTangentMode.kFBTangentModeBreak
            )
            if side == "left" and left_slope is not None:
                fcurve.KeySetLeftDerivative(index, left_slope)
                changed += 1
            elif side == "right" and right_slope is not None:
                fcurve.KeySetRightDerivative(index, right_slope)
                if not was_broken:
                    # MotionBuilder only propagates an unbroken tangent through
                    # the left setter. Repeat the right slope there so the key
                    # remains a single, unbroken tangent like Align Left does.
                    fcurve.KeySetLeftDerivative(index, right_slope)
                changed += 1
    finally:
        _end_undo(undo_manager, owns_transaction)

    _refresh_fcurves()
    return changed


def set_vector_tangents(selected_keys):
    if not selected_keys:
        return 0

    slopes = []
    for key in selected_keys:
        try:
            left_slope, right_slope = _neighbor_slopes(
                key["curve"],
                key["index"],
            )
        except Exception:
            left_slope, right_slope = None, None
        slopes.append((key, left_slope, right_slope))

    undo_manager, owns_transaction = _begin_undo(
        "Vector Tangents",
        selected_keys,
    )
    changed = 0

    try:
        for key, left_slope, right_slope in slopes:
            fcurve = key["curve"]
            index = key["index"]

            # Match the requested native sequence: break, set left/right
            # discontinuity, then remove tangent weighting.
            fcurve.KeySetTangentMode(
                index,
                FBTangentMode.kFBTangentModeBreak,
            )
            fcurve.KeySetTangentBreak(index, True)
            if left_slope is not None:
                fcurve.KeySetLeftDerivative(index, left_slope)
            if right_slope is not None:
                fcurve.KeySetRightDerivative(index, right_slope)
            changed += 1
        _set_selected_tangent_weight_sides(selected_keys, False)
    finally:
        _end_undo(undo_manager, owns_transaction)

    _refresh_fcurves()
    return changed


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


def _fcurve_focus_target(global_position, context_widget):
    app = QtWidgets.QApplication.instance()
    if app is None or context_widget is None:
        return context_widget

    try:
        context_window = context_widget.window()
    except Exception:
        context_window = None

    contained = []
    same_window = []
    try:
        widgets = app.allWidgets()
    except Exception:
        widgets = []

    for widget in widgets:
        try:
            if not widget.isVisible():
                continue
            if str(widget.accessibleName() or "").strip().lower() != "fcurve":
                continue
            if context_window is not None and widget.window() is not context_window:
                continue
            rect = _widget_global_rect(widget)
            item = (rect.width() * rect.height(), widget)
            same_window.append(item)
            if rect.contains(global_position):
                contained.append(item)
        except Exception:
            pass

    matches = contained or same_window
    if not matches:
        return context_widget
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


class DeferredTangentMenuPopup(QtCore.QObject):
    """Wait until the invoking shortcut is fully released."""

    def __init__(
        self,
        app,
        global_position,
        pressed_virtual_keys,
        key_state_reader=None,
    ):
        QtCore.QObject.__init__(self, app)
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
        if getattr(builtins, PENDING_STATE_NAME, None) is self:
            setattr(builtins, PENDING_STATE_NAME, None)
        self.deleteLater()

    def _keys_are_down(self):
        try:
            return bool(self.key_state_reader(self.pressed_virtual_keys))
        except Exception:
            return False

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyRelease:
            QtCore.QTimer.singleShot(0, self._schedule_if_released)
        return False

    def _poll(self):
        if not self._keys_are_down():
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
            setattr(builtins, PENDING_STATE_NAME, None)
        _show_tangent_menu_now(self.global_position)
        self.deleteLater()


class SelectedKeyTangentsMenu(QtWidgets.QMenu):
    def __init__(self, selected_keys, focus_target=None, parent=None):
        QtWidgets.QMenu.__init__(self, parent)
        self.selected_keys = selected_keys
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
        self._launching_action = False
        self._pending_operation = None
        self._outside_dismiss_button = QtCore.Qt.MouseButton.NoButton
        self._actions_by_id = {}
        self.setObjectName("SelectedKeyTangentsMenu")
        self.setWindowTitle(TOOL_NAME)
        self.setTearOffEnabled(False)

        should_break = all(
            not key.get("broken", False)
            for key in selected_keys
        )
        toggle_label = (
            "Break Tangents" if should_break else "Unbreak Tangents"
        )
        toggle_action = self.addAction(toggle_label)
        self._actions_by_id["break"] = toggle_action
        toggle_action.setEnabled(bool(selected_keys))
        toggle_action.triggered.connect(
            lambda _checked=False: self._queue_operation(
                lambda: set_tangents_broken(
                    self.selected_keys,
                    should_break,
                ),
                "break",
            )
        )

        should_weight = all(
            not key.get("weighted", False)
            for key in selected_keys
        )
        weight_label = (
            "Weighted Tangents"
            if should_weight
            else "Unweighted Tangents"
        )
        weight_action = self.addAction(weight_label)
        self._actions_by_id["weight"] = weight_action
        weight_action.setEnabled(bool(selected_keys))
        weight_action.triggered.connect(
            lambda _checked=False: self._queue_operation(
                lambda: set_tangents_weighted(
                    self.selected_keys,
                    should_weight,
                ),
                "weight",
            )
        )

        self.addSeparator()

        align_left_action = self.addAction("Align Left")
        self._actions_by_id["align_left"] = align_left_action
        align_left_action.setEnabled(bool(selected_keys))
        align_left_action.triggered.connect(
            lambda _checked=False: self._queue_operation(
                lambda: set_discontinuity_tangent(
                    self.selected_keys,
                    "left",
                ),
                "align_left",
            )
        )

        align_right_action = self.addAction("Align Right")
        self._actions_by_id["align_right"] = align_right_action
        align_right_action.setEnabled(bool(selected_keys))
        align_right_action.triggered.connect(
            lambda _checked=False: self._queue_operation(
                lambda: set_discontinuity_tangent(
                    self.selected_keys,
                    "right",
                ),
                "align_right",
            )
        )

        vector_action = self.addAction("Vector")
        self._actions_by_id["vector"] = vector_action
        vector_action.setEnabled(bool(selected_keys))
        vector_action.triggered.connect(
            lambda _checked=False: self._queue_operation(
                lambda: set_vector_tangents(self.selected_keys),
                "vector",
            )
        )

        self.aboutToShow.connect(self._install_outside_click_filter)
        self.aboutToHide.connect(self._remove_outside_click_filter)

    def action_for_id(self, action_id):
        return self._actions_by_id.get(action_id)

    def _queue_operation(self, operation, action_id=None):
        if self._pending_operation is not None:
            return
        if action_id is not None:
            setattr(builtins, LAST_ACTION_STATE_NAME, action_id)
        self._launching_action = True
        self._pending_operation = operation
        self.cancel_focus_restore()
        self.close()
        # QMenu must release its popup and mouse grab before the editor is
        # focused and the FCurve edit begins.
        QtCore.QTimer.singleShot(0, self._run_pending_operation)

    def _run_pending_operation(self):
        operation = self._pending_operation
        try:
            self._restore_source_focus(force=True)
            if operation is not None:
                operation()
        except Exception:
            print(traceback.format_exc())
        finally:
            self._pending_operation = None
            self._launching_action = False
            QtCore.QTimer.singleShot(0, self._finish_pending_operation)

    def _finish_pending_operation(self):
        # Reassert the source editor after evaluation/redraw, since either can
        # move native focus away from the FCurve surface.
        self._restore_source_focus(force=True)
        self._release()

    def _install_outside_click_filter(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    def _remove_outside_click_filter(self):
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._launching_action:
            self.cancel_focus_restore()
        else:
            self._schedule_focus_restore_and_release()

    def cancel_focus_restore(self):
        self._focus_restore_generation += 1

    def _schedule_focus_restore_and_release(self):
        self._focus_restore_generation += 1
        generation = self._focus_restore_generation
        QtCore.QTimer.singleShot(
            0,
            lambda expected=generation: self._restore_and_release(expected),
        )

    def _restore_and_release(self, expected_generation):
        self._restore_source_focus(expected_generation)
        self._release()

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
        return not self.frameGeometry().contains(
            _event_global_position(event)
        )

    def _begin_outside_dismiss(self, event):
        if self.isVisible() and self._is_outside(event):
            # Consume both halves of the same gesture. Letting only the release
            # reach FCurves can leave its cursor/manipulation mode stuck.
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

    def dismiss_if_outside(self, global_position):
        if self.isVisible() and not self.frameGeometry().contains(global_position):
            self.close()
            return True
        return False

    def _release(self):
        if self._pending_operation is not None or self._launching_action:
            return
        if getattr(builtins, STATE_NAME, None) is self:
            setattr(builtins, STATE_NAME, None)
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass
        self.deleteLater()


def _menu_popup_position(menu, cursor_position):
    """Place the last-used row under the cursor without covering its label."""
    action_id = getattr(builtins, LAST_ACTION_STATE_NAME, None)
    action = menu.action_for_id(action_id)
    if action is None:
        return cursor_position

    try:
        menu.ensurePolished()
        menu.adjustSize()
        action_rect = menu.actionGeometry(action)
        if action_rect.width() <= 0 or action_rect.height() <= 0:
            return cursor_position
        cursor_offset_x = action_rect.x() + int(
            round(action_rect.width() * 5.0 / 6.0)
        )
        cursor_offset_y = action_rect.y() + action_rect.height() // 2
        return QtCore.QPoint(
            cursor_position.x() - cursor_offset_x,
            cursor_position.y() - cursor_offset_y,
        )
    except Exception:
        return cursor_position


def _show_tangent_menu_now(global_position=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    if global_position is None:
        global_position = QtGui.QCursor.pos()

    context_widget = _fcurve_widget_at(global_position)
    if context_widget is None:
        return None
    focus_target = _fcurve_focus_target(global_position, context_widget)

    previous_menu = getattr(builtins, STATE_NAME, None)
    if previous_menu is not None:
        try:
            previous_menu.cancel_focus_restore()
            previous_menu.close()
        except Exception:
            pass

    try:
        parent = focus_target.window()
    except Exception:
        parent = app.activeWindow()

    menu = SelectedKeyTangentsMenu(
        _selected_keys(),
        focus_target,
        parent,
    )
    setattr(builtins, STATE_NAME, menu)
    menu.popup(_menu_popup_position(menu, global_position))
    return menu


def show_tangent_menu(global_position=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    if global_position is None:
        global_position = QtGui.QCursor.pos()

    if _fcurve_widget_at(global_position) is None:
        return None

    previous_pending = getattr(builtins, PENDING_STATE_NAME, None)
    if previous_pending is not None:
        try:
            previous_pending.cancel()
        except Exception:
            pass

    pressed_virtual_keys = _pressed_virtual_keys()
    if pressed_virtual_keys:
        pending = DeferredTangentMenuPopup(
            app,
            global_position,
            pressed_virtual_keys,
        )
        setattr(builtins, PENDING_STATE_NAME, pending)
        return pending.start()

    return _show_tangent_menu_now(global_position)


def run():
    try:
        return show_tangent_menu()
    except Exception:
        print(traceback.format_exc())
        return None


if globals().get(AUTORUN_NAME, True):
    run()
