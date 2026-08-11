"""Per-user settings with invalid-JSON recovery and atomic writes."""

from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import time

from .interactions.policy import DEFAULTS as INTERACTION_DEFAULTS
from .quick_favorites.settings import (
    DEFAULTS as QUICK_FAVORITES_DEFAULTS,
    validate_quick_favorites_settings,
)
from .story.settings import DEFAULTS as STORY_DEFAULTS


SETTINGS_VERSION = 4


class SettingsStore(object):
    def __init__(self, directory, filename="settings.json"):
        self.directory = os.path.abspath(directory)
        self.path = os.path.join(self.directory, filename)
        self.data = self.defaults()
        self.recovery_path = None

    @staticmethod
    def defaults():
        return {
            "version": SETTINGS_VERSION,
            "initialized": False,
            "features": {},
            "bindings": {},
            "active_profile": "",
            "interaction": dict(INTERACTION_DEFAULTS),
            "story": dict(STORY_DEFAULTS),
            "quick_favorites": validate_quick_favorites_settings(
                QUICK_FAVORITES_DEFAULTS
            ),
        }

    def load(self):
        if not os.path.isfile(self.path):
            self.data = self.defaults()
            return self.data
        try:
            with open(self.path, "r", encoding="utf-8-sig") as stream:
                incoming = json.load(stream)
            if not isinstance(incoming, dict):
                raise ValueError("settings root must be an object")
            merged = self.defaults()
            merged.update(incoming)
            merged["version"] = SETTINGS_VERSION
            if not isinstance(merged.get("features"), dict):
                merged["features"] = {}
            if not isinstance(merged.get("bindings"), dict):
                merged["bindings"] = {}
            interaction = dict(INTERACTION_DEFAULTS)
            if isinstance(merged.get("interaction"), dict):
                interaction.update(merged["interaction"])
            merged["interaction"] = interaction
            story = dict(STORY_DEFAULTS)
            if isinstance(merged.get("story"), dict):
                story.update(merged["story"])
            merged["story"] = story
            merged["quick_favorites"] = validate_quick_favorites_settings(
                merged.get("quick_favorites")
            )
            self.data = merged
        except Exception:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.recovery_path = self.path + ".invalid-" + stamp
            os.makedirs(self.directory, exist_ok=True)
            shutil.copy2(self.path, self.recovery_path)
            self.data = self.defaults()
        return self.data

    def save(self):
        os.makedirs(self.directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="settings-", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except Exception:
                    pass
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.path

    def enabled(self, feature_id, default=True):
        feature = self.data.get("features", {}).get(feature_id, {})
        return bool(feature.get("enabled", default))

    def set_enabled(self, feature_id, enabled):
        feature = self.data.setdefault("features", {}).setdefault(feature_id, {})
        feature["enabled"] = bool(enabled)

    def profile_bindings(self, profile_name):
        return self.data.setdefault("bindings", {}).setdefault(profile_name, {})

    def binding(self, profile_name, feature_id, default=""):
        return self.profile_bindings(profile_name).get(feature_id, default)

    def set_binding(self, profile_name, feature_id, value):
        self.profile_bindings(profile_name)[feature_id] = value
