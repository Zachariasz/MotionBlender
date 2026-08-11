"""Validated personal settings for managed Story tools."""

from __future__ import absolute_import


DEFAULTS = {
    "clip_path_min_distance": 50.0,
}


def validate_story_settings(values):
    incoming = values if isinstance(values, dict) else {}
    try:
        distance = float(
            incoming.get(
                "clip_path_min_distance",
                DEFAULTS["clip_path_min_distance"],
            )
        )
    except (TypeError, ValueError):
        raise ValueError("Path movement threshold must be a number.")

    if distance < 0.0:
        raise ValueError("Path movement threshold cannot be negative.")
    if distance > 1000000.0:
        raise ValueError(
            "Path movement threshold cannot exceed 1,000,000 units."
        )

    return {
        "clip_path_min_distance": distance,
    }

