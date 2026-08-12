"""Quick Favorites configuration shared by the manager UI and feature."""

from __future__ import absolute_import

from .settings import (
    CONTEXT_FCURVES,
    CONTEXT_OTHER,
    CONTEXT_TIMELINE,
    CONTEXT_VIEWER,
    CONTEXTS,
    DEFAULTS,
    context_for_ui_classification,
    favorite_key,
    validate_quick_favorites_settings,
)


__all__ = [
    "CONTEXT_FCURVES",
    "CONTEXT_OTHER",
    "CONTEXT_TIMELINE",
    "CONTEXT_VIEWER",
    "CONTEXTS",
    "DEFAULTS",
    "context_for_ui_classification",
    "favorite_key",
    "validate_quick_favorites_settings",
]
