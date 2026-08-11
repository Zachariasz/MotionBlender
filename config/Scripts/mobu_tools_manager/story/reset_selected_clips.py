"""Reset selected Story clips at the origin and align them to global +Z."""

from __future__ import absolute_import

import math

from pyfbsdk import (
    FBBodyNodeId,
    FBMatrix,
    FBModelTransformationType,
    FBPlayerControl,
    FBStory,
    FBStoryClipNodeFunction,
    FBStoryTrackType,
    FBSystem,
    FBTime,
    FBVector3d,
)

from .settings import DEFAULTS


TOOL_NAME = "Reset Selected Story Clips"
ALIGN_TOLERANCE_DEGREES = 0.10
ROTATION_PROBE_DEGREES = 5.0
MAX_ALIGNMENT_PASSES = 4
PATH_POSITION_TOLERANCE = 0.02


def context_system(context):
    return context.system if context is not None else FBSystem()


def context_player_control(context):
    return (
        context.player_control
        if context is not None
        else FBPlayerControl()
    )


def evaluate_scene(context):
    if context is not None:
        return context.evaluation.flush_now()
    return FBSystem().Scene.Evaluate()


def safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def safe_set(obj, name, value):
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def copy_vector3d(value):
    try:
        return FBVector3d(float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return FBVector3d(0.0, 0.0, 0.0)


def clip_label(clip):
    for name in ("Name", "LongName", "Label"):
        value = safe_get(clip, name, None)
        if value:
            return str(value)
    return "Story Clip"


def iter_track_tree(track):
    yield track
    for child in safe_get(track, "SubTracks", []):
        for nested in iter_track_tree(child):
            yield nested


def collect_story_items():
    story = FBStory()
    folders = []
    tracks = []
    clips = []
    targets = []

    def visit_folder(folder):
        folders.append(folder)

        for root_track in safe_get(folder, "Tracks", []):
            for track in iter_track_tree(root_track):
                tracks.append(track)
                for clip in safe_get(track, "Clips", []):
                    clips.append(clip)
                    if bool(safe_get(clip, "Selected", False)):
                        targets.append({"track": track, "clip": clip})

        for child_folder in safe_get(folder, "Childs", []):
            visit_folder(child_folder)

    visit_folder(story.RootFolder)
    return story, folders, tracks, clips, targets


def capture_story_state(story, folders, tracks, clips, context=None):
    system = context_system(context)
    return {
        "story_mute": safe_get(story, "Mute", False),
        "time": FBTime(system.LocalTime.Get()),
        "folders": [
            (folder, safe_get(folder, "Mute", False), safe_get(folder, "Solo", False))
            for folder in folders
        ],
        "tracks": [
            (track, safe_get(track, "Mute", False), safe_get(track, "Solo", False))
            for track in tracks
        ],
        "clips": [(clip, safe_get(clip, "Loaded", True)) for clip in clips],
    }


def restore_loaded_state(state):
    for clip, loaded in state["clips"]:
        safe_set(clip, "Loaded", loaded)


def restore_story_state(story, state, context=None):
    for folder, mute, solo in state["folders"]:
        safe_set(folder, "Mute", mute)
        safe_set(folder, "Solo", solo)

    for track, mute, solo in state["tracks"]:
        safe_set(track, "Mute", mute)
        safe_set(track, "Solo", solo)

    restore_loaded_state(state)
    safe_set(story, "Mute", state["story_mute"])

    try:
        context_player_control(context).Goto(state["time"])
    except Exception:
        pass

    try:
        evaluate_scene(context)
    except Exception:
        pass


def unmute_track_and_parents(track):
    current = track
    while current:
        safe_set(current, "Mute", False)
        safe_set(current, "Solo", False)
        current = safe_get(current, "ParentTrack", None)


def isolate_clip(story, state, target):
    restore_loaded_state(state)
    safe_set(story, "Mute", False)

    for folder, _mute, _solo in state["folders"]:
        safe_set(folder, "Mute", False)
        safe_set(folder, "Solo", False)

    for track, _mute, _solo in state["tracks"]:
        safe_set(track, "Mute", True)
        safe_set(track, "Solo", False)

    target_track = target["track"]
    target_clip = target["clip"]
    unmute_track_and_parents(target_track)

    for clip in safe_get(target_track, "Clips", []):
        safe_set(clip, "Loaded", clip == target_clip)

    safe_set(target_clip, "Loaded", True)


def get_track_character(track, context=None):
    character = safe_get(track, "Character", None)
    if character:
        return character

    character_index = safe_get(track, "CharacterIndex", 0)
    if not character_index or character_index <= 0:
        return None

    characters = context_system(context).Scene.Characters
    index = int(character_index) - 1
    if index < 0 or index >= len(characters):
        return None
    return characters[index]


def matrix_multiply(a, b):
    result = []
    for row in range(3):
        result_row = []
        for column in range(3):
            result_row.append(
                (a[row][0] * b[0][column])
                + (a[row][1] * b[1][column])
                + (a[row][2] * b[2][column])
            )
        result.append(result_row)
    return result


def matrix_transpose(matrix):
    return [
        [matrix[0][0], matrix[1][0], matrix[2][0]],
        [matrix[0][1], matrix[1][1], matrix[2][1]],
        [matrix[0][2], matrix[1][2], matrix[2][2]],
    ]


def transform_vector(matrix, vector):
    return [
        (matrix[0][0] * vector[0])
        + (matrix[0][1] * vector[1])
        + (matrix[0][2] * vector[2]),
        (matrix[1][0] * vector[0])
        + (matrix[1][1] * vector[1])
        + (matrix[1][2] * vector[2]),
        (matrix[2][0] * vector[0])
        + (matrix[2][1] * vector[1])
        + (matrix[2][2] * vector[2]),
    ]


def rotation_matrix_x(angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [1.0, 0.0, 0.0],
        [0.0, cosine, -sine],
        [0.0, sine, cosine],
    ]


def rotation_matrix_y(angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, 0.0, sine],
        [0.0, 1.0, 0.0],
        [-sine, 0.0, cosine],
    ]


