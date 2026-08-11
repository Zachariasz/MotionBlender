"""Contextual G Move feature."""

from __future__ import absolute_import

from ..fcurves.move import FCurveMoveStrategy
from ..object_transforms.move import ObjectMoveStrategy


FEATURE_ID = "transform.move_camera_plane"


def execute(context, invocation=None):
    values = dict(invocation or {})
    if values:
        classification = str(
            values.get("domain")
            or values.get("ui_context")
            or "other"
        ).lower()
        surface = values.get("surface")
    else:
        ui_context = context.ui_context
        classification = ui_context.get("hovered", "other")
        surface = ui_context.get("surface")
        values = {
            "surface_generation": ui_context.get(
                "surface_generation",
                0,
            ),
            "focus_widget": (
                ui_context.get("hovered_widget")
                or ui_context.get("surface")
            ),
        }
    if classification == "fcurve" and surface is not None:
        strategy = FCurveMoveStrategy(context, surface, timeline=False)
    elif classification == "timeline" and surface is not None:
        strategy = FCurveMoveStrategy(context, surface, timeline=True)
    elif classification == "viewer" and surface is not None:
        strategy = ObjectMoveStrategy(context, surface)
    else:
        return None
    values.update(
        {
            "operation": "move",
            "launcher_key": "G",
            "domain": classification,
            "ui_context": classification,
            "surface": surface,
        }
    )
    return context.interactions.start(
        FEATURE_ID,
        strategy,
        values,
    )
