"""Manager-native entrypoint for inserting the current take into Story."""

from __future__ import absolute_import

from ..story.insert_current_take import TOOL_NAME, insert_current_take


def execute(context):
    with context.undo.scope(TOOL_NAME):
        return insert_current_take(context=context)
