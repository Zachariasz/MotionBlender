import builtins
import importlib

import mobu_tools_manager.catalog as catalog_module
import mobu_tools_manager.manager as manager_module
import mobu_tools_manager.runtime as runtime_module
from mobu_tools_manager import restart_manager


catalog_module = importlib.reload(catalog_module)
runtime_module = importlib.reload(runtime_module)
manager_module.FEATURES = catalog_module.FEATURES
manager_module.FEATURE_BY_ID = catalog_module.FEATURE_BY_ID

manager = restart_manager()
feature_id = "animation.timeline_marker_labels"
feature = manager.feature(feature_id)
adapter = manager.adapters.get(feature_id)
if adapter is None or adapter.module is None:
    raise RuntimeError("Timeline Marker Labels resident adapter did not start")
service = getattr(adapter.module, "_SERVICE", None)
if service is None:
    raise RuntimeError("Timeline Marker Labels service did not start")
service._refresh_now()
status = service.status()
observer_registered = service._observer in manager.runtime.ui._event_observers
result = {
    "manager_started": bool(manager.started),
    "feature_name": feature.name,
    "feature_enabled": bool(manager.is_enabled(feature_id)),
    "feature_resident": bool(feature.resident),
    "observer_registered": bool(observer_registered),
    "service_status": status,
}

launcher = getattr(
    builtins,
    "_codex_motionbuilder_bridge_tool_controller",
    None,
)
if launcher is not None:
    result["bridge_restarted"] = bool(launcher.start_bridge())
else:
    result["bridge_restarted"] = False

set_result(result)
