"""Context-aware Deselect All for Viewport, FCurves, Timeline, and Navigator."""

from __future__ import absolute_import

FEATURE_ID = "selection.deselect_all"
_SERVICE = None


def _sdk():
    try:
        import pyfbsdk
        return pyfbsdk
    except ImportError:
        return None


def deselect_viewport(context):
    """Deselect all 3D objects / models in the 3D viewport context."""
    deselected = 0
    sdk = getattr(context, "sdk", None) or _sdk()
    selected_models = []

    # 1. Primary SDK method: FBGetSelectedModels
    if sdk is not None:
        try:
            model_list = sdk.FBModelList()
            sdk.FBGetSelectedModels(model_list)
            for model in model_list:
                if model is not None and model not in selected_models:
                    selected_models.append(model)
        except Exception:
            pass

    # 2. Check context.selection (can be a tuple or a SelectionCache)
    selection_obj = getattr(context, "selection", None)
    if selection_obj is not None:
        if callable(getattr(selection_obj, "snapshot", None)):
            try:
                for model in selection_obj.snapshot():
                    if model is not None and model not in selected_models:
                        selected_models.append(model)
            except Exception:
                pass
        elif isinstance(selection_obj, (list, tuple)):
            for model in selection_obj:
                if model is not None and model not in selected_models:
                    selected_models.append(model)

    # 3. Inspect scene models in case FBGetSelectedModels missed non-standard models
    def _is_model(comp):
        if sdk is not None:
            return isinstance(comp, sdk.FBModel)
        cls_name = getattr(comp, "ClassName", None)
        if callable(cls_name):
            cls_name = cls_name()
        elif not isinstance(cls_name, str):
            cls_name = type(comp).__name__
        return "model" in str(cls_name).lower()

    scene_index = getattr(context, "scene_index", None)
    if scene_index is not None:
        try:
            for component in scene_index.components():
                if getattr(component, "Selected", False) and component not in selected_models:
                    if _is_model(component):
                        selected_models.append(component)
        except Exception:
            pass

    scene = getattr(context, "scene", None)
    if scene is not None:
        try:
            for component in scene.Components:
                if getattr(component, "Selected", False) and component not in selected_models:
                    if _is_model(component):
                        selected_models.append(component)
        except Exception:
            pass

    # 4. Deselect all gathered models
    for model in selected_models:
        try:
            if getattr(model, "Selected", False):
                model.Selected = False
                deselected += 1
        except Exception:
            pass

    # Invalidate runtime selection cache if present
    runtime = getattr(context, "_runtime", None)
    if runtime is not None and hasattr(runtime, "selection"):
        try:
            runtime.selection.invalidate()
        except Exception:
            pass
    elif hasattr(context, "selection") and hasattr(context.selection, "invalidate"):
        try:
            context.selection.invalidate()
        except Exception:
            pass

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None:
        try:
            evaluation.request()
        except Exception:
            pass

    try:
        if scene is not None:
            scene.Evaluate()
        elif sdk is not None:
            sdk.FBSystem().Scene.Evaluate()
    except Exception:
        pass

    return deselected


