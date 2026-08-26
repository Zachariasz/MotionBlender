"""Context-aware Deselect All for Viewport, FCurves, Timeline, and Navigator."""

from __future__ import absolute_import

import builtins

FEATURE_ID = "selection.deselect_all"
NATIVE_DESELECT_ACTION = "action.global.deselect"
_SERVICE = None


def _sdk():
    try:
        import pyfbsdk
        return pyfbsdk
    except ImportError:
        return None


def _normalized(value):
    return " ".join(str(value or "").replace("&", "").lower().split())


def _application_actions(application):
    """Yield native Qt actions without retaining MotionBuilder wrappers."""
    action_class = None
    try:
        from PySide6 import QtGui
        action_class = QtGui.QAction
    except ImportError:
        try:
            from PySide2 import QtGui
            action_class = QtGui.QAction
        except ImportError:
            pass

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
        actions = []
        callback = getattr(widget, "actions", None)
        if callable(callback):
            try:
                actions.extend(tuple(callback()))
            except Exception:
                pass
        if action_class is not None:
            callback = getattr(widget, "findChildren", None)
            if callable(callback):
                try:
                    actions.extend(tuple(callback(action_class)))
                except Exception:
                    pass
        for action in actions:
            if action is None or id(action) in seen:
                continue
            seen.add(id(action))
            yield action


def _action_values(action):
    values = []
    for name in ("objectName", "text", "iconText", "toolTip", "statusTip"):
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


def _trigger_native_deselect_action(context):
    """Run MotionBuilder's native deselect action when it is exposed to Qt."""
    application = getattr(context, "qt_application", None)
    if application is None:
        return False

    fallback = None
    for action in _application_actions(application):
        values = _action_values(action)
        if NATIVE_DESELECT_ACTION in values:
            fallback = action
            break
        if fallback is None and any(
            value in ("deselect", "deselect all", "select none")
            for value in values
        ):
            fallback = action
    if fallback is None:
        return False
    try:
        is_enabled = getattr(fallback, "isEnabled", None)
        if callable(is_enabled) and not is_enabled():
            return False
        fallback.trigger()
        return True
    except Exception:
        return False


def _manager(context):
    candidates = (
        getattr(context, "manager", None),
        getattr(context, "_manager", None),
        getattr(getattr(context, "_runtime", None), "manager", None),
        getattr(builtins, "_motionbuilder_tools_manager", None),
    )
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def _dispatch_native_deselect(context):
    """Use the host action so private Timeline/tangent selection also clears."""
    if _trigger_native_deselect_action(context):
        return "qt_action"

    manager = _manager(context)
    if manager is None:
        return None
    exists = getattr(manager, "native_action_exists", None)
    dispatch = getattr(manager, "dispatch_native_action", None)
    if not callable(dispatch):
        return None
    try:
        if callable(exists) and not exists(NATIVE_DESELECT_ACTION):
            return None
        dispatch(NATIVE_DESELECT_ACTION)
        return "keyboard_action"
    except Exception:
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
        if take is not None:
            for layer_idx in range(layer_count):
                try:
                    # FBAnimationNode.GetFCurve takes a layer index.  FBTake's
                    # GetLayer returns an FBAnimationLayer wrapper, which does
                    # not resolve the timeline's non-current-layer curves.
                    _add_curve(node.GetFCurve(layer_idx))
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


def _gather_fcurve_context_curves(context):
    """Fast-path curve gathering for the FCurve and Timeline contexts."""
    curves = []
    seen = set()

    def _add_curve(curve):
        if curve is not None and id(curve) not in seen:
            seen.add(id(curve))
            curves.append(curve)

    # 1. Gather displayed curves from FCurves service
    fcurves_service = getattr(context, "fcurves", None)
    if fcurves_service is not None:
        try:
            for curve in fcurves_service.displayed_fcurves():
                _add_curve(curve)
        except Exception:
            pass

    # 2. Gather curves from currently selected models (current take / layers)
    sdk = getattr(context, "sdk", None) or _sdk()
    if sdk is not None:
        selected_models = []
        try:
            mlist = sdk.FBModelList()
            sdk.FBGetSelectedModels(mlist)
            selected_models.extend(mlist)
        except Exception:
            pass

        system = sdk.FBSystem()
        take = getattr(context, "take", None) or system.CurrentTake
        layer_count = take.GetLayerCount() if take is not None and hasattr(take, "GetLayerCount") else 1

        def _walk_anim_node(node):
            if not node:
                return
            try:
                _add_curve(node.FCurve)
            except Exception:
                pass
            if take is not None:
                for l_idx in range(layer_count):
                    try:
                        _add_curve(node.GetFCurve(l_idx))
                    except Exception:
                        pass
            try:
                for child in getattr(node, "Nodes", ()):
                    _walk_anim_node(child)
            except Exception:
                pass

        for model in selected_models:
            try:
                for prop in model.PropertyList:
                    if prop.IsAnimatable():
                        _walk_anim_node(prop.GetAnimationNode())
            except Exception:
                pass
            try:
                _walk_anim_node(model.AnimationNode)
            except Exception:
                pass

    # If no active/selected curves found, fallback to scene-wide curves
    if not curves:
        return _gather_scene_curves(context)

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


