from pyfbsdk import FBSystem, FBFCurve


VALUE_OFFSET = -1.0


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
    current_take = system.CurrentTake
    layer_indices = get_layer_indices(current_take)
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


def get_key_value(fcurve, index):
    try:
        return fcurve.KeyGetValue(index)
    except Exception:
        return fcurve.Keys[index].Value


def set_key_value(fcurve, index, value):
    try:
        fcurve.KeySetValue(index, value)
    except Exception:
        fcurve.Keys[index].Value = value


def move_selected_keys_value_up():
    system = FBSystem()
    scanned_curve_count = 0
    moved_count = 0
    affected_curve_count = 0

    for fcurve in collect_scene_fcurves():
        if not fcurve:
            continue

        scanned_curve_count += 1
        selected_indices = [
            index for index in range(len(fcurve.Keys))
            if key_is_selected(fcurve, index)
        ]

        if not selected_indices:
            continue

        affected_curve_count += 1

        for index in selected_indices:
            set_key_value(fcurve, index, get_key_value(fcurve, index) + VALUE_OFFSET)
            moved_count += 1

    if moved_count:
        system.Scene.Evaluate()
        print(
            "Success: moved {0} selected key(s) up by {1:g} value unit(s) on {2} FCurve(s).".format(
                moved_count,
                VALUE_OFFSET,
                affected_curve_count,
            )
        )
    else:
        print(
            "Failure: no selected FCurve keys found. Scanned {0} FCurve(s).".format(
                scanned_curve_count,
            )
        )


move_selected_keys_value_up()
