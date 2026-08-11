"""Contextual R Rotate feature."""

from __future__ import absolute_import

from ..fcurves.rotate_tangents import FCurveTangentRotateStrategy
from ..object_transforms.rotate import ObjectRotateStrategy


FEATURE_ID = "transform.rotate_mouse_orbit"


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
        strategy = FCurveTangentRotateStrategy(context, surface)
    elif classification == "viewer" and surface is not None:
        strategy = ObjectRotateStrategy(
            context,
            surface,
            mode=values.get("rotation_mode", "orbit"),
        )
    else:
        return None
    values.update(
        {
            "operation": "rotate",
            "launcher_key": "R",
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
