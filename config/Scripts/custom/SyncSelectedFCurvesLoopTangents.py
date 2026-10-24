"""Synchronize boundary tangents and values for selected FCurves in MotionBuilder."""

from __future__ import absolute_import

from mobu_tools_manager.fcurves.loop import sync_selected_fcurves_loop_tangents


def run():
    sync_selected_fcurves_loop_tangents(match_value=True)


if __name__ == "__main__":
    run()
