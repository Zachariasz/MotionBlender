"""Manager-owned transform precision policy entrypoint."""

from __future__ import absolute_import


def execute(context):
    context.retire_legacy_precision_services()
    return context.policy.as_dict()
