from pyfbsdk import *

def add_namespace_to_component(component, namespace):
    if isinstance(component, FBModel):
        componentName = component.LongName

        if ':' not in componentName:
            new_name_with_namespace = namespace + ':' + componentName
            component.LongName = new_name_with_namespace
            print("Namespace added for {}: {}".format(component.Name, new_name_with_namespace))

        for child in component.Children:
            add_namespace_to_component(child, namespace)

def add_namespace_to_selected_components():
    selectedComponents = FBModelList()
    FBGetSelectedModels(selectedComponents)

    for component in selectedComponents:
        namespace = FBMessageBoxGetUserValue(
            "Add Namespace",
            f"No namespace found for {component.Name}. Enter a new namespace: ",
            "",
            FBPopupInputType.kFBPopupString,
            "OK",
            "Cancel"
        )

        if namespace[0]:
            add_namespace_to_component(component, namespace[1])
        else:
            print("No new namespace provided for: {}".format(component.Name))

# Execute the function directly
add_namespace_to_selected_components()