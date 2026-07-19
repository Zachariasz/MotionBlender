from pyfbsdk import FBSystem

def destroy_component_and_children(component):
    # Recursively destroy the component and its children
    for child in list(component.Components):
        destroy_component_and_children(child)

    try:
        component.FBDelete()
    except Exception as e:
        pass

def is_component_selected(component):
    # Check if the given component is selected
    return component.Selected

def remove_selected_components_and_children():
    # Get all components in the scene
    component_list = FBSystem().Scene.Components

    # Create a list to store components to be deleted
    components_to_delete = []

    # Iterate through each component and add it to the list if selected
    for component in component_list:
        if is_component_selected(component):
            components_to_delete.append(component)

    # Iterate through the list of components to be deleted and remove them along with their children
    for component in components_to_delete:
        destroy_component_and_children(component)

def main():
    remove_selected_components_and_children()

# Call the main function directly
main()