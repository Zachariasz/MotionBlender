"""Create a Character Story track from the current take."""

from __future__ import absolute_import


TOOL_NAME = "Insert Current Take to Story"


def _safe_get(component, name, default=None):
    try:
        return getattr(component, name)
    except Exception:
        return default


def _safe_set(component, name, value):
    try:
        setattr(component, name, value)
        return True
    except Exception:
        return False


def _iter_track_tree(track):
    yield track
    for child in _safe_get(track, "SubTracks", ()):
        for nested in _iter_track_tree(child):
            yield nested


def _iter_story_items(folder):
    yield folder
    for root_track in _safe_get(folder, "Tracks", ()):
        for track in _iter_track_tree(root_track):
            yield track
            for clip in _safe_get(track, "Clips", ()):
                yield clip
    for child_folder in _safe_get(folder, "Childs", ()):
        for item in _iter_story_items(child_folder):
            yield item


def _replace_story_selection(root_folder, selected_item):
    for item in _iter_story_items(root_folder):
        _safe_set(item, "Selected", item is selected_item)


def insert_current_take(context=None, sdk=None):
    """Insert the current take and return its selected Story clip."""
    if sdk is None:
        import pyfbsdk as sdk

    application = (
        context.application if context is not None else sdk.FBApplication()
    )
    system = context.system if context is not None else sdk.FBSystem()
    take = context.take if context is not None else system.CurrentTake
    character = application.CurrentCharacter

    if character is None:
        raise RuntimeError(
            "No active character was found in Character Controls."
        )
    if take is None:
        raise RuntimeError("No current take was found.")

    story = sdk.FBStory()
    root_folder = story.RootFolder
    original_mute = bool(_safe_get(story, "Mute", False))
    original_selection = [
        item
        for item in _iter_story_items(root_folder)
        if bool(_safe_get(item, "Selected", False))
    ]
    track = None

    try:
        story.Mute = False
        track = sdk.FBStoryTrack(
            sdk.FBStoryTrackType.kFBStoryTrackCharacter,
            root_folder,
        )
        # Autodesk's InsertCurrentTake sample assigns the Character this way.
        track.Details.append(character)
        clip = track.CopyTakeIntoTrack(take.LocalTimeSpan, take)
        if clip is None:
            raise RuntimeError("MotionBuilder did not create a Story clip.")

        _replace_story_selection(root_folder, clip)
        if context is not None:
            context.evaluation.flush_now()
        else:
            system.Scene.Evaluate()
        return clip
    except Exception:
        if track is not None:
            try:
                track.FBDelete()
            except Exception:
                pass
        story.Mute = original_mute
        _replace_story_selection(root_folder, None)
        for item in original_selection:
            _safe_set(item, "Selected", True)
        raise
