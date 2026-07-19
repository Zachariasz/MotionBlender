from pyfbsdk import FBSystem, FBFCurve

def select_all_keys_on_active_fcurves():
    system = FBSystem()
    scene = system.Scene
    
    # Using a set to prevent processing the same FCurve multiple times
    fcurves_to_process = set()
    
    # METHOD 1: Direct Memory Scan
    # Grab all instances of FBFCurve directly from the Scene Components. 
    # This bypasses the hierarchy of Control Rigs and Effectors entirely.
    for comp in scene.Components:
        if isinstance(comp, FBFCurve):
            fcurves_to_process.add(comp)
            
    # METHOD 2: Deep Node Scan via IsAnimatable
    def scan_nodes(anim_node):
        if not anim_node:
            return
        if anim_node.FCurve:
            fcurves_to_process.add(anim_node.FCurve)
            
        for child in anim_node.Nodes:
            scan_nodes(child)

    for comp in scene.Components:
        for prop in comp.PropertyList:
            # Check IsAnimatable() instead of IsAnimated() to catch 
            # properties that only have keys on override layers (e.g., Layer2)
            if prop.IsAnimatable():
                node = prop.GetAnimationNode()
                if node:
                    scan_nodes(node)

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