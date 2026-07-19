from pyfbsdk import *

def remove_all_namespaces(node):
    """
    Recursively removes namespaces from the given node and its children.
    """
    # Remove namespace from the current object
    node.ProcessObjectNamespace(FBNamespaceAction.kFBRemoveAllNamespace, "")
    
    # Recursive call for all children
    for child in node.Children:
        remove_all_namespaces(child)

def select_hierarchy(node, include_current, is_root=True):
    """
    Recursively selects the hierarchy. If skipping the root (Empty), 
    it starts selecting from the immediate children.
    """
    if is_root:
        node.Selected = include_current
    else:
        node.Selected = True
        
    for child in node.Children:
        select_hierarchy(child, include_current, False)

def export_rig_animations():
    system = FBSystem()
    app = FBApplication()
    
    # 1. Get currently selected models
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models)
    
    if len(selected_models) == 0:
        FBMessageBox("Selection Error", "Please select the root (Empty) of the rig first.", "OK")
        return
        
    root_node = selected_models[0]
    
    # 2. Remove existing namespaces from the rig
    remove_all_namespaces(root_node)
    
    # 3. Prompt user about including the root (Empty)
    dialog_result = FBMessageBox(
        "Export Options",
        "Do you want to export the selected rig with the first element in the hierarchy (Empty) or skip it?",
        "Include Empty",
        "Skip Empty",
        "Cancel"
    )
    
    # Handle user decision
    if dialog_result == 3: # Cancel button pressed
        print("Export cancelled by user.")
        return
        
    include_root = (dialog_result == 1)
    
    # 4. Clear current selection in the Scene
    for comp in system.Scene.Components:
        comp.Selected = False
        
    # 5. Select appropriate hierarchy based on user choice
    select_hierarchy(root_node, include_root, is_root=True)
    
    # Verify if anything is actually selected after hierarchy traversal
    new_selection = FBModelList()
    FBGetSelectedModels(new_selection)
    if len(new_selection) == 0:
        FBMessageBox("Export Error", "Nothing to export! The rig might be empty inside.", "OK")
        return
    
    # 6. File save popup setup
    popup = FBFilePopup()
    popup.Style = FBFilePopupStyle.kFBFilePopupSave
    popup.Filter = "*.fbx"
    popup.Title = "Save Animations (FBX)"
    
    # Execute save if user confirms path
    if popup.Execute():
        export_path = popup.FullFilename
        
        # FBFbxOptions(False) creates options for Saving
        save_options = FBFbxOptions(False)
        save_options.SaveSelectedModelsOnly = True
        
        # Save the file (all current Takes are exported implicitly for the selected models)
        success = app.FileSave(export_path, save_options)
        
        if success:
            FBMessageBox("Success", "All animations exported successfully!", "OK")
        else:
            FBMessageBox("Error", "Failed to export animations.", "OK")

# Execute script
if __name__ in ("__main__", "__builtin__"):
    export_rig_animations()