import json
import os
import tempfile
import time
import traceback

from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList, FBSystem


TOOL_NAME = "Copy Selected Pose"
CLIPBOARD_FILE = ".selected_pose_clipboard.json"
CLIPBOARD_VERSION = 1
IDENTITY_FIELDS = ["class", "full_name", "long_name", "name"]


def current_scripts_root():
    try:
        folder = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return ""

    if os.path.basename(folder).lower() == "custom":
        return os.path.dirname(folder)

    return folder


def is_protected_install_path(path):
    try:
        lowered = os.path.abspath(path).lower()
    except Exception:
        return False

    return "\\program files\\" in lowered or "/program files/" in lowered


def user_config_scripts_root():
    try:
        user_config_path = str(FBSystem().UserConfigPath)
    except Exception:
        user_config_path = ""

    if not user_config_path:
        return ""

    if os.path.basename(os.path.normpath(user_config_path)).lower() == "scripts":
        return user_config_path

    return os.path.join(user_config_path, "Scripts")


def fallback_scripts_roots():
    roots = []
    current_root = current_scripts_root()
    user_root = user_config_scripts_root()

    for root in [
        user_root,
        os.path.join(os.path.expanduser("~"), "OneDrive", "Documents", "MB", "2026", "config", "Scripts"),
        os.path.join(os.path.expanduser("~"), "Documents", "MB", "2026", "config", "Scripts"),
        current_root,
        os.path.join(tempfile.gettempdir(), "MotionBuilderPoseClipboard"),
    ]:
        if root and root not in roots and not is_protected_install_path(root):
            roots.append(root)

    return roots


def can_write_directory(path):
    test_path = ""
    try:
        if not os.path.isdir(path):
            os.makedirs(path)
        test_path = os.path.join(path, ".pose_clipboard_write_test.tmp")
        with open(test_path, "w", encoding="utf-8") as output_file:
            output_file.write("ok")
        os.remove(test_path)
        return True
    except Exception:
        try:
            if os.path.exists(test_path):
                os.remove(test_path)
        except Exception:
            pass
        return False


def clipboard_path():
    for root in fallback_scripts_roots():
        if can_write_directory(root):
            return os.path.join(root, CLIPBOARD_FILE)

    return os.path.join(tempfile.gettempdir(), CLIPBOARD_FILE)


def selected_models():
    models = FBModelList()
    try:
        FBGetSelectedModels(models, None, True, True)
    except TypeError:
        FBGetSelectedModels(models)

    return [models[index] for index in range(len(models))]


def class_name(item):
    try:
        return str(item.ClassName())
    except Exception:
        return type(item).__name__


def text_attr(item, attr_name):
    try:
        value = getattr(item, attr_name)
    except Exception:
        return ""

    if value is None:
        return ""

    try:
        return str(value)
    except Exception:
        return ""


def model_segment(model):
    return {
        "class": class_name(model),
        "name": text_attr(model, "Name"),
        "long_name": text_attr(model, "LongName"),
        "full_name": text_attr(model, "FullName"),
    }


def model_identity(model):
    path = []
    current = model
    guard = 0

    while current is not None and guard < 64:
        path.append(model_segment(current))
        guard += 1
        try:
            current = current.Parent
        except Exception:
            current = None

    path.reverse()
    return {"path": path}


def identity_key(identity):
    return json.dumps(normalized_identity(identity), sort_keys=True, separators=(",", ":"))


def normalized_identity(identity):
    normalized_path = []

    for segment in identity.get("path", []):
        normalized_path.append(
            dict(
                (field, str(segment.get(field, "")))
                for field in IDENTITY_FIELDS
            )
        )

    return {"path": normalized_path}


def model_label(model):
    name = text_attr(model, "LongName") or text_attr(model, "Name") or text_attr(model, "FullName")
    if not name:
        name = "<unnamed>"
    return "%s: %s" % (class_name(model), name)


def vector_to_list(value):
    return [float(value[0]), float(value[1]), float(value[2])]


def current_take_name():
    try:
        take = FBSystem().CurrentTake
        if take is not None:
            return str(take.Name)
    except Exception:
        pass
    return ""


def safe_write_json(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, indent=2, sort_keys=True)

    try:
        os.replace(temp_path, path)
    except AttributeError:
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)


def copy_selected_pose():
    models = selected_models()
    if not models:
        return

    entries = []
    seen = {}
    duplicate_labels = []

    for model in models:
        identity = model_identity(model)
        key = identity_key(identity)
        label = model_label(model)

        if key in seen:
            duplicate_labels.append(label)
            duplicate_labels.append(seen[key])
            continue

        seen[key] = label
        entries.append(
            {
                "key": key,
                "label": label,
                "class_name": class_name(model),
                "identity": identity,
                "translation": vector_to_list(model.Translation),
                "rotation": vector_to_list(model.Rotation),
                "scaling": vector_to_list(model.Scaling),
            }
        )

    if duplicate_labels:
        duplicate_text = "\n".join(sorted(set(duplicate_labels))[:8])
        raise ValueError(
            "Cannot copy pose because two or more selected objects have the same strict identity.\n\n%s"
            % duplicate_text
        )

    data = {
        "tool": TOOL_NAME,
        "version": CLIPBOARD_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "take": current_take_name(),
        "count": len(entries),
        "models": entries,
    }
    safe_write_json(clipboard_path(), data)
    print("%s: copied pose for %d selected model(s)." % (TOOL_NAME, len(entries)))


def run_with_error_dialog():
    try:
        copy_selected_pose()
    except ValueError as exc:
        FBMessageBox(TOOL_NAME, str(exc), "OK")
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")


if __name__ != "__codex_mobu_command__":
    run_with_error_dialog()
