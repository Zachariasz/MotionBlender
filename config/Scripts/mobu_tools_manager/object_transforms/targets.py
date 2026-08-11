"""Captured object targets and camera/view mapping."""

from __future__ import absolute_import

import math


GLOBAL_AXES = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}
AXIS_GUIDE_WORLD_LENGTH = 1000.0


def add(left, right):
    return [left[index] + right[index] for index in range(3)]


def subtract(left, right):
    return [left[index] - right[index] for index in range(3)]


def multiply(values, scalar):
    return [values[index] * float(scalar) for index in range(3)]


def dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def cross(left, right):
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def length(values):
    return math.sqrt(max(0.0, dot(values, values)))


def normalize(values, fallback):
    magnitude = length(values)
    if magnitude <= 0.000001:
        return list(fallback)
    return multiply(values, 1.0 / magnitude)


def rotate_xyz(values, rotation_degrees):
    x, y, z = values
    rx, ry, rz = [math.radians(value) for value in rotation_degrees]
    cos_x, sin_x = math.cos(rx), math.sin(rx)
    cos_y, sin_y = math.cos(ry), math.sin(ry)
    cos_z, sin_z = math.cos(rz), math.sin(rz)
    y, z = (y * cos_x) - (z * sin_x), (y * sin_x) + (z * cos_x)
    x, z = (x * cos_y) + (z * sin_y), (-x * sin_y) + (z * cos_y)
    x, y = (x * cos_z) - (y * sin_z), (x * sin_z) + (y * cos_z)
    return [x, y, z]


def _sdk():
    import pyfbsdk

    return pyfbsdk


def model_vector(model, transform_type, global_space):
    sdk = _sdk()
    vector = sdk.FBVector3d()
    model.GetVector(vector, transform_type, global_space)
    return [float(vector[index]) for index in range(3)]


def world_translation(model):
    sdk = _sdk()
    try:
        return model_vector(
            model,
            sdk.FBModelTransformationType.kModelTranslation,
            True,
        )
    except Exception:
        return [float(model.Translation[index]) for index in range(3)]


def set_world_translation(model, values):
    sdk = _sdk()
    vector = sdk.FBVector3d(*values)
    try:
        model.SetVector(
            vector,
            sdk.FBModelTransformationType.kModelTranslation,
            True,
        )
    except Exception:
        model.Translation = vector


def model_scaling(model, global_space=False):
    sdk = _sdk()
    try:
        return model_vector(
            model,
            sdk.FBModelTransformationType.kModelScaling,
            bool(global_space),
        )
    except Exception:
        return [float(model.Scaling[index]) for index in range(3)]


def set_model_scaling(model, values, global_space=False):
    sdk = _sdk()
    vector = sdk.FBVector3d(*values)
    try:
        model.SetVector(
            vector,
            sdk.FBModelTransformationType.kModelScaling,
            bool(global_space),
        )
    except Exception:
        model.Scaling = vector


def world_rotation(model):
    sdk = _sdk()
    try:
        return model_vector(
            model,
            sdk.FBModelTransformationType.kModelRotation,
            True,
        )
    except Exception:
        return [float(model.Rotation[index]) for index in range(3)]


def local_axes(model):
    sdk = _sdk()
    try:
        matrix = sdk.FBMatrix()
        model.GetMatrix(
            matrix,
            sdk.FBModelTransformationType.kModelTransformation,
            True,
        )
        values = _matrix_values(matrix)
        axis_x = normalize(values[0:3], GLOBAL_AXES["x"])
        raw_y = values[4:7]
        axis_y = normalize(
            subtract(raw_y, multiply(axis_x, dot(raw_y, axis_x))),
            GLOBAL_AXES["y"],
        )
        raw_z = values[8:11]
        handedness = (
            -1.0
            if dot(cross(axis_x, axis_y), raw_z) < 0.0
            else 1.0
        )
        axis_z = normalize(
            multiply(cross(axis_x, axis_y), handedness),
            GLOBAL_AXES["z"],
        )
        return {
            "x": axis_x,
            "y": axis_y,
            "z": axis_z,
        }
    except Exception:
        rotation = world_rotation(model)
        return dict(
            (
                axis,
                normalize(rotate_xyz(direction, rotation), direction),
            )
            for axis, direction in GLOBAL_AXES.items()
        )


