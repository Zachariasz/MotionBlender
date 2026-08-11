"""Compatibility launcher for the manager-owned Fast Render feature."""

from mobu_tools_manager.features.render_two_cameras import (
    render,
    render_current_take,
    run,
)


__all__ = ("render", "render_current_take", "run")


if __name__ != "RenderSideFrontCameras":
    run()
