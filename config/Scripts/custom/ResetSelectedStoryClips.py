"""Compatibility launcher for the manager-owned Story clip command."""

from __future__ import absolute_import

from mobu_tools_manager import dispatch


dispatch("story.reset_selected_clips")
