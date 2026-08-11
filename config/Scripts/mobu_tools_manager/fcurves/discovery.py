"""Displayed/current-layer FCurve discovery."""

from __future__ import absolute_import


class CurveRecord(object):
    def __init__(self, prop, node, curve):
        self.property = prop
        self.node = node
        self.curve = curve


def _walk_nodes(node):
    yield node
    try:
        children = tuple(node.Nodes)
    except Exception:
        children = ()
    for child in children:
        for descendant in _walk_nodes(child):
            yield descendant


def _curve_records(context, properties):
    records = []
    seen = set()
    layer = context.animation_layer
    for prop in properties:
        try:
            root = prop.GetAnimationNode()
        except Exception:
            root = None
        if root is None:
            continue
        for node in _walk_nodes(root):
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
                    curve = None
            if curve is None or id(curve) in seen:
                continue
            seen.add(id(curve))
            records.append(CurveRecord(prop, node, curve))
    return tuple(records)


def displayed_curve_records(context):
    return _curve_records(
        context,
        context.fcurves.displayed_properties(refresh=True),
    )


def selected_curve_records(context):
    """Resolve current-layer curves for selected FCurve properties only."""
    return _curve_records(context, context.fcurves.selected_properties())