def rotation_matrix_z(angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, -sine, 0.0],
        [sine, cosine, 0.0],
        [0.0, 0.0, 1.0],
    ]


def euler_xyz_to_matrix(rotation_degrees):
    rx = math.radians(float(rotation_degrees[0]))
    ry = math.radians(float(rotation_degrees[1]))
    rz = math.radians(float(rotation_degrees[2]))
    return matrix_multiply(
        rotation_matrix_z(rz),
        matrix_multiply(rotation_matrix_y(ry), rotation_matrix_x(rx)),
    )


def fbmatrix_to_matrix3(matrix):
    return [
        [float(matrix[0]), float(matrix[4]), float(matrix[8])],
        [float(matrix[1]), float(matrix[5]), float(matrix[9])],
        [float(matrix[2]), float(matrix[6]), float(matrix[10])],
    ]


def normalized_angle(angle):
    value = (float(angle) + 180.0) % 360.0 - 180.0
    if value <= -180.0:
        return 180.0
    return value


def angle_delta(angle, reference):
    return normalized_angle(float(angle) - float(reference))


def set_clip_vector(clip, name, value):
    try:
        setattr(clip, name, value)
        return
    except Exception:
        pass

    try:
        clip.MakeWritable()
        setattr(clip, name, value)
    except Exception:
        raise RuntimeError("Could not set clip %s." % name)


def set_clip_yaw(clip, yaw, x_value, z_value):
    set_clip_vector(
        clip,
        "Rotation",
        FBVector3d(float(x_value), normalized_angle(yaw), float(z_value)),
    )


def evaluate_at_clip_start(clip, context=None):
    start = safe_get(clip, "Start", None)
    if start is None:
        raise RuntimeError("Clip has no valid start time.")
    context_player_control(context).Goto(FBTime(start.Get()))
    evaluate_scene(context)


def clip_sample_times(clip):
    start = safe_get(clip, "Start", None)
    stop = safe_get(clip, "Stop", None)
    if start is None or stop is None:
        raise RuntimeError("Clip has no valid start/stop time.")

    start_time = FBTime(start.Get())
    end_value = int(stop.Get()) - 1
    if end_value <= start_time.Get():
        end_value = int(stop.Get())
    return start_time, FBTime(end_value)


def model_global_position(model):
    value = FBVector3d()
    model.GetVector(
        value,
        FBModelTransformationType.kModelTranslation,
        True,
    )
    return [float(value[index]) for index in range(3)]


def average_model_position(models):
    if not models:
        raise RuntimeError("No travelling model is available.")

    result = [0.0, 0.0, 0.0]
    for model in models:
        position = model_global_position(model)
        for index in range(3):
            result[index] += position[index]

    divisor = float(len(models))
    return [value / divisor for value in result]


