from pyfbsdk import *

def remove_namespace_from_component(component):
    if isinstance(component, FBModel):
        componentName = component.LongName
        print("Processing:", componentName)
        print("The component is an instance of FBModel.")
        if ':' in componentName:
            print("Namespace found in:", componentName)
            # Splitting the component's name by ':' and taking the last part
            newName = componentName.split(':')[-1]
            print("New Name without namespace:", newName)
            # Create a new name without the namespace '::'
            newName = newName.split('::')[-1]
            print("Final Name without namespace:", newName)
            # Set the new name for the component
            component.LongName = newName
            print("Namespace removed for:", component.Name)
        
        # Process child components (recursively)
        for child in component.Children:
            remove_namespace_from_component(child)
    else:
        print("The component is NOT an instance of FBModel.")

def remove_namespace_from_selected_components():
    selectedComponents = FBModelList()
    FBGetSelectedModels(selectedComponents)

    for component in selectedComponents:
        remove_namespace_from_component(component)

# Execute the function directly
remove_namespace_from_selected_components()