def _clear_curve_key_selection(curves):
    """Clear selected and manipulation state without changing key data using EditBegin/EditEnd."""
    keys_deselected = 0
    for curve in curves:
        try:
            key_count = len(curve.Keys)
        except Exception:
            continue
        if key_count == 0:
            continue

        selected_indices = []
        for idx in range(key_count):
            try:
                if curve.KeyGetSelected(idx) or curve.KeyGetMarkedForManipulation(idx):
                    selected_indices.append(idx)
            except Exception:
                pass

        if not selected_indices:
            continue

        has_edit = False
        try:
            edit_begin = getattr(curve, "EditBegin", None)
            if callable(edit_begin):
                try:
                    edit_begin()
                    has_edit = True
                except Exception:
                    pass

            keys = curve.Keys
            for idx in selected_indices:
                try:
                    curve.KeySetSelected(idx, False)
                except Exception:
                    pass
                try:
                    curve.KeySetMarkedForManipulation(idx, False)
                except Exception:
                    pass
                try:
                    key = keys[idx]
                    key.Selected = False
                    key.MarkedForManipulation = False
                except Exception:
                    pass
                keys_deselected += 1
        finally:
            if has_edit:
                edit_end = getattr(curve, "EditEnd", None)
                if callable(edit_end):
                    try:
                        edit_end()
                    except Exception:
                        pass
    return keys_deselected


def _deselect_curve_context(context, fast_gather=True):
    if fast_gather:
        curves = _gather_fcurve_context_curves(context)
    else:
        curves = _gather_scene_curves(context)

    keys_deselected = _clear_curve_key_selection(curves)

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

    return keys_deselected


def deselect_fcurves(context):
    """Clear FCurve key state while preserving visible curve channels."""
    keys_deselected = _deselect_curve_context(context, fast_gather=True)

    return {
        "keys": keys_deselected,
    }


def deselect_timeline(context):
    """Clear Timeline keys across every layer without hiding FCurves."""
    keys_deselected = _deselect_curve_context(context, fast_gather=True)

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


def _classify_widget_text(widget):
    if widget is None:
        return "other"
    parts = []
    for name in ("objectName", "windowTitle", "accessibleName"):
        try:
            val = getattr(widget, name)()
        except Exception:
            val = ""
        if val:
            parts.append(str(val))
    try:
        parts.append(widget.metaObject().className())
    except Exception:
        parts.append(type(widget).__name__)
    text = " ".join(parts).lower()

    if any(n in text for n in ("fcurve", "curve editor", "fcurve_editor", "fcurvelist")):
        return "fcurve"
    if any(n in text for n in ("timecursor", "timeline", "transport", "timebar")):
        return "timeline"
    if any(n in text for n in ("navigator", "scene browser", "scene_browser")):
        return "navigator"
    if any(n in text for n in ("viewer", "render window", "viewport", "viewerwithrightbar", "view")):
        return "viewer"
    return "other"


def _resolve_target_context(context, target_context=None):
    if target_context:
        val = str(target_context).strip().lower()
        if val in ("viewer", "viewport", "3dviewport", "3d_viewport"):
            return "viewer"
        if val in ("fcurve", "fcurves", "fcurve_editor", "curve_editor"):
            return "fcurve"
        if val in ("timeline", "transport"):
            return "timeline"
        if val in ("navigator", "scene_browser"):
            return "navigator"
        return val

    snapshot = dict(getattr(context, "ui_context", {}) or {})
    hovered = str(snapshot.get("hovered") or "").strip().lower()
    known_contexts = {"viewer", "fcurve", "timeline", "navigator"}
    if hovered in known_contexts:
        return hovered

    # Check live Qt cursor and widgetAt
    try:
        try:
            from PySide6 import QtGui, QtWidgets
        except ImportError:
            from PySide2 import QtGui, QtWidgets
        point = QtGui.QCursor.pos()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            w = app.widgetAt(point)
            curr = w
            while curr is not None:
                classified = _classify_widget_text(curr)
                if classified in known_contexts:
                    return classified
                try:
                    curr = curr.parentWidget()
                except Exception:
                    break
    except Exception:
        pass

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
            for domain in ("fcurve", "timeline", "viewer", "navigator"):
                try:
                    geo = find_geo(domain)
                    if geo is not None:
                        gx, gy, gw, gh = geo
                        if gx <= cx <= gx + gw and gy <= cy <= gy + gh:
                            return domain
                except Exception:
                    pass

    active = str(snapshot.get("active") or "").strip().lower()
    if active in known_contexts:
        return active

    # Default fallback is always 3D Viewport ('viewer'), NEVER 'all'
    return "viewer"


def execute(context, target_context=None):
    """Execute context-aware deselect all."""
    resolved_context = _resolve_target_context(context, target_context)
    result = {"context": resolved_context}

    undo = getattr(context, "undo", None)
    transaction_name = "Deselect All (%s)" % resolved_context.capitalize()

    def _perform_deselect():
        if resolved_context == "fcurve":
            stats = deselect_fcurves(context)
            result.update(stats)
        elif resolved_context == "timeline":
            stats = deselect_timeline(context)
            result.update(stats)
        elif resolved_context == "navigator":
            count = deselect_navigator(context)
            result["navigator_objects"] = count
        else:
            count = deselect_viewport(context)
            result["viewport_objects"] = count

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

    def _current_binding(self):
        manager = getattr(getattr(self.context, "_runtime", None), "manager", None)
        if manager is None:
            manager = getattr(self.context, "manager", None)
        if manager is not None and hasattr(manager, "binding"):
            try:
                b = manager.binding(FEATURE_ID)
                if b:
                    return str(b).strip()
            except Exception:
                pass
        return "A"

    def status(self):
        return {
            "running": self.running,
            "binding": self._current_binding(),
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
