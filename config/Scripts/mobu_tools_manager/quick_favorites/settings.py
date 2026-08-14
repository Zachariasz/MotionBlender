"""Validated, JSON-safe Quick Favorites configuration."""

from __future__ import absolute_import

import copy


CONTEXT_VIEWER = "viewer"
CONTEXT_FCURVES = "fcurves"
CONTEXT_TIMELINE = "timeline"
CONTEXT_OTHER = "other"
CONTEXTS = (
    CONTEXT_VIEWER,
    CONTEXT_FCURVES,
    CONTEXT_TIMELINE,
    CONTEXT_OTHER,
)
SUPPORTED_KINDS = ("feature", "native_action", "separator")
QUICK_FAVORITES_FEATURE_ID = "ui.quick_favorites"
FCURVE_ADD_KEY_FEATURE_ID = "fcurves.add_key"
TIMELINE_MARKER_LABELS_FEATURE_ID = "animation.timeline_marker_labels"
FIND_IN_HIERARCHY_FEATURE_ID = "objects.find_in_hierarchy"
LEGACY_FCURVE_ADD_KEY_ACTION = "action.fcurve.insert_key"
SETTINGS_VERSION = 2


DEFAULT_CONTEXTS = {
    CONTEXT_VIEWER: [
        {
            "kind": "native_action",
            "label": "Hide Gizmo",
            "target": "action.viewer.pick_mode_object",
        },
        {
            "kind": "feature",
            "label": "Find Selected in Hierarchy",
            "target": FIND_IN_HIERARCHY_FEATURE_ID,
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
            "kind": "feature",
            "label": "Add Key",
            "target": FCURVE_ADD_KEY_FEATURE_ID,
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
    CONTEXT_TIMELINE: [
        {
            "kind": "feature",
            "label": "Toggle Marker Names",
            "target": TIMELINE_MARKER_LABELS_FEATURE_ID,
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

DEFAULTS = {"version": SETTINGS_VERSION, "contexts": DEFAULT_CONTEXTS}


def context_for_ui_classification(classification):
    """Map the manager's UI classification to a favorites context."""
    classification = str(classification or "").strip().lower()
    if classification in ("fcurve", CONTEXT_FCURVES):
        return CONTEXT_FCURVES
    if classification == CONTEXT_VIEWER:
        return CONTEXT_VIEWER
    if classification == CONTEXT_TIMELINE:
        return CONTEXT_TIMELINE
    return CONTEXT_OTHER


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
    if (
        kind == "native_action"
        and target.lower() == LEGACY_FCURVE_ADD_KEY_ACTION
    ):
        return {
            "kind": "feature",
            "label": label,
            "target": FCURVE_ADD_KEY_FEATURE_ID,
        }
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


def _migrate_viewer_entries(entries):
    if any(
        entry.get("kind") == "feature"
        and entry.get("target") == FIND_IN_HIERARCHY_FEATURE_ID
        for entry in entries
    ):
        return entries
    inserted = {
        "kind": "feature",
        "label": "Find Selected in Hierarchy",
        "target": FIND_IN_HIERARCHY_FEATURE_ID,
    }
    for index, entry in enumerate(entries):
        if entry.get("kind") == "native_action":
            entries.insert(index + 1, inserted)
            return entries
    entries.insert(0, inserted)
    return entries


def validate_quick_favorites_settings(values=None):
    """Merge partial settings with defaults and return validated data."""
    values = values if isinstance(values, dict) else {}
    incoming_contexts = values.get("contexts")
    if incoming_contexts is None:
        incoming_contexts = {}
    if not isinstance(incoming_contexts, dict):
        raise ValueError("Quick Favorites contexts must be an object")

    incoming_version = values.get("version", 0)
    try:
        incoming_version = int(incoming_version)
    except (TypeError, ValueError):
        incoming_version = 0
    contexts = {}
    for context in CONTEXTS:
        entries = incoming_contexts.get(
            context,
            copy.deepcopy(DEFAULT_CONTEXTS[context]),
        )
        contexts[context] = _normalize_entries(entries)
    if incoming_version < SETTINGS_VERSION:
        contexts[CONTEXT_VIEWER] = _migrate_viewer_entries(
            contexts[CONTEXT_VIEWER]
        )
    return {"version": SETTINGS_VERSION, "contexts": contexts}
