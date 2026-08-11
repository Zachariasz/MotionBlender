"""
Find Selected in Hierarchy (Unroll Scene Browser Location)
----------------------------------------------------------
Unrolls / expands the hierarchy in MotionBuilder Scene Browser to reveal
and center the location of all currently selected objects in the scene.
"""

import sys
import traceback

from pyfbsdk import (
    FBApplication,
    FBGetSelectedModels,
    FBMessageBox,
    FBModelList,
    FBSystem,
)

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets


TOOL_NAME = "Find Selected in Hierarchy"

CONTAINER_NAMES = set([
    "Scene", "Models", "Cameras", "Lights", "Materials", "Shaders",
    "Textures", "Video", "Characters", "Character Extensions", "Constraints",
    "Groups", "Sets", "Poses", "Scripts", "Audio", "Renderers"
])


def update_status(message):
    """Safely updates MotionBuilder status bar."""
    try:
        FBApplication().UpdateStatusBar(message)
    except Exception:
        pass


def get_selected_targets():
    """Returns a list of selected models and components in the MotionBuilder scene."""
    targets = []

    # 1. Fetch selected models
    selected_models = FBModelList()
    FBGetSelectedModels(selected_models, None, True, True)
    for model in selected_models:
        if model not in targets:
            targets.append(model)

    # 2. Check scene components for selected items if no models found, or add other selected components
    scene = FBSystem().Scene
    for comp in scene.Components:
        if getattr(comp, "Selected", False) and comp not in targets:
            targets.append(comp)

    return targets


def get_name_variants(obj):
    """Returns a set of string name variants for tree node matching."""
    names = set()
    if hasattr(obj, "Name") and obj.Name:
        s_name = str(obj.Name)
        names.add(s_name)
        if ":" in s_name:
            names.add(s_name.split(":")[-1])

    if hasattr(obj, "LongName") and obj.LongName:
        s_long = str(obj.LongName)
        names.add(s_long)
        if ":" in s_long:
            names.add(s_long.split(":")[-1])

    return names


def get_parent_chain(obj):
    """Builds a list of parent objects from root down to obj."""
    chain = []
    curr = obj
    while curr:
        chain.append(curr)
        curr = getattr(curr, "Parent", None)
    chain.reverse()
    return chain


def find_scene_browser_tree_views():
    """Finds QTreeView / tree widgets in MotionBuilder's UI safely to avoid GC crashes."""
    app = QtWidgets.QApplication.instance()
    if not app:
        return []

    tree_views = []

    for top_level in app.topLevelWidgets():
        try:
            # Safely find all QWidgets within this top level window
            widgets = top_level.findChildren(QtWidgets.QWidget)
            widgets.append(top_level) # Also check the top level window itself!
            
            for w in widgets:
                try:
                    is_tree = False
                    if isinstance(w, (QtWidgets.QTreeView, QtWidgets.QTreeWidget)):
                        is_tree = True
                    elif hasattr(w, "inherits") and (w.inherits("QTreeView") or w.inherits("QAbstractItemView")):
                        is_tree = True
                    else:
                        cls_name = w.metaObject().className() if hasattr(w, "metaObject") and w.metaObject() else ""
                        if "tree" in cls_name.lower():
                            is_tree = True
                            
                    if is_tree and w not in tree_views:
                        if hasattr(w, "model") and w.model() is not None:
                            tree_views.append(w)
                except Exception:
                    pass
        except Exception:
            pass

    return tree_views


def safe_expand(tree_view, index):
    """Safely expands a QModelIndex on tree_view."""
    if not index.isValid():
        return
    try:
        if hasattr(tree_view, "expand"):
            tree_view.expand(index)
        else:
            QtCore.QMetaObject.invokeMethod(
                tree_view, "expand",
                QtCore.Q_ARG(QtCore.QModelIndex, index)
            )
    except Exception:
        pass


def expand_all_ancestors(tree_view, index):
    """Expands all parent QModelIndexes of index up to the root."""
    parent = index.parent()
    while parent.isValid():
        safe_expand(tree_view, parent)
        parent = parent.parent()


