"""Compatibility launcher for the manager-owned Story command."""

from mobu_tools_manager import dispatch


dispatch("story.insert_current_take")
