"""Interactive FCurve key and tangent Scale strategy."""

from __future__ import absolute_import

import math

from .discovery import displayed_curve_records
from .mutation import FCurveCollision, FCurveMutationService
from .snapshots import capture_selected_keys
from .tangents import (
    MAX_TANGENT_WEIGHT,
    MIN_TANGENT_WEIGHT,
    TangentMutationService,
    capture_tangents,
    clamp,
    scale_tangent_angle,
    tangent_angle_degrees,
)
from .view_transform import FCurveViewTransform
from ..interactions.constraints import AxisConstraint


MIN_MOUSE_FACTOR = 0.001
SIDES = ("both", "left", "right")


def _widget_global_rect(widget):
    rect = widget.rect()
    top_left = widget.mapToGlobal(rect.topLeft())
    return (
        int(top_left.x()),
        int(top_left.y()),
        int(rect.width()),
        int(rect.height()),
    )


def _radius(center, point):
    return math.hypot(
        float(point[0]) - float(center[0]),
        float(point[1]) - float(center[1]),
    )


def _snap(value, increment):
    return round(float(value) / float(increment)) * float(increment)


class FCurveScaleStrategy(object):
    undo_label = "Scale FCurve Keys"

    def __init__(self, context, widget):
        self.context = context
        self.widget = widget
        self.constraint = AxisConstraint(graph=True)
        self.records = ()
        self.snapshots = ()
        self.tangent_snapshots = ()
        self.mutation = None
        self.tangents = None
        self.transform = None
        self.pivot_time = 0.0
        self.pivot_value = 0.0
        self.pivot_cursor = (0.0, 0.0)
        self.current_cursor = (0.0, 0.0)
        self.tangent_side = "both"
        self.position_factors = {"x": 1.0, "y": 1.0}
        self.weight_factors = {"left": 1.0, "right": 1.0}
        self.angle_factors = {"left": 1.0, "right": 1.0}
        self.segment_position_factors = {}
        self.segment_weight_factors = {}
        self.segment_angle_factors = {}
        self.last_factor = 1.0
        self.last_target_signature = None
        self.blocked = None
        self.clamped = False

    def capture(self, session):
        self.records = displayed_curve_records(self.context)
        self.snapshots = capture_selected_keys(self.records)
        if (
            not self.snapshots
            or any(
                snapshot.property is None
                for snapshot in self.snapshots
            )
        ):
            return False
        self.tangent_snapshots = capture_tangents(self.snapshots)
        if len(self.tangent_snapshots) != len(self.snapshots):
            return False
        self.mutation = FCurveMutationService(self.snapshots)
        self.tangents = TangentMutationService(
            self.tangent_snapshots,
            self.mutation,
        )
        self.transform = FCurveViewTransform.capture(
            self.context,
            self.widget,
            self.records,
            self.snapshots,
        )
        count = float(len(self.snapshots))
        self.pivot_time = sum(
            float(snapshot.original_time)
            for snapshot in self.snapshots
        ) / count
        self.pivot_value = sum(
            float(snapshot.original_value)
            for snapshot in self.snapshots
        ) / count
        local_pivot = self.transform.key_local_point(
            self.pivot_time,
            self.pivot_value,
        )
        rect_x, rect_y = self.overlay_rect()[:2]
        self.pivot_cursor = (
            rect_x + local_pivot[0],
            rect_y + local_pivot[1],
        )
        self.current_cursor = self.context.input.cursor_position()
        self.begin_segment(session)
        return True

    def undo_properties(self):
        unique = {}
        for snapshot in self.snapshots:
            unique[id(snapshot.property)] = snapshot.property
        return tuple(unique.values())

    def undo_models(self):
        return ()

    def overlay_rect(self):
        return _widget_global_rect(self.widget)

    def begin_segment(self, session):
        self.segment_position_factors = dict(self.position_factors)
        self.segment_weight_factors = dict(self.weight_factors)
        self.segment_angle_factors = dict(self.angle_factors)

    def rebase(self, session):
        self.begin_segment(session)

    def handles_key(self, session, payload):
        return (
            str(payload.get("key") or "").upper()
            == session.policy.tangent_side_cycle_key
        )

    def handle_key_press(self, session, payload):
        index = (SIDES.index(self.tangent_side) + 1) % len(SIDES)
        self.tangent_side = SIDES[index]

    def input_signature(self, session, payload):
        cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        return (
            round(float(cursor[0]), 3),
            round(float(cursor[1]), 3),
            session.precision_active,
            session.snap_active,
            self.constraint.axis,
            self.tangent_side,
            session.numeric.text,
        )

    def _mouse_factor(self, session, payload):
        cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        start_radius = max(
            8.0,
            _radius(self.pivot_cursor, session.segment_anchor),
        )
        current_radius = max(
            8.0,
            _radius(self.pivot_cursor, cursor),
        )
        ratio = current_radius / start_radius
        factor = 1.0 + (
            (ratio - 1.0) * session.precision_multiplier
        )
        return max(MIN_MOUSE_FACTOR, factor)

    def _factor(self, session, base, mouse_factor):
        numeric = session.numeric.value
        if numeric is not None:
            return float(numeric)
        result = float(base) * float(mouse_factor)
        if session.snap_active:
            result = _snap(result, session.policy.scale_snap)
        return result

    def _candidate_factors(self, session, mouse_factor):
        position = dict(self.segment_position_factors)
        weights = dict(self.segment_weight_factors)
        angles = dict(self.segment_angle_factors)
        axis = self.constraint.axis
        position_axes = ("x", "y") if axis is None else (axis,)
        for name in position_axes:
            position[name] = self._factor(
                session,
                self.segment_position_factors[name],
                mouse_factor,
            )

        active_sides = (
            ("left", "right")
            if self.tangent_side == "both"
            else (self.tangent_side,)
        )
        if axis in (None, "x"):
            for side in active_sides:
                weights[side] = self._factor(
                    session,
                    self.segment_weight_factors[side],
                    mouse_factor,
                )
        # Default uniform scaling preserves tangent angles. Axis-constrained
        # scaling multiplies the selected tangent angle by the exact factor.
        if axis in ("x", "y"):
            for side in active_sides:
                angles[side] = self._factor(
                    session,
                    self.segment_angle_factors[side],
                    mouse_factor,
                )
        return position, weights, angles

    def _key_targets(self, position):
        target_times = {}
        target_values = {}
        for snapshot in self.snapshots:
            target_times[snapshot] = int(
                round(
                    self.pivot_time
                    + (
                        (
                            float(snapshot.original_time)
                            - self.pivot_time
                        )
                        * position["x"]
                    )
                )
            )
            target_values[snapshot] = (
                self.pivot_value
                + (
                    (
                        float(snapshot.original_value)
                        - self.pivot_value
                    )
                    * position["y"]
                )
            )
        return target_times, target_values

    def _tangent_targets(self, weights, angles):
        targets = {}
        clamped = False
        derivative_scale = self.transform.derivative_scale
        for snapshot in self.tangent_snapshots:
            raw_left = (
                snapshot.original_left_weight * weights["left"]
            )
            raw_right = (
                snapshot.original_right_weight * weights["right"]
            )
            left_weight = clamp(
                raw_left,
                MIN_TANGENT_WEIGHT,
                MAX_TANGENT_WEIGHT,
            )
            right_weight = clamp(
                raw_right,
                MIN_TANGENT_WEIGHT,
                MAX_TANGENT_WEIGHT,
            )
            if (
                abs(left_weight - raw_left) > 0.000001
                or abs(right_weight - raw_right) > 0.000001
            ):
                clamped = True
            targets[snapshot] = {
                "left_weight": left_weight,
                "right_weight": right_weight,
                "left_derivative": scale_tangent_angle(
                    snapshot.original_left_derivative,
                    angles["left"],
                    derivative_scale,
                ),
                "right_derivative": scale_tangent_angle(
                    snapshot.original_right_derivative,
                    angles["right"],
                    derivative_scale,
                ),
            }
        return targets, clamped

    def preview(self, session, payload):
        self.current_cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        mouse_factor = self._mouse_factor(session, payload)
        position, weights, angles = self._candidate_factors(
            session,
            mouse_factor,
        )
        target_times, target_values = self._key_targets(position)
        tangent_targets, clamped = self._tangent_targets(
            weights,
            angles,
        )
        signature = (
            tuple(
                (
                    snapshot.original_index,
                    target_times[snapshot],
                    round(target_values[snapshot], 7),
                )
                for snapshot in self.snapshots
            ),
            tuple(
                (
                    snapshot.original_index,
                    round(
                        tangent_targets[snapshot]["left_weight"],
                        7,
                    ),
                    round(
                        tangent_targets[snapshot]["right_weight"],
                        7,
                    ),
                    round(
                        tangent_targets[snapshot]["left_derivative"],
                        7,
                    ),
                    round(
                        tangent_targets[snapshot]["right_derivative"],
                        7,
                    ),
                )
                for snapshot in self.tangent_snapshots
            ),
            self.tangent_side,
        )
        if signature == self.last_target_signature:
            return False
        try:
            self.mutation.apply(target_times, target_values)
        except FCurveCollision as error:
            self.blocked = str(error)
            return False
        self.tangents.apply(tangent_targets, self.tangent_side)
        self.position_factors = position
        self.weight_factors = weights
        self.angle_factors = angles
        self.clamped = clamped
        self.blocked = None
        axis = self.constraint.axis
        active = (
            tuple(position.values())
            if axis is None
            else (position[axis],)
        )
        self.last_factor = sum(active) / float(len(active))
        self.last_target_signature = signature
        try:
            self.widget.update()
        except Exception:
            pass
        self._request_evaluation()
        return False

    def commit(self, session):
        return None

    def can_commit(self, session):
        return self.blocked is None

    def cancel(self, session):
        if self.mutation is not None:
            self.mutation.restore()
        if self.tangents is not None:
            self.tangents.restore()
        self._request_evaluation()
        try:
            self.widget.update()
        except Exception:
            pass

    def close(self, session):
        return None

    def _request_evaluation(self):
        callback = getattr(
            self.context.evaluation,
            "request_fcurve",
            None,
        )
        if callable(callback):
            callback()
        else:
            self.context.evaluation.request()

    @staticmethod
    def _format(value):
        if abs(float(value)) < 0.0005:
            value = 0.0
        return "%.3f" % float(value)

    def _average_tangents(self):
        count = float(len(self.tangent_snapshots))
        left_weight = sum(
            snapshot.current_left_weight
            for snapshot in self.tangent_snapshots
        ) / count
        right_weight = sum(
            snapshot.current_right_weight
            for snapshot in self.tangent_snapshots
        ) / count
        left_angle = sum(
            tangent_angle_degrees(
                snapshot.current_left_derivative,
                self.transform.derivative_scale,
            )
            for snapshot in self.tangent_snapshots
        ) / count
        right_angle = sum(
            tangent_angle_degrees(
                snapshot.current_right_derivative,
                self.transform.derivative_scale,
            )
            for snapshot in self.tangent_snapshots
        ) / count
        return left_weight, right_weight, left_angle, right_angle

    def status(self, session):
        left_weight, right_weight, left_angle, right_angle = (
            self._average_tangents()
        )
        axis = self.constraint.axis
        axis_text = "XY" if axis is None else axis.upper()
        text = (
            "Scale %sx | %s | X %s  Y %s | Tangents %s "
            "L %.3f/%+.1f deg  R %.3f/%+.1f deg"
            % (
                self._format(self.last_factor),
                axis_text,
                self._format(self.position_factors["x"]),
                self._format(self.position_factors["y"]),
                self.tangent_side.upper(),
                left_weight,
                left_angle,
                right_weight,
                right_angle,
            )
        )
        if self.clamped:
            text += "  [CLAMPED]"
        if self.blocked:
            text += "  [BLOCKED: %s]" % self.blocked

        rect_x, rect_y, rect_width, rect_height = self.overlay_rect()
        center = (
            self.pivot_cursor[0] - rect_x,
            self.pivot_cursor[1] - rect_y,
        )
        cursor = (
            self.current_cursor[0] - rect_x,
            self.current_cursor[1] - rect_y,
        )
        axis_line = None
        if axis == "x":
            axis_line = (
                (0.0, center[1]),
                (float(rect_width), center[1]),
            )
        elif axis == "y":
            axis_line = (
                (center[0], 0.0),
                (center[0], float(rect_height)),
            )
        angle = math.degrees(
            math.atan2(
                cursor[1] - center[1],
                cursor[0] - center[0],
            )
        )
        return {
            "text": text,
            "axis": axis,
            "axis_line": axis_line,
            "radial_line": (center, cursor),
            "cursor_point": cursor,
            "cursor_angle": angle,
        }
