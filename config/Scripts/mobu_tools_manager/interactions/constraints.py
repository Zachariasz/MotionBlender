"""Axis constraint state shared by object and FCurve transforms."""

from __future__ import absolute_import


class AxisConstraint(object):
    def __init__(self, graph=False, timeline=False):
        self.graph = bool(graph)
        self.timeline = bool(timeline)
        self.axis = "x" if self.timeline else None
        self.space = "global"

    def press(self, axis):
        axis = str(axis).lower()
        if not self.accepts(axis):
            return False
        if self.graph:
            self.axis = None if self.axis == axis else axis
            self.space = "global"
            return True
        if self.axis != axis:
            self.axis = axis
            self.space = "global"
        elif self.space == "global":
            self.space = "local"
        else:
            self.axis = None
            self.space = "global"
        return True

    def accepts(self, axis):
        axis = str(axis).lower()
        if self.timeline:
            return False
        if self.graph:
            return axis in ("x", "y")
        return axis in ("x", "y", "z")

    @property
    def label(self):
        if self.axis is None:
            return None
        if self.graph or self.timeline:
            return self.axis.upper()
        return "%s %s" % (self.space.upper(), self.axis.upper())
