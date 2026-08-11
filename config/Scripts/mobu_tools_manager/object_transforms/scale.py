"""Interactive Viewer Scale strategy."""

from __future__ import absolute_import

import math

from ..interactions.constraints import AxisConstraint
from .targets import (
    FrozenAxisGuide,
    GLOBAL_AXES,
    capture_scale_targets,
    current_camera,
    points_center,
    project_point,
    set_model_scaling,
    viewport_rect,
)


AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
MIN_MOUSE_FACTOR = 0.001
EPSILON = 0.000001


def _radius(center, point):
    return math.hypot(
        float(point[0]) - float(center[0]),
        float(point[1]) - float(center[1]),
    )


def _snap(value, increment):
    return round(float(value) / float(increment)) * float(increment)


def _factor_between(value, original, fallback):
    if abs(float(original)) <= EPSILON:
        return float(fallback)
    return float(value) / float(original)


class ObjectScaleStrategy(object):
    undo_label = "Scale Objects"

    def __init__(self, context, widget):
        self.context = context
        self.widget = widget
        self.constraint = AxisConstraint()
        self.snapshots = ()
        self.camera = None
        self.viewport = None
        self.center_world = [0.0, 0.0, 0.0]
        self.center_cursor = (0.0, 0.0)
        self.current_cursor = (0.0, 0.0)
        self.segment_local = {}
        self.segment_global = {}
        self.last_factor = 1.0
        self.last_target_signature = None
        self.hik = None
        self.axis_guide = FrozenAxisGuide()

    def capture(self, session):
        self.snapshots = capture_scale_targets(self.context)
        if not self.snapshots:
            return False
        self.camera = current_camera(self.context)
        self.viewport = viewport_rect(self.widget, self.camera)
        self.axis_guide.clear()
        self.center_world = points_center(
            [snapshot.original for snapshot in self.snapshots]
        )
        self.hik = self.context.begin_character_manipulation(
            "scale",
            self.snapshots,
        )
        projected = project_point(
            self.camera,
            self.center_world,
            self.viewport,
        )
        self.center_cursor = (
            projected
            if projected is not None
            else self.context.input.cursor_position()
        )
        self.current_cursor = self.context.input.cursor_position()
        self.begin_segment(session)
        return True

    def undo_properties(self):
        return ()

    def undo_models(self):
        models = [snapshot.model for snapshot in self.snapshots]
        if self.hik is not None:
            models.extend(self.hik.undo_models)
        result = []
        for model in models:
            if model is None or any(model is item for item in result):
                continue
            result.append(model)
        return tuple(result)

    def overlay_rect(self):
        return self.viewport

    def begin_segment(self, session):
        for snapshot in self.snapshots:
            snapshot.refresh_scales()
        self.segment_local = dict(
            (
                snapshot,
                list(snapshot.current_local_scale),
            )
            for snapshot in self.snapshots
        )
        self.segment_global = dict(
            (
                snapshot,
                list(snapshot.current_global_scale),
            )
            for snapshot in self.snapshots
        )

    def rebase(self, session):
        self.begin_segment(session)

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
            self.constraint.space,
            session.numeric.text,
        )

    def _mouse_factor(self, session, payload):
        cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        start_radius = max(
            8.0,
            _radius(self.center_cursor, session.segment_anchor),
        )
        current_radius = max(
            8.0,
            _radius(self.center_cursor, cursor),
        )
        ratio = current_radius / start_radius
        factor = 1.0 + (
            (ratio - 1.0) * session.precision_multiplier
        )
        return max(MIN_MOUSE_FACTOR, factor)

    def _target(self, session, snapshot, factor):
        axis = self.constraint.axis
        use_global = axis is not None and self.constraint.space == "global"
        base = list(
            self.segment_global[snapshot]
            if use_global
            else self.segment_local[snapshot]
        )
        original = list(
            snapshot.original_global_scale
            if use_global
            else snapshot.original_local_scale
        )
        enabled = range(3) if axis is None else (AXIS_INDEX[axis],)
        numeric = session.numeric.value
        target = list(base)
        for index in enabled:
            if numeric is not None:
                total_factor = float(numeric)
                target[index] = original[index] * total_factor
                continue
            target[index] = base[index] * factor
            total_factor = _factor_between(
                target[index],
                original[index],
                factor,
            )
            if session.snap_active:
                total_factor = _snap(
                    total_factor,
                    session.policy.scale_snap,
                )
                target[index] = original[index] * total_factor
        factors = [
            _factor_between(target[index], original[index], factor)
            for index in enabled
        ]
        return use_global, target, (
            sum(factors) / float(len(factors))
            if factors
            else 1.0
        )

    def preview(self, session, payload):
        self.current_cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        factor = self._mouse_factor(session, payload)
        targets = [
            (snapshot,) + self._target(session, snapshot, factor)
            for snapshot in self.snapshots
        ]
        signature = tuple(
            (
                id(snapshot.model),
                use_global,
                tuple(round(value, 7) for value in target),
            )
            for snapshot, use_global, target, _total_factor in targets
        )
        if signature == self.last_target_signature:
            return False
        for snapshot, use_global, target, _total_factor in targets:
            set_model_scaling(snapshot.model, target, use_global)
        for snapshot in self.snapshots:
            snapshot.refresh_scales()
        self.last_factor = sum(
            item[3] for item in targets
        ) / float(len(targets))
        self.last_target_signature = signature
        evaluated = (
            self.hik.finish_direct_preview()
            if self.hik is not None
            else False
        )
        return False if evaluated else None

    def commit(self, session):
        return None

    def cancel(self, session):
        for snapshot in self.snapshots:
            set_model_scaling(
                snapshot.model,
                snapshot.original_local_scale,
                False,
            )
            snapshot.refresh_scales()
        if self.hik is not None and self.hik.has_hik_targets:
            self.hik.restore()
        else:
            self.context.evaluation.request()

    def close(self, session):
        if self.hik is not None:
            self.hik.close()

    @staticmethod
    def _format(value):
        if abs(float(value)) < 0.0005:
            value = 0.0
        return "%.3f" % float(value)

    def _axis_line(self):
        axis = self.constraint.axis
        if axis is None:
            self.axis_guide.clear()
            return None
        direction = (
            self.snapshots[0].local_axes[axis]
            if self.constraint.space == "local"
            else GLOBAL_AXES[axis]
        )
        return self.axis_guide.overlay_line(
            self.camera,
            self.viewport,
            axis,
            self.constraint.space,
            self.center_world,
            direction,
        )

    def status(self, session):
        scales = points_center(
            [
                snapshot.current_local_scale
                for snapshot in self.snapshots
            ]
        )
        vector = "X %s  Y %s  Z %s" % tuple(
            self._format(value) for value in scales
        )
        if self.constraint.axis is None:
            text = "Scale %sx | %s" % (
                self._format(self.last_factor),
                vector,
            )
        else:
            text = "Scale %sx along %s | %s" % (
                self._format(self.last_factor),
                self.constraint.label,
                vector,
            )
        if self.hik is not None:
            text += self.hik.status_suffix
        rect_x, rect_y = self.viewport[:2]
        center = (
            self.center_cursor[0] - rect_x,
            self.center_cursor[1] - rect_y,
        )
        cursor = (
            self.current_cursor[0] - rect_x,
            self.current_cursor[1] - rect_y,
        )
        angle = math.degrees(
            math.atan2(
                cursor[1] - center[1],
                cursor[0] - center[0],
            )
        )
        return {
            "text": text,
            "axis": self.constraint.axis,
            "axis_line": self._axis_line(),
            "radial_line": (center, cursor),
            "cursor_point": cursor,
            "cursor_angle": angle,
        }
