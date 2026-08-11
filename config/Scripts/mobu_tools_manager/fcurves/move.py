"""Interactive FCurve and Timeline Move strategy."""

from __future__ import absolute_import

from .discovery import CurveRecord, displayed_curve_records
from .mutation import FCurveCollision, FCurveMutationService
from .snapshots import capture_selected_keys
from .view_transform import FCurveViewTransform
from ..interactions.constraints import AxisConstraint


def _widget_global_rect(widget):
    rect = widget.rect()
    top_left = widget.mapToGlobal(rect.topLeft())
    return (
        int(top_left.x()),
        int(top_left.y()),
        int(rect.width()),
        int(rect.height()),
    )


def _frame_ticks(context):
    try:
        mode = context.player_control.GetTransportFps()
        from pyfbsdk import FBTime

        return max(1, abs(int(FBTime(0, 0, 0, 1, 0, mode).Get())))
    except Exception:
        return 1


class FCurveMoveStrategy(object):
    undo_label = "Move FCurve Keys"

    def __init__(self, context, widget, timeline=False):
        self.context = context
        self.widget = widget
        self.timeline = bool(timeline)
        self.constraint = AxisConstraint(
            graph=not self.timeline,
            timeline=self.timeline,
        )
        self.records = ()
        self.snapshots = ()
        self.mutation = None
        self.transform = None
        self.segment_times = {}
        self.segment_values = {}
        self.last_time_delta = 0
        self.last_value_delta = 0.0
        self.blocked = None

    def capture(self, session):
        if self.timeline:
            self.records = tuple(
                CurveRecord(prop, node, curve)
                for prop, node, curve
                in self.context.fcurves.whole_scene_fcurve_records()
            )
        else:
            self.records = displayed_curve_records(self.context)
        snapshots = capture_selected_keys(self.records)
        if any(snapshot.property is None for snapshot in snapshots):
            return False
        self.snapshots = snapshots
        if not self.snapshots:
            return False
        self.mutation = FCurveMutationService(self.snapshots)
        if self.timeline:
            start = int(self.context.player_control.ZoomWindowStart.Get())
            stop = int(self.context.player_control.ZoomWindowStop.Get())
            width = max(1.0, float(self.widget.width()))
            self.transform = type(
                "TimelineTransform",
                (),
                {
                    "ticks_per_pixel": abs(float(stop - start)) / width,
                    "value_per_pixel": 0.0,
                    "frame_ticks": _frame_ticks(self.context),
                },
            )()
        else:
            self.transform = FCurveViewTransform.capture(
                self.context,
                self.widget,
                self.records,
                self.snapshots,
            )
        self.begin_segment(session)
        return True

    def undo_properties(self):
        unique = {}
        for snapshot in self.snapshots:
            if snapshot.property is not None:
                unique[id(snapshot.property)] = snapshot.property
        return tuple(unique.values())

    def undo_models(self):
        return ()

    def overlay_rect(self):
        return _widget_global_rect(self.widget)

    def begin_segment(self, session):
        self.segment_times = dict(
            (snapshot, snapshot.current_time)
            for snapshot in self.snapshots
        )
        self.segment_values = dict(
            (snapshot, snapshot.current_value)
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
            session.numeric.text,
        )

    @staticmethod
    def _snap(value, increment):
        return round(float(value) / float(increment)) * float(increment)

    def _mouse_deltas(self, session, payload):
        cursor = payload.get("cursor", session.context.input.cursor_position())
        delta_x = float(cursor[0] - session.segment_anchor[0])
        delta_y = float(cursor[1] - session.segment_anchor[1])
        multiplier = session.precision_multiplier
        time_delta = delta_x * self.transform.ticks_per_pixel * multiplier
        value_delta = (
            -delta_y * self.transform.value_per_pixel * multiplier
        )
        if self.timeline:
            time_delta = (
                round(time_delta / self.transform.frame_ticks)
                * self.transform.frame_ticks
            )
        elif session.snap_active:
            time_delta = self._snap(
                time_delta,
                self.transform.frame_ticks,
            )
            value_delta = self._snap(
                value_delta,
                session.policy.fcurve_value_snap,
            )
        return int(round(time_delta)), float(value_delta)

    def _targets(self, session, payload):
        time_delta, value_delta = self._mouse_deltas(session, payload)
        numeric = session.numeric.value
        numeric_from_original = numeric is not None
        if numeric_from_original:
            if self.constraint.axis == "y" and not self.timeline:
                time_delta = 0
                value_delta = float(numeric)
            else:
                time_delta = int(
                    round(float(numeric) * self.transform.frame_ticks)
                )
                value_delta = 0.0

        if self.constraint.axis == "x" or self.timeline:
            value_delta = 0.0
        elif self.constraint.axis == "y":
            time_delta = 0

        if numeric_from_original:
            base_times = dict(
                (snapshot, snapshot.original_time)
                for snapshot in self.snapshots
            )
            base_values = dict(
                (snapshot, snapshot.original_value)
                for snapshot in self.snapshots
            )
        else:
            base_times = self.segment_times
            base_values = self.segment_values

        target_times = dict(
            (
                snapshot,
                int(base_times[snapshot] + time_delta),
            )
            for snapshot in self.snapshots
        )
        target_values = dict(
            (
                snapshot,
                float(base_values[snapshot] + value_delta),
            )
            for snapshot in self.snapshots
        )
        return target_times, target_values

    def preview(self, session, payload):
        target_times, target_values = self._targets(session, payload)
        try:
            self.mutation.apply(target_times, target_values)
            self.blocked = None
        except FCurveCollision as error:
            self.blocked = str(error)
            return
        first = self.snapshots[0]
        self.last_time_delta = first.current_time - first.original_time
        self.last_value_delta = first.current_value - first.original_value
        try:
            self.widget.update()
        except Exception:
            pass

    def commit(self, session):
        return None

    def can_commit(self, session):
        return self.blocked is None

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
        frame_delta = (
            float(self.last_time_delta)
            / float(max(1, self.transform.frame_ticks))
        )
        if self.timeline:
            text = "Move keys %+d frame%s" % (
                int(round(frame_delta)),
                "" if abs(int(round(frame_delta))) == 1 else "s",
            )
        elif self.constraint.axis == "x":
            text = "Move keys %+.3f frames" % frame_delta
        elif self.constraint.axis == "y":
            text = "Move keys %+.3f value" % self.last_value_delta
        else:
            text = "Move keys %+.3f frames, %+.3f value" % (
                frame_delta,
                self.last_value_delta,
            )
        if self.blocked:
            text += "  [BLOCKED: %s]" % self.blocked

        rect_x, rect_y, rect_width, rect_height = self.overlay_rect()
        axis_line = None
        axis = self.constraint.axis
        if axis == "x":
            local_y = session.segment_anchor[1] - rect_y
            axis_line = ((0.0, local_y), (float(rect_width), local_y))
        elif axis == "y":
            local_x = session.segment_anchor[0] - rect_x
            axis_line = ((local_x, 0.0), (local_x, float(rect_height)))
        return {
            "text": text,
            "axis": axis,
            "axis_line": axis_line,
        }
