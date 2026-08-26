"""Native ActionScript and interaction-mode keyboard file management."""

from __future__ import absolute_import

import os
import re
import shutil
import tempfile
import time


SCRIPT_PATTERN = re.compile(
    r"^([ \t]*Script)(\d+)([ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?$"
)
ACTION_PATTERN = re.compile(
    r"^([ \t]*)(action\.[^=\s]+)([ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?$",
    re.IGNORECASE,
)
PROFILE_PATTERN = re.compile(r"^\s*Name\s*=\s*(.*?)\s*$", re.IGNORECASE)
NATIVE_ACTION_TEMP_KEYS = (
    ("F11", 0x7A),
    ("F10", 0x79),
    ("F9", 0x78),
    ("F12", 0x7B),
)


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as stream:
        return stream.read()


def atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except Exception:
                pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backup_file(path, backup_directory):
    os.makedirs(backup_directory, exist_ok=True)
    destination = os.path.join(backup_directory, os.path.basename(path))
    if os.path.isfile(destination):
        stem, extension = os.path.splitext(os.path.basename(path))
        destination = os.path.join(
            backup_directory, "%s-%s%s" % (stem, int(time.time() * 1000), extension)
        )
    shutil.copy2(path, destination)
    return destination


def action_script_slots(text):
    slots = {}
    for line in text.splitlines(True):
        match = SCRIPT_PATTERN.match(line)
        if match:
            slots[int(match.group(2))] = match.group(4).strip()
    return slots


def update_action_script(text, replacements):
    found = set()
    output = []
    for line in text.splitlines(True):
        match = SCRIPT_PATTERN.match(line)
        if not match:
            output.append(line)
            continue
        slot = int(match.group(2))
        if slot not in replacements:
            output.append(line)
            continue
        newline = match.group(5) or "\n"
        output.append(
            "%s%s%s%s%s"
            % (
                match.group(1),
                match.group(2),
                match.group(3),
                replacements[slot],
                newline,
            )
        )
        found.add(slot)
    missing = set(replacements) - found
    if missing:
        raise ValueError("ActionScript slots not present: %s" % sorted(missing))
    return "".join(output)


def parse_profile_name(text, fallback=""):
    in_config = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_config = stripped.lower() == "[config]"
            continue
        if in_config:
            match = PROFILE_PATTERN.match(line)
            if match:
                return match.group(1).strip()
    return fallback


def split_bindings(value):
    return tuple(part.strip() for part in value.split("|") if part.strip())


def keyboard_actions(text):
    actions = {}
    for line in text.splitlines(True):
        match = ACTION_PATTERN.match(line)
        if match:
            actions[match.group(2).lower()] = {
                "name": match.group(2),
                "value": match.group(4).strip(),
                "bindings": split_bindings(match.group(4)),
            }
    return actions


def normalize_binding(binding):
    value = binding.strip()
    if not value:
        return ""
    if not (value.startswith("{") and value.endswith("}")):
        raise ValueError("binding must use MotionBuilder syntax, e.g. {SHFT:F*DN}")
    return value.upper()


def find_conflicts(text, binding, exclude_action=None):
    wanted = normalize_binding(binding)
    if not wanted:
        return ()
    conflicts = []
    for action_key, record in keyboard_actions(text).items():
        if exclude_action and action_key == exclude_action.lower():
            continue
        if wanted in tuple(item.upper() for item in record["bindings"]):
            conflicts.append(record["name"])
    return tuple(conflicts)


def set_action_bindings(text, target_action, bindings, replace_existing=False):
    normalized = []
    for binding in bindings:
        value = normalize_binding(binding)
        if value and value not in normalized:
            normalized.append(value)

    conflicts = {}
    for binding in normalized:
        found = find_conflicts(text, binding, exclude_action=target_action)
        if found:
            conflicts[binding] = found
    if conflicts and not replace_existing:
        raise ShortcutConflict(conflicts)

    output = []
    target_found = False
    for line in text.splitlines(True):
        match = ACTION_PATTERN.match(line)
        if not match:
            output.append(line)
            continue
        action = match.group(2)
        current = list(split_bindings(match.group(4)))
        if replace_existing and action.lower() != target_action.lower():
            current = [
                value
                for value in current
                if value.upper() not in set(normalized)
            ]
        if action.lower() == target_action.lower():
            current = normalized
            target_found = True
        newline = match.group(5) or "\n"
        output.append(
            "%s%s%s%s%s"
            % (match.group(1), action, match.group(3), "|".join(current), newline)
        )
    if not target_found:
        raise ValueError("keyboard action not found: " + target_action)
    return "".join(output), conflicts


