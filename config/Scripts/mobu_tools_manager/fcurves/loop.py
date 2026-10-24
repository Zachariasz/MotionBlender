"""Loop boundary key tangent and value synchronization for MotionBuilder FCurves."""

from __future__ import absolute_import

import math

try:
    from pyfbsdk import (
        FBExtrapolationMode,
        FBFCurveEditorUtility,
        FBMessageBox,
        FBSystem,
        FBTangentMode,
        FBTangentWeightMode,
        FBTime,
        FBUndoManager,
    )
except ImportError:
    pass

from .discovery import (
    _curve_for_node,
    focused_animation_nodes,
    selected_curve_records,
)


TOOL_NAME = "Sync Loop Tangents"
EPSILON = 0.000001
MAX_DERIVATIVE = 1000000.0


def key_is_selected(fcurve, index):
    """Check if key at index is selected or marked for manipulation."""
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


def fcurve_has_selected_key(fcurve):
    """Return True if any key on the curve is selected."""
    try:
        key_count = len(fcurve.Keys)
    except Exception:
        key_count = 0
    for index in range(key_count):
        if key_is_selected(fcurve, index):
            return True
    return False


def fcurve_is_selected(fcurve):
    """Check if curve itself is selected or has any selected keys."""
    try:
        if fcurve.Selected:
            return True
    except Exception:
        pass
    return fcurve_has_selected_key(fcurve)


def collect_visible_fcurves(system=None):
    """Collect all FCurves visible in the FCurve editor."""
    if system is None:
        system = FBSystem()
    fcurves = set()
    try:
        layer_index = int(system.CurrentTake.GetCurrentLayer())
    except Exception:
        layer_index = None

    properties = []
    try:
        FBFCurveEditorUtility().GetProperties(properties, True)
    except Exception:
        return fcurves

    for prop in properties:
        for node in focused_animation_nodes(prop):
            curve = _curve_for_node(node, layer_index)
            if curve is not None:
                try:
                    if len(curve.Keys) > 0:
                        fcurves.add(curve)
                except Exception:
                    pass
    return fcurves


def _clamp(value, min_val, max_val):
    return max(float(min_val), min(float(max_val), float(value)))


def _balanced_derivative(deriv_a, deriv_b):
    """Compute balanced slope angle between two derivatives."""
    angle_a = math.atan(float(deriv_a))
    angle_b = math.atan(float(deriv_b))
    avg_angle = (angle_a + angle_b) * 0.5
    limit = (math.pi * 0.5) - 0.0001
    avg_angle = _clamp(avg_angle, -limit, limit)
    return _clamp(math.tan(avg_angle), -MAX_DERIVATIVE, MAX_DERIVATIVE)


