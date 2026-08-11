import importlib
import types

import mobu_tools_manager.runtime as runtime_module
from mobu_tools_manager import get_manager


runtime_module = importlib.reload(runtime_module)
manager = get_manager()
ui = manager.runtime.ui
ui._valid_widget = runtime_module.UIContextService._valid_widget
ui.find_surface = types.MethodType(
    runtime_module.UIContextService.find_surface,
    ui,
)
ui._surface_discovery_owners = {}

feature_id = "animation.timeline_marker_labels"
manager.reload_feature(feature_id)
adapter = manager.adapters.get(feature_id)
if adapter is None or adapter.module is None:
    raise RuntimeError("Timeline Marker Labels resident adapter did not start")
service = getattr(adapter.module, "_SERVICE", None)
if service is None:
    raise RuntimeError("Timeline Marker Labels service did not start")
service._refresh_now()
surface = service.surface
overlay = service.overlay
set_result(
    {
        "feature_enabled": bool(manager.is_enabled(feature_id)),
        "observer_registered": bool(
            service._observer in manager.runtime.ui._event_observers
        ),
        "surface_attached": bool(surface is not None and ui._valid_widget(surface)),
        "surface_name": surface.accessibleName() if surface is not None else None,
        "overlay_created": bool(overlay is not None and ui._valid_widget(overlay)),
        "service_status": service.status(),
    }
)
