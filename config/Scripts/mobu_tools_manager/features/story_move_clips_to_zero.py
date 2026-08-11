"""Manager-native entrypoint for moving selected Story clips to frame 0."""

from __future__ import absolute_import

from ..story.clip_timing import (
    TOOL_NAME,
    move_selected_story_clips_to_zero,
)


def execute(context):
    with context.undo.scope(TOOL_NAME):
        report = move_selected_story_clips_to_zero(context)
    return report
