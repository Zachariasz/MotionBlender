"""Captured tangent state and balanced weighted-tangent mutation."""

from __future__ import absolute_import

import math


MIN_TANGENT_WEIGHT = 0.0001
MAX_TANGENT_WEIGHT = 0.99
MAX_DERIVATIVE = 1000000.0
EPSILON = 0.000001

_OPTIONAL_ATTRIBUTES = (
    ("tangent_clamp_mode", "KeyGetTangentClampMode", "KeySetTangentClampMode"),
    (
        "tangent_constant_mode",
        "KeyGetTangentConstantMode",
        "KeySetTangentConstantMode",
    ),
    (
        "tangent_custom_index",
        "KeyGetTangentCustomIndex",
        "KeySetTangentCustomIndex",
    ),
)


def clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def scale_tangent_angle(derivative, factor, derivative_scale):
    scale = max(EPSILON, abs(float(derivative_scale)))
    angle = math.atan(float(derivative) / scale) * float(factor)
    limit = (math.pi * 0.5) - 0.0001
    angle = clamp(angle, -limit, limit)
    return clamp(
        math.tan(angle) * scale,
        -MAX_DERIVATIVE,
        MAX_DERIVATIVE,
    )


def rotate_tangent_angle(derivative, angle_degrees, derivative_scale):
    scale = max(EPSILON, abs(float(derivative_scale)))
    angle = math.atan(float(derivative) / scale) + math.radians(
        float(angle_degrees)
    )
    limit = (math.pi * 0.5) - 0.0001
    angle = clamp(angle, -limit, limit)
    return clamp(
        math.tan(angle) * scale,
        -MAX_DERIVATIVE,
        MAX_DERIVATIVE,
    )


def tangent_angle_degrees(derivative, derivative_scale):
    scale = max(EPSILON, abs(float(derivative_scale)))
    return math.degrees(math.atan(float(derivative) / scale))


class TangentSnapshot(object):
    def __init__(self, key_snapshot, index):
        curve = key_snapshot.curve
        self.key_snapshot = key_snapshot
        self.curve = curve
        self.original_index = int(index)
        self.original_tangent_mode = curve.KeyGetTangentMode(index)
        self.original_tangent_break = bool(
            curve.KeyGetTangentBreak(index)
        )
        self.original_weight_mode = curve.KeyGetTangentWeightMode(index)
        self.original_left_derivative = float(
            curve.KeyGetLeftDerivative(index)
        )
        self.original_right_derivative = float(
            curve.KeyGetRightDerivative(index)
        )
        self.original_left_weight = float(
            curve.KeyGetLeftTangentWeight(index)
        )
        self.original_right_weight = float(
            curve.KeyGetRightTangentWeight(index)
        )
        self.current_left_derivative = self.original_left_derivative
        self.current_right_derivative = self.original_right_derivative
        self.current_left_weight = self.original_left_weight
        self.current_right_weight = self.original_right_weight
        self.independent_edit = False
        self.manual_prepared = False
        self.original_unified = (
            not self.original_tangent_break
            and abs(
                self.original_left_derivative
                - self.original_right_derivative
            )
            <= EPSILON
        )
        self.optional_attributes = {}
        for name, getter_name, setter_name in _OPTIONAL_ATTRIBUTES:
            try:
                self.optional_attributes[name] = (
                    setter_name,
                    getattr(curve, getter_name)(index),
                )
            except Exception:
                pass


def capture_tangents(key_snapshots):
    snapshots = []
    for key_snapshot in key_snapshots:
        try:
            snapshots.append(
                TangentSnapshot(
                    key_snapshot,
                    key_snapshot.original_index,
                )
            )
        except Exception:
            continue
    return tuple(snapshots)


