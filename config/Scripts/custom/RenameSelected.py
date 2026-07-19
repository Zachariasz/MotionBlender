import traceback

from pyfbsdk import FBGetSelectedModels, FBMessageBox, FBModelList, FBSystem

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


IGNORED_SELECTED_CLASSES = set(
    [
        "FBAnimationLayer",
    ]
)


class RenameTarget(object):
    def __init__(self, label, item, kind, owner=None):
        self.label = label
        self.item = item
        self.kind = kind
        self.owner = owner

    def current_name(self):
        return get_item_name(self.item)

    def rename(self, new_name):
        set_item_name(self.item, new_name)


class RenameDialog(QtWidgets.QDialog):
    def __init__(self, targets, parent=None):
        QtWidgets.QDialog.__init__(self, parent)

        self.targets = targets
        self.setWindowTitle("Rename Selected")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.target_combo = None
        if len(targets) > 1:
            self.target_combo = QtWidgets.QComboBox(self)
            for target in targets:
                self.target_combo.addItem(target.label)
            self.target_combo.currentIndexChanged.connect(self.on_target_changed)
            layout.addWidget(self.target_combo)

        self.name_edit = QtWidgets.QLineEdit(self)
        self.name_edit.setMinimumWidth(300)
        layout.addWidget(self.name_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.on_target_changed(0)
        QtCore.QTimer.singleShot(0, self.select_name_text)

    def selected_target(self):
        if self.target_combo is None:
            return self.targets[0]

        return self.targets[self.target_combo.currentIndex()]

    def on_target_changed(self, index):
        del index
        self.name_edit.setText(self.selected_target().current_name())
        self.select_name_text()

    def select_name_text(self):
        self.name_edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.name_edit.selectAll()

    def new_name(self):
        return self.name_edit.text().strip()


def class_name(item):
    try:
        return item.ClassName()
    except Exception:
        return type(item).__name__


def get_item_name(item):
    try:
        return str(item.Name)
    except Exception:
        pass

    try:
        return str(item.GetName())
    except Exception:
        return ""


def set_item_name(item, new_name):
    if hasattr(item, "SetName"):
        try:
            item.SetName(new_name)
            return
        except Exception:
            pass

    item.Name = new_name


def is_user_property(prop):
    try:
        value = prop.IsUserProperty
        if callable(value):
            value = value()
        return bool(value)
    except Exception:
        return False


def has_editable_name(item):
    name = get_item_name(item)
    if not name:
        return False

    if class_name(item) in IGNORED_SELECTED_CLASSES:
        return False

    try:
        if hasattr(item, "IsReadOnly") and item.IsReadOnly():
            return False
    except Exception:
        pass

    return hasattr(item, "Name") or hasattr(item, "SetName")


def item_key(item):
    try:
        return (class_name(item), str(item.FullName))
    except Exception:
        pass

    try:
        return (class_name(item), str(item.LongName))
    except Exception:
        pass

    return (class_name(item), get_item_name(item), id(item))


def target_label(prefix, item, owner=None):
    name = get_item_name(item)
    if owner is not None:
        return "%s: %s / %s" % (prefix, get_item_name(owner), name)

    item_class = class_name(item)
    if prefix:
        return "%s: %s" % (prefix, name)

    return "%s: %s" % (item_class, name)


def add_unique_target(targets, seen, target):
    key = (target.kind, item_key(target.item))
    if target.owner is not None:
        key = key + (item_key(target.owner),)

    if key in seen:
        return

    targets.append(target)
    seen.add(key)


def get_selected_models():
    models = FBModelList()
    FBGetSelectedModels(models, None, True, True)
    return [models[index] for index in range(len(models))]


def iter_scene_collection(scene, collection_name):
    try:
        collection = getattr(scene, collection_name)
    except Exception:
        return

    for item in collection:
        yield item


def is_selected(item):
    try:
        return bool(item.Selected)
    except Exception:
        return False


def selected_component_targets(selected_model_keys):
    scene = FBSystem().Scene
    targets = []
    seen = set()
    collection_names = [
        "Components",
        "Constraints",
        "Poses",
        "CharacterPoses",
        "ObjectPoses",
    ]

    for collection_name in collection_names:
        for item in iter_scene_collection(scene, collection_name):
            if not is_selected(item):
                continue

            key = item_key(item)
            if key in selected_model_keys:
                continue

            if not has_editable_name(item):
                continue

            add_unique_target(
                targets,
                seen,
                RenameTarget(target_label("", item), item, "component"),
            )

    return targets


def add_user_property_targets(targets, seen, owner):
    try:
        property_list = owner.PropertyList
    except Exception:
        return

    for prop in property_list:
        if not is_user_property(prop):
            continue
        if not has_editable_name(prop):
            continue

        add_unique_target(
            targets,
            seen,
            RenameTarget(target_label("Custom property", prop, owner), prop, "property", owner),
        )


def find_rename_targets():
    targets = []
    seen = set()
    selected_models = get_selected_models()

    if len(selected_models) > 1:
        raise ValueError("Select only one item to rename.")

    selected_model_keys = set(item_key(model) for model in selected_models)
    component_targets = selected_component_targets(selected_model_keys)

    if len(selected_models) == 0 and len(component_targets) > 1:
        raise ValueError("Select only one editable item to rename.")

    for target in component_targets:
        add_unique_target(targets, seen, target)

    if len(selected_models) == 1:
        model = selected_models[0]
        add_unique_target(
            targets,
            seen,
            RenameTarget(target_label("Model", model), model, "model"),
        )
        add_user_property_targets(targets, seen, model)

    if len(selected_models) == 0 and len(targets) == 1:
        add_user_property_targets(targets, seen, targets[0].item)

    return targets


def motionbuilder_main_window():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    for widget in app.topLevelWidgets():
        try:
            if isinstance(widget, QtWidgets.QMainWindow) and widget.isVisible():
                return widget
        except Exception:
            pass

    return None


def rename_selected_object():
    targets = find_rename_targets()
    if not targets:
        FBMessageBox(
            "Rename Selected",
            "Select one editable item, or select an object with a custom property.",
            "OK",
        )
        return

    dialog = RenameDialog(targets, motionbuilder_main_window())
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return

    new_name = dialog.new_name()
    if not new_name:
        FBMessageBox("Rename Selected", "Name cannot be empty.", "OK")
        return

    target = dialog.selected_target()
    old_name = target.current_name()
    if new_name == old_name:
        return

    target.rename(new_name)
    FBSystem().Scene.Evaluate()


def run_with_error_dialog():
    try:
        rename_selected_object()
    except ValueError as exc:
        FBMessageBox("Rename Selected", str(exc), "OK")
    except Exception:
        FBMessageBox("Rename Selected Error", traceback.format_exc()[-1800:], "OK")


if __name__ != "__codex_mobu_command__":
    run_with_error_dialog()
