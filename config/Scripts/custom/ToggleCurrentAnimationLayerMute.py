from pyfbsdk import FBMessageBox, FBSystem
import traceback


TOOL_NAME = "Toggle Current Animation Layer Mute"


def get_target_animation_layers(take):
    """Return a list of (layer_index, FBAnimationLayer) for selected layers or the active layer."""
    if take is None:
        raise RuntimeError("There is no current take.")

    layer_count = int(take.GetLayerCount()) if hasattr(take, "GetLayerCount") else 0
    if layer_count <= 0:
        raise RuntimeError("The current take has no animation layers.")

    selected_layers = []
    for index in range(layer_count):
        layer = take.GetLayer(index)
        if layer is not None and getattr(layer, "Selected", False):
            selected_layers.append((index, layer))

    # If no layers are explicitly selected, fall back to the active layer
    if not selected_layers:
        active_index = int(take.GetCurrentLayer())
        layer = take.GetLayer(active_index)
        if layer is None:
            raise RuntimeError("The current take has no active animation layer.")
        selected_layers.append((active_index, layer))

    return selected_layers


def toggle_current_animation_layer_mute():
    """Toggle mute state for selected animation layers or the active layer."""
    system = FBSystem()
    take = system.CurrentTake
    if take is None:
        raise RuntimeError("There is no current take.")

    target_layers = get_target_animation_layers(take)

    all_muted = all(bool(layer.Mute) for _, layer in target_layers)
    new_mute_state = not all_muted

    for index, layer in target_layers:
        layer.Mute = new_mute_state
        state = "muted" if new_mute_state else "unmuted"
        print(
            "Animation layer '{0}' (index {1}) is now {2}.".format(
                layer.Name, index, state
            )
        )

    system.Scene.Evaluate()


def run_with_error_dialog():
    try:
        toggle_current_animation_layer_mute()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
