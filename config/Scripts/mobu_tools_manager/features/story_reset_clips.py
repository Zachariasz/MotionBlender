"""Manager-native entrypoint for resetting and aligning Story clips."""

from __future__ import absolute_import

from ..story.reset_selected_clips import (
    TOOL_NAME,
    reset_selected_story_clips,
)
from ..story.settings import DEFAULTS


def execute(context):
    """Reset selected Story clips using the manager-owned Story settings."""
    settings = context.story_settings
    threshold = float(
        settings.get(
            "clip_path_min_distance",
            DEFAULTS["clip_path_min_distance"],
        )
    )
    with context.undo.scope(TOOL_NAME):
        report = reset_selected_story_clips(
            path_min_distance=threshold,
            context=context,
        )
    return report
