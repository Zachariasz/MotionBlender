from __future__ import absolute_import

import builtins

FEATURE_ID = "scene.grid_axis_lines"
GRID_HALF_LENGTH = 500.0
LINE_HEIGHT = 0.0
X_AXIS_NAME = "Grid Axis Guide - X Red"
Z_AXIS_NAME = "Grid Axis Guide - Z Blue"
PARENT_NULL_NAME = "Scene"
TRANSFORM_PROPERTY_NAME_GROUPS = (
    ("Translation (Lcl)", "Lcl Translation"),
    ("Rotation (Lcl)", "Lcl Rotation"),
    ("Scaling (Lcl)", "Lcl Scaling")
)
AXIS_DUPLICATE_SEPARATORS = (" ", "_", ".", "(", "-")
LEGACY_SERVICE_ATTR = "_grid_axis_lines_autostart_service"
_SDK = None


def _sdk(context=None):
    sdk = getattr(context, "sdk", None)
    if sdk is None:
        runtime = getattr(context, "_runtime", None)
        if runtime is not None:
            sdk = getattr(runtime, "sdk", None)
    if sdk is None:
        import pyfbsdk
        sdk = pyfbsdk
    return sdk


def set_if_available(model, attribute_name, value):
    try:
        setattr(model, attribute_name, value)
    except Exception:
        pass


def model_name_values(model):
    values = []
    for attr in ("Name", "LongName"):
        val = getattr(model, attr, None)
        if isinstance(val, str) and val:
            values.append(val)
    return values