def append_unique_model(output, model):
    if model is None or not hasattr(model, "GetVector"):
        return

    for existing in output:
        try:
            if existing == model:
                return
        except Exception:
            pass
    output.append(model)


def connected_property_models(component, property_name):
    result = []
    prop = None
    try:
        prop = component.PropertyList.Find(property_name)
    except Exception:
        prop = None
    if prop is None:
        return result

    for count_name, get_name in (
        ("GetSrcCount", "GetSrc"),
        ("GetDstCount", "GetDst"),
    ):
        try:
            count = int(getattr(prop, count_name)())
        except Exception:
            continue
        for index in range(count):
            try:
                append_unique_model(result, getattr(prop, get_name)(index))
            except Exception:
                pass
    return result


def get_travelling_models(track, clip, character):
    result = []

    try:
        for model in clip.TravellingNode:
            append_unique_model(result, model)
    except Exception:
        pass

    if not result:
        for model in connected_property_models(track, "TravellingNode"):
            append_unique_model(result, model)

    if not result and character:
        try:
            append_unique_model(
                result,
                character.GetModel(FBBodyNodeId.kFBHipsNodeId),
            )
        except Exception:
            pass

    if not result:
        try:
            for model in clip.GetAffectedObjects():
                append_unique_model(result, model)
        except Exception:
            pass

    return result


def measure_motion_path(models, clip, context=None):
    start_time, end_time = clip_sample_times(clip)

    context_player_control(context).Goto(start_time)
    evaluate_scene(context)
    start_position = average_model_position(models)

    context_player_control(context).Goto(end_time)
    evaluate_scene(context)
    end_position = average_model_position(models)

    delta = [
        end_position[index] - start_position[index]
        for index in range(3)
    ]
    horizontal_distance = math.sqrt(
        (delta[0] * delta[0]) + (delta[2] * delta[2])
    )
    yaw = None
    if horizontal_distance > 0.000001:
        yaw = normalized_angle(
            math.degrees(math.atan2(delta[0], delta[2]))
        )

    return {
        "start": start_position,
        "end": end_position,
        "delta": delta,
        "distance": horizontal_distance,
        "yaw": yaw,
    }


def align_motion_path_to_positive_z(
    track,
    clip,
    character,
    path_min_distance,
    context=None,
):
    travelling_models = get_travelling_models(track, clip, character)
    if not travelling_models:
        return None

    measurement = measure_motion_path(travelling_models, clip, context)
    if measurement["distance"] < float(path_min_distance):
        return None

    # The travelling ghost should live on the ground plane. This changes only
    # the clip-vector/travelling-node calculation; the character keeps its
    # vertical animation and remains upright.
    clip.TravellingNodeFunction = (
        FBStoryClipNodeFunction.kFBStoryClipNodeFloorProjection
    )
    set_clip_vector(clip, "Translation", FBVector3d(0.0, 0.0, 0.0))

    original_rotation = copy_vector3d(clip.Rotation)
    x_value = float(original_rotation[0])
    z_value = float(original_rotation[2])
    base_yaw = float(original_rotation[1])

    measurement = measure_motion_path(travelling_models, clip, context)
    path_yaw = measurement["yaw"]
    if path_yaw is None:
        return None

    if abs(path_yaw) > ALIGN_TOLERANCE_DEGREES:
        set_clip_yaw(
            clip,
            base_yaw + ROTATION_PROBE_DEGREES,
            x_value,
            z_value,
        )
        probe = measure_motion_path(travelling_models, clip, context)
        if probe["yaw"] is None:
            raise RuntimeError("Could not measure the travelling-path rotation.")

        response = (
            angle_delta(probe["yaw"], path_yaw)
            / ROTATION_PROBE_DEGREES
        )
        if abs(response) < 0.05:
            set_clip_yaw(clip, base_yaw, x_value, z_value)
            raise RuntimeError(
                "The travelling path did not respond to the clip's global Y rotation."
            )

        set_clip_yaw(
            clip,
            base_yaw - (path_yaw / response),
            x_value,
            z_value,
        )

        for _pass_index in range(MAX_ALIGNMENT_PASSES):
            measurement = measure_motion_path(
                travelling_models,
                clip,
                context,
            )
            path_yaw = measurement["yaw"]
            if path_yaw is not None and abs(path_yaw) <= ALIGN_TOLERANCE_DEGREES:
                break
            if path_yaw is None:
                raise RuntimeError("The travelling path became too short to align.")

            current_rotation = copy_vector3d(clip.Rotation)
            set_clip_yaw(
                clip,
                float(current_rotation[1]) - (path_yaw / response),
                x_value,
                z_value,
            )

    # Rotation and travelling-node changes can recalculate the exposed clip
    # offset, so zero the start position once more before final verification.
    set_clip_vector(clip, "Translation", FBVector3d(0.0, 0.0, 0.0))
    measurement = measure_motion_path(travelling_models, clip, context)
    path_yaw = measurement["yaw"]
    delta = measurement["delta"]
    allowed_position_error = max(
        PATH_POSITION_TOLERANCE,
        measurement["distance"] * 0.0001,
    )

    if path_yaw is None or abs(path_yaw) > 0.50:
        raise RuntimeError(
            "Path verification failed (remaining yaw %.3f degrees)."
            % (path_yaw if path_yaw is not None else 999.0)
        )
    if abs(delta[0]) > allowed_position_error or delta[2] < 0.0:
        raise RuntimeError(
            "Path verification failed (end offset X %.4f, Z %.4f)."
            % (delta[0], delta[2])
        )

    return {
        "remaining_yaw": float(path_yaw),
        # The travelling-node function projects the visible root path to XZ.
        "end_offset": [float(delta[0]), 0.0, float(delta[2])],
        "distance": float(measurement["distance"]),
    }