class ObjectSnapshot(object):
    def __init__(self, model):
        self.model = model
        self.original = world_translation(model)
        self.current = list(self.original)
        self.local_axes = local_axes(model)
        try:
            self.parent = model.Parent
        except Exception:
            self.parent = None


class ObjectScaleSnapshot(ObjectSnapshot):
    def __init__(self, model):
        ObjectSnapshot.__init__(self, model)
        self.original_local_scale = model_scaling(model, False)
        self.original_global_scale = model_scaling(model, True)
        self.current_local_scale = list(self.original_local_scale)
        self.current_global_scale = list(self.original_global_scale)

    def refresh_scales(self):
        self.current_local_scale = model_scaling(self.model, False)
        self.current_global_scale = model_scaling(self.model, True)


def _transformable_models(context):
    models = []
    for model in context.selection:
        try:
            if getattr(model, "Transformable", True):
                models.append(model)
        except Exception:
            continue
    return tuple(models)


def capture_targets(context):
    snapshots = []
    for model in _transformable_models(context):
        try:
            snapshots.append(ObjectSnapshot(model))
        except Exception:
            continue
    return tuple(sorted(snapshots, key=lambda item: _hierarchy_depth(item.model)))


def capture_scale_targets(context):
    snapshots = []
    for model in _transformable_models(context):
        try:
            snapshots.append(ObjectScaleSnapshot(model))
        except Exception:
            continue
    return tuple(sorted(snapshots, key=lambda item: _hierarchy_depth(item.model)))


def _hierarchy_depth(model):
    depth = 0
    seen = set()
    current = model
    while current is not None:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        try:
            current = current.Parent
        except Exception:
            break
        if current is not None:
            depth += 1
    return depth


def points_center(points):
    if not points:
        return [0.0, 0.0, 0.0]
    total = [0.0, 0.0, 0.0]
    for point in points:
        total = add(total, point)
    return multiply(total, 1.0 / float(len(points)))


def selection_center(snapshots):
    return points_center([snapshot.original for snapshot in snapshots])


def current_camera(context):
    try:
        camera = context.scene.Renderer.GetCameraInPane(0)
        if camera is not None:
            return camera
    except Exception:
        pass
    try:
        return _sdk().FBCameraSwitcher().CurrentCamera
    except Exception:
        return None


def camera_axes(camera):
    if camera is None:
        return (
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
        )
    axes = local_axes(camera)
    return (
        axes["z"],
        axes["y"],
        axes["x"],
    )


def numeric_value(value, fallback):
    try:
        return float(value)
    except Exception:
        pass
    try:
        return float(value.Data)
    except Exception:
        return fallback


def _matrix_values(matrix):
    return [float(matrix[index]) for index in range(16)]


def _project_ndc(point, values):
    x, y, z = point
    clip_x = values[0] * x + values[4] * y + values[8] * z + values[12]
    clip_y = values[1] * x + values[5] * y + values[9] * z + values[13]
    clip_w = values[3] * x + values[7] * y + values[11] * z + values[15]
    # A negative homogeneous W is behind the camera. Dividing it still
    # produces finite screen coordinates, but those coordinates are mirrored
    # through the camera plane and can move a long axis guide away from its
    # selected pivot.
    if clip_w <= 0.000001:
        return None
    return clip_x / clip_w, clip_y / clip_w


