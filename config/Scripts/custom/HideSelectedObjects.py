from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList
import traceback


TOOL_NAME = "Hide Selected Objects"


def hide_selected_objects():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)

    if len(selected_models) == 0:
        FBMessageBox(TOOL_NAME, "Select at least one object to hide.", "OK")
        return

    for model in selected_models:
        model.Visibility = False

    print("Set visibility off for %d selected object(s)." % len(selected_models))


def run_with_error_dialog():
    try:
        hide_selected_objects()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


run_with_error_dialog()
