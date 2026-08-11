"""Validated, JSON-safe Quick Favorites configuration."""

from __future__ import absolute_import

import copy


CONTEXT_VIEWER = "viewer"
CONTEXT_FCURVES = "fcurves"
CONTEXT_OTHER = "other"
CONTEXTS = (CONTEXT_VIEWER, CONTEXT_FCURVES, CONTEXT_OTHER)
SUPPORTED_KINDS = ("feature", "native_action", "separator")
QUICK_FAVORITES_FEATURE_ID = "ui.quick_favorites"


DEFAULT_CONTEXTS = {
    CONTEXT_VIEWER: [
        {
            "kind": "native_action",
            "label": "Hide Gizmo",
            "target": "action.viewer.pick_mode_object",
        },
        {"kind": "separator"},
        {
            "kind": "feature",
            "label": "Camera Follow Selected",
            "target": "objects.lock_camera",
        },
    ],
    CONTEXT_FCURVES: [
        {
            "kind": "feature",
            "label": "Select FCurve",
            "target": "fcurves.select_displayed_keys",
        },
        {
            "kind": "native_action",
            "label": "Add Key",
            "target": "action.fcurve.insert_key",
        },
        {"kind": "separator"},
        {
            "kind": "feature",
            "label": "Apply Filter",
            "target": "fcurves.apply_filter",
        },
        {
            "kind": "feature",
            "label": "Set Loop",
            "target": "fcurves.infinite_repetition",
        },
    ],
    CONTEXT_OTHER: [
        {
            "kind": "feature",
            "label": "Duplicate",
            "target": "objects.duplicate",
        },
        {
            "kind": "feature",
            "label": "Rename Selected...",
            "target": "objects.rename_selected",
        },
        {"kind": "separator"},
        {
            "kind": "feature",
            "label": "Set Namespace...",
            "target": "objects.set_namespace",
        },
        {
            "kind": "feature",
            "label": "Remove Namespace...",
            "target": "objects.remove_namespace",
        },
        {"kind": "separator"},
        {
            "kind": "feature",
            "label": "Bake Story Clips to Takes...",
            "target": "story.bake_clips_to_takes",
        },
        {
            "kind": "feature",
            "label": "Export Custom...",
            "target": "objects.export_custom",
        },
    ],
}

DEFAULTS = {"contexts": DEFAULT_CONTEXTS}


def favorite_key(entry):
    """Return a stable identity for remembered-row placement."""
    if not isinstance(entry, dict):
        return ""
    kind = str(entry.get("kind") or "").strip().lower()
    if kind == "separator":
        return "separator"
    target = str(entry.get("target") or "").strip()
    return "%s:%s" % (kind, target)


def _normalize_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("each Quick Favorite must be an object")
    kind = str(entry.get("kind") or "").strip().lower()
    if kind not in SUPPORTED_KINDS:
        raise ValueError("unsupported Quick Favorite kind: " + kind)
    if kind == "separator":
        return {"kind": "separator"}

    label = str(entry.get("label") or "").strip()
    target = str(entry.get("target") or "").strip()
    if not label:
        raise ValueError("Quick Favorite label cannot be empty")
    if not target:
        raise ValueError("Quick Favorite target cannot be empty")
    if kind == "feature" and target == QUICK_FAVORITES_FEATURE_ID:
        raise ValueError("Quick Favorites cannot dispatch itself")
    if kind == "native_action" and not target.startswith("action."):
        raise ValueError(
            "native action targets must begin with 'action.'"
        )
    return {"kind": kind, "label": label, "target": target}


def _normalize_entries(entries):
    if not isinstance(entries, (list, tuple)):
        raise ValueError("Quick Favorites context entries must be a list")
    normalized = []
    for incoming in entries:
        entry = _normalize_entry(incoming)
        if entry["kind"] == "separator":
            if not normalized or normalized[-1]["kind"] == "separator":
                continue
        normalized.append(entry)
    while normalized and normalized[-1]["kind"] == "separator":
        normalized.pop()
    return normalized


def validate_quick_favorites_settings(values=None):
    """Merge partial settings with defaults and return validated data."""
    values = values if isinstance(values, dict) else {}
    incoming_contexts = values.get("contexts")
    if incoming_contexts is None:
        incoming_contexts = {}
    if not isinstance(incoming_contexts, dict):
        raise ValueError("Quick Favorites contexts must be an object")

    contexts = {}
    for context in CONTEXTS:
        entries = incoming_contexts.get(
            context,
            copy.deepcopy(DEFAULT_CONTEXTS[context]),
        )
        contexts[context] = _normalize_entries(entries)
    return {"contexts": contexts}