class TangentMutationService(object):
    def __init__(self, snapshots, key_mutation):
        self.snapshots = tuple(snapshots)
        self.key_mutation = key_mutation
        self.by_curve = {}
        self.original_weight_modes = {}
        self.original_curve_tcb = {}
        self.weight_prepared_curves = set()
        self.weight_mode_dirty_curves = set()
        self.prepared = False
        for snapshot in self.snapshots:
            self.by_curve.setdefault(snapshot.curve, []).append(snapshot)
        for curve in self.by_curve:
            modes = []
            try:
                key_count = len(curve.Keys)
            except Exception:
                key_count = 0
            for index in range(key_count):
                try:
                    modes.append(curve.KeyGetTangentWeightMode(index))
                except Exception:
                    modes.append(None)
            self.original_weight_modes[curve] = tuple(modes)
            tcb_states = []
            for index in range(key_count):
                values = []
                for getter_name in (
                    "KeyGetTCBTension",
                    "KeyGetTCBContinuity",
                    "KeyGetTCBBias",
                ):
                    try:
                        values.append(
                            float(getattr(curve, getter_name)(index))
                        )
                    except Exception:
                        values.append(None)
                tcb_states.append(tuple(values))
            self.original_curve_tcb[curve] = tuple(tcb_states)

    @staticmethod
    def _weight_mode_sides(mode, enum):
        if mode == enum.kFBTangentWeightModeBoth:
            return True, True
        if mode == enum.kFBTangentWeightModeRight:
            return True, False
        if mode == enum.kFBTangentWeightModeNextLeft:
            return False, True
        return False, False

    @staticmethod
    def _weight_mode(right_active, next_left_active, enum):
        if right_active and next_left_active:
            return enum.kFBTangentWeightModeBoth
        if right_active:
            return enum.kFBTangentWeightModeRight
        if next_left_active:
            return enum.kFBTangentWeightModeNextLeft
        return enum.kFBTangentWeightModeNone

    def _prepare_curve(
        self,
        curve,
        states,
        weight_enum,
        targets,
        side,
    ):
        updates = {}

        def update(index):
            current = updates.get(index)
            if current is None:
                mode = curve.KeyGetTangentWeightMode(index)
                right, next_left = self._weight_mode_sides(
                    mode,
                    weight_enum,
                )
                current = [right, next_left]
                updates[index] = current
            return current

        key_count = len(curve.Keys)
        for snapshot in states:
            index = self.key_mutation.resolve_index(
                snapshot.key_snapshot
            )
            target = targets[snapshot]
            right_changed = side in ("both", "right") and self._changed(
                target["right_weight"],
                snapshot.current_right_weight,
            )
            left_changed = side in ("both", "left") and self._changed(
                target["left_weight"],
                snapshot.current_left_weight,
            )
            if right_changed and index < key_count - 1:
                update(index)[0] = True
            if left_changed and index > 0:
                update(index - 1)[1] = True
        for index, sides in updates.items():
            curve.KeySetTangentWeightMode(
                index,
                self._weight_mode(sides[0], sides[1], weight_enum),
            )
        return bool(updates)

    @staticmethod
    def _changed(left, right):
        return abs(float(left) - float(right)) > EPSILON

    def _break_for_independent_edit(
        self,
        snapshot,
        index,
        tangent_mode_enum,
    ):
        if snapshot.independent_edit:
            return
        curve = snapshot.curve
        left_derivative = snapshot.current_left_derivative
        right_derivative = snapshot.current_right_derivative
        curve.KeySetTangentMode(
            index,
            tangent_mode_enum.kFBTangentModeBreak,
        )
        curve.KeySetTangentBreak(index, True)
        curve.KeySetLeftDerivative(index, left_derivative)
        curve.KeySetRightDerivative(index, right_derivative)
        snapshot.independent_edit = True

    def _prepare_for_both_edit(
        self,
        snapshot,
        index,
        tangent_mode_enum,
    ):
        if snapshot.manual_prepared:
            return
        curve = snapshot.curve
        manual_mode = (
            tangent_mode_enum.kFBTangentModeBreak
            if (
                snapshot.original_tangent_break
                or self._changed(
                    snapshot.original_left_derivative,
                    snapshot.original_right_derivative,
                )
            )
            else tangent_mode_enum.kFBTangentModeUser
        )
        curve.KeySetTangentMode(index, manual_mode)
        curve.KeySetTangentBreak(
            index,
            manual_mode == tangent_mode_enum.kFBTangentModeBreak,
        )
        curve.KeySetLeftDerivative(
            index,
            snapshot.current_left_derivative,
        )
        curve.KeySetRightDerivative(
            index,
            snapshot.current_right_derivative,
        )
        snapshot.manual_prepared = True

    def apply(self, targets, side):
        from pyfbsdk import FBTangentMode, FBTangentWeightMode

        side = str(side).lower()
        for curve, states in self.by_curve.items():
            began = False
            try:
                try:
                    curve.KeyModifyBegin()
                    began = True
                except Exception:
                    pass
                if curve not in self.weight_prepared_curves:
                    if self._prepare_curve(
                        curve,
                        states,
                        FBTangentWeightMode,
                        targets,
                        side,
                    ):
                        self.weight_prepared_curves.add(curve)
                for snapshot in states:
                    index = self.key_mutation.resolve_index(
                        snapshot.key_snapshot
                    )
                    target = targets[snapshot]
                    left_weight_changed = (
                        side in ("both", "left")
                        and self._changed(
                            target["left_weight"],
                            snapshot.current_left_weight,
                        )
                    )
                    left_derivative_changed = (
                        side in ("both", "left")
                        and self._changed(
                            target["left_derivative"],
                            snapshot.current_left_derivative,
                        )
                    )
                    right_weight_changed = (
                        side in ("both", "right")
                        and self._changed(
                            target["right_weight"],
                            snapshot.current_right_weight,
                        )
                    )
                    right_derivative_changed = (
                        side in ("both", "right")
                        and self._changed(
                            target["right_derivative"],
                            snapshot.current_right_derivative,
                        )
                    )
                    left_changed = (
                        left_weight_changed
                        or left_derivative_changed
                    )
                    right_changed = (
                        right_weight_changed
                        or right_derivative_changed
                    )
                    if (
                        side != "both"
                        and (left_changed or right_changed)
                    ):
                        self._break_for_independent_edit(
                            snapshot,
                            index,
                            FBTangentMode,
                        )
                    elif side == "both" and (
                        left_changed or right_changed
                    ):
                        self._prepare_for_both_edit(
                            snapshot,
                            index,
                            FBTangentMode,
                        )
                    if (
                        left_derivative_changed
                        or right_derivative_changed
                    ):
                        self.weight_mode_dirty_curves.add(curve)
                    if side in ("both", "left"):
                        if left_changed:
                            if left_weight_changed:
                                curve.KeySetLeftTangentWeight(
                                    index,
                                    target["left_weight"],
                                )
                            if left_derivative_changed:
                                curve.KeySetLeftDerivative(
                                    index,
                                    target["left_derivative"],
                                )
                        snapshot.current_left_weight = target["left_weight"]
                        snapshot.current_left_derivative = target[
                            "left_derivative"
                        ]
                    if side in ("both", "right"):
                        if right_changed:
                            if right_weight_changed:
                                curve.KeySetRightTangentWeight(
                                    index,
                                    target["right_weight"],
                                )
                            if right_derivative_changed:
                                curve.KeySetRightDerivative(
                                    index,
                                    target["right_derivative"],
                                )
                        snapshot.current_right_weight = target["right_weight"]
                        snapshot.current_right_derivative = target[
                            "right_derivative"
                        ]
            finally:
                if began:
                    curve.KeyModifyEnd()
        self.prepared = True

    def restore(self):
        from pyfbsdk import FBTangentMode, FBTangentWeightMode

        for curve, states in self.by_curve.items():
            began = False
            try:
                try:
                    curve.KeyModifyBegin()
                    began = True
                except Exception:
                    pass
                resolved = [
                    (
                        snapshot,
                        self.key_mutation.resolve_index(
                            snapshot.key_snapshot
                        ),
                    )
                    for snapshot in states
                ]
                # Make every selected key independent before writing either
                # handle. This prevents a linked write from overwriting the
                # opposite derivative and prevents procedural neighbors from
                # recalculating against a partly restored curve.
                for snapshot, index in resolved:
                    curve.KeySetTangentMode(
                        index,
                        FBTangentMode.kFBTangentModeBreak,
                    )
                    curve.KeySetTangentBreak(index, True)
                for snapshot, index in resolved:
                    curve.KeySetLeftDerivative(
                        index,
                        snapshot.original_left_derivative,
                    )
                    curve.KeySetRightDerivative(
                        index,
                        snapshot.original_right_derivative,
                    )
                    if curve in self.weight_prepared_curves:
                        curve.KeySetLeftTangentWeight(
                            index,
                            snapshot.original_left_weight,
                        )
                        curve.KeySetRightTangentWeight(
                            index,
                            snapshot.original_right_weight,
                        )
                for snapshot, index in resolved:
                    for setter_name, value in (
                        item
                        for item in snapshot.optional_attributes.values()
                    ):
                        try:
                            getattr(curve, setter_name)(index, value)
                        except Exception:
                            pass
                if (
                    curve in self.weight_prepared_curves
                    or curve in self.weight_mode_dirty_curves
                ):
                    for index, mode in enumerate(
                        self.original_weight_modes.get(curve, ())
                    ):
                        if mode is not None:
                            curve.KeySetTangentWeightMode(index, mode)
                for index, values in enumerate(
                    self.original_curve_tcb.get(curve, ())
                ):
                    for setter_name, value in zip(
                        (
                            "KeySetTCBTension",
                            "KeySetTCBContinuity",
                            "KeySetTCBBias",
                        ),
                        values,
                    ):
                        if value is None:
                            continue
                        try:
                            getattr(curve, setter_name)(index, value)
                        except Exception:
                            pass
                for snapshot, index in resolved:
                    curve.KeySetTangentBreak(
                        index,
                        snapshot.original_tangent_break,
                    )
                    curve.KeySetTangentMode(
                        index,
                        snapshot.original_tangent_mode,
                    )
                    snapshot.current_left_derivative = (
                        snapshot.original_left_derivative
                    )
                    snapshot.current_right_derivative = (
                        snapshot.original_right_derivative
                    )
                    snapshot.current_left_weight = (
                        snapshot.original_left_weight
                    )
                    snapshot.current_right_weight = (
                        snapshot.original_right_weight
                    )
                    snapshot.independent_edit = False
                    snapshot.manual_prepared = False
            finally:
                if began:
                    curve.KeyModifyEnd()
        self.prepared = False
        self.weight_prepared_curves = set()
        self.weight_mode_dirty_curves = set()
