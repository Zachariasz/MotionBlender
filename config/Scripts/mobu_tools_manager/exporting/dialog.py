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
    for scoped_name in (
        "CheckState",
        "ItemDataRole",
        "ItemFlag",
        "Key",
        "MouseButton",
        "ContextMenuPolicy",
        "SelectionMode",
        "ViewItemFeature",
        "SubElement",
    ):
        scoped = getattr(owner, scoped_name, None)
        if scoped is not None and hasattr(scoped, name):
            return getattr(scoped, name)
    for attr in dir(owner):
        if attr.startswith("_"):
            continue
        try:
            scoped = getattr(owner, attr, None)
            if scoped is not None and hasattr(scoped, name):
                return getattr(scoped, name)
        except Exception:
            pass
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
KEY_SPACE = _qt_value(QtCore.Qt, "Key_Space")
LEFT_BUTTON = _qt_value(QtCore.Qt, "LeftButton")
EXTENDED_SELECTION = _qt_value(QtWidgets.QAbstractItemView, "ExtendedSelection")
CUSTOM_CONTEXT_MENU = _qt_value(QtCore.Qt, "CustomContextMenu")
HAS_CHECK_INDICATOR = _qt_value(
    QtWidgets.QStyleOptionViewItem, "HasCheckIndicator"
)
CHECK_INDICATOR_SUB_ELEMENT = _qt_value(
    QtWidgets.QStyle, "SE_ItemViewItemCheckIndicator"
)
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


class ExportHierarchyTree(QtWidgets.QTreeWidget):
    """Tree widget supporting multi-selection and batch check-state toggling."""

    def __init__(self, parent=None):
        QtWidgets.QTreeWidget.__init__(self, parent)
        self.setSelectionMode(EXTENDED_SELECTION)

    def keyPressEvent(self, event):
        key = event.key()
        if hasattr(key, "value"):
            key = key.value
        expected_key = KEY_SPACE
        if hasattr(expected_key, "value"):
            expected_key = expected_key.value
        if key == expected_key:
            selected = self.selectedItems()
            if not selected:
                curr = self.currentItem()
                selected = [curr] if curr is not None else []
            if selected:
                new_state = (
                    UNCHECKED
                    if all(item.checkState(0) == CHECKED for item in selected)
                    else CHECKED
                )
                for item in selected:
                    item.setCheckState(0, new_state)
                event.accept()
                return
        QtWidgets.QTreeWidget.keyPressEvent(self, event)

    def mousePressEvent(self, event):
        try:
            button = event.button()
            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            item = self.itemAt(pos)
            if button == LEFT_BUTTON and item is not None:
                index = self.indexAt(pos)
                opt = QtWidgets.QStyleOptionViewItem()
                opt.initFrom(self)
                opt.rect = self.visualRect(index)
                opt.features |= HAS_CHECK_INDICATOR
                check_rect = self.style().subElementRect(
                    CHECK_INDICATOR_SUB_ELEMENT,
                    opt,
                    self,
                )
                if check_rect.contains(pos):
                    selected = self.selectedItems()
                    if item in selected and len(selected) > 1:
                        new_state = (
                            UNCHECKED
                            if item.checkState(0) == CHECKED
                            else CHECKED
                        )
                        for sel_item in selected:
                            sel_item.setCheckState(0, new_state)
                        event.accept()
                        return
        except Exception:
            pass
        QtWidgets.QTreeWidget.mousePressEvent(self, event)


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

        tree_header = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Hierarchy objects to export", self)
        tree_header.addWidget(label)
        tree_header.addStretch(1)

        self.check_selected_btn = QtWidgets.QPushButton(
            "Check Selected",
            self,
        )
        self.check_selected_btn.setToolTip(
            "Enable all selected hierarchy objects (Space)"
        )
        self.check_selected_btn.clicked.connect(self._check_selected)
        tree_header.addWidget(self.check_selected_btn)

        self.uncheck_selected_btn = QtWidgets.QPushButton(
            "Uncheck Selected",
            self,
        )
        self.uncheck_selected_btn.setToolTip(
            "Disable all selected hierarchy objects"
        )
        self.uncheck_selected_btn.clicked.connect(self._uncheck_selected)
        tree_header.addWidget(self.uncheck_selected_btn)

        outer.addLayout(tree_header)

        self.tree = ExportHierarchyTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(CUSTOM_CONTEXT_MENU)
        self.tree.customContextMenuRequested.connect(
            self._show_tree_context_menu
        )
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

    def _set_selected_check_state(self, state):
        for item in self.tree.selectedItems():
            item.setCheckState(0, state)

    def _check_selected(self):
        self._set_selected_check_state(CHECKED)

    def _uncheck_selected(self):
        self._set_selected_check_state(UNCHECKED)

    def _set_all_check_state(self, state):
        pending = [
            self.tree.topLevelItem(index)
            for index in reversed(range(self.tree.topLevelItemCount()))
        ]
        while pending:
            item = pending.pop()
            item.setCheckState(0, state)
            pending.extend(
                item.child(index)
                for index in reversed(range(item.childCount()))
            )

    def _check_all(self):
        self._set_all_check_state(CHECKED)

    def _uncheck_all(self):
        self._set_all_check_state(UNCHECKED)

    def _show_tree_context_menu(self, position):
        menu = QtWidgets.QMenu(self.tree)
        has_selection = bool(self.tree.selectedItems())

        check_selected_action = menu.addAction("Check Selected")
        check_selected_action.setEnabled(has_selection)
        check_selected_action.triggered.connect(self._check_selected)

        uncheck_selected_action = menu.addAction("Uncheck Selected")
        uncheck_selected_action.setEnabled(has_selection)
        uncheck_selected_action.triggered.connect(self._uncheck_selected)

        menu.addSeparator()

        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.tree.selectAll)

        check_all_action = menu.addAction("Check All")
        check_all_action.triggered.connect(self._check_all)

        uncheck_all_action = menu.addAction("Uncheck All")
        uncheck_all_action.triggered.connect(self._uncheck_all)

        exec_method = (
            getattr(menu, "exec", None)
            or getattr(menu, "exec_")
        )
        exec_method(self.tree.viewport().mapToGlobal(position))


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