def _gather_scene_curves(context):
    """Gather all FBFCurve objects across all components, animatable properties, takes, and layers."""
    sdk = getattr(context, "sdk", None) or _sdk()
    curves = []
    seen = set()

    def _add_curve(curve):
        if curve is not None and id(curve) not in seen:
            seen.add(id(curve))
            curves.append(curve)

    # 1. Gather displayed and whole scene curves from fcurves service if available
    fcurves_service = getattr(context, "fcurves", None)
    if fcurves_service is not None:
        try:
            for curve in fcurves_service.displayed_fcurves():
                _add_curve(curve)
        except Exception:
            pass
        try:
            for curve in fcurves_service.whole_scene_fcurves():
                _add_curve(curve)
        except Exception:
            pass

    if sdk is None:
        return tuple(curves)

    system = sdk.FBSystem()
    scene = getattr(context, "scene", None)
    if scene is None:
        try:
            scene = system.Scene
        except Exception:
            scene = None
    if scene is None:
        return tuple(curves)

    take = getattr(context, "take", None)
    if take is None:
        try:
            take = system.CurrentTake
        except Exception:
            take = None
    layer_count = take.GetLayerCount() if take is not None and hasattr(take, "GetLayerCount") else 1

    def _walk_node(node):
        if not node:
            return
        try:
            _add_curve(node.FCurve)
        except Exception:
            pass
        if take is not None and hasattr(take, "GetLayer"):
            for layer_idx in range(layer_count):
                try:
                    layer = take.GetLayer(layer_idx)
                    if layer is not None:
                        _add_curve(node.GetFCurve(layer))
                except Exception:
                    pass
        try:
            children = tuple(node.Nodes)
        except Exception:
            children = ()
        for child in children:
            _walk_node(child)

    # 2. Walk scene index / scene components and all their animatable properties
    scene_index = getattr(context, "scene_index", None)
    components = ()
    if scene_index is not None:
        try:
            components = scene_index.components()
        except Exception:
            components = ()
    if not components and scene is not None:
        try:
            components = tuple(scene.Components)
        except Exception:
            components = ()

    for comp in components:
        try:
            if isinstance(comp, sdk.FBFCurve):
                _add_curve(comp)
        except Exception:
            pass
        try:
            for prop in comp.PropertyList:
                try:
                    if prop.IsAnimatable():
                        _walk_node(prop.GetAnimationNode())
                except Exception:
                    pass
        except Exception:
            pass
        try:
            _walk_node(comp.AnimationNode)
        except Exception:
            pass

    # 3. Check takes
    try:
        for t in scene.Takes:
            try:
                for l_idx in range(t.GetLayerCount()):
                    layer = t.GetLayer(l_idx)
                    if layer is not None:
                        try:
                            for prop in layer.PropertyList:
                                if prop.IsAnimatable():
                                    _walk_node(prop.GetAnimationNode())
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass

    return tuple(curves)


def _refresh_timeline_ui(context):
    sdk = getattr(context, "sdk", None) or _sdk()
    if sdk is not None:
        try:
            system = sdk.FBSystem()
            player = sdk.FBPlayerControl()
            player.Goto(sdk.FBTime(system.LocalTime.Get()))
        except Exception:
            pass
        try:
            scene = getattr(context, "scene", None)
            if scene is not None:
                scene.Evaluate()
            else:
                sdk.FBSystem().Scene.Evaluate()
        except Exception:
            pass

    qt_app = getattr(context, "qt_application", None)
    if qt_app is not None:
        try:
            ui_service = getattr(getattr(context, "_runtime", None), "ui", None)
            for w in qt_app.allWidgets():
                try:
                    cls = ui_service.classify(w) if ui_service else ""
                    if cls in ("timeline", "fcurve") or "timecursor" in getattr(w, "objectName", lambda: "")().lower():
                        w.update()
                except Exception:
                    pass
        except Exception:
            pass


def deselect_fcurves(context):
    """Deselect only keys in the FCurve editor context (preserves curve/axis selection)."""
    keys_deselected = 0
    curves = _gather_scene_curves(context)

    for curve in curves:
        keys = getattr(curve, "Keys", None)
        if keys is not None:
            try:
                key_count = len(keys)
            except Exception:
                key_count = 0
            for idx in range(key_count):
                try:
                    key = keys[idx]
                    if getattr(key, "Selected", False):
                        key.Selected = False
                        keys_deselected += 1
                except Exception:
                    pass

    fcurves_service = getattr(context, "fcurves", None)
    if fcurves_service is not None:
        try:
            fcurves_service.invalidate()
        except Exception:
            pass

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None:
        try:
            evaluation.request_fcurve()
            if hasattr(evaluation, "flush_now"):
                evaluation.flush_now()
        except Exception:
            try:
                evaluation.request()
            except Exception:
                pass

    _refresh_timeline_ui(context)

    return {
        "keys": keys_deselected,
    }


