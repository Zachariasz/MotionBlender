"""Modeless Qt manager UI."""

from __future__ import absolute_import

import os
import time

from .catalog import FEATURES
from .shortcuts import ShortcutConflict

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


class ManagerWindow(QtWidgets.QWidget):
    def __init__(self, manager):
        super(ManagerWindow, self).__init__()
        self.manager = manager
        self.setWindowTitle("MotionBuilder Tools Manager")
        self.setObjectName("motionbuilder_tools_manager")
        self.resize(980, 650)
        self._building = False
        self._quick_favorites_editor = None
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search features...")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            ("Feature", "Enabled", "Shortcut", "Status", "Last ms", "Error")
        )
        self.tree.setRootIsDecorated(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(self._edit_shortcut_from_item)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(
            self._show_shortcut_context_menu
        )
        layout.addWidget(self.tree, 2)

        buttons = QtWidgets.QHBoxLayout()
        self.favorites_button = QtWidgets.QPushButton("Quick Favorites...")
        self.export_button = QtWidgets.QPushButton("Export Diagnostics")
        for button in (
            self.favorites_button,
            self.export_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self._build_interaction_settings(layout)

        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        layout.addWidget(self.details)

        self.favorites_button.clicked.connect(self._show_quick_favorites_editor)
        self.export_button.clicked.connect(self._export)

    def _build_interaction_settings(self, parent_layout):
        group = QtWidgets.QGroupBox("Interaction Settings")
        grid = QtWidgets.QGridLayout(group)
        self.precision_modifier = QtWidgets.QComboBox()
        self.precision_modifier.addItems(("Shift", "Control", "Alt"))
        self.precision_multiplier = self._number_input(0.001, 1.0, 3)
        self.snap_modifier = QtWidgets.QComboBox()
        self.snap_modifier.addItems(("Control", "Shift", "Alt"))
        self.translation_snap = self._number_input(0.001, 1000000.0, 3)
        self.rotation_snap = self._number_input(0.001, 360.0, 3)
        self.scale_snap = self._number_input(0.001, 1000.0, 3)
        self.fcurve_value_snap = self._number_input(0.001, 1000000.0, 3)
        self.tangent_key = QtWidgets.QLineEdit()
        self.tangent_key.setMaxLength(1)
        self.tangent_key.setMaximumWidth(45)
        self.object_pivot = QtWidgets.QComboBox()
        self.object_pivot.addItems(("individual", "median", "active"))
        self.fcurve_pivot = QtWidgets.QComboBox()
        self.fcurve_pivot.addItems(("median", "individual", "current"))
        self.apply_interaction_button = QtWidgets.QPushButton("Apply")

        entries = (
            ("Precision modifier", self.precision_modifier),
            ("Precision multiplier", self.precision_multiplier),
            ("Snap modifier", self.snap_modifier),
            ("Translation snap", self.translation_snap),
            ("Rotation snap", self.rotation_snap),
            ("Scale snap", self.scale_snap),
            ("FCurve value snap", self.fcurve_value_snap),
            ("Tangent cycle key", self.tangent_key),
            ("Object pivot", self.object_pivot),
            ("FCurve pivot", self.fcurve_pivot),
        )
        for index, (label, control) in enumerate(entries):
            row = index // 3
            column = (index % 3) * 2
            grid.addWidget(QtWidgets.QLabel(label), row, column)
            grid.addWidget(control, row, column + 1)
        grid.addWidget(self.apply_interaction_button, 3, 5)
        parent_layout.addWidget(group)
        self.apply_interaction_button.clicked.connect(
            self._apply_interaction_settings
        )
        self._refresh_interaction_settings()

    @staticmethod
    def _number_input(minimum, maximum, decimals):
        control = QtWidgets.QDoubleSpinBox()
        control.setDecimals(decimals)
        control.setRange(minimum, maximum)
        control.setSingleStep(0.1)
        control.setMaximumWidth(100)
        return control

    def _refresh_interaction_settings(self):
        values = self.manager.interaction_settings()
        controls = (
            (
                self.precision_modifier,
                values.get("precision_modifier", "Shift"),
            ),
            (self.snap_modifier, values.get("snap_modifier", "Control")),
            (
                self.object_pivot,
                values.get("object_pivot_mode", "individual"),
            ),
            (
                self.fcurve_pivot,
                values.get("fcurve_pivot_mode", "median"),
            ),
        )
        for control, value in controls:
            index = control.findText(str(value))
            if index >= 0:
                control.setCurrentIndex(index)
        self.precision_multiplier.setValue(
            float(values.get("precision_multiplier", 0.1))
        )
        self.translation_snap.setValue(
            float(values.get("translation_snap", 1.0))
        )
        self.rotation_snap.setValue(
            float(values.get("rotation_snap", 10.0))
        )
        self.scale_snap.setValue(float(values.get("scale_snap", 0.1)))
        self.fcurve_value_snap.setValue(
            float(values.get("fcurve_value_snap", 1.0))
        )
        self.tangent_key.setText(
            str(values.get("tangent_side_cycle_key", "T"))
        )

    def _apply_interaction_settings(self):
        values = {
            "precision_modifier": str(self.precision_modifier.currentText()),
            "precision_multiplier": self.precision_multiplier.value(),
            "snap_modifier": str(self.snap_modifier.currentText()),
            "translation_snap": self.translation_snap.value(),
            "rotation_snap": self.rotation_snap.value(),
            "scale_snap": self.scale_snap.value(),
            "fcurve_value_snap": self.fcurve_value_snap.value(),
            "tangent_side_cycle_key": str(self.tangent_key.text() or "T"),
            "object_pivot_mode": str(self.object_pivot.currentText()),
            "fcurve_pivot_mode": str(self.fcurve_pivot.currentText()),
        }
        try:
            self.manager.update_interaction_settings(values)
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self,
                "Interaction Settings",
                str(error),
            )
            return
        self._refresh_interaction_settings()

    def selected_feature(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        feature_id = items[0].data(0, QtCore.Qt.UserRole)
        if not feature_id:
            return None
        return self.manager.feature(str(feature_id))

    def refresh(self, *args):
        if self._building:
            return
        selected = self.selected_feature()
        selected_id = selected.id if selected else None
        query = self.search.text().strip().lower()
        self._building = True
        try:
            self.tree.clear()
            categories = {}
            for feature in FEATURES:
                haystack = " ".join(
                    (feature.name, feature.id, feature.category, " ".join(feature.files))
                ).lower()
                if query and query not in haystack:
                    continue
                parent = categories.get(feature.category)
                if parent is None:
                    parent = QtWidgets.QTreeWidgetItem((feature.category,))
                    parent.setFirstColumnSpanned(True)
                    categories[feature.category] = parent
                    self.tree.addTopLevelItem(parent)
                status = self.manager.feature_status(feature.id)
                state = "Loaded" if status["loaded"] else (
                    "Compiled" if status["compiled"] else "Lazy"
                )
                total = status.get("last_total_ms")
                item = QtWidgets.QTreeWidgetItem(
                    (
                        feature.name,
                        "Yes" if status["enabled"] else "No",
                        status.get("binding", ""),
                        state,
                        "" if total is None else "%.3f" % total,
                        "Yes" if status.get("last_error") else "",
                    )
                )
                item.setData(0, QtCore.Qt.UserRole, feature.id)
                parent.addChild(item)
                if feature.id == selected_id:
                    self.tree.setCurrentItem(item)
            for parent in categories.values():
                parent.setExpanded(True)
            for column in range(6):
                self.tree.resizeColumnToContents(column)
        finally:
            self._building = False
        self._selection_changed()

    def _selection_changed(self):
        feature = self.selected_feature()
        if feature is None:
            self.details.setPlainText(
                "Select a feature to inspect its scripts, dependencies, timing, and error."
            )
            return
        status = self.manager.feature_status(feature.id)
        lines = [
            "%s (%s)" % (feature.name, feature.id),
            "Kind: %s    Category: %s" % (feature.kind, feature.category),
            "Profile: %s    ActionScript slot: %s"
            % (
                self.manager.profile_name,
                feature.action_slot
                if feature.action_slot is not None
                else "None",
            ),
            "Dependencies: %s"
            % (", ".join(feature.dependencies) if feature.dependencies else "None"),
            "Context: %s"
            % (
                ", ".join(feature.context_requirements)
                if feature.context_requirements
                else "None"
            ),
            "Timing (ms): compile=%s  load=%s  warm-overhead=%s  feature=%s  total=%s"
            % (
                self._time_text(status.get("last_compile_ms")),
                self._time_text(status.get("last_load_ms")),
                self._time_text(status.get("last_dispatch_overhead_ms")),
                self._time_text(status.get("last_execution_ms")),
                self._time_text(status.get("last_total_ms")),
            ),
            "Tracked resources: %s" % status.get("resource_count", 0),
            "Physical scripts:",
        ]
        lines.extend("  - " + path for path in feature.files)
        if feature.implementation_files:
            lines.append("Native implementation files:")
            lines.extend(
                "  - " + path for path in feature.implementation_files
            )
        if status.get("last_error"):
            lines.extend(("", "Last error:", status["last_error"][-3000:]))
        self.details.setPlainText("\n".join(lines))

    @staticmethod
    def _time_text(value):
        return "-" if value is None else "%.3f" % value

    def _run(self):
        feature = self.selected_feature()
        if feature:
            self.manager.dispatch(feature.id)

    def _run_or_stop(self):
        feature = self.selected_feature()
        if feature is None:
            return
        if self.manager.is_feature_running(feature.id):
            self.manager.stop_feature(feature.id)
        else:
            self.manager.dispatch(feature.id)

    def _toggle(self):
        feature = self.selected_feature()
        if not feature:
            return
        if self.manager.is_enabled(feature.id):
            self.manager.disable(feature.id)
        else:
            self.manager.enable(feature.id)

    def _reload(self):
        feature = self.selected_feature()
        if feature:
            self.manager.reload_feature(feature.id)

    def _edit_shortcut_from_item(self, item, _column):
        if item is None or not item.data(0, QtCore.Qt.UserRole):
            return
        self.tree.setCurrentItem(item)
        self._edit_shortcut()

    def _show_shortcut_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item is None or not item.data(0, QtCore.Qt.UserRole):
            return
        self.tree.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        feature_id = str(item.data(0, QtCore.Qt.UserRole))
        run_label = "Stop" if self.manager.is_feature_running(feature_id) else "Run"
        run_action = menu.addAction(run_label)
        run_action.triggered.connect(self._run_or_stop)
        toggle_label = "Disable" if self.manager.is_enabled(feature_id) else "Enable"
        toggle_action = menu.addAction(toggle_label)
        toggle_action.triggered.connect(self._toggle)
        reload_action = menu.addAction("Reload")
        reload_action.triggered.connect(self._reload)
        edit_action = menu.addAction("Edit Shortcut")
        edit_action.triggered.connect(self._edit_shortcut)
        reset_action = menu.addAction("Reset Shortcut")
        reset_action.triggered.connect(self._reset_shortcut)
        execute = getattr(menu, "exec", None)
        if execute is None:
            execute = menu.exec_
        execute(self.tree.viewport().mapToGlobal(position))

    def _edit_shortcut(self):
        feature = self.selected_feature()
        if feature is None or feature.action_slot is None:
            QtWidgets.QMessageBox.information(
                self, "Shortcut", "This feature has no ActionScript shortcut slot."
            )
            return
        current = self.manager.binding(feature.id)
        value, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Edit MotionBuilder Shortcut",
            "MotionBuilder binding(s), separated by |:",
            QtWidgets.QLineEdit.Normal,
            current,
        )
        if not accepted:
            return
        try:
            self.manager.edit_shortcut(feature.id, str(value), False)
        except ShortcutConflict as error:
            choice = QtWidgets.QMessageBox.question(
                self,
                "Shortcut Conflict",
                self.manager.shortcut_conflict_message(error)
                + "\n\nReplace existing binding(s)? This clears them from the previous action.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if choice == QtWidgets.QMessageBox.Yes:
                self.manager.edit_shortcut(feature.id, str(value), True)

    def _reset_shortcut(self):
        feature = self.selected_feature()
        if feature and feature.action_slot is not None:
            self.manager.reset_shortcut(feature.id)

    def _show_quick_favorites_editor(self):
        editor = self._quick_favorites_editor
        if editor is None:
            from .quick_favorites.editor import QuickFavoritesEditorDialog

            editor = QuickFavoritesEditorDialog(self.manager, self)
            self._quick_favorites_editor = editor

            def clear_reference(*_args):
                if self._quick_favorites_editor is editor:
                    self._quick_favorites_editor = None

            editor.destroyed.connect(clear_reference)
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _export(self):
        base = self.manager.settings.directory
        default = os.path.join(
            base, "diagnostics-%s.json" % time.strftime("%Y%m%d-%H%M%S")
        )
        path, accepted = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Diagnostics", default, "JSON (*.json)"
        )
        if path:
            self.manager.export_diagnostics(str(path))
            QtWidgets.QMessageBox.information(
                self, "Diagnostics Exported", str(path)
            )

    def closeEvent(self, event):
        self.hide()
        event.ignore()
