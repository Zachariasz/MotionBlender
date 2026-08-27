"""Native MotionBuilder SDK implementation for the 'Motion Blender' topbar menu tab.

Uses FBMenuManager.InsertBefore(None, "Help", "Motion Blender") to create a real,
native C++ top-level root menu on MotionBuilder's main menu bar without touching
Qt QMenuBar, preventing any tooldesktop.dll crashes.
"""

from __future__ import absolute_import

import traceback

MENU_NAME = "Motion Blender"

ID_SHOW_MANAGER = 95270101
ID_QUICK_FAVORITES = 95270102
ID_CODEX_BRIDGE = 95270103
ID_ANTIGRAVITY_BRIDGE = 95270104
ID_FAST_RENDER = 95270105
ID_EXPORT_FBX = 95270106
ID_RELOAD_MANAGER = 95270107

_CONTROLLER = None


class MotionBlenderMenuController(object):
    def __init__(self, manager=None):
        self.manager = manager
        self.menu_manager = None
        self.menu = None
        self.menu_root_item = None
        self._callback = self._on_menu_activate
        self._installed = False

    def _sdk(self):
        try:
            import pyfbsdk
            return pyfbsdk
        except ImportError:
            return None

    def start(self, context=None):
        if self._installed:
            return self
        sdk = self._sdk()
        if sdk is None:
            return self

        try:
            menu_mgr = sdk.FBMenuManager()
            self.menu_manager = menu_mgr

            # 1. Check if "Motion Blender" menu already exists
            menu = menu_mgr.GetMenu(MENU_NAME)
            if menu is None:
                # Insert top-level menu before Help
                item = menu_mgr.InsertBefore(None, "Help", MENU_NAME)
                if item is None:
                    item = menu_mgr.InsertBefore(None, "&Help", MENU_NAME)
                if item is None:
                    item = menu_mgr.InsertAfter(None, "Python Tools", MENU_NAME)
                if item is None:
                    item = menu_mgr.InsertAfter(None, "&Python Tools", MENU_NAME)
                if item is None:
                    item = menu_mgr.InsertLast(None, MENU_NAME)
                self.menu_root_item = item
                menu = menu_mgr.GetMenu(MENU_NAME)

            if menu is None:
                return self

            self.menu = menu

            # 2. Populate menu items if empty
            self._ensure_menu_items(menu)

            # 3. Connect OnMenuActivate callback
            try:
                menu.OnMenuActivate.Add(self._callback)
            except Exception:
                pass

            self._installed = True
        except Exception:
            if self.manager and hasattr(self.manager, "_record"):
                self.manager._record(
                    "motion_blender_menu_start_error",
                    error=traceback.format_exc(),
                )
        return self

    def _ensure_menu_items(self, menu):
        """Add standard items to the Motion Blender menu."""
        items_to_add = [
            ("MotionBuilder Tools Manager", ID_SHOW_MANAGER),
            ("Quick Favorites...", ID_QUICK_FAVORITES),
            ("Start / Stop Codex Bridge", ID_CODEX_BRIDGE),
            ("Start / Stop Antigravity Bridge", ID_ANTIGRAVITY_BRIDGE),
            ("Fast Render (Active Take)", ID_FAST_RENDER),
            ("Export FBX...", ID_EXPORT_FBX),
            ("Reload Tools Manager", ID_RELOAD_MANAGER),
        ]
        for caption, item_id in items_to_add:
            existing = menu.GetItem(item_id)
            if existing is None:
                menu.InsertLast(caption, item_id)

    def _on_menu_activate(self, control, event):
        del control
        try:
            item_id = int(getattr(event, "Id", 0))
            if item_id == ID_SHOW_MANAGER:
                self._dispatch_show_manager()
            elif item_id == ID_QUICK_FAVORITES:
                self._dispatch_feature("ui.quick_favorites")
            elif item_id == ID_CODEX_BRIDGE:
                self._toggle_bridge("developer.codex_bridge")
            elif item_id == ID_ANTIGRAVITY_BRIDGE:
                self._toggle_bridge("developer.antigravity_bridge")
            elif item_id == ID_FAST_RENDER:
                self._dispatch_feature("animation.render_side_front")
            elif item_id == ID_EXPORT_FBX:
                self._dispatch_feature("scene.export_fbx")
            elif item_id == ID_RELOAD_MANAGER:
                self._reload_manager()
        except Exception:
            if self.manager and hasattr(self.manager, "_record"):
                self.manager._record(
                    "motion_blender_menu_activate_error",
                    error=traceback.format_exc(),
                )

    def _dispatch_show_manager(self):
        if self.manager and hasattr(self.manager, "show_manager"):
            self.manager.show_manager()
        else:
            try:
                import mobu_tools_manager
                mobu_tools_manager.show_manager()
            except Exception:
                pass

    def _dispatch_feature(self, feature_id):
        if self.manager and hasattr(self.manager, "dispatch"):
            self.manager.dispatch(feature_id)
        else:
            try:
                import mobu_tools_manager
                mobu_tools_manager.dispatch(feature_id)
            except Exception:
                pass

    def _toggle_bridge(self, feature_id):
        if self.manager:
            if self.manager.is_feature_running(feature_id):
                self.manager.disable(feature_id)
            else:
                if not self.manager.is_enabled(feature_id):
                    self.manager.enable(feature_id)
                self.manager.dispatch(feature_id)

    def _reload_manager(self):
        try:
            import mobu_tools_manager
            mobu_tools_manager.restart_manager()
        except Exception:
            pass

    def stop(self):
        if not self._installed:
            return
        self._installed = False
        if self.menu is not None:
            try:
                self.menu.OnMenuActivate.Remove(self._callback)
            except Exception:
                pass
            self.menu = None
        self.menu_manager = None
        self.menu_root_item = None

    def status(self):
        return {"running": self._installed}


def start(context=None):
    global _CONTROLLER
    if _CONTROLLER is None:
        manager = getattr(context, "manager", None) if context else None
        if manager is None:
            try:
                import mobu_tools_manager
                manager = mobu_tools_manager.get_manager()
            except Exception:
                manager = None
        _CONTROLLER = MotionBlenderMenuController(manager)
    return _CONTROLLER.start(context)


def stop():
    global _CONTROLLER
    if _CONTROLLER is not None:
        _CONTROLLER.stop()
        _CONTROLLER = None


def status():
    if _CONTROLLER is not None:
        return _CONTROLLER.status()
    return {"running": False}
