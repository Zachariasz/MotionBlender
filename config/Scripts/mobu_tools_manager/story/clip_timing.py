"""Story clip timeline-placement commands."""

from __future__ import absolute_import


TOOL_NAME = "Move Selected Story Clips to Frame 0"


def _safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe_set(obj, name, value):
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def _clip_label(clip):
    for name in ("Name", "LongName", "Label"):
        value = _safe_get(clip, name, None)
        if value:
            return str(value)
    return "Story Clip"


def selected_story_clips():
    from pyfbsdk import FBStory

    selected = []

    def visit_track(track):
        try:
            for clip in track.Clips:
                try:
                    if bool(clip.Selected):
                        selected.append(clip)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for child in track.SubTracks:
                visit_track(child)
        except Exception:
            pass

    def visit_folder(folder):
        try:
            for track in folder.Tracks:
                visit_track(track)
        except Exception:
            pass
        try:
            for child in folder.Childs:
                visit_folder(child)
        except Exception:
            pass

    visit_folder(FBStory().RootFolder)
    return selected


def _restore_clip_timing(clip, start, stop, locked, sdk):
    _safe_set(clip, "StartStopLocked", False)
    try:
        clip.MoveTo(sdk.FBTime(start.Get()), True)
    except Exception:
        _safe_set(clip, "Start", sdk.FBTime(start.Get()))
    _safe_set(clip, "Stop", sdk.FBTime(stop.Get()))
    _safe_set(clip, "StartStopLocked", locked)


def _move_clip_to_zero(clip, sdk):
    original_start = sdk.FBTime(clip.Start.Get())
    original_stop = sdk.FBTime(clip.Stop.Get())
    original_locked = bool(_safe_get(clip, "StartStopLocked", False))
    duration_ticks = int(original_stop.Get()) - int(original_start.Get())
    if duration_ticks < 0:
        raise RuntimeError("Clip stop time is earlier than its start time.")

    try:
        try:
            clip.MakeWritable()
        except Exception:
            pass
        _safe_set(clip, "StartStopLocked", False)
        zero = sdk.FBTime(0)
        try:
            clip.MoveTo(zero, True)
        except Exception:
            clip.Start = zero

        # MoveTo normally preserves duration. Set Stop explicitly so the
        # command remains correct for clip types that implement Start as a
        # trim operation instead of a placement operation.
        clip.Stop = sdk.FBTime(duration_ticks)
        if int(clip.Start.Get()) != 0:
            clip.Start = sdk.FBTime(0)
        if int(clip.Start.Get()) != 0:
            raise RuntimeError("MotionBuilder did not move the clip to frame 0.")
        if int(clip.Stop.Get()) - int(clip.Start.Get()) != duration_ticks:
            raise RuntimeError("MotionBuilder did not preserve the clip duration.")
        _safe_set(clip, "StartStopLocked", original_locked)
        return {
            "name": _clip_label(clip),
            "original_start_ticks": int(original_start.Get()),
            "duration_ticks": duration_ticks,
        }
    except Exception:
        _restore_clip_timing(
            clip,
            original_start,
            original_stop,
            original_locked,
            sdk,
        )
        raise


def move_selected_story_clips_to_zero(context=None):
    import pyfbsdk as sdk

    clips = selected_story_clips()
    if not clips:
        return {
            "ok": False,
            "message": "No Story clips are selected.",
            "results": [],
            "errors": [],
        }

    results = []
    errors = []
    for clip in clips:
        try:
            results.append(_move_clip_to_zero(clip, sdk))
        except Exception as error:
            errors.append(
                {
                    "name": _clip_label(clip),
                    "error": str(error),
                }
            )

    if context is not None:
        context.evaluation.flush_now()
    return {
        "ok": bool(results) and not errors,
        "message": None,
        "results": results,
        "errors": errors,
    }


def format_summary(report):
    if not report["results"]:
        return report.get("message") or "No clips were changed."
    lines = [
        "Moved %d selected Story clip(s) to frame 0."
        % len(report["results"]),
        "Clip duration was preserved.",
    ]
    if report["errors"]:
        lines.extend(["", "Could not move %d clip(s):" % len(report["errors"])])
        for item in report["errors"][:8]:
            lines.append("- %s: %s" % (item["name"], item["error"]))
    return "\n".join(lines)

