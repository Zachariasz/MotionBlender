from pyfbsdk import (
    FBExtrapolationMode,
    FBFCurve,
    FBMessageBox,
    FBSystem,
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


def get_layer_indices(current_take):
    layer_indices = set()

    if not current_take:
        return layer_indices

    try:
        layer_indices.add(current_take.GetCurrentLayer())
    except Exception:
        pass

    try:
        for index in range(current_take.GetLayerCount()):
            layer = current_take.GetLayer(index)
            if layer and layer.IsSelected():
                layer_indices.add(index)
    except Exception:
        pass

    return layer_indices


def collect_scene_fcurves():
    system = FBSystem()
    scene = system.Scene
    layer_indices = get_layer_indices(system.CurrentTake)
    fcurves = set()

    # Direct scene scan catches FCurves already exposed in the scene.
    for component in scene.Components:
        if isinstance(component, FBFCurve):
            add_fcurve(fcurves, component)

    def scan_animation_node(animation_node):
        if not animation_node:
            return

        try:
            add_fcurve(fcurves, animation_node.FCurve)
        except Exception:
            pass

        # Current/selected animation layers can have their own FCurves.
        for layer_index in layer_indices:
            try:
                add_fcurve(fcurves, animation_node.GetFCurve(layer_index))
            except Exception:
                pass

        for child_node in animation_node.Nodes:
            scan_animation_node(child_node)

    # Deep property scan catches nested transform channels such as X/Y/Z.
    for component in scene.Components:
        for prop in component.PropertyList:
            if prop.IsAnimatable():
                scan_animation_node(prop.GetAnimationNode())

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

    for fcurve in collect_scene_fcurves():
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