def project_point(camera, point, rect):
    if camera is None:
        return None
    sdk = _sdk()
    matrix = sdk.FBMatrix()
    try:
        camera.GetCameraMatrix(
            matrix,
            sdk.FBCameraMatrixType.kFBModelViewProj,
            None,
        )
    except TypeError:
        camera.GetCameraMatrix(
            matrix,
            sdk.FBCameraMatrixType.kFBModelViewProj,
        )
    ndc = _project_ndc(point, _matrix_values(matrix))
    if ndc is None or not all(math.isfinite(value) for value in ndc):
        return None
    x, y, width, height = rect
    return (
        x + (ndc[0] + 1.0) * 0.5 * width,
        y + (1.0 - ndc[1]) * 0.5 * height,
    )


def viewport_rect(widget, camera):
    rect = widget.rect()
    top_left = widget.mapToGlobal(rect.topLeft())
    candidate = (
        int(top_left.x()),
        int(top_left.y()),
        int(rect.width()),
        int(rect.height()),
    )
    if camera is None:
        return candidate
    try:
        viewport_width = int(camera.CameraViewportWidth)
        viewport_height = int(camera.CameraViewportHeight)
        window_width = int(camera.WindowWidth)
        window_height = int(camera.WindowHeight)
        if (
            viewport_width > 0
            and viewport_height > 0
            and abs(candidate[2] - window_width) <= 4
            and abs(candidate[3] - window_height) <= 4
        ):
            return (
                candidate[0] + int(camera.CameraViewportX),
                candidate[1] + int(camera.CameraViewportY),
                viewport_width,
                viewport_height,
            )
    except Exception:
        pass
    return candidate


def _orthographic_units_per_pixel(
    camera,
    snapshots,
    view_right,
    view_up,
    viewport,
):
    center = selection_center(snapshots)
    center_screen = project_point(camera, center, viewport)
    if center_screen is None:
        return None
    samples = []
    sample_distance = 100.0
    for axis in (view_right, view_up):
        endpoint = add(center, multiply(axis, sample_distance))
        endpoint_screen = project_point(camera, endpoint, viewport)
        if endpoint_screen is None:
            continue
        pixel_distance = math.hypot(
            endpoint_screen[0] - center_screen[0],
            endpoint_screen[1] - center_screen[1],
        )
        if pixel_distance > 0.000001:
            samples.append(sample_distance / pixel_distance)
    if not samples:
        return None
    return sum(samples) / float(len(samples))


def viewport_units_per_pixel(
    camera,
    snapshots,
    view_right,
    view_up,
    view_depth,
    viewport,
):
    if camera is None:
        return 0.05
    sdk = _sdk()
    viewport_height = max(1, int(viewport[3]))
    try:
        if camera.Type == sdk.FBCameraType.kFBCameraTypeOrthogonal:
            projected = _orthographic_units_per_pixel(
                camera,
                snapshots,
                view_right,
                view_up,
                viewport,
            )
            if projected is not None and projected > 0.000001:
                return projected
            ortho_zoom = numeric_value(camera.OrthoZoom, 0.0)
            if ortho_zoom > 0.000001:
                return max(2.0 * ortho_zoom / viewport_height, 0.000001)
    except Exception:
        pass
    camera_position = world_translation(camera)
    to_selection = subtract(selection_center(snapshots), camera_position)
    depth = abs(dot(to_selection, view_depth))
    if depth <= 0.000001:
        depth = max(length(to_selection), 1.0)
    field_of_view = numeric_value(
        getattr(camera, "FieldOfViewY", None),
        0.0,
    )
    if field_of_view <= 0.000001:
        field_of_view = numeric_value(
            getattr(camera, "FieldOfView", None),
            40.0,
        )
    world_height = 2.0 * depth * math.tan(math.radians(field_of_view) * 0.5)
    return max(world_height / viewport_height, 0.000001)


