"""Qt editor for scene-persistent FBX export settings."""

from __future__ import absolute_import

import os

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from .fbx import (
    ExportSettings,
    iter_model_hierarchy,
    model_long_name,
    read_settings,
    write_settings,
)


def _qt_value(owner, name):
    value = getattr(owner, name, None)
    if value is not None:
        return value
    for scoped_name in ("CheckState", "ItemDataRole", "ItemFlag"):
        scoped = getattr(owner, scoped_name, None)
        if scoped is not None and hasattr(scoped, name):
            return getattr(scoped, name)
    raise AttributeError(name)


def _widget_enum(owner, scoped_name, value_name):
    value = getattr(owner, value_name, None)
    if value is not None:
        return value
    return getattr(getattr(owner, scoped_name), value_name)


CHECKED = _qt_value(QtCore.Qt, "Checked")
UNCHECKED = _qt_value(QtCore.Qt, "Unchecked")
USER_ROLE = _qt_value(QtCore.Qt, "UserRole")
ITEM_IS_USER_CHECKABLE = _qt_value(QtCore.Qt, "ItemIsUserCheckable")
DIALOG_SAVE = _widget_enum(
    QtWidgets.QDialogButtonBox,
    "StandardButton",
    "Save",
)
DIALOG_CANCEL = _widget_enum(
    QtWidgets.QDialogButtonBox,
    "StandardButton",
    "Cancel",
)


class ExportSettingsDialog(QtWidgets.QDialog):
    def __init__(self, system, application, sdk, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.system = system
        self.application = application
        self.sdk = sdk
        self.setWindowTitle("FBX Export Settings")
        self.resize(520, 560)

        settings = read_settings(system, application, sdk)
        outer = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        outer.addLayout(form)

        folder_row = QtWidgets.QWidget(self)
        folder_layout = QtWidgets.QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(4)
        self.folder_edit = QtWidgets.QLineEdit(settings.folder, folder_row)
        browse = QtWidgets.QPushButton("Browse...", folder_row)
        browse.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(browse)
        form.addRow("Export folder", folder_row)

        self.file_name_edit = QtWidgets.QLineEdit(settings.file_name, self)
        form.addRow("File name", self.file_name_edit)

        self.one_take_check = QtWidgets.QCheckBox(
            "Save one take per file",
            self,
        )
        self.one_take_check.setChecked(settings.one_take_per_file)
        form.addRow("", self.one_take_check)

        label = QtWidgets.QLabel("Hierarchy objects to export", self)
        outer.addWidget(label)
        self.tree = QtWidgets.QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        outer.addWidget(self.tree, 1)
        self._populate_tree(set(settings.model_names))

        note = QtWidgets.QLabel(
            "These settings are custom properties on the ExportPreset Null. "
            "The Null is included in every export so the settings travel in "
            "the exported FBX. Save the source FBX to keep them in the "
            "working scene too.",
            self,
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        buttons = QtWidgets.QDialogButtonBox(
            DIALOG_SAVE | DIALOG_CANCEL,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _populate_tree(self, selected_names):
        parents = {}
        for model, depth in iter_model_hierarchy(self.system.Scene):
            parent_item = parents.get(depth - 1)
            item = QtWidgets.QTreeWidgetItem(
                parent_item if parent_item is not None else self.tree,
                (
                    str(getattr(model, "Name", "") or model_long_name(model)),
                ),
            )
            item.setData(0, USER_ROLE, model_long_name(model))
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)
            item.setCheckState(
                0,
                CHECKED
                if model_long_name(model) in selected_names
                else UNCHECKED,
            )
            parents[depth] = item
            for stale_depth in tuple(
                key for key in parents if key > depth
            ):
                del parents[stale_depth]
        self.tree.expandAll()

    def _browse_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select FBX export folder",
            self.folder_edit.text(),
        )
        if folder:
            self.folder_edit.setText(str(folder))

    def _checked_model_names(self):
        names = []
        pending = [
            self.tree.topLevelItem(index)
            for index in reversed(range(self.tree.topLevelItemCount()))
        ]
        while pending:
            item = pending.pop()
            if item.checkState(0) == CHECKED:
                names.append(str(item.data(0, USER_ROLE) or ""))
            pending.extend(
                item.child(index)
                for index in reversed(range(item.childCount()))
            )
        return tuple(name for name in names if name)

    def _save(self):
        folder = os.path.abspath(
            str(self.folder_edit.text() or "").strip()
        )
        file_name = str(self.file_name_edit.text() or "").strip()
        model_names = self._checked_model_names()
        if not folder:
            QtWidgets.QMessageBox.warning(
                self,
                self.windowTitle(),
                "Choose an export folder.",
            )
            return
        if not os.path.isdir(folder):
            answer = QtWidgets.QMessageBox.question(
                self,
                self.windowTitle(),
                "The folder does not exist. Create it?\n\n" + folder,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
            try:
                os.makedirs(folder)
            except OSError as error:
                QtWidgets.QMessageBox.critical(
                    self,
                    self.windowTitle(),
                    "Could not create the folder.\n\n" + str(error),
                )
                return
        if not file_name:
            QtWidgets.QMessageBox.warning(
                self,
                self.windowTitle(),
                "Enter a file name.",
            )
            return
        if not model_names:
            QtWidgets.QMessageBox.warning(
                self,
                self.windowTitle(),
                "Toggle at least one hierarchy object for export.",
            )
            return
        write_settings(
            self.system,
            self.sdk,
            ExportSettings(
                folder=folder,
                file_name=file_name,
                one_take_per_file=self.one_take_check.isChecked(),
                model_names=model_names,
            ),
        )
        self.accept()


def show_export_settings(system, application, sdk, parent=None):
    dialog = ExportSettingsDialog(
        system,
        application,
        sdk,
        parent=parent,
    )
    exec_method = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return exec_method()