def search_and_expand_model(tree_view, model, parent_index, target_name_sets, ancestor_name_set, found_indices, visited_indices=None):
    """
    Recursively inspects the tree model:
    - If a node matches a container or ancestor, expands it so children become visible.
    - If a node matches a target object, records its index and expands all its ancestors.
    """
    if visited_indices is None:
        visited_indices = set()

    if parent_index.isValid():
        key = (parent_index.internalId() if hasattr(parent_index, "internalId") else 0, parent_index.row(), parent_index.column())
        if key in visited_indices:
            return
        visited_indices.add(key)

    if parent_index.isValid() and hasattr(model, "canFetchMore") and model.canFetchMore(parent_index):
        try:
            model.fetchMore(parent_index)
        except Exception:
            pass

    row_count = model.rowCount(parent_index)

    for r in range(row_count):
        index = model.index(r, 0, parent_index)
        if not index.isValid():
            continue

        disp = model.data(index, QtCore.Qt.DisplayRole)
        tooltip = model.data(index, QtCore.Qt.ToolTipRole)
        user_data = model.data(index, QtCore.Qt.UserRole)

        texts = set()
        for t in (disp, tooltip, user_data):
            if t is not None:
                st = str(t)
                texts.add(st)
                if ":" in st:
                    texts.add(st.split(":")[-1])

        # Check if node matches target object
        is_target_match = False
        for names_set in target_name_sets:
            if not texts.isdisjoint(names_set):
                is_target_match = True
                break

        if is_target_match:
            found_indices.append(index)
            expand_all_ancestors(tree_view, index)
            safe_expand(tree_view, index)
        else:
            # Check if node matches container or ancestor in parent chain
            is_ancestor_or_container = not texts.isdisjoint(ancestor_name_set) or not texts.isdisjoint(CONTAINER_NAMES)
            if is_ancestor_or_container:
                safe_expand(tree_view, index)

        # Recurse into children
        search_and_expand_model(tree_view, model, index, target_name_sets, ancestor_name_set, found_indices, visited_indices)


def find_selected_in_hierarchy():
    """Main entrypoint: Finds selected object in hierarchy and unrolls all parent objects in Scene Browser."""
    targets = get_selected_targets()
    if not targets:
        update_status("Find in Hierarchy: No object selected.")
        FBMessageBox(TOOL_NAME, "Please select an object in the scene first.", "OK")
        return

    tree_views = find_scene_browser_tree_views()
    if not tree_views:
        update_status("Find in Hierarchy: Could not locate Scene Browser tree view.")
        FBMessageBox(TOOL_NAME, "Could not locate Scene Browser tree view in MotionBuilder UI.", "OK")
        return

    target_name_sets = [get_name_variants(obj) for obj in targets]

    ancestor_name_set = set()
    for obj in targets:
        chain = get_parent_chain(obj)
        for ancestor in chain:
            ancestor_name_set.update(get_name_variants(ancestor))

    total_found = 0

    for tree_view in tree_views:
        model = tree_view.model()
        if not model:
            continue

        found_indices = []

        # Traverse tree view from root
        search_and_expand_model(
            tree_view=tree_view,
            model=model,
            parent_index=QtCore.QModelIndex(),
            target_name_sets=target_name_sets,
            ancestor_name_set=ancestor_name_set,
            found_indices=found_indices,
        )

        if found_indices:
            try:
                if hasattr(tree_view, "selectionModel"):
                    selection_model = tree_view.selectionModel()
                    if selection_model:
                        selection_model.clearSelection()
                        for idx in found_indices:
                            expand_all_ancestors(tree_view, idx)
                            selection_model.select(
                                idx,
                                QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
                            )
            except Exception:
                pass

            first_idx = found_indices[0]
            try:
                if hasattr(tree_view, "setCurrentIndex"):
                    tree_view.setCurrentIndex(first_idx)
            except Exception:
                pass

            try:
                if hasattr(tree_view, "scrollTo"):
                    tree_view.scrollTo(first_idx, QtWidgets.QAbstractItemView.PositionAtCenter)
            except Exception:
                pass

            try:
                if hasattr(tree_view, "setFocus"):
                    tree_view.setFocus()
            except Exception:
                pass

            total_found += len(found_indices)

    msg = "Unrolled hierarchy for %d selected object(s) (%d match(es) shown in Scene Browser)." % (len(targets), total_found)
    update_status(msg)
    print("[%s] %s" % (TOOL_NAME, msg))


def run_with_error_dialog():
    try:
        find_selected_in_hierarchy()
    except Exception:
        FBMessageBox(TOOL_NAME + " Error", traceback.format_exc(), "OK")


if __name__ == "__main__":
    run_with_error_dialog()