def axis_overlay_line(
    camera,
    viewport,
    center,
    direction,
    total_world_length=None,
):
    direction = normalize(direction, [1.0, 0.0, 0.0])
    if total_world_length is not None:
        half_length = max(float(total_world_length) * 0.5, 0.0)
        center_screen = project_point(camera, center, viewport)
        if center_screen is None:
            return None
        start_screen = project_point(
            camera,
            add(center, multiply(direction, -half_length)),
            viewport,
        )
        end_screen = project_point(
            camera,
            add(center, multiply(direction, half_length)),
            viewport,
        )
        candidates = []
        if start_screen is not None:
            delta_x = float(center_screen[0]) - float(start_screen[0])
            delta_y = float(center_screen[1]) - float(start_screen[1])
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.000001:
                # Negating the center-to-negative-end delta gives the positive
                # world-axis screen direction.
                candidates.append((distance, delta_x, delta_y, "start"))
        if end_screen is not None:
            delta_x = float(end_screen[0]) - float(center_screen[0])
            delta_y = float(end_screen[1]) - float(center_screen[1])
            distance = math.hypot(delta_x, delta_y)
            if distance > 0.000001:
                candidates.append((distance, delta_x, delta_y, "end"))
        if not candidates:
            return None

        half_screen_length = min(item[0] for item in candidates)
        direction_source = next(
            (item for item in candidates if item[3] == "end"),
            candidates[0],
        )
        screen_direction = normalize(
            [direction_source[1], direction_source[2], 0.0],
            [1.0, 0.0, 0.0],
        )
        offset_x = screen_direction[0] * half_screen_length
        offset_y = screen_direction[1] * half_screen_length
        # Perspective makes equal world-space halves project to unequal pixel
        # lengths. Balance the visible guide around the projected pivot so the
        # selected object is always its exact visual midpoint. If one endpoint
        # is behind the camera, mirror the valid half instead of using the
        # behind-camera projection.
        return (
            (
                center_screen[0] - offset_x,
                center_screen[1] - offset_y,
            ),
            (
                center_screen[0] + offset_x,
                center_screen[1] + offset_y,
            ),
        )
    center_screen = project_point(camera, center, viewport)
    if center_screen is None:
        return None
    camera_position = world_translation(camera)
    base_scale = max(length(subtract(center, camera_position)) * 0.25, 1.0)
    for factor in (0.25, 1.0, 4.0, 16.0, 64.0, 256.0):
        endpoint = add(center, multiply(direction, base_scale * factor))
        endpoint_screen = project_point(camera, endpoint, viewport)
        if endpoint_screen is None:
            continue
        if math.hypot(
            endpoint_screen[0] - center_screen[0],
            endpoint_screen[1] - center_screen[1],
        ) >= 4.0:
            return center_screen, endpoint_screen
    return None


class FrozenAxisGuide(object):
    """One exact world-space guide captured when an axis lock changes."""

    def __init__(self, total_world_length=AXIS_GUIDE_WORLD_LENGTH):
        self.total_world_length = float(total_world_length)
        self.signature = None
        self.center = None
        self.direction = None

    def clear(self):
        self.signature = None
        self.center = None
        self.direction = None

    def _capture_if_changed(self, axis, space, center, direction):
        axis = str(axis or "").lower()
        if axis not in GLOBAL_AXES:
            self.clear()
            return False
        signature = (axis, str(space or "global").lower())
        if signature == self.signature:
            return False
        self.signature = signature
        self.center = [float(value) for value in center[:3]]
        self.direction = normalize(direction, GLOBAL_AXES[axis])
        return True

    def overlay_line(
        self,
        camera,
        viewport,
        axis,
        space,
        center,
        direction,
    ):
        self._capture_if_changed(
            axis,
            space,
            center,
            direction,
        )
        if self.center is None or self.direction is None:
            return None
        projected = axis_overlay_line(
            camera,
            viewport,
            self.center,
            self.direction,
            total_world_length=self.total_world_length,
        )
        if projected is None:
            return None
        viewport_x, viewport_y = viewport[:2]
        return (
            (
                projected[0][0] - viewport_x,
                projected[0][1] - viewport_y,
            ),
            (
                projected[1][0] - viewport_x,
                projected[1][1] - viewport_y,
            ),
        )
