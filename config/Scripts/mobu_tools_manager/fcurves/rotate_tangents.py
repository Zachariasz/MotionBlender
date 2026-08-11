"""Interactive FCurve tangent Rotate strategy."""

from __future__ import absolute_import

import math

from .discovery import displayed_curve_records
from .mutation import FCurveMutationService
from .snapshots import capture_selected_keys
from .tangents import (
    TangentMutationService,
    capture_tangents,
    rotate_tangent_angle,
    tangent_angle_degrees,
)
from .view_transform import FCurveViewTransform


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


def _median(values):
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5


def _pointer_angle(center, cursor):
    delta_x = float(cursor[0]) - float(center[0])
    delta_y = float(cursor[1]) - float(center[1])
    if math.hypot(delta_x, delta_y) <= 0.000001:
        return None
    return math.degrees(math.atan2(-delta_y, delta_x))


def _wrapped_delta(current, previous):
    delta = float(current) - float(previous)
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


class TangentConstraint(object):
    axis = None
    space = "global"

    @staticmethod
    def accepts(axis):
        return False

    @staticmethod
    def press(axis):
        return False


class FCurveTangentRotateStrategy(object):
    undo_label = "Rotate FCurve Tangents"

    def __init__(self, context, widget):
        self.context = context
        self.widget = widget
        self.constraint = TangentConstraint()
        self.records = ()
        self.key_snapshots = ()
        self.snapshots = ()
        self.key_mutation = None
        self.mutation = None
        self.transform = None
        self.side = "both"
        self.center = (0.0, 0.0)
        self.derivative_scale = 1.0
        self.segment_base_angle = 0.0
        self.segment_angle = 0.0
        self.current_angle = 0.0
        self.last_pointer_angle = None
        self._overlay_geometry = None

    def capture(self, session):
        from pyfbsdk import FBInterpolation, FBTime

        self.records = displayed_curve_records(self.context)
        selected = capture_selected_keys(self.records)
        self.key_snapshots = tuple(
            snapshot
            for snapshot in selected
            if snapshot.curve.KeyGetInterpolation(
                snapshot.original_index
            )
            == FBInterpolation.kFBInterpolationCubic
        )
        if not self.key_snapshots or any(
            snapshot.property is None for snapshot in self.key_snapshots
        ):
            return False
        self.snapshots = capture_tangents(self.key_snapshots)
        if not self.snapshots:
            return False
        self.key_mutation = FCurveMutationService(self.key_snapshots)
        self.mutation = TangentMutationService(
            self.snapshots,
            self.key_mutation,
        )
        self.transform = FCurveViewTransform.capture(
            self.context,
            self.widget,
            self.records,
            self.key_snapshots,
        )
        self._overlay_geometry = _widget_global_rect(self.widget)
        rect = self._overlay_geometry
        points = [
            self.transform.key_local_point(
                snapshot.original_time,
                snapshot.original_value,
            )
            for snapshot in self.key_snapshots
        ]
        self.center = (
            rect[0] + _median(point[0] for point in points),
            rect[1] + _median(point[1] for point in points),
        )
        ticks_per_second = max(1.0, abs(float(FBTime.OneSecond.Get())))
        seconds_per_pixel = (
            abs(float(self.transform.ticks_per_pixel))
            / ticks_per_second
        )
        self.derivative_scale = (
            abs(float(self.transform.value_per_pixel))
            / max(seconds_per_pixel, 0.000000001)
        )
        return True

    def undo_properties(self):
        unique = {}
        for snapshot in self.key_snapshots:
            unique[id(snapshot.property)] = snapshot.property
        return tuple(unique.values())

    def undo_models(self):
        return ()

    def overlay_rect(self):
        current_geometry = getattr(
            self.context,
            "current_ui_surface_geometry",
            lambda classification: None,
        )("fcurve")
        if current_geometry is not None:
            current_geometry = tuple(current_geometry)
            previous = self._overlay_geometry
            if previous is not None and current_geometry != previous:
                self.center = (
                    self.center[0] + current_geometry[0] - previous[0],
                    self.center[1] + current_geometry[1] - previous[1],
                )
            self._overlay_geometry = current_geometry
        if self._overlay_geometry is None:
            raise RuntimeError("FCurve overlay geometry was not captured")
        return self._overlay_geometry

    def begin_segment(self, session):
        self.segment_base_angle = self.current_angle
        self.segment_angle = 0.0
        self.last_pointer_angle = _pointer_angle(
            self.center,
            session.segment_anchor,
        )

    def rebase(self, session):
        self.segment_base_angle = self.current_angle
        self.segment_angle = 0.0
        self.last_pointer_angle = None

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
            session.numeric.text,
            self.side,
        )

    def handles_key(self, session, payload):
        return (
            str(payload.get("key") or "").upper()
            == session.policy.tangent_side_cycle_key
        )

    def handle_key_press(self, session, payload):
        self.side = SIDES[(SIDES.index(self.side) + 1) % len(SIDES)]

    def _mouse_angle(self, session, payload):
        cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        pointer_angle = _pointer_angle(self.center, cursor)
        if pointer_angle is not None:
            if self.last_pointer_angle is not None:
                self.segment_angle += (
                    _wrapped_delta(
                        pointer_angle,
                        self.last_pointer_angle,
                    )
                    * session.precision_multiplier
                )
            self.last_pointer_angle = pointer_angle
        return self.segment_base_angle + self.segment_angle

    def _effective_angle(self, session, payload):
        numeric = session.numeric.value
        if numeric is not None:
            return float(numeric)
        angle = self._mouse_angle(session, payload)
        if session.snap_active:
            increment = session.policy.rotation_snap
            angle = round(angle / increment) * increment
        return angle

    def _targets(self, angle):
        targets = {}
        for snapshot in self.snapshots:
            targets[snapshot] = {
                "left_derivative": rotate_tangent_angle(
                    snapshot.original_left_derivative,
                    angle,
                    self.derivative_scale,
                ),
                "right_derivative": rotate_tangent_angle(
                    snapshot.original_right_derivative,
                    angle,
                    self.derivative_scale,
                ),
                "left_weight": snapshot.original_left_weight,
                "right_weight": snapshot.original_right_weight,
            }
        return targets

    def preview(self, session, payload):
        self.overlay_rect()
        angle = self._effective_angle(session, payload)
        if abs(angle) <= 0.000001:
            if self.mutation.prepared:
                self.mutation.restore()
        else:
            self.mutation.apply(self._targets(angle), self.side)
        self.current_angle = angle
        try:
            self.widget.update()
        except Exception:
            pass

    def commit(self, session):
        return None

    def cancel(self, session):
        if self.mutation is not None:
            self.mutation.restore()
        self.context.evaluation.request()
        try:
            self.widget.update()
        except Exception:
            pass

    def close(self, session):
        return None

    def status(self, session):
        rect_x, rect_y, _width, _height = self.overlay_rect()
        cursor = session.context.input.cursor_position()
        cursor_angle = _pointer_angle(self.center, cursor)
        left = sum(
            tangent_angle_degrees(
                snapshot.current_left_derivative,
                self.derivative_scale,
            )
            for snapshot in self.snapshots
        ) / float(len(self.snapshots))
        right = sum(
            tangent_angle_degrees(
                snapshot.current_right_derivative,
                self.derivative_scale,
            )
            for snapshot in self.snapshots
        ) / float(len(self.snapshots))
        return {
            "text": (
                "Rotate tangents %+.3f deg | %s | L %+.3f  R %+.3f"
                % (
                    self.current_angle,
                    self.side.title(),
                    left,
                    right,
                )
            ),
            "radial_line": (
                (self.center[0] - rect_x, self.center[1] - rect_y),
                (cursor[0] - rect_x, cursor[1] - rect_y),
            ),
            "cursor_point": (
                cursor[0] - rect_x,
                cursor[1] - rect_y,
            ),
            "cursor_angle": (
                0.0 if cursor_angle is None else cursor_angle
            ),
            "cursor_variant": "orbit",
            "_overlay_rect": self._overlay_geometry,
        }
