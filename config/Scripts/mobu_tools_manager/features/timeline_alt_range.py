"""Per-take alternate Timeline range command.

The command is exposed through Timeline Quick Favorites. The current and
alternate ``FBTake.LocalTimeSpan`` values live in one custom string property on
the take, so the per-take state follows the source FBX.
"""

from __future__ import absolute_import

import json


FEATURE_ID = "animation.timeline_toggle_alt_range"
PROPERTY_NAME = "MTM Timeline Alternate Range"
PROPERTY_VERSION = 1
MAIN_SLOT = "main"
ALT_SLOT = "alternate"


def _sdk_module():
    import pyfbsdk

    return pyfbsdk


def _safe(callback, default=None):
    try:
        return callback()
    except (AttributeError, RuntimeError, ReferenceError, TypeError, ValueError):
        return default


def _time_range(take):
    """Return the current local range as immutable FBTime ticks."""
    if take is None:
        raise RuntimeError("No current take.")
    try:
        span = take.LocalTimeSpan
        start = int(span.GetStart().Get())
        stop = int(span.GetStop().Get())
    except Exception as error:
        raise RuntimeError("Could not read the current take Timeline range.") from error
    if stop < start:
        raise RuntimeError("The current take has an invalid Timeline range.")
    return start, stop


def _valid_range(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        start, stop = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None
    return (start, stop) if stop >= start else None


def _state_from_data(value):
    try:
        state = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    try:
        version = int(state.get("version", 0))
    except (TypeError, ValueError):
        return None
    if version != PROPERTY_VERSION:
        return None
    main_range = _valid_range(state.get(MAIN_SLOT))
    alt_range = _valid_range(state.get(ALT_SLOT))
    if main_range is None or alt_range is None:
        return None
    active = state.get("active")
    if active not in (MAIN_SLOT, ALT_SLOT):
        return None
    return {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: main_range,
        ALT_SLOT: alt_range,
        "active": active,
    }


def _state_property(take, sdk, create=False):
    try:
        property_list = take.PropertyList
        prop = property_list.Find(PROPERTY_NAME)
    except Exception as error:
        raise RuntimeError("Could not access the current take properties.") from error
    if prop is not None or not create:
        return prop
    try:
        prop = take.PropertyCreate(
            PROPERTY_NAME,
            sdk.FBPropertyType.kFBPT_charptr,
            "String",
            False,
            True,
            None,
        )
    except Exception as error:
        raise RuntimeError("Could not create the alternate range property.") from error
    if prop is None:
        raise RuntimeError("Could not create the alternate range property.")
    return prop


def read_state(take, sdk):
    """Read validated persisted state, or ``None`` for a new/corrupt take."""
    prop = _state_property(take, sdk, create=False)
    return None if prop is None else _state_from_data(_safe(lambda: prop.Data, ""))


def is_alternate_active(take, sdk=None):
    """Return whether ``take`` is currently showing its alternate range."""
    state = read_state(take, sdk or _sdk_module())
    return bool(state and state["active"] == ALT_SLOT)


def quick_favorite_checked(context, sdk=None):
    """Provide the checked state when this command appears in Quick Favorites."""
    return is_alternate_active(context.take, sdk=sdk)


def _new_state(current_range):
    return {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: tuple(current_range),
        ALT_SLOT: tuple(current_range),
        "active": MAIN_SLOT,
    }


def _write_state(take, sdk, state, prop=None):
    prop = prop or _state_property(take, sdk, create=True)
    payload = {
        "version": PROPERTY_VERSION,
        MAIN_SLOT: list(state[MAIN_SLOT]),
        ALT_SLOT: list(state[ALT_SLOT]),
        "active": state["active"],
    }
    try:
        prop.Data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception as error:
        raise RuntimeError("Could not save the alternate Timeline range.") from error


def _set_time_range(take, sdk, time_range):
    start, stop = _valid_range(time_range) or (None, None)
    if start is None:
        raise RuntimeError("The saved alternate Timeline range is invalid.")
    try:
        take.LocalTimeSpan = sdk.FBTimeSpan(sdk.FBTime(start), sdk.FBTime(stop))
    except Exception as error:
        raise RuntimeError("Could not set the current take Timeline range.") from error


def _local_time_span_property(take):
    return _safe(lambda: take.PropertyList.Find("LocalTimeSpan"), None)


def toggle_alt_range(context, sdk=None):
    """Save edits to the active side, then swap to the other saved range.

    The first invocation initializes both sides from the current range and
    enters alternate mode without changing the visible range. The user can then
    edit Timeline start/end normally; the next invocation captures those edits
    and restores the original main range.
    """
    sdk = sdk or _sdk_module()
    take = context.take
    current_range = _time_range(take)
    state = read_state(take, sdk) or _new_state(current_range)
    active = state["active"]
    target = ALT_SLOT if active == MAIN_SLOT else MAIN_SLOT
    state_prop = _state_property(take, sdk, create=True)

    def swap():
        state[active] = current_range
        _set_time_range(take, sdk, state[target])
        state["active"] = target
        _write_state(take, sdk, state, prop=state_prop)

    undo_helper = getattr(context, "undo", None)
    if undo_helper is not None and hasattr(undo_helper, "begin"):
        transaction = undo_helper.begin("Toggle Timeline Alternate Range")
        transaction.add_property(_local_time_span_property(take))
        transaction.add_property(state_prop)
        try:
            swap()
        except Exception:
            transaction.cancel()
            raise
        else:
            transaction.commit()
    elif undo_helper is not None and hasattr(undo_helper, "scope"):
        with undo_helper.scope("Toggle Timeline Alternate Range"):
            swap()
    else:
        swap()

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None and hasattr(evaluation, "request"):
        evaluation.request()
    return {
        "ok": True,
        "kind": "timeline_alt_range_toggle",
        "active": target,
        "saved_range": tuple(current_range),
        "applied_range": tuple(state[target]),
    }


execute = toggle_alt_range
