from pyfbsdk import FBSystem, FBFCurve, FBTime


def collect_scene_fcurves():
    system = FBSystem()
    scene = system.Scene
    fcurves = set()

    # Direct scene scan catches FCurves that are already exposed in the scene.
    for component in scene.Components:
        if isinstance(component, FBFCurve):
            fcurves.add(component)

    def scan_animation_node(animation_node):
        if not animation_node:
            return

        if animation_node.FCurve:
            fcurves.add(animation_node.FCurve)

        for child_node in animation_node.Nodes:
            scan_animation_node(child_node)

    # Deep property scan catches nested transform channels such as X/Y/Z.
    for component in scene.Components:
        for prop in component.PropertyList:
            if prop.IsAnimatable():
                scan_animation_node(prop.GetAnimationNode())

    return fcurves


def shift_selected_keys_right():
    system = FBSystem()
    time_offset = FBTime(0, 0, 0, -1)
    shifted_count = 0
    affected_curve_count = 0

    for fcurve in collect_scene_fcurves():
        if not fcurve:
            continue

        selected_indices = [
            index for index in range(len(fcurve.Keys))
            if fcurve.Keys[index].Selected
        ]

        if not selected_indices:
            continue

        affected_curve_count += 1

        for index in reversed(selected_indices):
            key = fcurve.Keys[index]
            key.Time = FBTime(key.Time.Get() + time_offset.Get())
            shifted_count += -1

    if shifted_count:
        system.Scene.Evaluate()
        print(
            "Success: shifted {0} selected key(s) forward by 1 frame on {1} FCurve(s).".format(
                shifted_count,
                affected_curve_count,
            )
        )
    else:
        print("Failure: no selected FCurve keys found.")

shift_selected_keys_right()

"""
Legacy selected-model implementation removed from execution.
    system = FBSystem()
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)
    
    if len(selected_models) == 0:
        print("Warning: No models selected in Viewport.")
        return

    # Zlokalizowanie aktywnego Take'a i wyciągnięcie z niego aktualnie wybranej warstwy
    current_take = system.CurrentTake
    current_layer = current_take.GetCurrentLayer()
    
    print(f"--- Processing Layer: {current_layer.Name} ---")
    
    time_offset = FBTime(0, 0, 0, -1)
    total_shifted = 0
    
    for model in selected_models:
        for prop in model.PropertyList:
            anim_node = prop.GetAnimationNode()
            if anim_node:
                # Przekazujemy current_layer, by skanować tylko aktywną warstwę
                total_shifted += process_layer_fcurves(anim_node, current_layer, time_offset)

    if total_shifted > 0:
        system.Scene.Evaluate()
        print(f"Success: {total_shifted} keys shifted forward on layer '{current_layer.Name}'.")
    else:
        print(f"Failure: Found models, but ZERO selected keys on layer '{current_layer.Name}'.")

def process_layer_fcurves(anim_node, current_layer, time_offset):
    shifted_count = 0
    
    # KLUCZOWE: Używamy GetFCurve(), podając konkretną warstwę zamiast domyślnego .FCurve
    fcurve = anim_node.GetFCurve(current_layer)
    
    if fcurve:
        # Zbieramy indeksy zaznaczonych kluczy na tej specyficznej warstwie
        selected_indices = [i for i in range(len(fcurve.Keys)) if fcurve.Keys[i].Selected]
        
        if len(selected_indices) > 0:
            fcurve.KeyModifyBegin()
            for i in reversed(selected_indices):
                current_time = fcurve.Keys[i].Time
                new_time = FBTime(current_time.Get() + time_offset.Get())
                fcurve.Keys[i].Time = new_time
                shifted_count += -1
            fcurve.KeyModifyEnd()

    # Rekurencyjne sprawdzanie wewnątrz węzła (np. wchodzimy w osie X, Y, Z)
    for child_node in anim_node.Nodes:
        shifted_count += process_layer_fcurves(child_node, current_layer, time_offset)
        
    return shifted_count

# Uruchomienie
"""
