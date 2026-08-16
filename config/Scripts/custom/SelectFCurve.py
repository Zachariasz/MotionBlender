from pyfbsdk import FBFCurveEditorUtility

from mobu_tools_manager.fcurves.discovery import (
    _curve_for_node,
    focused_animation_nodes,
)

def select_all_keys_on_active_fcurves():
    # Use the FCurve editor's focused child channels. Selected key flags on a
    # hidden curve deliberately do not make that curve an action target.
    from pyfbsdk import FBSystem

    system = FBSystem()
    fcurves_to_process = set()
    try:
        layer_index = int(system.CurrentTake.GetCurrentLayer())
    except Exception:
        layer_index = None
    properties = []
    try:
        FBFCurveEditorUtility().GetProperties(properties, True)
    except Exception:
        properties = []
    for prop in properties:
        for node in focused_animation_nodes(prop):
            curve = _curve_for_node(node, layer_index)
            if curve:
                fcurves_to_process.add(curve)

    # PROCESS CURVES
    affected_count = 0
    
    for fcurve in fcurves_to_process:
        if not fcurve:
            continue
            
        has_selected_keys = False
        
        # Check if the FCurve has at least one selected key
        for key in fcurve.Keys:
            if key.Selected:
                has_selected_keys = True
                break
                
        # If true, select all keys on this specific FCurve
        if has_selected_keys:
            for key in fcurve.Keys:
                key.Selected = True
            affected_count += 1
            
    print(f"--- Script Finished. Selected keys on {affected_count} FCurve(s) ---")

select_all_keys_on_active_fcurves()
