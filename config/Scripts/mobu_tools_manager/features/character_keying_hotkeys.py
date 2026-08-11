"""Reliable 1/2/3 Character Controls keying-mode hotkeys."""

from __future__ import absolute_import


FEATURE_ID = "input.character_keying_hotkeys"
KEY_TO_ENUM = {
    "1": "kFBCharacterKeyingFullBody",
    "2": "kFBCharacterKeyingBodyPart",
    "3": "kFBCharacterKeyingSelection",
}

_SERVICE = None


def _sdk():
    import pyfbsdk

    return pyfbsdk


class CharacterKeyingHotkeyService(object):
    def __init__(self, context):
        self.context = context
        self._callback = self.handle_key
        self.running = False
        self.last_key = None
        self.last_mode = None
        self.last_character = None
        self.last_error = None

    def start(self):
        if self.running:
            return self
        self.context.input.configure_character_keying_launcher(
            self._callback,
        )
        self.running = True
        return self

    def stop(self):
        if self.context is not None:
            try:
                self.context.input.clear_character_keying_launcher(
                    self._callback,
                )
            except Exception:
                pass
        self.running = False

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        callback = getattr(diagnostics, "record", None)
        if callable(callback):
            try:
                callback(event, FEATURE_ID, **data)
            except Exception:
                pass

    def handle_key(self, key, payload=None):
        enum_name = KEY_TO_ENUM.get(str(key))
        if not self.running or enum_name is None:
            return False

        try:
            character = self.context.application.CurrentCharacter
        except Exception:
            character = None
        if character is None:
            return False

        try:
            mode = getattr(_sdk().FBCharacterKeyingMode, enum_name)
            character.KeyingMode = mode
            self.context.evaluation.request()
        except Exception as error:
            self.last_error = str(error)
            self._record(
                "character_keying_hotkey_error",
                key=str(key),
                mode=enum_name,
                error=self.last_error,
            )
            return False

        self.last_key = str(key)
        self.last_mode = enum_name
        self.last_character = str(
            getattr(character, "LongName", None)
            or getattr(character, "Name", None)
            or ""
        )
        self.last_error = None
        self._record(
            "character_keying_mode_changed",
            key=self.last_key,
            mode=self.last_mode,
            character=self.last_character,
        )
        return True

    def status(self):
        return {
            "running": self.running,
            "bindings": {
                "1": "Full Body",
                "2": "Body Part",
                "3": "Selection",
            },
            "last_key": self.last_key,
            "last_mode": self.last_mode,
            "last_character": self.last_character,
            "last_error": self.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None:
        if _SERVICE.context is context:
            return _SERVICE.start()
        _SERVICE.stop()
    _SERVICE = CharacterKeyingHotkeyService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    if _SERVICE is not None:
        _SERVICE.stop()
    _SERVICE = None


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
