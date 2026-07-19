import json
import os
import tempfile
import traceback

from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList, FBSystem, FBVector3d


TOOL_NAME = "Paste Selected Pose"
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
    existing_paths = [os.path.join(root, CLIPBOARD_FILE) for root in fallback_scripts_roots()]
    for path in existing_paths:
        if os.path.isfile(path):
            return path

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


def vector_from_list(values):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("Clipboard contains an invalid transform vector.")

    return FBVector3d(float(values[0]), float(values[1]), float(values[2]))


def read_clipboard():
    path = clipboard_path()
    if not os.path.isfile(path):
        raise ValueError("No copied pose found. Run CopySelectedPose.py first.")

    with open(path, "r", encoding="utf-8-sig") as input_file:
        data = json.load(input_file)

    if data.get("version") != CLIPBOARD_VERSION:
        raise ValueError("Copied pose data uses an unsupported version.")

    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Copied pose data is empty or invalid.")

    return data


def entry_key(entry):
    identity = entry.get("identity")
    if not isinstance(identity, dict):
        key = entry.get("key")
        if key:
            return str(key)
        raise ValueError("Copied pose data is missing strict identity data.")

    return identity_key(identity)


def keyed_clipboard_entries(entries):
    keyed = {}
    duplicates = []

    for entry in entries:
        key = entry_key(entry)
        label = str(entry.get("label", "<unknown>"))
        if key in keyed:
            duplicates.append(label)
            duplicates.append(str(keyed[key].get("label", "<unknown>")))
            continue
        keyed[key] = entry

    if duplicates:
        duplicate_text = "\n".join(sorted(set(duplicates))[:8])
        raise ValueError(
            "Copied pose data contains duplicate strict identities and cannot be pasted safely.\n\n%s"
            % duplicate_text
        )

    return keyed


def keyed_selected_models(models):
    keyed = {}
    duplicates = []

    for model in models:
        key = identity_key(model_identity(model))
        label = model_label(model)
        if key in keyed:
            duplicates.append(label)
            duplicates.append(model_label(keyed[key]))
            continue
        keyed[key] = model

    if duplicates:
        duplicate_text = "\n".join(sorted(set(duplicates))[:8])
        raise ValueError(
            "Selected objects contain duplicate strict identities and cannot be matched safely.\n\n%s"
            % duplicate_text
        )

    return keyed


def label_for_entry(entry):
    return str(entry.get("label", "<unknown>"))


def mismatch_message(copied_by_key, selected_by_key):
    copied_keys = set(copied_by_key.keys())
    selected_keys = set(selected_by_key.keys())
    missing = copied_keys - selected_keys
    extra = selected_keys - copied_keys

    lines = [
        "Selected objects do not exactly match the copied pose.",
        "",
        "Copied count: %d" % len(copied_keys),
        "Selected count: %d" % len(selected_keys),
    ]

    if missing:
        lines.extend(["", "Missing from current selection:"])
        for key in sorted(missing)[:8]:
            lines.append("- " + label_for_entry(copied_by_key[key]))
        if len(missing) > 8:
            lines.append("- ...")

    if extra:
        lines.extend(["", "Extra selected now:"])
        for key in sorted(extra)[:8]:
            lines.append("- " + model_label(selected_by_key[key]))
        if len(extra) > 8:
            lines.append("- ...")

    return "\n".join(lines)


def paste_transform(model, entry):
    model.Translation = vector_from_list(entry.get("translation"))
    model.Rotation = vector_from_list(entry.get("rotation"))
    model.Scaling = vector_from_list(entry.get("scaling"))


def paste_selected_pose():
    models = selected_models()
    if not models:
        return

    data = read_clipboard()
    copied_by_key = keyed_clipboard_entries(data["models"])
    selected_by_key = keyed_selected_models(models)

    if set(copied_by_key.keys()) != set(selected_by_key.keys()):
        raise ValueError(mismatch_message(copied_by_key, selected_by_key))

    for key, entry in copied_by_key.items():
        paste_transform(selected_by_key[key], entry)

    FBSystem().Scene.Evaluate()
    print("%s: pasted pose onto %d selected model(s)." % (TOOL_NAME, len(copied_by_key)))


def run_with_error_dialog():
    try:
        paste_selected_pose()
    except ValueError as exc:
        FBMessageBox(TOOL_NAME, str(exc), "OK")
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-1800:], "OK")


if __name__ != "__codex_mobu_command__":
    run_with_error_dialog()