def character_facing_yaw(character):
    if not character:
        raise RuntimeError("The clip's Story track has no assigned character.")

    try:
        if not character.GetCharacterize():
            raise RuntimeError("The assigned character is not characterized.")
    except AttributeError:
        pass

    hips = character.GetModel(FBBodyNodeId.kFBHipsNodeId)
    if not hips:
        raise RuntimeError("The assigned character has no characterized Hips model.")

    hips_matrix = FBMatrix()
    hips.GetMatrix(
        hips_matrix,
        FBModelTransformationType.kModelRotation,
        True,
    )
    hips_world = fbmatrix_to_matrix3(hips_matrix)

    rest_offset = FBVector3d()
    character.GetROffset(FBBodyNodeId.kFBHipsNodeId, rest_offset)
    skeleton_from_character = euler_xyz_to_matrix(rest_offset)

    # The HIK rotation offset converts the canonical character frame into the
    # skeleton's characterized/rest-pose frame. Removing it from the evaluated
    # Hips matrix gives the actual character frame in world space.
    character_world = matrix_multiply(
        hips_world,
        matrix_transpose(skeleton_from_character),
    )
    forward = transform_vector(character_world, [0.0, 0.0, 1.0])

    horizontal_length = math.sqrt(
        (forward[0] * forward[0]) + (forward[2] * forward[2])
    )
    if horizontal_length < 0.000001:
        raise RuntimeError("Could not resolve the character's horizontal facing direction.")

    return normalized_angle(
        math.degrees(math.atan2(forward[0], forward[2]))
    )


def align_character_clip_to_positive_z(
    clip,
    character,
    context=None,
):
    original_rotation = copy_vector3d(clip.Rotation)
    x_value = float(original_rotation[0])
    z_value = float(original_rotation[2])

    evaluate_at_clip_start(clip, context)
    base_yaw = float(copy_vector3d(clip.Rotation)[1])
    facing_yaw = character_facing_yaw(character)

    if abs(facing_yaw) <= ALIGN_TOLERANCE_DEGREES:
        return facing_yaw

    probe_yaw = base_yaw + ROTATION_PROBE_DEGREES
    set_clip_yaw(clip, probe_yaw, x_value, z_value)
    evaluate_at_clip_start(clip, context)
    probe_facing = character_facing_yaw(character)
    response = angle_delta(probe_facing, facing_yaw) / ROTATION_PROBE_DEGREES

    if abs(response) < 0.05:
        set_clip_yaw(clip, base_yaw, x_value, z_value)
        raise RuntimeError(
            "The character did not respond to the Story clip's global Y rotation."
        )

    set_clip_yaw(
        clip,
        base_yaw - (facing_yaw / response),
        x_value,
        z_value,
    )

    for _pass_index in range(MAX_ALIGNMENT_PASSES):
        evaluate_at_clip_start(clip, context)
        remaining_yaw = character_facing_yaw(character)
        if abs(remaining_yaw) <= ALIGN_TOLERANCE_DEGREES:
            return remaining_yaw

        current_rotation = copy_vector3d(clip.Rotation)
        set_clip_yaw(
            clip,
            float(current_rotation[1]) - (remaining_yaw / response),
            x_value,
            z_value,
        )

    evaluate_at_clip_start(clip, context)
    remaining_yaw = character_facing_yaw(character)
    if abs(remaining_yaw) > 0.50:
        raise RuntimeError(
            "Facing verification failed (remaining yaw %.3f degrees)." % remaining_yaw
        )
    return remaining_yaw


