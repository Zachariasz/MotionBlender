"""Visible/current-layer FCurve discovery.

MotionBuilder stores a vector property's X/Y/Z curves below one animation
node.  The FCurve editor records which of those submembers are visible through
``FBProperty.IsFocusedChild``; walking every child node would therefore revive
hidden curves that still have selected keys.
"""

from __future__ import absolute_import


class CurveRecord(object):
    def __init__(self, prop, node, curve):
        self.property = prop
        self.node = node
        self.curve = curve


def _curve_for_node(node, layer):
    curve = None
    if layer is not None:
        try:
            curve = node.GetFCurve(layer)
        except Exception:
            pass
    if curve is None:
        try:
            curve = node.FCurve
        except Exception:
            pass
    return curve


def focused_animation_nodes(prop):
    """Return exactly the nodes currently visible in the FCurve editor.

    A scalar property owns one curve directly.  A vector property owns child
    nodes, and only the focused child channels are visible.  We deliberately
    fail closed for a vector property whose child-focus state cannot be read:
    editing a hidden curve is worse than declining an unsupported property.
    """
    try:
        root = prop.GetAnimationNode()
    except Exception:
        return ()
    if root is None:
        return ()

    try:
        children = tuple(root.Nodes)
    except Exception:
        children = ()
    try:
        member_count = int(prop.GetSubMemberCount())
    except Exception:
        member_count = 0

    if member_count <= 1 or not children:
        return (root,)

    nodes = []
    for index, node in enumerate(children[:member_count]):
        try:
            focused = bool(prop.IsFocusedChild(index))
        except Exception:
            focused = False
        if focused:
            nodes.append(node)
    return tuple(nodes)


def _curve_records(context, properties):
    records = []
    seen = set()
    layer = context.animation_layer
    for prop in properties:
        for node in focused_animation_nodes(prop):
            curve = _curve_for_node(node, layer)
            if curve is None or id(curve) in seen:
                continue
            seen.add(id(curve))
            records.append(CurveRecord(prop, node, curve))
    return tuple(records)


def displayed_curve_records(context):
    """Compatibility name for the editor's visible/focused curve scope."""
    return _curve_records(
        context,
        context.fcurves.selected_properties(),
    )


def selected_curve_records(context):
    """Resolve current-layer curves for visible/focused FCurve channels."""
    return displayed_curve_records(context)
