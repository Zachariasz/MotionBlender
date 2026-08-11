"""Manager-native entrypoint for inserting selected FCurve keys."""

from __future__ import absolute_import

from ..fcurves.add_key import add_key


def execute(context):
    return add_key(context)
