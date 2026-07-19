from pyfbsdk import *
import traceback


PLOT_CHARACTER_TO = FBCharacterPlotWhere.kFBCharacterPlotOnSkeleton
MUTE_STORY_AFTER_BAKE = True
PARK_OTHER_CLIPS_AT_FRAME = 1000000
CLIP_OFFSET_TRANSLATION = FBVector3d(0.0, 0.0, 0.0)
CLIP_OFFSET_ROTATION = FBVector3d(0.0, -90.0, 0.0)


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def safe_set(obj, attr, value):
    try:
        setattr(obj, attr, value)
        return True
    except Exception:
        return False


def copy_vector3d(value, fallback=None):
    if value is None:
        return fallback if fallback is not None else FBVector3d(0.0, 0.0, 0.0)

    try:
        return FBVector3d(value)
    except Exception:
        pass

    try:
        return FBVector3d(value[0], value[1], value[2])
    except Exception:
        return fallback if fallback is not None else FBVector3d(0.0, 0.0, 0.0)


def label_of(obj, fallback):
    for attr in ("Name", "Label", "LongName"):
        value = safe_get(obj, attr, None)
        if value:
            return str(value)
    return fallback


def clean_take_name(name):
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid else char for char in name).strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = "Story Clip"
    return cleaned[:80]


def unique_take_name(base_name):
    existing = set()
    for take in FBSystem().Scene.Takes:
        existing.add(take.Name)

    base_name = clean_take_name(base_name)
    if base_name not in existing:
        return base_name

    index = 1
    while True:
        suffix = " {0:02d}".format(index)
        candidate = clean_take_name(base_name[: 80 - len(suffix)] + suffix)
        if candidate not in existing:
            return candidate
        index += 1


def iter_track_tree(track):
    yield track

    for sub_track in safe_get(track, "SubTracks", []):
        for nested_track in iter_track_tree(sub_track):
            yield nested_track


def collect_story_items():
    story = FBStory()
    folders = []
    tracks = []
    clips = []
    targets = []

    def visit_folder(folder, folder_path):
        folders.append(folder)

        for track in safe_get(folder, "Tracks", []):
            for story_track in iter_track_tree(track):
                tracks.append(story_track)
                track_label = label_of(story_track, "Story Track")

                for clip in safe_get(story_track, "Clips", []):
                    clips.append(clip)

                    track_type = safe_get(story_track, "Type", None)
                    if track_type not in (
                        FBStoryTrackType.kFBStoryTrackCharacter,
                        FBStoryTrackType.kFBStoryTrackAnimation,
                    ):
                        continue

                    start = safe_get(clip, "Start", None)
                    stop = safe_get(clip, "Stop", None)
                    if start is None or stop is None or stop <= start:
                        continue

                    targets.append(
                        {
                            "track": story_track,
                            "clip": clip,
                            "track_label": track_label,
                            "folder_path": folder_path,
                            "start": FBTime(start.Get()),
                            "stop": FBTime(stop.Get()),
                            "duration": FBTime(stop.Get() - start.Get()),
                        }
                    )

        for child_folder in safe_get(folder, "Childs", []):
            child_label = label_of(child_folder, "Folder")
            child_path = folder_path + "/" + child_label if folder_path else child_label
            visit_folder(child_folder, child_path)

    visit_folder(story.RootFolder, "")
    return story, folders, tracks, clips, targets


def capture_story_state(story, folders, tracks, clips):
    return {
        "story_mute": safe_get(story, "Mute", False),
        "folders": [
            (folder, safe_get(folder, "Mute", False), safe_get(folder, "Solo", False))
            for folder in folders
        ],
        "tracks": [
            (track, safe_get(track, "Mute", False), safe_get(track, "Solo", False))
            for track in tracks
        ],
        "clips": [
            (
                clip,
                safe_get(clip, "Loaded", True),
                FBTime(clip.Start.Get()),
                FBTime(clip.Stop.Get()),
                safe_get(clip, "StartStopLocked", False),
                copy_vector3d(safe_get(clip, "Translation", None)),
                copy_vector3d(safe_get(clip, "Rotation", None)),
            )
            for clip in clips
        ],
    }


