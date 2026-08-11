"""Interactive Viewer Move strategy."""

from __future__ import absolute_import

from ..interactions.constraints import AxisConstraint
from .targets import (
    FrozenAxisGuide,
    GLOBAL_AXES,
    add,
    camera_axes,
    capture_targets,
    current_camera,
    dot,
    length,
    multiply,
    normalize,
    points_center,
    selection_center,
    set_world_translation,
    subtract,
    viewport_rect,
    viewport_units_per_pixel,
)


class ObjectMoveStrategy(object):
    undo_label = "Move Objects"

    def __init__(self, context, widget):
        self.context = context
        self.widget = widget
        self.constraint = AxisConstraint()
        self.snapshots = ()
        self.hik = None
        self.camera = None
        self.view_right = [1.0, 0.0, 0.0]
        self.view_up = [0.0, 1.0, 0.0]
        self.view_depth = [1.0, 0.0, 0.0]
        self.viewport = None
        self.units_per_pixel = 0.05
        self.segment_positions = {}
        self.last_direction = [1.0, 0.0, 0.0]
        self.last_targets = ()
        self.axis_guide = FrozenAxisGuide()

    def capture(self, session):
        self.snapshots = capture_targets(self.context)
        if not self.snapshots:
            return False
        self.camera = current_camera(self.context)
        self.view_right, self.view_up, self.view_depth = camera_axes(
            self.camera
        )
        self.viewport = viewport_rect(self.widget, self.camera)
        self.axis_guide.clear()
        self.units_per_pixel = viewport_units_per_pixel(
            self.camera,
            self.snapshots,
            self.view_right,
            self.view_up,
            self.view_depth,
            self.viewport,
        )
        self.hik = self.context.begin_character_manipulation(
            "move",
            self.snapshots,
        )
        self.last_targets = tuple(
            list(snapshot.original)
            for snapshot in self.snapshots
        )
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
        self.segment_positions = dict(
            (snapshot, list(snapshot.current))
            for snapshot in self.snapshots
        )

    def rebase(self, session):
        self.begin_segment(session)

    def input_signature(self, session, payload):
        cursor = payload.get("cursor", session.context.input.cursor_position())
        return (
            round(float(cursor[0]), 3),
            round(float(cursor[1]), 3),
            session.precision_active,
            session.snap_active,
            self.constraint.axis,
            self.constraint.space,
            session.numeric.text,
        )

    @staticmethod
    def _snap_scalar(value, increment):
        return round(float(value) / float(increment)) * float(increment)

    def _raw_view_offset(self, session, payload):
        cursor = payload.get("cursor", session.context.input.cursor_position())
        delta_x = float(cursor[0] - session.segment_anchor[0])
        delta_y = float(cursor[1] - session.segment_anchor[1])
        units = self.units_per_pixel * session.precision_multiplier
        offset = add(
            multiply(self.view_right, delta_x * units),
            multiply(self.view_up, -delta_y * units),
        )
        if length(offset) > 0.000001:
            self.last_direction = normalize(offset, self.last_direction)
        return offset

    def _axis_for(self, snapshot):
        if self.constraint.axis is None:
            return None
        if self.constraint.space == "local":
            return snapshot.local_axes[self.constraint.axis]
        return list(GLOBAL_AXES[self.constraint.axis])

    def _offset_for_snapshot(self, session, raw_offset, snapshot):
        axis = self._axis_for(snapshot)
        numeric = session.numeric.value
        if numeric is not None:
            direction = (
                normalize(axis, GLOBAL_AXES[self.constraint.axis])
                if axis is not None
                else normalize(self.last_direction, self.view_right)
            )
            return multiply(direction, numeric)

        if axis is not None:
            direction = normalize(
                axis,
                GLOBAL_AXES[self.constraint.axis],
            )
            distance = dot(raw_offset, direction)
            return multiply(direction, distance)

        return raw_offset

    def _snap_target(self, session, snapshot, target):
        """Snap the complete displacement, never only the current segment."""
        increment = session.policy.translation_snap
        displacement = subtract(target, snapshot.original)
        axis = self._axis_for(snapshot)
        if axis is None:
            # Free camera-plane movement has no single scalar to snap.  Round
            # every displayed world-space displacement component independently
            # so Ctrl works without requiring an X/Y/Z constraint.
            snapped = [
                self._snap_scalar(component, increment)
                for component in displacement
            ]
            return add(snapshot.original, snapped)

        direction = normalize(
            axis,
            GLOBAL_AXES[self.constraint.axis],
        )
        distance = dot(displacement, direction)
        snapped_distance = self._snap_scalar(distance, increment)
        return add(
            target,
            multiply(direction, snapped_distance - distance),
        )

    def _targets(self, session, payload):
        raw_offset = self._raw_view_offset(session, payload)
        numeric_from_original = session.numeric.value is not None
        targets = []
        for snapshot in self.snapshots:
            base = (
                snapshot.original
                if numeric_from_original
                else self.segment_positions[snapshot]
            )
            target = add(
                base,
                self._offset_for_snapshot(session, raw_offset, snapshot),
            )
            if session.snap_active and not numeric_from_original:
                target = self._snap_target(session, snapshot, target)
            targets.append(target)
        return tuple(targets)

    def preview(self, session, payload):
        targets = self._targets(session, payload)
        if targets == self.last_targets:
            return None
        pairs = tuple(zip(self.snapshots, targets))
        for snapshot, target in pairs:
            if self.hik is None or not self.hik.handles(snapshot):
                set_world_translation(snapshot.model, target)
        evaluated = (
            self.hik.apply_translation(pairs)
            if self.hik is not None
            else False
        )
        for snapshot, target in zip(self.snapshots, targets):
            snapshot.current = list(target)
        self.last_targets = tuple(list(target) for target in targets)
        return False if evaluated else None

    def commit(self, session):
        return None

    def cancel(self, session):
        for snapshot in self.snapshots:
            set_world_translation(snapshot.model, snapshot.original)
            snapshot.current = list(snapshot.original)
        if self.hik is not None and self.hik.has_hik_targets:
            self.hik.restore()
        else:
            self.context.evaluation.request()

    def close(self, session):
        if self.hik is not None:
            self.hik.close()

    @staticmethod
    def _format(value):
        if abs(value) < 0.0005:
            value = 0.0
        return "%.3f" % value

    def _status_text(self):
        original_center = selection_center(self.snapshots)
        current_center = points_center(
            [snapshot.current for snapshot in self.snapshots]
        )
        delta = subtract(current_center, original_center)
        xyz = "X %s  Y %s  Z %s" % tuple(
            self._format(value)
            for value in delta
        )
        if self.constraint.axis is None:
            text = "Move %s" % xyz
            return text + (
                self.hik.status_suffix if self.hik is not None else ""
            )
        distances = []
        for snapshot in self.snapshots:
            direction = normalize(
                self._axis_for(snapshot),
                GLOBAL_AXES[self.constraint.axis],
            )
            distances.append(
                dot(
                    subtract(snapshot.current, snapshot.original),
                    direction,
                )
            )
        distance = sum(distances) / max(1.0, float(len(distances)))
        text = "Move %s along %s | %s" % (
            self._format(distance),
            self.constraint.label,
            xyz,
        )
        return text + (
            self.hik.status_suffix if self.hik is not None else ""
        )

    def status(self, session):
        axis = self.constraint.axis
        line = None
        if axis is not None and self.snapshots:
            if self.constraint.space == "local":
                center = self.snapshots[0].current
                direction = self.snapshots[0].local_axes[axis]
            else:
                center = points_center(
                    [snapshot.current for snapshot in self.snapshots]
                )
                direction = GLOBAL_AXES[axis]
            line = self.axis_guide.overlay_line(
                self.camera,
                self.viewport,
                axis,
                self.constraint.space,
                center,
                direction,
            )
        else:
            self.axis_guide.clear()
        return {
            "text": self._status_text(),
            "axis": axis,
            "axis_line": line,
        }