def sync_fcurve_loop_tangents(fcurve, match_value=True):
    """Synchronize boundary tangents and optionally values for a single FCurve.

    Identifies key 0 (start) and key N-1 (end):
    - If key 0 is selected and key N-1 is not: propagates key 0 to key N-1.
    - If key N-1 is selected and key 0 is not: propagates key N-1 to key 0.
    - If both or neither are selected: calculates the balanced average slope
      between key 0 right derivative and key N-1 left derivative, and copies
      key 0 value to key N-1.

    Sets tangent mode to User and unbreaks tangents to ensure seamless C1
    continuity across cycle repetition.
    """
    try:
        key_count = len(fcurve.Keys)
    except Exception:
        return False

    if key_count < 2:
        return False

    first_idx = 0
    last_idx = key_count - 1

    first_sel = key_is_selected(fcurve, first_idx)
    last_sel = key_is_selected(fcurve, last_idx)

    # Determine master key / source
    if first_sel and not last_sel:
        # Key 0 is master
        target_derivative = float(fcurve.KeyGetRightDerivative(first_idx))
        target_value = float(fcurve.KeyGetValue(first_idx))
        target_weight = float(fcurve.KeyGetRightTangentWeight(first_idx))
        value_dest_idx = last_idx
    elif last_sel and not first_sel:
        # Key N-1 is master
        target_derivative = float(fcurve.KeyGetLeftDerivative(last_idx))
        target_value = float(fcurve.KeyGetValue(last_idx))
        target_weight = float(fcurve.KeyGetLeftTangentWeight(last_idx))
        value_dest_idx = first_idx
    else:
        # Both or neither: balanced average slope, start key anchors value
        deriv_0 = float(fcurve.KeyGetRightDerivative(first_idx))
        deriv_last = float(fcurve.KeyGetLeftDerivative(last_idx))
        target_derivative = _balanced_derivative(deriv_0, deriv_last)
        target_value = float(fcurve.KeyGetValue(first_idx))
        w0 = float(fcurve.KeyGetRightTangentWeight(first_idx))
        w_last = float(fcurve.KeyGetLeftTangentWeight(last_idx))
        target_weight = (w0 + w_last) * 0.5
        value_dest_idx = last_idx

    try:
        fcurve.EditBegin()
    except Exception:
        pass

    try:
        # Switch both boundary keys to User mode (manual) to prevent procedural overwrite
        user_mode = getattr(FBTangentMode, "kFBTangentModeUser", 2)
        fcurve.KeySetTangentMode(first_idx, user_mode)
        fcurve.KeySetTangentMode(last_idx, user_mode)

        # Unbreak tangents so handle forms a continuous straight tangent across the key
        fcurve.KeySetTangentBreak(first_idx, False)
        fcurve.KeySetTangentBreak(last_idx, False)

        # Apply synchronized derivatives to both keys
        fcurve.KeySetLeftDerivative(first_idx, target_derivative)
        fcurve.KeySetRightDerivative(first_idx, target_derivative)
        fcurve.KeySetLeftDerivative(last_idx, target_derivative)
        fcurve.KeySetRightDerivative(last_idx, target_derivative)

        # Synchronize tangent weights
        try:
            fcurve.KeySetLeftTangentWeight(first_idx, target_weight)
            fcurve.KeySetRightTangentWeight(first_idx, target_weight)
            fcurve.KeySetLeftTangentWeight(last_idx, target_weight)
            fcurve.KeySetRightTangentWeight(last_idx, target_weight)
        except Exception:
            pass

        # Match values to eliminate vertical step/pop in looping animation
        if match_value:
            fcurve.KeySetValue(value_dest_idx, target_value)

        return True
    finally:
        try:
            fcurve.EditEnd()
        except Exception:
            pass


def _refresh_fcurves():
    """Trigger scene and Qt FCurve widget updates."""
    try:
        FBSystem().Scene.Evaluate()
    except Exception:
        pass

    try:
        from PySide6 import QtWidgets
    except ImportError:
        try:
            from PySide2 import QtWidgets
        except ImportError:
            return

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


def sync_selected_fcurves_loop_tangents(match_value=True):
    """Main command entrypoint to synchronize loop tangents on all selected FCurves."""
    undo_mgr = None
    owns_transaction = False
    try:
        undo_mgr = FBUndoManager()
        if not undo_mgr.TransactionIsOpen():
            owns_transaction = bool(undo_mgr.TransactionBegin(TOOL_NAME))
    except Exception:
        undo_mgr = None

    changed_count = 0
    scanned_count = 0

    try:
        curves = collect_visible_fcurves()
        for fcurve in curves:
            scanned_count += 1
            if not fcurve_is_selected(fcurve):
                continue
            if sync_fcurve_loop_tangents(fcurve, match_value=match_value):
                changed_count += 1
    finally:
        if undo_mgr is not None and owns_transaction:
            try:
                undo_mgr.TransactionEnd()
            except Exception:
                pass

    if changed_count > 0:
        _refresh_fcurves()
        print("Success: Synchronized loop tangents on %d FCurve(s)." % changed_count)
    else:
        print("Notice: No selected FCurves with >= 2 keys found. Scanned %d FCurve(s)." % scanned_count)

    return changed_count
