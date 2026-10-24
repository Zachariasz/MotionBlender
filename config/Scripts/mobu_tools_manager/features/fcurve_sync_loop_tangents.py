"""Manager-native entrypoint for synchronizing loop boundary tangents."""

from __future__ import absolute_import

from ..fcurves.loop import sync_selected_fcurves_loop_tangents


def execute(context=None):
    return sync_selected_fcurves_loop_tangents(match_value=True)