def _clear_timeline_selection_range(context):
    """Clear any drag-selected colored time range on the MotionBuilder timeline canvas."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        try:
            from PySide2 import QtCore, QtGui, QtWidgets
        except ImportError:
            return False

    qt_app = getattr(context, "qt_application", None)
    if qt_app is None:
        try:
            qt_app = QtWidgets.QApplication.instance()
        except Exception:
            qt_app = None
    if qt_app is None:
        return False

    sdk = getattr(context, "sdk", None) or _sdk()
    system = sdk.FBSystem() if sdk else None
    player = sdk.FBPlayerControl() if sdk else None

    current_frame = 0
    start_frame = 0
    stop_frame = 100
    if system is not None:
        try:
            current_frame = system.LocalTime.GetFrame()
        except Exception:
            pass
    if player is not None:
        try:
            start_frame = player.ZoomWindowStart.GetFrame()
            stop_frame = player.ZoomWindowStop.GetFrame()
        except Exception:
            pass

    timeline_canvas = None
    for w in qt_app.allWidgets():
        try:
            cls_name = type(w).__name__
            if cls_name == "TimelineMarkerLabelsOverlay" or "TimelineMarkerLabelsOverlay" in cls_name:
                parent = w.parentWidget()
                if parent:
                    for child in parent.children():
                        if hasattr(child, "geometry") and type(child).__name__ == "QWidget":
                            geo = child.geometry()
                            if geo.width() > 300 and geo.height() >= 15:
                                timeline_canvas = child
                                break
                if timeline_canvas:
                    break
        except Exception:
            pass

    if timeline_canvas is None:
        ui_service = getattr(getattr(context, "_runtime", None), "ui", None)
        for w in qt_app.allWidgets():
            try:
                if ui_service and ui_service.classify(w) == "timeline":
                    geo = w.geometry()
                    if geo.width() > 300 and geo.height() >= 15:
                        timeline_canvas = w
                        break
            except Exception:
                pass

    if timeline_canvas is None:
        return False

    try:
        width = float(timeline_canvas.width())
        height = float(timeline_canvas.height())
        span = max(1.0, float(stop_frame - start_frame))
        frac = max(0.0, min(1.0, float(current_frame - start_frame) / span))
        x = frac * width
        y = height / 2.0

        pos = QtCore.QPointF(x, y)
        global_pos = timeline_canvas.mapToGlobal(QtCore.QPoint(int(x), int(y)))
        global_pos_f = QtCore.QPointF(float(global_pos.x()), float(global_pos.y()))

        press_event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            pos,
            global_pos_f,
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier
        )
        release_event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            pos,
            global_pos_f,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoButton,
            QtCore.Qt.NoModifier
        )

        QtWidgets.QApplication.postEvent(timeline_canvas, press_event)
        QtWidgets.QApplication.postEvent(timeline_canvas, release_event)
        return True
    except Exception:
        return False


def deselect_timeline(context):
    """Deselect all keys in the timeline / transport context (preserves curve/axis selection)."""
    keys_deselected = 0
    curves = _gather_scene_curves(context)

    for curve in curves:
        keys = getattr(curve, "Keys", None)
        if keys is not None:
            try:
                key_count = len(keys)
            except Exception:
                key_count = 0
            for idx in range(key_count):
                try:
                    key = keys[idx]
                    if getattr(key, "Selected", False):
                        key.Selected = False
                        keys_deselected += 1
                except Exception:
                    pass

    # Clear drag-selected colored timeline range
    _clear_timeline_selection_range(context)

    fcurves_service = getattr(context, "fcurves", None)
    if fcurves_service is not None:
        try:
            fcurves_service.invalidate()
        except Exception:
            pass

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None:
        try:
            evaluation.request_fcurve()
            if hasattr(evaluation, "flush_now"):
                evaluation.flush_now()
        except Exception:
            try:
                evaluation.request()
            except Exception:
                pass

    _refresh_timeline_ui(context)

    return {
        "keys": keys_deselected,
    }


def deselect_navigator(context):
    """Deselect all selected components/objects in the Navigator / Scene context."""
    sdk = getattr(context, "sdk", None) or _sdk()
    deselected = 0
    components = ()

    scene_index = getattr(context, "scene_index", None)
    if scene_index is not None:
        try:
            components = scene_index.components()
        except Exception:
            components = ()

    if not components:
        scene = getattr(context, "scene", None)
        if scene is None and sdk is not None:
            try:
                scene = sdk.FBSystem().Scene
            except Exception:
                scene = None
        if scene is not None:
            try:
                components = tuple(scene.Components)
            except Exception:
                components = ()

    for comp in components:
        try:
            if getattr(comp, "Selected", False):
                comp.Selected = False
                if not getattr(comp, "Selected", True):
                    deselected += 1
        except Exception:
            pass

    runtime = getattr(context, "_runtime", None)
    if runtime is not None and hasattr(runtime, "selection"):
        try:
            runtime.selection.invalidate()
        except Exception:
            pass
    elif hasattr(context, "selection") and hasattr(context.selection, "invalidate"):
        try:
            context.selection.invalidate()
        except Exception:
            pass

    evaluation = getattr(context, "evaluation", None)
    if evaluation is not None:
        try:
            evaluation.request()
        except Exception:
            pass

    return deselected


def deselect_all_contexts(context):
    """Deselect everything across Viewport, Navigator, FCurves, and Timeline."""
    viewport_count = deselect_viewport(context)
    navigator_count = deselect_navigator(context)
    fcurves_stats = deselect_fcurves(context)
    timeline_stats = deselect_timeline(context)

    return {
        "context": "all",
        "viewport_objects": viewport_count,
        "navigator_objects": navigator_count,
        "fcurve_keys": fcurves_stats["keys"],
        "timeline_keys": timeline_stats["keys"],
    }


def _resolve_target_context(context, target_context=None):
    if target_context:
        return str(target_context).strip().lower()

    snapshot = dict(getattr(context, "ui_context", {}) or {})
    hovered = str(snapshot.get("hovered") or "").strip().lower()
    active = str(snapshot.get("active") or "").strip().lower()

    known_contexts = {"viewer", "fcurve", "timeline", "navigator"}
    if hovered in known_contexts:
        return hovered

    # Check cursor position against known editor geometries
    cursor_pos = None
    input_router = getattr(context, "input", None)
    if input_router is not None and hasattr(input_router, "cursor_position"):
        try:
            cursor_pos = input_router.cursor_position()
        except Exception:
            cursor_pos = None

    if cursor_pos is not None:
        cx, cy = cursor_pos
        find_geo = getattr(context, "find_ui_surface_geometry", None)
        if callable(find_geo):
            for domain in ("viewer", "fcurve", "timeline"):
                try:
                    geo = find_geo(domain)
                    if geo is not None:
                        gx, gy, gw, gh = geo
                        if gx <= cx <= gx + gw and gy <= cy <= gy + gh:
                            return domain
                except Exception:
                    pass

    if active in known_contexts:
        return active
    return "all"


def execute(context, target_context=None):
    """Execute context-aware deselect all."""
    resolved_context = _resolve_target_context(context, target_context)
    result = {"context": resolved_context}

    undo = getattr(context, "undo", None)
    transaction_name = "Deselect All (%s)" % resolved_context.capitalize()

    def _perform_deselect():
        if resolved_context == "viewer":
            count = deselect_viewport(context)
            result["viewport_objects"] = count
        elif resolved_context == "fcurve":
            stats = deselect_fcurves(context)
            result.update(stats)
        elif resolved_context == "timeline":
            stats = deselect_timeline(context)
            result.update(stats)
        elif resolved_context == "navigator":
            count = deselect_navigator(context)
            result["navigator_objects"] = count
        else:
            stats = deselect_all_contexts(context)
            result.update(stats)

    if undo is not None and hasattr(undo, "transaction"):
        with undo.transaction(transaction_name):
            _perform_deselect()
    else:
        _perform_deselect()

    diagnostics = getattr(context, "diagnostics", None)
    record = getattr(diagnostics, "record", None)
    if callable(record):
        try:
            record("deselect_all_executed", FEATURE_ID, **result)
        except Exception:
            pass

    return result


class DeselectAllHotkeyService(object):
    """Own the context-aware 'A' key deselect binding through InputRouter."""

    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_context = None
        self.last_result = None
        self.last_error = None

    def start(self):
        if self.running:
            return self
        input_service = getattr(self.context, "input", None)
        if input_service is not None and hasattr(input_service, "configure_deselect_all_launcher"):
            input_service.configure_deselect_all_launcher(self._callback)
        self.running = True
        return self

    def execute(self, target_context=None):
        return execute(self.context, target_context=target_context)

    def stop(self):
        if self.context is not None:
            input_service = getattr(self.context, "input", None)
            if input_service is not None and hasattr(input_service, "clear_deselect_all_launcher"):
                try:
                    input_service.clear_deselect_all_launcher(self._callback)
                except Exception:
                    pass
        self.running = False

    def handle_key(self, payload=None):
        if not self.running:
            return False

        try:
            result = execute(self.context)
            self.last_context = result.get("context")
            self.last_result = result
            self.last_error = None
            return True
        except Exception as error:
            self.last_error = str(error)
            return False

    def status(self):
        return {
            "running": self.running,
            "binding": "A",
            "last_context": self.last_context,
            "last_result": self.last_result,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = DeselectAllHotkeyService(context)
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
