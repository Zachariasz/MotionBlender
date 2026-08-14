"""Compatibility launcher for the manager-owned Antigravity bridge service."""

from mobu_tools_manager import dispatch


def start_bridge():
    return dispatch("developer.antigravity_bridge")


start_bridge()