def short_model_name(value):
    s = str(value or "")
    s = s.replace("\\", "/")
    for sep in ("/", "::", ":"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s


def model_name_matches(model, name):
    for val in model_name_values(model):
        if val == name or val.endswith("::" + name):
            return True
    return False


def is_path_model(model, sdk):
    cls = getattr(sdk, "FBModelPath3D", ())
    try:
        if isinstance(model, cls):
            return True
    except TypeError:
        pass
    return all(hasattr(model, a) for a in ("PathKeyGetCount", "PathKeySet", "PathKeyRemove"))


def axis_name_matches(model, base_name, sdk):
    if not is_path_model(model, sdk):
        return False
    for val in model_name_values(model):
        sn = short_model_name(val)
        if sn == base_name:
            return True
        if any(sn.startswith(base_name + sep) for sep in AXIS_DUPLICATE_SEPARATORS):
            return True
    return False


def model_has_exact_short_name(model, name):
    for v in model_name_values(model):
        if short_model_name(v) == name:
            return True
    return False


def set_model_name(model, name):
    try:
        model.SetName(name)
    except Exception:
        pass
    try:
        model.Name = name
    except Exception:
        pass


def _scene_components(context, sdk):
    if hasattr(context, "scene") and context.scene is not None:
        return tuple(context.scene.Components)
    try:
        return tuple(sdk.FBSystem().Scene.Components)
    except Exception:
        return ()


def choose_axis_path(base_name, context=None, sdk=None):
    sdk = sdk or _sdk(context)
    candidates = [c for c in _scene_components(context, sdk) if axis_name_matches(c, base_name, sdk)]
    if not candidates:
        return sdk.FBModelPath3D(base_name)
    primary = next((c for c in candidates if model_has_exact_short_name(c, base_name)), candidates[0])
    for c in candidates:
        if c is not primary:
            try:
                c.FBDelete()
            except Exception:
                pass
    if not model_has_exact_short_name(primary, base_name):
        set_model_name(primary, base_name)
    return primary


def find_model_by_name(name, context=None, sdk=None):
    sdk = sdk or _sdk(context)
    finder = getattr(sdk, "FBFindModelByLabelName", None)
    if callable(finder):
        m = finder(name)
        if m is not None:
            return m
    for comp in _scene_components(context, sdk):
        if model_name_matches(comp, name):
            return comp
    return None


def find_property(model, property_names):
    for name in property_names:
        try:
            p = model.PropertyList.Find(name)
        except Exception:
            p = None
        if p is not None:
            return p
    return None


def lock_scene_null_transforms(scene_null):
    for group in TRANSFORM_PROPERTY_NAME_GROUPS:
        prop = find_property(scene_null, group)
        if prop is not None:
            try:
                for i in range(3):
                    prop.SetMemberLocked(i, True)
                prop.SetLocked(True)
            except Exception:
                pass
    set_if_available(scene_null, "Transformable", False)


def get_scene_null(context=None, sdk=None):
    sdk = sdk or _sdk(context)
    scene_null = find_model_by_name(PARENT_NULL_NAME, context, sdk)
    if scene_null is None:
        scene_null = sdk.FBModelNull(PARENT_NULL_NAME)
        set_if_available(scene_null, "Show", True)
        set_if_available(scene_null, "Visibility", True)
        set_if_available(scene_null, "Translation", sdk.FBVector3d(0.0, 0.0, 0.0))
        set_if_available(scene_null, "Rotation", sdk.FBVector3d(0.0, 0.0, 0.0))
        set_if_available(scene_null, "Scaling", sdk.FBVector3d(1.0, 1.0, 1.0))
    else:
        set_if_available(scene_null, "Show", True)
        set_if_available(scene_null, "Visibility", True)
    lock_scene_null_transforms(scene_null)
    return scene_null


def configure_axis_path(path, translation, start_point, end_point, color, parent, sdk):
    set_if_available(path, "Show", True)
    set_if_available(path, "Visibility", True)
    set_if_available(path, "Color", color)
    set_if_available(path, "Pickable", False)
    set_if_available(path, "Transformable", False)
    set_if_available(path, "PathLengthShow", False)
    try:
        path.ShowCurveControls(False)
    except Exception:
        pass
    try:
        path.ShowCurvePoints(False)
    except Exception:
        pass
    while path.PathKeyGetCount() > 2:
        path.PathKeyRemove(path.PathKeyGetCount() - 1)
    while path.PathKeyGetCount() < 2:
        path.PathKeyEndAdd(sdk.FBVector4d(0.0, LINE_HEIGHT, 0.0, 0.0))
    path.PathKeySet(0, start_point)
    path.PathKeySet(1, end_point)
    set_if_available(path, "Selected", False)
    set_if_available(path, "Parent", parent)
    try:
        path.SetVector(translation, sdk.FBModelTransformationType.kModelTranslation, True)
    except Exception:
        set_if_available(path, "Translation", translation)
    try:
        path.SetVector(sdk.FBVector3d(0.0, 0.0, 0.0), sdk.FBModelTransformationType.kModelRotation, True)
    except Exception:
        set_if_available(path, "Rotation", sdk.FBVector3d(0.0, 0.0, 0.0))
    return path


def create_grid_axis_lines(context=None):
    sdk = _sdk(context)
    parent = get_scene_null(context, sdk)
    half = float(GRID_HALF_LENGTH)
    y = float(LINE_HEIGHT)
    x_axis = configure_axis_path(
        choose_axis_path(X_AXIS_NAME, context, sdk),
        sdk.FBVector3d(-half, y, 0.0),
        sdk.FBVector4d(0.0, 0.0, 0.0, 0.0),
        sdk.FBVector4d(half * 2.0, 0.0, 0.0, 0.0),
        sdk.FBColor(1.0, 0.0, 0.0),
        parent,
        sdk
    )
    z_axis = configure_axis_path(
        choose_axis_path(Z_AXIS_NAME, context, sdk),
        sdk.FBVector3d(0.0, y, -half),
        sdk.FBVector4d(0.0, 0.0, 0.0, 0.0),
        sdk.FBVector4d(0.0, 0.0, half * 2.0, 0.0),
        sdk.FBColor(0.0, 0.25, 1.0),
        parent,
        sdk
    )
    if hasattr(context, "scene_index") and hasattr(context.scene_index, "invalidate"):
        try:
            context.scene_index.invalidate()
        except Exception:
            pass
    if hasattr(context, "evaluation"):
        try:
            context.evaluation.request()
        except Exception:
            pass
    else:
        try:
            sdk.FBSystem().Scene.Evaluate()
        except Exception:
            pass
    return (x_axis, z_axis)


def retire_legacy_service():
    service = getattr(builtins, LEGACY_SERVICE_ATTR, None)
    if service is not None:
        try:
            service.stop()
        except Exception:
            pass
        setattr(builtins, LEGACY_SERVICE_ATTR, None)


class GridAxisLinesService(object):
    def __init__(self, context):
        self.context = context
        self.running = False
        self.run_count = 0
        self.last_reason = None
        self.last_error = None
        self._open_callback = self._on_file_open_completed
        self._new_callback = self._on_file_new_completed
        self._application = None

    def _record(self, event, **data):
        try:
            self.context.diagnostics.record(event, FEATURE_ID, **data)
        except Exception:
            pass

    def _resolve_application(self):
        app = getattr(self.context, "application", None)
        if app is None:
            sdk = _sdk(self.context)
            app = sdk.FBApplication()
        return app

    def start(self):
        if self.running:
            return self
        retire_legacy_service()
        app = self._resolve_application()
        try:
            app.OnFileOpenCompleted.Add(self._open_callback)
            app.OnFileNewCompleted.Add(self._new_callback)
        except Exception:
            pass
        self._application = app
        self.running = True
        self.ensure_axes("startup")
        self._record("grid_axis_lines_started")
        return self

    def stop(self):
        if self._application is not None:
            try:
                self._application.OnFileOpenCompleted.Remove(self._open_callback)
                self._application.OnFileNewCompleted.Remove(self._new_callback)
            except Exception:
                pass
        self._application = None
        self.running = False
        self._record("grid_axis_lines_stopped")

    def ensure_axes(self, reason="manual"):
        try:
            axes = create_grid_axis_lines(self.context)
            self.run_count += 1
            self.last_reason = reason
            self.last_error = None
            self._record("grid_axis_lines_ensured")
            return axes
        except Exception as exc:
            self.last_error = str(exc)
            self._record("grid_axis_lines_error", error=str(exc))
            return None

    def _on_file_open_completed(self, control=None, event=None):
        if self.running:
            self.ensure_axes("file_open_completed")

    def _on_file_new_completed(self, control=None, event=None):
        if self.running:
            self.ensure_axes("file_new_completed")

    def execute(self, context=None):
        return self.ensure_axes("execute")

    def status(self):
        return {
            "running": self.running,
            "run_count": self.run_count,
            "last_reason": self.last_reason,
            "last_error": self.last_error
        }


_SERVICE = None


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = GridAxisLinesService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.stop()
        _SERVICE = None


def execute(context):
    global _SERVICE
    if _SERVICE is None:
        start(context)
    return _SERVICE.execute(context)


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
