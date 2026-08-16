"""Interactive Viewer Rotate strategy."""

from __future__ import absolute_import

import math

from ..interactions.constraints import AxisConstraint
from .targets import (
    FrozenAxisGuide,
    GLOBAL_AXES,
    add,
    camera_axes,
    capture_targets,
    current_camera,
    dot,
    multiply,
    normalize,
    project_point,
    selection_center,
    subtract,
    viewport_rect,
    world_translation,
)


TRACKBALL_RADIANS_PER_PIXEL = 0.01


def _matrix_multiply(left, right):
    return [
        [
            sum(left[row][index] * right[index][column] for index in range(3))
            for column in range(3)
        ]
        for row in range(3)
    ]


def _matrix_transpose(matrix):
    return [
        [matrix[column][row] for column in range(3)]
        for row in range(3)
    ]


def _quaternion_from_matrix(matrix):
    """Return a normalized (w, x, y, z) quaternion for a rotation matrix."""
    trace = sum(float(matrix[index][index]) for index in range(3))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        values = (
            0.25 * scale,
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
        )
    else:
        index = max(range(3), key=lambda item: matrix[item][item])
        if index == 0:
            scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
            values = (
                (matrix[2][1] - matrix[1][2]) / scale,
                0.25 * scale,
                (matrix[0][1] + matrix[1][0]) / scale,
                (matrix[0][2] + matrix[2][0]) / scale,
            )
        elif index == 1:
            scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
            values = (
                (matrix[0][2] - matrix[2][0]) / scale,
                (matrix[0][1] + matrix[1][0]) / scale,
                0.25 * scale,
                (matrix[1][2] + matrix[2][1]) / scale,
            )
        else:
            scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
            values = (
                (matrix[1][0] - matrix[0][1]) / scale,
                (matrix[0][2] + matrix[2][0]) / scale,
                (matrix[1][2] + matrix[2][1]) / scale,
                0.25 * scale,
            )
    length = math.sqrt(sum(float(value) * float(value) for value in values))
    if length <= 0.000001:
        return (1.0, 0.0, 0.0, 0.0)
    return tuple(float(value) / length for value in values)


def _twist_angle(matrix, axis):
    """Extract the signed twist of ``matrix`` around a world-space axis."""
    direction = normalize(axis, GLOBAL_AXES["x"])
    w, x, y, z = _quaternion_from_matrix(matrix)
    vector = [x, y, z]
    projected = dot(vector, direction)
    if abs(w) <= 0.000001 and abs(projected) <= 0.000001:
        return 0.0
    return math.degrees(2.0 * math.atan2(projected, w))


def _axis_angle_matrix(axis, angle_degrees):
    x, y, z = normalize(axis, GLOBAL_AXES["x"])
    angle = math.radians(float(angle_degrees))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    one_minus_cosine = 1.0 - cosine
    return [
        [
            cosine + x * x * one_minus_cosine,
            x * y * one_minus_cosine - z * sine,
            x * z * one_minus_cosine + y * sine,
        ],
        [
            y * x * one_minus_cosine + z * sine,
            cosine + y * y * one_minus_cosine,
            y * z * one_minus_cosine - x * sine,
        ],
        [
            z * x * one_minus_cosine - y * sine,
            z * y * one_minus_cosine + x * sine,
            cosine + z * z * one_minus_cosine,
        ],
    ]


def _matrix3_from_values(values):
    return [
        [float(values[0]), float(values[4]), float(values[8])],
        [float(values[1]), float(values[5]), float(values[9])],
        [float(values[2]), float(values[6]), float(values[10])],
    ]


def _matrix_values(model):
    import pyfbsdk

    matrix = pyfbsdk.FBMatrix()
    model.GetMatrix(
        matrix,
        pyfbsdk.FBModelTransformationType.kModelRotation,
        True,
    )
    return [float(matrix[index]) for index in range(16)]


def _set_world_rotation_matrix(model, matrix3):
    import pyfbsdk

    matrix = pyfbsdk.FBMatrix()
    for index in range(16):
        matrix[index] = 0.0
    matrix[15] = 1.0
    for row in range(3):
        for column in range(3):
            matrix[column * 4 + row] = float(matrix3[row][column])
    model.SetMatrix(
        matrix,
        pyfbsdk.FBModelTransformationType.kModelRotation,
        True,
    )


def _channel_rotation(model):
    return [float(model.Rotation[index]) for index in range(3)]


def _restore_channel_rotation(model, rotation):
    import pyfbsdk

    model.Rotation = pyfbsdk.FBVector3d(*rotation)


def _matrix_axis(matrix, axis):
    column = {"x": 0, "y": 1, "z": 2}[axis]
    return normalize(
        [matrix[0][column], matrix[1][column], matrix[2][column]],
        GLOBAL_AXES[axis],
    )


def _pointer_angle(center, cursor):
    delta_x = float(cursor[0]) - float(center[0])
    delta_y = float(cursor[1]) - float(center[1])
    if math.hypot(delta_x, delta_y) <= 0.000001:
        return None
    return math.degrees(math.atan2(-delta_y, delta_x))