class ShortcutConflict(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        details = ", ".join(
            "%s -> %s" % (binding, ", ".join(actions))
            for binding, actions in sorted(conflicts.items())
        )
        ValueError.__init__(self, "shortcut conflict: " + details)


class ShortcutManager(object):
    def __init__(self, action_script_path, backup_directory, rescan_callback=None):
        self.action_script_path = action_script_path
        self.backup_directory = backup_directory
        self.rescan_callback = rescan_callback

    def install_wrappers(self, slot_paths):
        original = read_text(self.action_script_path)
        updated = update_action_script(original, slot_paths)
        if updated == original:
            return None
        backup = backup_file(self.action_script_path, self.backup_directory)
        atomic_write(self.action_script_path, updated)
        try:
            if self.rescan_callback:
                self.rescan_callback(True, False)
        except Exception:
            shutil.copy2(backup, self.action_script_path)
            raise
        return backup

    def edit_binding(
        self,
        keyboard_path,
        action_slot,
        bindings,
        replace_existing=False,
    ):
        original = read_text(keyboard_path)
        action = "action.global.script%s" % action_slot
        updated, conflicts = set_action_bindings(
            original, action, bindings, replace_existing=replace_existing
        )
        backup = backup_file(keyboard_path, self.backup_directory)
        atomic_write(keyboard_path, updated)
        try:
            if self.rescan_callback:
                self.rescan_callback(False, True)
        except Exception:
            shutil.copy2(backup, keyboard_path)
            if self.rescan_callback:
                try:
                    self.rescan_callback(False, True)
                except Exception:
                    pass
            raise
        return conflicts


class NativeActionDispatcher(object):
    """Run a MotionBuilder action through a complete temporary key pair.

    MotionBuilder does not expose a reliable Python execute method for every
    keyboard-map action. The manager therefore owns this short-lived binding,
    its backup, the matching key down/up pair, and restoration.
    """

    def __init__(
        self,
        keyboard_path,
        backup_directory,
        rescan_callback,
        qt_core,
        key_sender=None,
    ):
        self.keyboard_path = keyboard_path
        self.backup_directory = backup_directory
        self.rescan_callback = rescan_callback
        self.QtCore = qt_core
        self.key_sender = key_sender or self._send_windows_key_pair
        self.active_key_sender = None
        self.action_name = ""
        self.original_value = ""
        self.bound_value = ""
        self.bound_text = ""
        self.virtual_key = 0
        self.active = False
        self.restore_attempts = 0
        self.last_error = None

    def action_exists(self, action_name):
        if not self.keyboard_path or not os.path.isfile(self.keyboard_path):
            return False
        try:
            return str(action_name).lower() in keyboard_actions(
                read_text(self.keyboard_path)
            )
        except Exception:
            return False

    def _rescan(self):
        result = self.rescan_callback()
        if result is False:
            raise RuntimeError(
                "MotionBuilder did not accept the keyboard-map update."
            )
        return result

    @staticmethod
    def _send_windows_key_pair(virtual_key):
        import ctypes

        key_up = 0x0002
        user32 = ctypes.windll.user32
        try:
            user32.keybd_event(int(virtual_key), 0, 0, 0)
        finally:
            user32.keybd_event(int(virtual_key), 0, key_up, 0)

    @staticmethod
    def _replace_action_value(text, target_action, value):
        output = []
        found = False
        for line in text.splitlines(True):
            match = ACTION_PATTERN.match(line)
            if not match or match.group(2).lower() != target_action.lower():
                output.append(line)
                continue
            newline = match.group(5) or "\n"
            output.append(
                "%s%s%s%s%s"
                % (
                    match.group(1),
                    match.group(2),
                    match.group(3),
                    value,
                    newline,
                )
            )
            found = True
        if not found:
            raise ValueError("keyboard action not found: " + target_action)
        return "".join(output)

    def dispatch(self, action_name, key_sender=None):
        if self.active and not self.restore():
            raise RuntimeError(
                "The previous native action binding could not be restored."
            )
        if not self.keyboard_path or not os.path.isfile(self.keyboard_path):
            raise RuntimeError("The active MotionBuilder keyboard map was not found.")

        sender = key_sender or self.key_sender
        if not callable(sender):
            raise TypeError("Native action key sender must be callable.")

        action_name = str(action_name).strip()
        original = read_text(self.keyboard_path)
        actions = keyboard_actions(original)
        record = actions.get(action_name.lower())
        if record is None:
            raise RuntimeError(
                "MotionBuilder action is not present in the active keyboard map:\n"
                + action_name
            )

        temporary_name = ""
        virtual_key = 0
        for candidate_name, candidate_virtual_key in NATIVE_ACTION_TEMP_KEYS:
            binding = "{NONE:%s*DN}" % candidate_name
            if not find_conflicts(
                original,
                binding,
                exclude_action=action_name,
            ):
                temporary_name = candidate_name
                virtual_key = candidate_virtual_key
                break
        if not temporary_name:
            raise RuntimeError(
                "No unused temporary function key is available for native action dispatch."
            )

        bound_value = "{NONE:%s*DN}" % temporary_name
        bound_text = self._replace_action_value(
            original,
            action_name,
            bound_value,
        )
        backup = backup_file(self.keyboard_path, self.backup_directory)
        try:
            atomic_write(self.keyboard_path, bound_text)
            self._rescan()
        except Exception:
            shutil.copy2(backup, self.keyboard_path)
            try:
                self._rescan()
            except Exception:
                pass
            raise

        self.action_name = action_name
        self.original_value = record["value"]
        self.bound_value = bound_value
        self.bound_text = bound_text
        self.virtual_key = virtual_key
        self.active_key_sender = sender
        self.active = True
        self.restore_attempts = 0
        self.last_error = None

        # MotionBuilder processes the native action only after the Python
        # callback returns. Always send a complete pair on a later event turn.
        self.QtCore.QTimer.singleShot(0, self._send_key_pair)
        self.QtCore.QTimer.singleShot(2000, self.restore)
        return self

    def _send_key_pair(self):
        if not self.active:
            return
        try:
            sender = self.active_key_sender or self.key_sender
            sender(self.virtual_key)
        except Exception as error:
            # A deferred sender error must not escape through MotionBuilder's
            # Qt event loop. Restoration still runs below.
            self.last_error = str(error)
        finally:
            self.QtCore.QTimer.singleShot(300, self.restore)

    def restore(self):
        if not self.active:
            return True
        try:
            current = read_text(self.keyboard_path)
            current_record = keyboard_actions(current).get(
                self.action_name.lower()
            )
            if (
                current_record is not None
                and current_record["value"].upper()
                == self.bound_value.upper()
            ):
                restored = self._replace_action_value(
                    current,
                    self.action_name,
                    self.original_value,
                )
                if restored != current:
                    atomic_write(self.keyboard_path, restored)
            self._rescan()
        except Exception:
            self.restore_attempts += 1
            if self.restore_attempts < 3:
                self.QtCore.QTimer.singleShot(250, self.restore)
            return False

        self.active = False
        self.action_name = ""
        self.original_value = ""
        self.bound_value = ""
        self.bound_text = ""
        self.virtual_key = 0
        self.active_key_sender = None
        self.restore_attempts = 0
        return True

    def stop(self):
        return self.restore()


def find_keyboard_profile(user_config_path, install_config_path, profile_name):
    roots = (
        os.path.join(user_config_path, "Keyboard"),
        os.path.join(install_config_path, "Keyboard"),
    )
    for root in roots:
        if not os.path.isdir(root):
            continue
        for filename in os.listdir(root):
            if not filename.lower().endswith(".txt"):
                continue
            path = os.path.join(root, filename)
            try:
                name = parse_profile_name(
                    read_text(path), fallback=os.path.splitext(filename)[0]
                )
            except Exception:
                continue
            if name == profile_name:
                return path
    return None
