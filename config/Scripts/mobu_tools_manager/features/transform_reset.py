from __future__ import absolute_import

# Feature identifiers and undo labels
FEATURE_ID_TRANSLATION = "transform.reset_translation"
FEATURE_ID_ROTATION = "transform.reset_rotation"
FEATURE_ID_SCALE = "transform.reset_scale"

UNDO_LABEL_TRANSLATION = "Reset Local Translation"
UNDO_LABEL_ROTATION = "Reset Local Rotation"
UNDO_LABEL_SCALE = "Reset Local Scale"

def _sdk(context=None):
    """Return the SDK object from context or import pyfbsdk."""
    sdk = getattr(context, "sdk", None)
    if sdk is not None:
        return sdk
    runtime = getattr(context, "_runtime", None)
    if runtime is not None:
        sdk = getattr(runtime, "sdk", None)
        if sdk is not None:
            return sdk
    import pyfbsdk
    return pyfbsdk

def _record(context, feature_id, event, **data):
    """Record diagnostics if available."""
    try:
        diag = getattr(context, "diagnostics", None)
        if diag is not None:
            context.diagnostics.record(event, feature_id, **data)
    except Exception:
        pass

def _selected_transformable_models(context):
    """Return a tuple of selected transformable models."""
    selection = getattr(context, "selection", None)
    mlist = None
    if selection is not None:
        snap = getattr(selection, "snapshot", None)
        if callable(snap):
            try:
                mlist = tuple(snap())
            except Exception:
                mlist = None
        if mlist is None:
            try:
                mlist = tuple(selection)
            except Exception:
                mlist = None
    if mlist is None:
        try:
            sdk = _sdk(context)
            mlist_obj = sdk.FBModelList()
            sdk.FBGetSelectedModels(mlist_obj)
            mlist = tuple(mlist_obj)
        except Exception:
            mlist = ()
    # Filter models
    seen_ids = set()
    filtered = []
    for m in mlist:
        if m is None or id(m) in seen_ids:
            continue
        seen_ids.add(id(m))
        try:
            if not getattr(m, "Transformable", True):
                continue
            if hasattr(m, "IsValid") and callable(m.IsValid) and not m.IsValid():
                continue
        except Exception:
            continue
        filtered.append(m)
    return tuple(filtered)

def _apply_local_vector(model, sdk, kind, values):
    """Apply local vector to model."""
    vec = sdk.FBVector3d(float(values[0]), float(values[1]), float(values[2]))
    enum_attr = None
    prop_attr = None
    if kind == "translation":
        enum_attr = "kModelTranslation"
        prop_attr = "Translation"
    elif kind == "rotation":
        enum_attr = "kModelRotation"
        prop_attr = "Rotation"
    elif kind == "scale":
        enum_attr = "kModelScaling"
        prop_attr = "Scaling"
    # Try SetVector
    try:
        transform_type = getattr(getattr(sdk, "FBModelTransformationType", None), enum_attr, None)
        if transform_type is not None and hasattr(model, "SetVector"):
            model.SetVector(vec, transform_type, False)
    except Exception:
        pass
    # Try setting property directly
    try:
        setattr(model, prop_attr, vec)
    except Exception:
        pass

def _evaluate_and_notify(context, sdk, models):
    """Evaluate scene and notify HIK if needed."""
    # HIK target evaluation
    if hasattr(context, "hik"):
        for m in models:
            try:
                if context.hik.find_target(context, m):
                    break
            except Exception:
                pass
        else:
            m = None
        if m is not None:
            try:
                scene = getattr(context, "scene", None)
                if scene is not None:
                    context.scene.CandidateEvaluationAndResolve()
            except Exception:
                pass
    # Evaluation request
    if hasattr(context, "evaluation"):
        try:
            context.evaluation.request()
        except Exception:
            try:
                if hasattr(context.evaluation, "flush_now") and not getattr(context.evaluation, "request", None):
                    context.evaluation.flush_now()
            except Exception:
                pass
    else:
        # Fallback to SDK evaluate
        try:
            sdk.FBSystem().Scene.Evaluate()
        except Exception:
            pass

def _reset_transform(context, kind, feature_id, undo_label, default_values):
    """Core reset transform logic."""
    models = _selected_transformable_models(context)
    if not models:
        _record(context, feature_id, "transform_reset_noop", reason="empty_selection", kind=kind)
        return {"reset_count": 0, "kind": kind}
    sdk = _sdk(context)
    tx = None
    try:
        undo = getattr(context, "undo", None)
        if undo is not None and hasattr(undo, "begin"):
            tx = context.undo.begin(undo_label)
            for model in models:
                try:
                    tx.add_model_trs(model)
                except Exception:
                    pass
                # Try adding property
                try:
                    prop = getattr(model.PropertyList.Find(kind), "Property", None)
                    if prop is not None:
                        tx.add_property(prop)
                except Exception:
                    pass
    except Exception:
        tx = None
    reset_count = 0
    try:
        for model in models:
            _apply_local_vector(model, sdk, kind, default_values)
            reset_count += 1
        if tx is not None:
            tx.commit()
    except Exception as e:
        if tx is not None:
            tx.cancel()
        raise e
    _evaluate_and_notify(context, sdk, models)
    _record(context, feature_id, "transform_reset_applied", kind=kind, reset_count=reset_count)
    return {"reset_count": reset_count, "kind": kind}

def reset_translation(context, invocation=None):
    """Reset local translation of selected models."""
    return _reset_transform(
        context,
        "translation",
        FEATURE_ID_TRANSLATION,
        UNDO_LABEL_TRANSLATION,
        (0.0, 0.0, 0.0)
    )

def reset_rotation(context, invocation=None):
    """Reset local rotation of selected models."""
    return _reset_transform(
        context,
        "rotation",
        FEATURE_ID_ROTATION,
        UNDO_LABEL_ROTATION,
        (0.0, 0.0, 0.0)
    )

def reset_scale(context, invocation=None):
    """Reset local scale of selected models."""
    return _reset_transform(
        context,
        "scale",
        FEATURE_ID_SCALE,
        UNDO_LABEL_SCALE,
        (1.0, 1.0, 1.0)
    )

def execute(context, invocation=None):
    """Dispatch based on kind or feature_id in invocation."""
    if not isinstance(invocation, dict):
        return reset_translation(context)
    kind = invocation.get("kind")
    fid = invocation.get("feature_id")
    if fid == FEATURE_ID_TRANSLATION or kind == "translation":
        return reset_translation(context)
    if fid == FEATURE_ID_ROTATION or kind == "rotation":
        return reset_rotation(context)
    if fid == FEATURE_ID_SCALE or kind == "scale":
        return reset_scale(context)
    # Default
    return reset_translation(context)
