"""Standalone & Manager entrypoint for Deselect All."""

from __future__ import absolute_import

import builtins


def main():
    manager = getattr(builtins, "_motionbuilder_tools_manager", None)
    if manager is not None and hasattr(manager, "runtime") and manager.runtime is not None:
        try:
            from mobu_tools_manager.features import deselect_all
            return deselect_all.execute(manager.runtime.context)
        except Exception:
            pass

    try:
        from mobu_tools_manager.features import deselect_all
        from mobu_tools_manager import get_manager
        return deselect_all.execute(get_manager().runtime.context)
    except Exception:
        pass

    # Fallback to direct pyfbsdk execution
    import pyfbsdk as sdk

    # 1. Deselect models
    model_list = sdk.FBModelList()
    sdk.FBGetSelectedModels(model_list)
    for model in model_list:
        try:
            model.Selected = False
        except Exception:
            pass

    # 2. Deselect all components in scene
    system = sdk.FBSystem()
    scene = system.Scene
    for comp in scene.Components:
        try:
            if getattr(comp, "Selected", False):
                comp.Selected = False
        except Exception:
            pass

    # 3. Deselect keys on all fcurves (preserves curve and axis selection)
    take = system.CurrentTake
    for comp in scene.Components:
        if isinstance(comp, sdk.FBFCurve):
            try:
                for key in comp.Keys:
                    if key.Selected:
                        key.Selected = False
            except Exception:
                pass
        try:
            props = tuple(comp.PropertyList)
        except Exception:
            props = ()
        for prop in props:
            try:
                if not prop.IsAnimatable():
                    continue
                node = prop.GetAnimationNode()
                if node:
                    _clear_node_keys(node, take=take)
            except Exception:
                pass

    try:
        scene.Evaluate()
    except Exception:
        pass


def _clear_node_keys(node, take=None):
    try:
        curve = getattr(node, "FCurve", None)
        if curve:
            for key in curve.Keys:
                if key.Selected:
                    key.Selected = False
        if take is not None and hasattr(take, "GetLayerCount"):
            for l_idx in range(take.GetLayerCount()):
                layer = take.GetLayer(l_idx)
                if layer is not None:
                    layer_curve = node.GetFCurve(layer)
                    if layer_curve is not None:
                        for key in layer_curve.Keys:
                            if key.Selected:
                                key.Selected = False
    except Exception:
        pass
    try:
        children = tuple(node.Nodes)
    except Exception:
        children = ()
    for child in children:
        _clear_node_keys(child, take=take)


if __name__ == "__main__" or __name__ == "builtins":
    main()