def _cursor_visual_angle(center, cursor):
    """Match the legacy orbit cursor's y-down screen-space orientation."""
    delta_x = float(cursor[0]) - float(center[0])
    delta_y = float(cursor[1]) - float(center[1])
    if math.hypot(delta_x, delta_y) <= 0.000001:
        return None
    return math.degrees(math.atan2(delta_y, delta_x))


def _wrapped_delta(current, previous):
    delta = float(current) - float(previous)
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


class ObjectRotateStrategy(object):
    undo_label = "Rotate Objects"

    def __init__(self, context, widget, mode="orbit"):
        self.context = context
        self.widget = widget
        self.mode = "trackball" if str(mode).lower() == "trackball" else "orbit"
        self.constraint = AxisConstraint()
        self.snapshots = ()
        self.camera = None
        self.viewport = None
        self.view_right = [1.0, 0.0, 0.0]
        self.view_up = [0.0, 1.0, 0.0]
        self.view_depth = [0.0, 0.0, 1.0]
        self.view_axis = [0.0, 0.0, 1.0]
        self.center = (0.0, 0.0)
        self.segment_matrices = {}
        self.segment_base_angle = 0.0
        self.segment_angle = 0.0
        self.current_angle = 0.0
        self.last_pointer_angle = None
        self.hik = None
        self.axis_guide = FrozenAxisGuide()

    def capture(self, session):
        self.snapshots = capture_targets(self.context)
        if not self.snapshots:
            return False
        for snapshot in self.snapshots:
            snapshot.original_rotation = _channel_rotation(snapshot.model)
            snapshot.original_rotation_matrix = _matrix3_from_values(
                _matrix_values(snapshot.model)
            )
            snapshot.current_rotation_matrix = [
                list(row) for row in snapshot.original_rotation_matrix
            ]
        self.hik = self.context.begin_character_manipulation(
            "rotate",
            self.snapshots,
        )
        self.camera = current_camera(self.context)
        self.view_right, self.view_up, self.view_depth = camera_axes(
            self.camera
        )
        self.viewport = viewport_rect(self.widget, self.camera)
        self.axis_guide.clear()
        center_world = selection_center(self.snapshots)
        camera_position = (
            world_translation(self.camera)
            if self.camera is not None
            else add(center_world, self.view_depth)
        )
        self.view_axis = normalize(
            subtract(camera_position, center_world),
            self.view_depth,
        )
        projected = project_point(
            self.camera,
            center_world,
            self.viewport,
        )
        if projected is None:
            projected = (
                self.viewport[0] + self.viewport[2] * 0.5,
                self.viewport[1] + self.viewport[3] * 0.5,
            )
        self.center = projected
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
        self.segment_matrices = dict(
            (
                snapshot,
                [list(row) for row in snapshot.current_rotation_matrix],
            )
            for snapshot in self.snapshots
        )
        self.segment_base_angle = self.current_angle
        self.segment_angle = 0.0
        self.last_pointer_angle = _pointer_angle(
            self.center,
            session.segment_anchor,
        )

    def rebase(self, session):
        self.segment_matrices = dict(
            (
                snapshot,
                [list(row) for row in snapshot.current_rotation_matrix],
            )
            for snapshot in self.snapshots
        )
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
            self.constraint.axis,
            self.constraint.space,
            session.numeric.text,
            self.mode,
        )

    def handles_key(self, session, payload):
        return str(payload.get("key") or "").upper() == "R"

    def handle_key_press(self, session, payload):
        self.mode = "trackball" if self.mode == "orbit" else "orbit"
        self.constraint.axis = None
        self.constraint.space = "global"

    def _orbit_angle(self, session, cursor):
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

    def _trackball(self, session, cursor):
        delta_x = float(cursor[0] - session.segment_anchor[0])
        delta_y = float(cursor[1] - session.segment_anchor[1])
        factor = TRACKBALL_RADIANS_PER_PIXEL * session.precision_multiplier
        vector = add(
            multiply(self.view_right, delta_y * factor),
            multiply(self.view_up, delta_x * factor),
        )
        angle_radians = math.sqrt(sum(value * value for value in vector))
        if angle_radians <= 0.000001:
            return self.view_right, self.segment_base_angle
        return (
            normalize(vector, self.view_right),
            self.segment_base_angle + math.degrees(angle_radians),
        )

    def _angle_and_axis(self, session, payload):
        cursor = payload.get(
            "cursor",
            session.context.input.cursor_position(),
        )
        numeric = session.numeric.value
        if self.constraint.axis is not None:
            angle = (
                float(numeric)
                if numeric is not None
                else self._orbit_angle(session, cursor)
            )
            return None, angle
        if numeric is not None:
            return self.view_axis, float(numeric)
        if self.mode == "trackball":
            return self._trackball(session, cursor)
        return self.view_axis, self._orbit_angle(session, cursor)

    def _effective_angle(self, session, angle):
        if session.numeric.value is not None:
            return float(angle)
        if session.snap_active:
            increment = session.policy.rotation_snap
            return round(float(angle) / increment) * increment
        return float(angle)

    def _axis_for(self, snapshot, base_matrix, default_axis):
        axis = self.constraint.axis
        if axis is None:
            return default_axis
        if self.constraint.space == "local":
            return _matrix_axis(base_matrix, axis)
        return list(GLOBAL_AXES[axis])

    def preview(self, session, payload):
        default_axis, raw_angle = self._angle_and_axis(session, payload)
        angle = self._effective_angle(session, raw_angle)
        numeric = session.numeric.value is not None
        delta_angle = angle if numeric else angle - self.segment_base_angle
        targets = []
        for snapshot in self.snapshots:
            base = (
                snapshot.original_rotation_matrix
                if numeric
                else self.segment_matrices[snapshot]
            )
            axis = self._axis_for(snapshot, base, default_axis)
            delta = _axis_angle_matrix(axis, delta_angle)
            target = _matrix_multiply(
                delta,
                base,
            )
            targets.append((snapshot, target, delta))
        for snapshot, target, _delta in targets:
            if self.hik is None or not self.hik.handles(snapshot):
                _set_world_rotation_matrix(snapshot.model, target)
        evaluated = (
            self.hik.apply_rotation(targets)
            if self.hik is not None
            else False
        )
        for snapshot, target, _delta in targets:
            snapshot.current_rotation_matrix = [
                list(row) for row in target
            ]
        self.current_angle = angle
        return False if evaluated else None

    def commit(self, session):
        return None

    def restart_from_original(self, session):
        for snapshot in self.snapshots:
            _restore_channel_rotation(
                snapshot.model,
                snapshot.original_rotation,
            )
            snapshot.current_rotation_matrix = [
                list(row) for row in snapshot.original_rotation_matrix
            ]
        self.segment_base_angle = 0.0
        self.segment_angle = 0.0
        self.current_angle = 0.0
        self.last_pointer_angle = None
        self.axis_guide.clear()
        if self.hik is not None and self.hik.has_hik_targets:
            self.hik.restore()
        else:
            self.context.evaluation.request()

    def restart_for_axis(self, session, payload):
        """Keep only the current rotation twist around the new axis lock."""
        axis = self.constraint.axis
        if axis is None:
            self.restart_from_original(session)
            return
        targets = []
        angles = []
        for snapshot in self.snapshots:
            direction = self._axis_for(
                snapshot,
                snapshot.original_rotation_matrix,
                self.view_axis,
            )
            delta = _matrix_multiply(
                snapshot.current_rotation_matrix,
                _matrix_transpose(snapshot.original_rotation_matrix),
            )
            angle = _twist_angle(delta, direction)
            twist = _axis_angle_matrix(direction, angle)
            targets.append(
                (
                    snapshot,
                    _matrix_multiply(twist, snapshot.original_rotation_matrix),
                    twist,
                )
            )
            angles.append(angle)
        if self.hik is not None and self.hik.has_hik_targets:
            self.hik.restore()
        for snapshot, target, _delta in targets:
            if self.hik is None or not self.hik.handles(snapshot):
                _set_world_rotation_matrix(snapshot.model, target)
        evaluated = (
            self.hik.apply_rotation(targets)
            if self.hik is not None
            else False
        )
        for snapshot, target, _delta in targets:
            snapshot.current_rotation_matrix = [list(row) for row in target]
        self.segment_base_angle = 0.0
        self.segment_angle = 0.0
        self.current_angle = sum(angles) / float(len(angles))
        self.last_pointer_angle = None
        self.axis_guide.clear()
        if not evaluated:
            self.context.evaluation.request()

    def cancel(self, session):
        self.restart_from_original(session)

    def close(self, session):
        if self.hik is not None:
            self.hik.close()

    def status(self, session):
        viewport_x, viewport_y = self.viewport[:2]
        cursor = session.context.input.cursor_position()
        cursor_angle = _cursor_visual_angle(self.center, cursor)
        status = {
            "text": "Rotation %+.3f deg%s%s" % (
                self.current_angle,
                (
                    " along %s" % self.constraint.label
                    if self.constraint.axis is not None
                    else (
                        " Trackball"
                        if self.mode == "trackball"
                        else ""
                    )
                ),
                (
                    self.hik.status_suffix
                    if self.hik is not None
                    else ""
                ),
            ),
            "radial_line": (
                (self.center[0] - viewport_x, self.center[1] - viewport_y),
                (cursor[0] - viewport_x, cursor[1] - viewport_y),
            ),
            "cursor_point": (
                cursor[0] - viewport_x,
                cursor[1] - viewport_y,
            ),
            "cursor_angle": (
                0.0 if cursor_angle is None else cursor_angle
            ),
            "cursor_variant": (
                "trackball" if self.mode == "trackball" else "orbit"
            ),
        }
        if self.constraint.axis is None:
            self.axis_guide.clear()
            return status
        first = self.snapshots[0]
        base = first.current_rotation_matrix
        axis = self._axis_for(first, base, self.view_axis)
        status["axis"] = self.constraint.axis
        status["axis_line"] = self.axis_guide.overlay_line(
            self.camera,
            self.viewport,
            self.constraint.axis,
            self.constraint.space,
            selection_center(self.snapshots),
            axis,
        )
        return status
