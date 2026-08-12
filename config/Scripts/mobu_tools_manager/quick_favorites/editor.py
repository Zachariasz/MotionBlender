"""Manager-owned editor for ordered Quick Favorites entries."""

from __future__ import absolute_import

import copy

from ..catalog import FEATURES
from .settings import (
    CONTEXT_FCURVES,
    CONTEXT_OTHER,
    CONTEXT_TIMELINE,
    CONTEXT_VIEWER,
    DEFAULT_CONTEXTS,
    validate_quick_favorites_settings,
)

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


CONTEXT_LABELS = (
    ("3D Viewer", CONTEXT_VIEWER),
    ("FCurves", CONTEXT_FCURVES),
    ("Timeline", CONTEXT_TIMELINE),
    ("General / Other", CONTEXT_OTHER),
)


def _enum(container, nested_name, name):
    nested = getattr(container, nested_name, container)
    return getattr(nested, name)


class QuickFavoritesEditorDialog(QtWidgets.QDialog):
    def __init__(self, manager, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.manager = manager
        self.setWindowTitle("Configure Quick Favorites")
        self.setObjectName("motionbuilder_quick_favorites_editor")
        self.resize(720, 520)
        self.setModal(False)
        self.setAttribute(
            _enum(QtCore.Qt, "WidgetAttribute", "WA_DeleteOnClose"),
            True,
        )
        settings = validate_quick_favorites_settings(
            manager.quick_favorites_settings()
        )
        self._contexts = copy.deepcopy(settings["contexts"])
        self._current_context = CONTEXT_VIEWER
        self._building = False
        self._build_ui()
        self._load_context(CONTEXT_VIEWER)

    @property
    def user_role(self):
        return _enum(QtCore.Qt, "ItemDataRole", "UserRole")

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Each context has its own ordered list. Managed features are "
            "stored by stable feature ID; MotionBuilder actions use their "
            "keyboard-map action name."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        context_row = QtWidgets.QHBoxLayout()
        context_row.addWidget(QtWidgets.QLabel("Context"))
        self.context_combo = QtWidgets.QComboBox()
        for label, context_name in CONTEXT_LABELS:
            self.context_combo.addItem(label, context_name)
        context_row.addWidget(self.context_combo, 1)
        self.reset_context_button = QtWidgets.QPushButton("Reset Context")
        context_row.addWidget(self.reset_context_button)
        layout.addLayout(context_row)

        self.entries = QtWidgets.QListWidget()
        self.entries.setSelectionMode(
            _enum(
                QtWidgets.QAbstractItemView,
                "SelectionMode",
                "SingleSelection",
            )
        )
        layout.addWidget(self.entries, 1)

        add_row = QtWidgets.QHBoxLayout()
        self.add_feature_button = QtWidgets.QPushButton("Add Managed Feature")
        self.add_action_button = QtWidgets.QPushButton("Add Native Action")
        self.add_separator_button = QtWidgets.QPushButton("Add Separator")
        self.edit_button = QtWidgets.QPushButton("Edit")
        self.remove_button = QtWidgets.QPushButton("Remove")
        for button in (
            self.add_feature_button,
            self.add_action_button,
            self.add_separator_button,
            self.edit_button,
            self.remove_button,
        ):
            add_row.addWidget(button)
        layout.addLayout(add_row)

        order_row = QtWidgets.QHBoxLayout()
        self.up_button = QtWidgets.QPushButton("Move Up")
        self.down_button = QtWidgets.QPushButton("Move Down")
        order_row.addWidget(self.up_button)
        order_row.addWidget(self.down_button)
        order_row.addStretch(1)
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.close_button = QtWidgets.QPushButton("Close")
        order_row.addWidget(self.apply_button)
        order_row.addWidget(self.close_button)
        layout.addLayout(order_row)

        self.context_combo.currentIndexChanged.connect(
            self._context_changed
        )
        self.entries.itemSelectionChanged.connect(self._update_buttons)
        self.entries.itemDoubleClicked.connect(lambda _item: self._edit())
        self.add_feature_button.clicked.connect(self._add_feature)
        self.add_action_button.clicked.connect(self._add_native_action)
        self.add_separator_button.clicked.connect(self._add_separator)
        self.edit_button.clicked.connect(self._edit)
        self.remove_button.clicked.connect(self._remove)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        self.reset_context_button.clicked.connect(self._reset_context)
        self.apply_button.clicked.connect(self._apply)
        self.close_button.clicked.connect(self.close)

    def _context_from_combo(self):
        value = self.context_combo.currentData()
        return str(value or CONTEXT_VIEWER)

    def _context_changed(self, _index):
        if self._building:
            return
        self._save_visible_context()
        self._load_context(self._context_from_combo())

    def _save_visible_context(self):
        entries = []
        for index in range(self.entries.count()):
            entry = self.entries.item(index).data(self.user_role)
            if isinstance(entry, dict):
                entries.append(dict(entry))
        self._contexts[self._current_context] = entries

    def _load_context(self, context_name):
        self._building = True
        try:
            self._current_context = context_name
            self.entries.clear()
            for entry in self._contexts.get(context_name, ()):
                self._append_entry(entry)
        finally:
            self._building = False
        self._update_buttons()

    def _append_entry(self, entry, row=None):
        entry = dict(entry)
        if entry["kind"] == "separator":
            text = "---------------- separator ----------------"
        elif entry["kind"] == "feature":
            text = "%s    [feature: %s]" % (
                entry["label"],
                entry["target"],
            )
        else:
            text = "%s    [action: %s]" % (
                entry["label"],
                entry["target"],
            )
        item = QtWidgets.QListWidgetItem(text)
        item.setData(self.user_role, entry)
        if row is None:
            self.entries.addItem(item)
        else:
            self.entries.insertItem(row, item)
        return item

    def _insert_entry(self, entry):
        row = self.entries.currentRow()
        if row < 0:
            row = self.entries.count()
        else:
            row += 1
        item = self._append_entry(entry, row)
        self.entries.setCurrentItem(item)

    def _feature_choice(self, initial_target=""):
        candidates = tuple(
            feature
            for feature in FEATURES
            if feature.id != "ui.quick_favorites"
        )
        labels = [
            "%s  [%s]" % (feature.name, feature.id)
            for feature in candidates
        ]
        current = next(
            (
                index
                for index, feature in enumerate(candidates)
                if feature.id == initial_target
            ),
            0,
        )
        selected, accepted = QtWidgets.QInputDialog.getItem(
            self,
            "Managed Feature",
            "Feature:",
            labels,
            current,
            False,
        )
        if not accepted:
            return None
        return candidates[labels.index(str(selected))]

    def _label_input(self, initial):
        value, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Favorite Label",
            "Menu label:",
            QtWidgets.QLineEdit.Normal,
            str(initial),
        )
        if not accepted:
            return None
        value = str(value).strip()
        if not value:
            QtWidgets.QMessageBox.warning(
                self,
                "Quick Favorites",
                "The menu label cannot be empty.",
            )
            return None
        return value

    def _action_input(self, initial="action."):
        value, accepted = QtWidgets.QInputDialog.getText(
            self,
            "MotionBuilder Native Action",
            "Keyboard-map action name:",
            QtWidgets.QLineEdit.Normal,
            str(initial),
        )
        if not accepted:
            return None
        value = str(value).strip()
        if not value.startswith("action."):
            QtWidgets.QMessageBox.warning(
                self,
                "Quick Favorites",
                "A native action name must begin with 'action.'.",
            )
            return None
        return value

    def _add_feature(self):
        feature = self._feature_choice()
        if feature is None:
            return
        label = self._label_input(feature.name)
        if label is not None:
            self._insert_entry(
                {"kind": "feature", "label": label, "target": feature.id}
            )

    def _add_native_action(self):
        target = self._action_input()
        if target is None:
            return
        default_label = target.rsplit(".", 1)[-1].replace("_", " ").title()
        label = self._label_input(default_label)
        if label is not None:
            self._insert_entry(
                {
                    "kind": "native_action",
                    "label": label,
                    "target": target,
                }
            )

    def _add_separator(self):
        self._insert_entry({"kind": "separator"})

    def _selected_entry(self):
        item = self.entries.currentItem()
        if item is None:
            return None, None
        return item, dict(item.data(self.user_role))

    def _edit(self):
        item, entry = self._selected_entry()
        if item is None or entry["kind"] == "separator":
            return
        if entry["kind"] == "feature":
            feature = self._feature_choice(entry["target"])
            if feature is None:
                return
            target = feature.id
            default_label = entry["label"]
        else:
            target = self._action_input(entry["target"])
            if target is None:
                return
            default_label = entry["label"]
        label = self._label_input(default_label)
        if label is None:
            return
        row = self.entries.row(item)
        self.entries.takeItem(row)
        updated = {
            "kind": entry["kind"],
            "label": label,
            "target": target,
        }
        self.entries.setCurrentItem(self._append_entry(updated, row))

    def _remove(self):
        row = self.entries.currentRow()
        if row >= 0:
            self.entries.takeItem(row)
            if self.entries.count():
                self.entries.setCurrentRow(
                    min(row, self.entries.count() - 1)
                )

    def _move(self, offset):
        row = self.entries.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.entries.count():
            return
        item = self.entries.takeItem(row)
        self.entries.insertItem(target, item)
        self.entries.setCurrentItem(item)

    def _reset_context(self):
        self._contexts[self._current_context] = copy.deepcopy(
            DEFAULT_CONTEXTS[self._current_context]
        )
        self._load_context(self._current_context)

    def _apply(self):
        self._save_visible_context()
        try:
            validated = self.manager.update_quick_favorites_settings(
                {"contexts": self._contexts}
            )
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self,
                "Quick Favorites",
                str(error),
            )
            return
        self._contexts = copy.deepcopy(validated["contexts"])
        self._load_context(self._current_context)

    def _update_buttons(self):
        row = self.entries.currentRow()
        has_selection = row >= 0
        _item, entry = self._selected_entry()
        editable = bool(
            has_selection
            and entry is not None
            and entry.get("kind") != "separator"
        )
        self.edit_button.setEnabled(editable)
        self.remove_button.setEnabled(has_selection)
        self.up_button.setEnabled(has_selection and row > 0)
        self.down_button.setEnabled(
            has_selection and row < self.entries.count() - 1
        )