def reset_target_clip(target, path_min_distance, context=None):
    track = target["track"]
    clip = target["clip"]
    original_translation = copy_vector3d(clip.Translation)
    original_rotation = copy_vector3d(clip.Rotation)
    original_node_function = safe_get(clip, "TravellingNodeFunction", None)

    try:
        try:
            clip.MakeWritable()
        except Exception:
            pass

        set_clip_vector(clip, "Translation", FBVector3d(0.0, 0.0, 0.0))

        character = None
        if safe_get(track, "Type", None) == FBStoryTrackType.kFBStoryTrackCharacter:
            character = get_track_character(track, context)

        path_result = align_motion_path_to_positive_z(
            track,
            clip,
            character,
            path_min_distance,
            context,
        )
        if path_result:
            return {
                "name": clip_label(clip),
                "mode": "motion_path_verified",
                "remaining_yaw": path_result["remaining_yaw"],
                "end_offset": path_result["end_offset"],
                "distance": path_result["distance"],
            }

        if character:
            remaining_yaw = align_character_clip_to_positive_z(
                clip,
                character,
                context,
            )
            return {
                "name": clip_label(clip),
                "mode": "rest_pose_verified",
                "remaining_yaw": float(remaining_yaw),
            }

        rotation = copy_vector3d(clip.Rotation)
        set_clip_yaw(clip, 0.0, rotation[0], rotation[2])
        return {
            "name": clip_label(clip),
            "mode": "standard_positive_z",
            "remaining_yaw": None,
        }
    except Exception:
        try:
            if original_node_function is not None:
                clip.TravellingNodeFunction = original_node_function
            set_clip_vector(clip, "Translation", original_translation)
            set_clip_vector(clip, "Rotation", original_rotation)
        except Exception:
            pass
        raise


def reset_selected_story_clips(
    path_min_distance=DEFAULTS["clip_path_min_distance"],
    context=None,
):
    story, folders, tracks, clips, targets = collect_story_items()
    if not targets:
        return {
            "ok": False,
            "message": "No Story clips are selected.",
            "results": [],
            "errors": [],
        }

    state = capture_story_state(
        story,
        folders,
        tracks,
        clips,
        context,
    )
    results = []
    errors = []

    try:
        for target in targets:
            try:
                isolate_clip(story, state, target)
                results.append(
                    reset_target_clip(
                        target,
                        path_min_distance,
                        context,
                    )
                )
            except Exception as exc:
                errors.append(
                    {
                        "name": clip_label(target["clip"]),
                        "error": str(exc),
                    }
                )
    finally:
        restore_story_state(story, state, context)

    return {
        "ok": bool(results) and not errors,
        "message": None,
        "results": results,
        "errors": errors,
    }


def format_summary(report):
    results = report["results"]
    errors = report["errors"]

    if not results:
        if report.get("message"):
            return report["message"]
        return "No clips were changed."

    path_aligned = sum(
        1 for item in results if item["mode"] == "motion_path_verified"
    )
    pose_aligned = sum(
        1 for item in results if item["mode"] == "rest_pose_verified"
    )
    standard = len(results) - path_aligned - pose_aligned
    lines = [
        "Reset %d selected Story clip(s)." % len(results),
        "",
        "Translation: 0, 0, 0",
        "Direction: global +Z",
    ]

    if path_aligned:
        lines.append("Root paths aligned and verified: %d" % path_aligned)
    if pose_aligned:
        lines.append("Static poses aligned and verified: %d" % pose_aligned)
    if standard:
        lines.append(
            "Standard +Z fallback (no assigned character): %d" % standard
        )

    if errors:
        lines.extend(["", "Could not change %d clip(s):" % len(errors)])
        for item in errors[:8]:
            lines.append("- %s: %s" % (item["name"], item["error"]))
        if len(errors) > 8:
            lines.append("- ...and %d more" % (len(errors) - 8))

    return "\n".join(lines)