def move_clip_to(clip, start_time):
    try:
        clip.MakeWritable()
    except Exception:
        pass

    safe_set(clip, "StartStopLocked", False)

    try:
        clip.MoveTo(start_time, True)
        return True
    except Exception:
        pass

    try:
        duration = FBTime(clip.Stop.Get() - clip.Start.Get())
        clip.Start = start_time
        clip.Stop = FBTime(start_time.Get() + duration.Get())
        return True
    except Exception:
        return False


def apply_bake_clip_offsets(clip):
    try:
        clip.MakeWritable()
    except Exception:
        pass

    clip.Translation = copy_vector3d(CLIP_OFFSET_TRANSLATION)
    clip.Rotation = copy_vector3d(CLIP_OFFSET_ROTATION)


def restore_clip_state(
    clip,
    loaded,
    start,
    stop,
    start_stop_locked,
    translation,
    rotation,
):
    safe_set(clip, "StartStopLocked", False)

    if not move_clip_to(clip, start):
        safe_set(clip, "Start", start)

    safe_set(clip, "Stop", stop)
    safe_set(clip, "Translation", translation)
    safe_set(clip, "Rotation", rotation)
    safe_set(clip, "Loaded", loaded)
    safe_set(clip, "StartStopLocked", start_stop_locked)


def restore_story_state(state, mute_story_after_bake):
    safe_set(FBStory(), "Mute", bool(mute_story_after_bake))

    for folder, mute, solo in state["folders"]:
        safe_set(folder, "Mute", mute)
        safe_set(folder, "Solo", solo)

    for track, mute, solo in state["tracks"]:
        safe_set(track, "Mute", mute)
        safe_set(track, "Solo", solo)

    for (
        clip,
        loaded,
        start,
        stop,
        start_stop_locked,
        translation,
        rotation,
    ) in state["clips"]:
        restore_clip_state(
            clip,
            loaded,
            start,
            stop,
            start_stop_locked,
            translation,
            rotation,
        )

    if not mute_story_after_bake:
        safe_set(FBStory(), "Mute", state["story_mute"])


def unmute_track_and_parents(track):
    current = track
    while current:
        safe_set(current, "Mute", False)
        safe_set(current, "Solo", False)
        current = safe_get(current, "ParentTrack", None)


def isolate_story_clip(story, target, folders, tracks, clips):
    safe_set(story, "Mute", False)

    for folder in folders:
        safe_set(folder, "Mute", False)
        safe_set(folder, "Solo", False)

    for track in tracks:
        safe_set(track, "Mute", True)
        safe_set(track, "Solo", False)

    for index, clip in enumerate(clips):
        safe_set(clip, "Loaded", False)
        if clip != target["clip"]:
            move_clip_to(
                clip,
                FBTime(0, 0, 0, PARK_OTHER_CLIPS_AT_FRAME + (index * 1000)),
            )

    unmute_track_and_parents(target["track"])
    move_clip_to(target["clip"], FBTime(0))
    apply_bake_clip_offsets(target["clip"])
    safe_set(target["clip"], "Loaded", True)


def make_plot_options():
    options = FBPlotOptions()
    options.ConstantKeyReducerKeepOneKey = False
    options.PlotAllTakes = False
    options.PlotOnFrame = True
    options.PlotPeriod = FBTime(0, 0, 0, 1)
    options.PlotTranslationOnRootOnly = True
    options.PreciseTimeDiscontinuities = True
    options.RotationFilterToApply = FBRotationFilter.kFBRotationFilterGimbleKiller
    options.UseConstantKeyReducer = False
    options.PlotLockedProperties = True
    return options


def get_track_character(track):
    character = safe_get(track, "Character", None)
    if character:
        return character

    character_index = safe_get(track, "CharacterIndex", 0)
    if character_index <= 0:
        return None

    characters = FBSystem().Scene.Characters
    if character_index - 1 >= len(characters):
        return None

    return characters[character_index - 1]


def clip_is_connected_to_current_take(clip):
    return bool(safe_get(clip, "ConnectedToTake", False))


def create_take_for_clip(source_take, take_name, clip):
    system = FBSystem()

    if clip_is_connected_to_current_take(clip):
        system.CurrentTake = source_take
        return source_take.CopyTake(take_name)

    new_take = FBTake(take_name)
    system.Scene.Takes.append(new_take)
    system.CurrentTake = new_take
    return new_take


