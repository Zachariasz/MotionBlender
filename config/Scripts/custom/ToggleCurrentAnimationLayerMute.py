from pyfbsdk import FBMessageBox, FBSystem
import traceback


TOOL_NAME = "Toggle Current Animation Layer Mute"


def get_current_animation_layer():
    system = FBSystem()
    take = system.CurrentTake

    if take is None:
        raise RuntimeError("There is no current take.")

    layer_index = int(take.GetCurrentLayer())
    layer = take.GetLayer(layer_index)
    if layer is None:
        raise RuntimeError("The current take has no active animation layer.")

    return system, layer_index, layer


def toggle_current_animation_layer_mute():
    system, layer_index, layer = get_current_animation_layer()

    was_muted = bool(layer.Mute)
    layer.Mute = not was_muted
    system.Scene.Evaluate()

    state = "muted" if layer.Mute else "unmuted"
    print(
        "Animation layer '{0}' (index {1}) is now {2}.".format(
            layer.Name, layer_index, state
        )
    )


def run_with_error_dialog():
    try:
        toggle_current_animation_layer_mute()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
