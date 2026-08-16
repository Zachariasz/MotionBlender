from pyfbsdk import (
    FBExtrapolationMode,
    FBFCurveEditorUtility,
    FBMessageBox,
    FBSystem,
)

from mobu_tools_manager.fcurves.discovery import (
    _curve_for_node,
    focused_animation_nodes,
)


INFINITE_REPEAT_COUNT = 0xFFFFFFFF
INFINITE_REPEAT_COUNT_SIGNED = -1
REPEAT_MODE = FBExtrapolationMode.kFCurveExtrapolationRepetition


def add_fcurve(fcurves, fcurve):
    if not fcurve:
        return

    try:
        if len(fcurve.Keys) == 0:
            return
    except Exception:
        return

    fcurves.add(fcurve)


def collect_visible_fcurves():
    system = FBSystem()
    fcurves = set()
    try:
        layer_index = int(system.CurrentTake.GetCurrentLayer())
    except Exception:
        layer_index = None
    properties = []
    try:
        FBFCurveEditorUtility().GetProperties(properties, True)
    except Exception:
        return fcurves
    for prop in properties:
        for node in focused_animation_nodes(prop):
            add_fcurve(fcurves, _curve_for_node(node, layer_index))

    return fcurves


def key_is_selected(fcurve, index):
    try:
        return fcurve.KeyGetSelected(index)
    except Exception:
        return fcurve.Keys[index].Selected


def fcurve_has_selected_key(fcurve):
    for index in range(len(fcurve.Keys)):
        if key_is_selected(fcurve, index):
            return True

    return False


def fcurve_is_selected(fcurve):
    try:
        if fcurve.Selected:
            return True
    except Exception:
        pass

    return fcurve_has_selected_key(fcurve)


def set_infinite_extrapolation_count(set_count):
    try:
        set_count(INFINITE_REPEAT_COUNT)
    except Exception:
        set_count(INFINITE_REPEAT_COUNT_SIGNED)


def set_fcurve_infinite_repetition(fcurve):
    fcurve.SetPreExtrapolationMode(REPEAT_MODE)
    fcurve.SetPostExtrapolationMode(REPEAT_MODE)
    set_infinite_extrapolation_count(fcurve.SetPreExtrapolationCount)
    set_infinite_extrapolation_count(fcurve.SetPostExtrapolationCount)


def set_selected_fcurves_infinite_repetition():
    system = FBSystem()
    scanned_curve_count = 0
    changed_count = 0
    failed_count = 0

    for fcurve in collect_visible_fcurves():
        scanned_curve_count += 1

        if not fcurve_is_selected(fcurve):
            continue

        try:
            set_fcurve_infinite_repetition(fcurve)
            changed_count += 1
        except Exception:
            failed_count += 1

    if changed_count:
        system.Scene.Evaluate()
        message = "Set infinite pre/post repetition on {0} FCurve(s).".format(
            changed_count
        )
        if failed_count:
            message += "\n{0} FCurve(s) could not be changed.".format(failed_count)
        print("Success: " + message.replace("\n", " "))
    else:
        message = "No selected FCurves found. Scanned {0} FCurve(s).".format(
            scanned_curve_count
        )
        FBMessageBox("Infinite FCurve Repetition", message, "OK")
        print("Failure: " + message)


set_selected_fcurves_infinite_repetition()