def delete_created_take(take, fallback_take):
    if not take or take == fallback_take:
        return

    system = FBSystem()
    if system.CurrentTake == take:
        system.CurrentTake = fallback_take

    try:
        take.FBDelete()
    except Exception:
        pass


def set_take_span(take, start, stop):
    time_span = FBTimeSpan(start, stop)
    take.LocalTimeSpan = time_span
    take.ReferenceTimeSpan = time_span


def bake_target(target, source_take, target_index):
    system = FBSystem()
    scene = system.Scene
    clip = target["clip"]
    track = target["track"]
    duration = FBTime(target["duration"].Get())
    zero = FBTime(0)

    clip_label = label_of(clip, "Clip {0:02d}".format(target_index))
    take_name = unique_take_name("{0:02d}_{1}".format(target_index, clip_label))
    new_take = create_take_for_clip(source_take, take_name, clip)
    if not new_take:
        return None, "Could not create a take for this clip."

    system.CurrentTake = new_take

    try:
        new_take.SetCurrentLayer(0)
    except Exception:
        pass

    set_take_span(new_take, zero, duration)
    FBPlayerControl().Goto(zero)
    scene.Evaluate()

    options = make_plot_options()
    track_type = safe_get(track, "Type", None)
    baked = False

    if track_type == FBStoryTrackType.kFBStoryTrackCharacter:
        character = get_track_character(track)
        if character:
            baked = bool(character.PlotAnimation(PLOT_CHARACTER_TO, options))

    if not baked:
        affected_objects = []
        try:
            affected_objects = list(clip.GetAffectedObjects())
        except Exception:
            affected_objects = []

        if affected_objects:
            new_take.PlotTakeOnObjects(options, affected_objects)
            baked = True

    if not baked:
        delete_created_take(new_take, source_take)
        return None, "Could not find a character or affected objects to plot."

    # The target Story clip has been moved to frame 0 before this plot.
    # Keep only the baked 0..duration range.
    try:
        new_take.DeleteAnimation(FBTime.MinusInfinity, zero, False, -1, True)
        new_take.DeleteAnimation(duration, FBTime.Infinity, False, -1, True)
    except Exception:
        pass

    set_take_span(new_take, zero, duration)
    FBPlayerControl().Goto(zero)
    scene.Evaluate()

    return new_take, None


def bake_story_clips_to_takes():
    system = FBSystem()
    source_take = system.CurrentTake

    if not source_take:
        FBMessageBox("Bake Story Clips", "No current take found.", "OK")
        return

    story, folders, tracks, clips, targets = collect_story_items()

    if not targets:
        FBMessageBox(
            "Bake Story Clips",
            "No character or animation Story clips found.",
            "OK",
        )
        return

    state = capture_story_state(story, folders, tracks, clips)
    created = []
    failures = []

    try:
        for index, target in enumerate(targets, 1):
            isolate_story_clip(story, target, folders, tracks, clips)
            take, error = bake_target(target, source_take, index)

            if take:
                created.append(take)
                print(
                    "Baked Story clip '{0}' to take '{1}' starting at frame 0.".format(
                        label_of(target["clip"], "Clip"),
                        take.Name,
                    )
                )
            else:
                failures.append(
                    "{0}: {1}".format(label_of(target["clip"], "Clip"), error)
                )
    finally:
        restore_story_state(state, MUTE_STORY_AFTER_BAKE and bool(created))
        system.CurrentTake = created[-1] if created else source_take
        system.Scene.Evaluate()

    message = "Created {0} take(s).".format(len(created))
    if MUTE_STORY_AFTER_BAKE and created:
        message += "\nStory is muted so the new baked takes play without Story driving them again."
    if failures:
        message += "\n\nSkipped {0} clip(s):\n{1}".format(
            len(failures),
            "\n".join(failures[:10]),
        )

    FBMessageBox("Bake Story Clips", message, "OK")
    print(message.replace("\n", " "))


def run_with_error_dialog():
    try:
        bake_story_clips_to_takes()
    except Exception:
        details = traceback.format_exc()
        print(details)
        FBMessageBox("Bake Story Clips - Error", details[-1800:], "OK")


run_with_error_dialog()
