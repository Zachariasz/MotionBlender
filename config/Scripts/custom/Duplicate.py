from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList
import traceback


def _model_key(model):
    try:
        return model.UniqueName
    except Exception:
        return repr(model)


def _has_selected_parent(model, selected_keys):
    parent = model.Parent

    while parent is not None:
        if _model_key(parent) in selected_keys:
            return True
        parent = parent.Parent

    return False


def _get_selected_top_models():
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)

    selected = [model for model in selected_models]
    selected_keys = set(_model_key(model) for model in selected)

    return [
        model
        for model in selected
        if not _has_selected_parent(model, selected_keys)
    ]


def duplicate_selected_models():
    selected = _get_selected_top_models()

    if not selected:
        FBMessageBox("Duplicate", "Select at least one object to duplicate.", "OK")
        return

    duplicates = []

    for model in selected:
        duplicate = model.Clone()
        if duplicate is None:
            raise RuntimeError("Could not duplicate: %s" % model.LongName)
        duplicates.append(duplicate)

    for model in selected:
        model.Selected = False

    for duplicate in duplicates:
        duplicate.Selected = True

    print("Duplicated %d selected object(s)." % len(duplicates))


def run_with_error_dialog():
    try:
        duplicate_selected_models()
    except Exception:
        FBMessageBox("Duplicate Error", traceback.format_exc(), "OK")


run_with_error_dialog()
