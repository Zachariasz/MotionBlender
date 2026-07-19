from pyfbsdk import FBMessageBox, FBModel, FBSystem
import traceback


TOOL_NAME = "Unhide All Objects"


def get_scene_models():
    return [
        component
        for component in FBSystem().Scene.Components
        if isinstance(component, FBModel)
    ]


def unhide_all_objects():
    models = get_scene_models()

    if len(models) == 0:
        FBMessageBox(TOOL_NAME, "No scene objects found to unhide.", "OK")
        return

    for model in models:
        model.Visibility = True

    FBSystem().Scene.Evaluate()
    print("Set visibility on for %d scene object(s)." % len(models))


def run_with_error_dialog():
    try:
        unhide_all_objects()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
