"""Stable public API for the MotionBuilder Tools Manager.

ActionScript wrappers intentionally import only this module.  The heavier
manager implementation is imported lazily on first use.
"""

from __future__ import absolute_import

import builtins


SINGLETON_NAME = "_motionbuilder_tools_manager"


def get_manager(start=True):
    manager = getattr(builtins, SINGLETON_NAME, None)
    if manager is None:
        from .manager import MotionBuilderToolsManager

        manager = MotionBuilderToolsManager()
        setattr(builtins, SINGLETON_NAME, manager)
    if start and not manager.started:
        manager.start()
    return manager


def restart_manager():
    previous = getattr(builtins, SINGLETON_NAME, None)
    if previous is not None:
        try:
            previous.shutdown()
        finally:
            try:
                delattr(builtins, SINGLETON_NAME)
            except Exception:
                pass
    return get_manager(start=True)


def dispatch(feature_id):
    return get_manager().dispatch(feature_id)


def dispatch_native_action(action_name):
    return get_manager().dispatch_native_action(action_name)


def show_manager():
    return get_manager().show_manager()


def enable(feature_id):
    return get_manager().enable(feature_id)


def disable(feature_id):
    return get_manager().disable(feature_id)


def reload_feature(feature_id):
    return get_manager().reload_feature(feature_id)


__all__ = [
    "dispatch",
    "dispatch_native_action",
    "disable",
    "enable",
    "get_manager",
    "reload_feature",
    "restart_manager",
    "show_manager",
]
