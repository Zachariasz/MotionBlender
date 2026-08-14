"""Idempotent PythonStartup entry and Python Tools menu registration."""

from __future__ import absolute_import

import traceback


TOOL_NAME = "MotionBuilder Tools Manager"
CODEX_BRIDGE_START_MENU_NAME = "Start Codex Bridge"
CODEX_BRIDGE_STOP_MENU_NAME = "Stop Codex Bridge"
CODEX_BRIDGE_FEATURE_ID = "developer.codex_bridge"

ANTIGRAVITY_BRIDGE_START_MENU_NAME = "Start Antigravity Bridge"
ANTIGRAVITY_BRIDGE_STOP_MENU_NAME = "Stop Antigravity Bridge"
ANTIGRAVITY_BRIDGE_FEATURE_ID = "developer.antigravity_bridge"

# Compatibility aliases
BRIDGE_START_MENU_NAME = CODEX_BRIDGE_START_MENU_NAME
BRIDGE_STOP_MENU_NAME = CODEX_BRIDGE_STOP_MENU_NAME
BRIDGE_FEATURE_ID = CODEX_BRIDGE_FEATURE_ID


class ManagerMenuLauncher(object):
    def __init__(self, manager):
        self.manager = manager
        self.tool = None
        self._pre_show_callback = self._on_show
        self._show_callback = self._on_show
        self.bridge_menu = None
        self.codex_bridge_action = None
        self.antigravity_bridge_action = None
        self.bridge_actions = []
        self._codex_action_callback = self._on_codex_bridge_action_triggered
        self._antigravity_action_callback = self._on_antigravity_bridge_action_triggered
        self._bridge_action_callback = self._on_codex_bridge_action_triggered
        self._ui_observer = self._observe_ui_event
        self._toggle_generation = 0
        self._stopped = False
        self._register()
        self._remove_legacy_bridge_menu_items()
        self.manager.runtime.context.add_ui_event_observer(self._ui_observer)

    @property
    def bridge_action(self):
        return self.codex_bridge_action

    @bridge_action.setter
    def bridge_action(self, value):
        self.codex_bridge_action = value

    def _register(self):
        import pyfbsdk_additions
        from pyfbsdk_additions import FBCreateUniqueTool

        self.tool = FBCreateUniqueTool(TOOL_NAME)
        try:
            self.tool.OnPreShow.Add(self._pre_show_callback)
        except Exception:
            pass
        try:
            self.tool.OnShow.Add(self._show_callback)
        except Exception:
            pass
        try:
            self.tool.Visible = False
        except Exception:
            pass
        try:
            entry = pyfbsdk_additions.FBToolManager.tools.get(TOOL_NAME)
            if entry is not None:
                entry.activated = False
        except Exception:
            pass

    def _remove_legacy_bridge_menu_items(self):
        """Remove bridge entries created by old FBTool/native-menu paths."""
        try:
            from pyfbsdk import FBMenuManager
            import pyfbsdk_additions

            legacy_names = (
                "Start Codex MotionBuilder Bridge",
                CODEX_BRIDGE_START_MENU_NAME,
                CODEX_BRIDGE_STOP_MENU_NAME,
                "Start Antigravity MotionBuilder Bridge",
                ANTIGRAVITY_BRIDGE_START_MENU_NAME,
                ANTIGRAVITY_BRIDGE_STOP_MENU_NAME,
            )
            for legacy_name in legacy_names:
                if legacy_name in pyfbsdk_additions.FBGetTools():
                    pyfbsdk_additions.FBDestroyToolByName(legacy_name)
            menu_manager = FBMenuManager()
            menu = menu_manager.GetMenu("Python Tools")
            if menu is None:
                return
            stale_item = menu.GetFirstItem()
            for _index in range(512):
                if stale_item is None:
                    break
                next_item = menu.GetNextItem(stale_item)
                if str(getattr(stale_item, "Caption", "") or "") in legacy_names:
                    menu.DeleteItem(stale_item)
                stale_item = next_item
        except Exception:
            self.manager._record(
                "bridge_legacy_python_tools_cleanup_error",
                BRIDGE_FEATURE_ID,
                error=traceback.format_exc(),
            )

    @staticmethod
    def _qt_modules():
        try:
            try:
                from PySide6 import QtCore, QtGui, QtWidgets
            except ImportError:
                from PySide2 import QtCore, QtGui, QtWidgets
            return QtCore, QtGui, QtWidgets
        except ImportError:
            return None, None, None

    @staticmethod
    def _event_value(QtCore, name):
        group = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
        value = getattr(QtCore.QEvent, name, None)
        return value if value is not None else getattr(group, name, None)

    @staticmethod
    def _menu_title(menu):
        values = []
        for callback_name in ("title", "objectName"):
            try:
                values.append(str(getattr(menu, callback_name)() or ""))
            except Exception:
                pass
        try:
            values.append(str(menu.menuAction().text() or ""))
        except Exception:
            pass
        return tuple(
            " ".join(value.replace("&", "").split()).casefold()
            for value in values
        )

    def _observe_ui_event(self, watched, event):
        if self._stopped:
            return False
        QtCore, _QtGui, QtWidgets = self._qt_modules()
        if QtCore is None or not isinstance(watched, QtWidgets.QMenu):
            return False
        event_type = event.type()
        if event_type == self._event_value(QtCore, "Show"):
            if "python tools" in self._menu_title(watched):
                self._install_bridge_action(watched)
        elif watched is self.bridge_menu and event_type in (
            self._event_value(QtCore, "Destroy"),
        ):
            self._remove_bridge_action()
        elif (
            watched is self.bridge_menu
            and event_type == self._event_value(QtCore, "Hide")
        ):
            # QMenu hides before QAction.triggered is emitted. Disconnecting
            # here would discard the user's click, so clean up next turn.
            QtCore.QTimer.singleShot(0, self._remove_bridge_action)
        return False

    def _install_bridge_action(self, menu):
        self._remove_bridge_action()
        _QtCore, QtGui, QtWidgets = self._qt_modules()
        action_class = getattr(QtGui, "QAction", None)
        if action_class is None:
            action_class = QtWidgets.QAction

        # 1. Codex Bridge Action
        codex_caption = (
            CODEX_BRIDGE_STOP_MENU_NAME
            if self._bridge_is_running(CODEX_BRIDGE_FEATURE_ID)
            else CODEX_BRIDGE_START_MENU_NAME
        )
        codex_action = action_class(codex_caption, menu)
        codex_action.setObjectName("MobuCodexBridgeMenuAction")
        codex_action.triggered.connect(self._codex_action_callback)
        menu.addAction(codex_action)

        # 2. Antigravity Bridge Action
        antigravity_caption = (
            ANTIGRAVITY_BRIDGE_STOP_MENU_NAME
            if self._bridge_is_running(ANTIGRAVITY_BRIDGE_FEATURE_ID)
            else ANTIGRAVITY_BRIDGE_START_MENU_NAME
        )
        antigravity_action = action_class(antigravity_caption, menu)
        antigravity_action.setObjectName("MobuAntigravityBridgeMenuAction")
        antigravity_action.triggered.connect(self._antigravity_action_callback)
        menu.addAction(antigravity_action)

        self.bridge_menu = menu
        self.codex_bridge_action = codex_action
        self.antigravity_bridge_action = antigravity_action
        self.bridge_actions = [codex_action, antigravity_action]
        return codex_action

    def _reset_activation(self):
        try:
            import pyfbsdk_additions

            entry = pyfbsdk_additions.FBToolManager.tools.get(TOOL_NAME)
            if entry is not None:
                entry.activated = False
        except Exception:
            pass

    def _on_show(self, control, event):
        try:
            self.tool.Visible = False
        except Exception:
            pass
        self.manager.show_manager()
        try:
            from PySide6 import QtCore
        except ImportError:
            from PySide2 import QtCore
        QtCore.QTimer.singleShot(0, self._reset_activation)

    def _on_codex_bridge_action_triggered(self, checked=False):
        del checked
        self._toggle_generation += 1
        generation = self._toggle_generation
        QtCore, _QtGui, _QtWidgets = self._qt_modules()
        if QtCore is None:
            self._toggle_bridge(generation, CODEX_BRIDGE_FEATURE_ID)
            return
        QtCore.QTimer.singleShot(
            0,
            lambda: self._toggle_bridge(generation, CODEX_BRIDGE_FEATURE_ID),
        )

    def _on_antigravity_bridge_action_triggered(self, checked=False):
        del checked
        self._toggle_generation += 1
        generation = self._toggle_generation
        QtCore, _QtGui, _QtWidgets = self._qt_modules()
        if QtCore is None:
            self._toggle_bridge(generation, ANTIGRAVITY_BRIDGE_FEATURE_ID)
            return
        QtCore.QTimer.singleShot(
            0,
            lambda: self._toggle_bridge(generation, ANTIGRAVITY_BRIDGE_FEATURE_ID),
        )

    def _on_bridge_action_triggered(self, checked=False):
        self._on_codex_bridge_action_triggered(checked)

    def _toggle_bridge(self, generation, feature_id=CODEX_BRIDGE_FEATURE_ID):
        if self._stopped or generation != self._toggle_generation:
            return
        try:
            if self._bridge_is_running(feature_id):
                self.manager.disable(feature_id)
            else:
                if not self.manager.is_enabled(feature_id):
                    self.manager.enable(feature_id)
                self.manager.dispatch(feature_id)
        except Exception:
            self.manager._record(
                "bridge_python_tools_dispatch_error",
                feature_id,
                error=traceback.format_exc(),
            )

    def _bridge_is_running(self, feature_id=CODEX_BRIDGE_FEATURE_ID):
        adapter = self.manager.adapters.get(feature_id)
        if adapter is None:
            return False
        for resource in reversed(adapter.resource_handles):
            callback = getattr(resource, "status", None)
            if not callable(callback):
                continue
            try:
                return bool(dict(callback() or {}).get("running"))
            except Exception:
                return False
        return False

    def sync_bridge_state(self):
        updated = False
        if self.codex_bridge_action is not None:
            caption = (
                CODEX_BRIDGE_STOP_MENU_NAME
                if self._bridge_is_running(CODEX_BRIDGE_FEATURE_ID)
                else CODEX_BRIDGE_START_MENU_NAME
            )
            try:
                self.codex_bridge_action.setText(caption)
                updated = True
            except Exception:
                pass
        if self.antigravity_bridge_action is not None:
            caption = (
                ANTIGRAVITY_BRIDGE_STOP_MENU_NAME
                if self._bridge_is_running(ANTIGRAVITY_BRIDGE_FEATURE_ID)
                else ANTIGRAVITY_BRIDGE_START_MENU_NAME
            )
            try:
                self.antigravity_bridge_action.setText(caption)
                updated = True
            except Exception:
                pass
        return updated

    def _remove_bridge_action(self):
        menu = self.bridge_menu
        actions = list(self.bridge_actions)
        self.bridge_menu = None
        self.codex_bridge_action = None
        self.antigravity_bridge_action = None
        self.bridge_actions = []

        for action in actions:
            if action is None:
                continue
            try:
                action.triggered.disconnect()
            except Exception:
                pass
            if menu is not None:
                try:
                    menu.removeAction(action)
                except Exception:
                    pass
            try:
                action.deleteLater()
            except Exception:
                pass

    def stop(self):
        self._stopped = True
        self._toggle_generation += 1
        try:
            self.manager.runtime.context.remove_ui_event_observer(
                self._ui_observer
            )
        except Exception:
            pass
        self._remove_bridge_action()
        if self.tool is None:
            return
        try:
            self.tool.OnPreShow.Remove(self._pre_show_callback)
        except Exception:
            pass
        try:
            self.tool.OnShow.Remove(self._show_callback)
        except Exception:
            pass
        try:
            self.tool.Visible = False
        except Exception:
            pass
        self._reset_activation()
        self.tool = None


def bootstrap():
    from . import restart_manager

    return restart_manager()
