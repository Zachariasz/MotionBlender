"""Toggle MotionBuilder's Viewer Global and Local reference modes."""

from __future__ import absolute_import


FEATURE_ID = "viewer.toggle_global_local_reference"
GLOBAL_ACTION = "action.viewer.manipulator.global"
LOCAL_ACTION = "action.viewer.manipulator.local"
_MODE_ACTIONS = {
    "global": GLOBAL_ACTION,
    "local": LOCAL_ACTION,
}
_MODE_VIRTUAL_KEYS = {
    "global": 0x75,  # F6
    "local": 0x74,  # F5
}
_LAST_MODE_ATTR = "_mobu_tools_manager_reference_mode"
_SERVICE = None


def _normalized(value):
    return " ".join(str(value or "").replace("&", "").lower().split())


def _action_values(action):
    values = []
    for name in (
        "objectName",
        "text",
        "iconText",
        "toolTip",
        "statusTip",
        "whatsThis",
    ):
        callback = getattr(action, name, None)
        if not callable(callback):
            continue
        try:
            value = _normalized(callback())
        except Exception:
            value = ""
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _action_mode(action):
    values = _action_values(action)
    for mode, action_name in _MODE_ACTIONS.items():
        if action_name in values:
            return mode
    for mode in _MODE_ACTIONS:
        if mode in values:
            return mode
        if any(
            mode in value and ("reference" in value or "manipulator" in value)
            for value in values
        ):
            return mode
    return None


def _application_actions(application):
    """Yield native actions without retaining MotionBuilder-owned wrappers."""
    widgets = []
    for name in ("allWidgets", "topLevelWidgets"):
        callback = getattr(application, name, None)
        if not callable(callback):
            continue
        try:
            widgets.extend(tuple(callback()))
        except Exception:
            pass
    seen = set()
    for widget in widgets:
        callback = getattr(widget, "actions", None)
        if not callable(callback):
            continue
        try:
            actions = tuple(callback())
        except Exception:
            continue
        for action in actions:
            if action is None or id(action) in seen:
                continue
            seen.add(id(action))
            yield action


def _ui_reference_mode(context):
    """Return the checked native reference action's mode, when available."""
    application = getattr(context, "qt_application", None)
    if application is None:
        return None
    for action in _application_actions(application):
        mode = _action_mode(action)
        if mode is None:
            continue
        is_checked = getattr(action, "isChecked", None)
        if not callable(is_checked):
            continue
        try:
            if is_checked():
                return mode
        except Exception:
            pass
    return None


def _manager():
    from mobu_tools_manager import get_manager

    return get_manager()


def _send_key_pair(virtual_key):
    """Run the existing Viewer shortcut without changing its keyboard map."""
    import ctypes

    key_up = 0x0002
    user32 = ctypes.windll.user32
    try:
        user32.keybd_event(int(virtual_key), 0, 0, 0)
    finally:
        user32.keybd_event(int(virtual_key), 0, key_up, 0)


def execute(context):
    """Toggle the host Viewer reference mode through its native actions."""
    manager = _manager()
    current_mode = _ui_reference_mode(context)
    source = "viewer_ui"
    if current_mode is None:
        current_mode = getattr(manager, _LAST_MODE_ATTR, None)
        source = "manager_cache"
    if current_mode not in _MODE_ACTIONS:
        # Native Viewer actions are not exposed by every MotionBuilder layout.
        # Global is the normal initial mode; later presses use the manager cache.
        current_mode = "global"
        source = "default_global"

    target_mode = "local" if current_mode == "global" else "global"
    action_name = _MODE_ACTIONS[target_mode]
    virtual_key = _MODE_VIRTUAL_KEYS[target_mode]
    _send_key_pair(virtual_key)
    setattr(manager, _LAST_MODE_ATTR, target_mode)

    diagnostics = getattr(context, "diagnostics", None)
    record = getattr(diagnostics, "record", None)
    if callable(record):
        record(
            "reference_mode_toggled",
            FEATURE_ID,
            previous_mode=current_mode,
            mode=target_mode,
            source=source,
            action=action_name,
            virtual_key=virtual_key,
        )
    return {
        "previous_mode": current_mode,
        "mode": target_mode,
        "source": source,
        "action": action_name,
        "virtual_key": virtual_key,
    }


class ReferenceModeHotkeyService(object):
    """Own the Viewer-only X binding through the shared input router."""

    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_mode = None
        self.last_error = None

    def start(self):
        if self.running:
            return self
        self.context.input.configure_reference_mode_launcher(self._callback)
        self.running = True
        return self

    def stop(self):
        if self.context is not None:
            try:
                self.context.input.clear_reference_mode_launcher(self._callback)
            except Exception:
                pass
        self.running = False

    def handle_key(self, payload=None):
        if not self.running:
            return False
        snapshot = dict(getattr(self.context, "ui_context", {}) or {})
        if str(snapshot.get("hovered") or "").lower() != "viewer":
            return False
        try:
            result = execute(self.context)
        except Exception as error:
            self.last_error = str(error)
            return False
        self.last_mode = result["mode"]
        self.last_error = None
        return True

    def status(self):
        return {
            "running": self.running,
            "binding": "X",
            "last_mode": self.last_mode,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = ReferenceModeHotkeyService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.stop()
    _SERVICE = None


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
