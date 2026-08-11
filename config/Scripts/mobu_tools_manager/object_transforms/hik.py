"""Shared HIK manipulation policy, topology index, and solve lifecycle."""

from __future__ import absolute_import

from .targets import (
    model_vector,
    set_world_translation,
)


EFFECTOR_ID_LIMIT = 64
EFFECTOR_SET_LIMIT = 16
FK_MODEL_LIMIT = 256
CHANGE_EPSILON = 0.00001

KEYING_FULL_BODY = "full_body"
KEYING_FULL_BODY_NO_PULL = "full_body_no_pull"
KEYING_BODY_PART = "body_part"
KEYING_SELECTION = "selection"

BODY_PART_NODE_NAMES = {
    "hips": (
        "kFBReferenceNodeId",
        "kFBHipsNodeId",
        "kFBHipsTranslationNodeId",
    ),
    "chest": (
        "kFBWaistNodeId",
        "kFBChestNodeId",
        "kFBSpine2NodeId",
        "kFBSpine3NodeId",
        "kFBSpine4NodeId",
        "kFBSpine5NodeId",
        "kFBSpine6NodeId",
        "kFBSpine7NodeId",
        "kFBSpine8NodeId",
        "kFBSpine9NodeId",
    ),
    "left_arm": (
        "kFBLeftCollarNodeId",
        "kFBLeftShoulderNodeId",
        "kFBLeftShoulderRollNodeId",
        "kFBLeftElbowNodeId",
        "kFBLeftElbowRollNodeId",
        "kFBLeftWristNodeId",
    ),
    "right_arm": (
        "kFBRightCollarNodeId",
        "kFBRightShoulderNodeId",
        "kFBRightShoulderRollNodeId",
        "kFBRightElbowNodeId",
        "kFBRightElbowRollNodeId",
        "kFBRightWristNodeId",
    ),
    "left_leg": (
        "kFBLeftHipNodeId",
        "kFBLeftHipRollNodeId",
        "kFBLeftKneeNodeId",
        "kFBLeftKneeRollNodeId",
        "kFBLeftAnkleNodeId",
    ),
    "right_leg": (
        "kFBRightHipNodeId",
        "kFBRightHipRollNodeId",
        "kFBRightKneeNodeId",
        "kFBRightKneeRollNodeId",
        "kFBRightAnkleNodeId",
    ),
    "head": tuple(
        ["kFBHeadNodeId", "kFBNeckNodeId"]
        + ["kFBNeck%dNodeId" % index for index in range(1, 10)]
    ),
    "left_hand": tuple(
        ["kFBLeftHandNodeId"]
        + [
            "kFBLeft%s%sNodeId" % (finger, segment)
            for finger in (
                "Thumb",
                "Index",
                "Middle",
                "Ring",
                "Pinky",
                "ExtraFinger",
            )
            for segment in ("In", "A", "B", "C", "D")
        ]
    ),
    "right_hand": tuple(
        ["kFBRightHandNodeId"]
        + [
            "kFBRight%s%sNodeId" % (finger, segment)
            for finger in (
                "Thumb",
                "Index",
                "Middle",
                "Ring",
                "Pinky",
                "ExtraFinger",
            )
            for segment in ("In", "A", "B", "C", "D")
        ]
    ),
    "left_foot": tuple(
        ["kFBLeftFootNodeId"]
        + [
            "kFBLeftFoot%s%sNodeId" % (finger, segment)
            for finger in (
                "Thumb",
                "Index",
                "Middle",
                "Ring",
                "Pinky",
                "ExtraFinger",
            )
            for segment in ("In", "A", "B", "C", "D")
        ]
    ),
    "right_foot": tuple(
        ["kFBRightFootNodeId"]
        + [
            "kFBRightFoot%s%sNodeId" % (finger, segment)
            for finger in (
                "Thumb",
                "Index",
                "Middle",
                "Ring",
                "Pinky",
                "ExtraFinger",
            )
            for segment in ("In", "A", "B", "C", "D")
        ]
    ),
}

BODY_PART_ENUM_NAMES = {
    "hips": "kFBCtrlSetPartHips",
    "chest": "kFBCtrlSetPartChest",
    "left_arm": "kFBCtrlSetPartLeftArm",
    "right_arm": "kFBCtrlSetPartRightArm",
    "left_leg": "kFBCtrlSetPartLeftLeg",
    "right_leg": "kFBCtrlSetPartRightLeg",
    "head": "kFBCtrlSetPartHead",
    "left_hand": "kFBCtrlSetPartLeftHand",
    "right_hand": "kFBCtrlSetPartRightHand",
    "left_foot": "kFBCtrlSetPartLeftFoot",
    "right_foot": "kFBCtrlSetPartRightFoot",
}

BODY_PART_DRIVER_EFFECTORS = {
    "hips": ("kFBHipsEffectorId",),
    "chest": ("kFBChestEndEffectorId", "kFBChestOriginEffectorId"),
    "left_arm": ("kFBLeftWristEffectorId", "kFBLeftElbowEffectorId"),
    "right_arm": ("kFBRightWristEffectorId", "kFBRightElbowEffectorId"),
    "left_leg": ("kFBLeftAnkleEffectorId", "kFBLeftKneeEffectorId"),
    "right_leg": ("kFBRightAnkleEffectorId", "kFBRightKneeEffectorId"),
    "head": ("kFBHeadEffectorId",),
    "left_hand": ("kFBLeftHandEffectorId",),
    "right_hand": ("kFBRightHandEffectorId",),
    "left_foot": ("kFBLeftFootEffectorId",),
    "right_foot": ("kFBRightFootEffectorId",),
}


def _sdk():
    import pyfbsdk

    return pyfbsdk


def _find_property(owner, name):
    try:
        return owner.PropertyList.Find(name)
    except Exception:
        return None


def _numeric_value(value, fallback=0.0):
    try:
        return float(value)
    except Exception:
        pass
    try:
        return float(value.Data)
    except Exception:
        return fallback


def _component_key(component):
    for attribute in ("LongName", "Name"):
        try:
            value = str(getattr(component, attribute))
        except Exception:
            value = ""
        if value:
            return value
    return str(component)


def _same_component(left, right):
    if left is None or right is None:
        return False
    try:
        if left == right:
            return True
    except Exception:
        pass
    return _component_key(left) == _component_key(right)


def _enum_value(enum_type, value):
    try:
        return enum_type(value)
    except Exception:
        return value


def _enum_int(value, fallback=-1):
    try:
        return int(value)
    except Exception:
        pass
    try:
        return int(value.value)
    except Exception:
        return fallback


def _enum_member(sdk, enum_name, member_name):
    try:
        return getattr(getattr(sdk, enum_name), member_name)
    except Exception:
        return None


def _body_part_value(sdk, body_part_name):
    enum_name = BODY_PART_ENUM_NAMES.get(str(body_part_name or ""))
    if enum_name is None:
        return None
    return _enum_member(sdk, "FBBodyPartId", enum_name)


def _body_part_name(sdk, value):
    numeric = _enum_int(value)
    for name, member_name in BODY_PART_ENUM_NAMES.items():
        member = _enum_member(sdk, "FBBodyPartId", member_name)
        if member is None:
            continue
        try:
            if value == member:
                return name
        except Exception:
            pass
        if numeric >= 0 and numeric == _enum_int(member):
            return name
    text = str(value or "").lower()
    for name in BODY_PART_ENUM_NAMES:
        if name.replace("_", "") in text.replace("_", "").lower():
            return name
    return None


def _infer_body_part_name(model, hint=""):
    values = [str(hint or "")]
    for attribute in ("LongName", "Name"):
        try:
            values.append(str(getattr(model, attribute) or ""))
        except Exception:
            pass
    text = " ".join(values).replace("_", "").replace(" ", "").lower()
    left = "left" in text
    right = "right" in text
    if left or right:
        side = "left" if left else "right"
        if any(token in text for token in ("finger", "thumb", "pinky", "hand")):
            return side + "_hand"
        if any(token in text for token in ("toe", "foot")):
            return side + "_foot"
        if any(token in text for token in ("hip", "knee", "ankle", "leg")):
            return side + "_leg"
        if any(
            token in text
            for token in ("collar", "shoulder", "elbow", "wrist", "arm")
        ):
            return side + "_arm"
    if any(token in text for token in ("head", "neck")):
        return "head"
    if any(token in text for token in ("spine", "chest", "waist")):
        return "chest"
    if any(token in text for token in ("hips", "reference")):
        return "hips"
    return None


def _keying_mode_name(sdk, mode):
    choices = (
        (
            KEYING_SELECTION,
            "kFBCharacterKeyingSelection",
        ),
        (
            KEYING_BODY_PART,
            "kFBCharacterKeyingBodyPart",
        ),
        (
            KEYING_FULL_BODY_NO_PULL,
            "kFBCharacterKeyingFullBodyNoPull",
        ),
        (
            KEYING_FULL_BODY,
            "kFBCharacterKeyingFullBody",
        ),
    )
    numeric = _enum_int(mode)
    for name, member_name in choices:
        member = _enum_member(sdk, "FBCharacterKeyingMode", member_name)
        if member is None:
            continue
        try:
            if mode == member:
                return name
        except Exception:
            pass
        if numeric >= 0 and numeric == _enum_int(member):
            return name
    text = str(mode or "").replace("_", "").replace(" ", "").lower()
    if "selection" in text:
        return KEYING_SELECTION
    if "bodypart" in text:
        return KEYING_BODY_PART
    if "nopull" in text:
        return KEYING_FULL_BODY_NO_PULL
    return KEYING_FULL_BODY


def _read_keying_mode(sdk, character):
    try:
        return character.KeyingMode
    except Exception:
        pass
    getter = getattr(sdk, "FBGetCharactersKeyingMode", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    return _enum_member(
        sdk,
        "FBCharacterKeyingMode",
        "kFBCharacterKeyingFullBody",
    )


def _active_body_parts(character):
    for arguments in (
        (),
        ([False] * (len(BODY_PART_ENUM_NAMES) + 1),),
    ):
        try:
            values = character.GetActiveBodyPart(*arguments)
        except Exception:
            continue
        if values is None and arguments:
            values = arguments[0]
        try:
            return tuple(bool(value) for value in values)
        except Exception:
            pass
    return ()


def _characters(context):
    result = []
    try:
        current = context.application.CurrentCharacter
    except Exception:
        current = None
    if current is not None:
        result.append(current)
    try:
        scene_characters = tuple(context.scene.Characters)
    except Exception:
        scene_characters = ()
    for character in scene_characters:
        if not any(_same_component(character, existing) for existing in result):
            result.append(character)
    return result


def _current_control_set(character):
    for arguments in ((), (True,)):
        try:
            control_set = character.GetCurrentControlSet(*arguments)
        except Exception:
            continue
        if control_set is not None:
            return control_set
    return None


class HIKIndex(object):
    """Runtime-owned lookup of stable HIK topology between interactions."""

    def __init__(self):
        self.invalidate()

    def invalidate(self):
        self._signature = None
        self._effectors = {}
        self._character_effectors = {}
        self._fk_models = {}
        self._targets = {}
        self._character_controls = {}
        self._node_controls = {}

    def _topology(self, context):
        topology = []
        for character in _characters(context):
            control_set = _current_control_set(character)
            topology.append(
                (
                    _component_key(character),
                    id(character),
                    id(control_set),
                    character,
                    control_set,
                )
            )
        return topology

    def _ensure(self, context):
        topology = self._topology(context)
        signature = tuple(item[:3] for item in topology)
        if signature == self._signature:
            return
        sdk = _sdk()
        effectors = {}
        character_effectors = {}
        fk_models = {}
        targets = {}
        character_controls = {}
        node_controls = {}

        def add_target(entry):
            model = entry.get("model")
            if model is None:
                return
            entries = targets.setdefault(_component_key(model), [])
            if any(
                existing.get("kind") == entry.get("kind")
                and _same_component(existing.get("model"), model)
                for existing in entries
            ):
                return
            entries.append(entry)

        for character_key, _character_id, _control_id, character, control_set in topology:
            indexed_effectors = []
            seen_effectors = set()
            for numeric_effector_id in range(EFFECTOR_ID_LIMIT):
                effector_id = _enum_value(
                    sdk.FBEffectorId,
                    numeric_effector_id,
                )
                for numeric_set_id in range(EFFECTOR_SET_LIMIT):
                    if numeric_set_id:
                        set_id = _enum_value(
                            sdk.FBEffectorSetID,
                            numeric_set_id,
                        )
                        arguments = (effector_id, set_id)
                    else:
                        arguments = (effector_id,)
                    try:
                        model = character.GetEffectorModel(*arguments)
                    except Exception:
                        model = None
                    if model is None:
                        continue
                    entry = {
                        "character": character,
                        "control_set": control_set,
                        "effector_id": effector_id,
                        "model": model,
                        "kind": "ik",
                        "body_part": None,
                        "body_part_name": None,
                    }
                    try:
                        body_part = sdk.FBGetEffectorBodyPart(effector_id)
                    except Exception:
                        body_part = None
                    entry["body_part"] = body_part
                    entry["body_part_name"] = _body_part_name(
                        sdk,
                        body_part,
                    )
                    effectors.setdefault(_component_key(model), []).append(entry)
                    add_target(entry)
                    model_key = _component_key(model)
                    if model_key not in seen_effectors:
                        seen_effectors.add(model_key)
                        indexed_effectors.append(
                            (
                                effector_id,
                                model,
                                body_part,
                                entry["body_part_name"],
                            )
                        )
            character_effectors[character_key] = tuple(indexed_effectors)

            models = []
            controls = []
            seen_fk = set()
            node_control_map = {}
            for body_part_name, node_names in BODY_PART_NODE_NAMES.items():
                body_part = _body_part_value(sdk, body_part_name)
                for node_name in node_names:
                    body_node_id = _enum_member(
                        sdk,
                        "FBBodyNodeId",
                        node_name,
                    )
                    if body_node_id is None:
                        continue
                    try:
                        fk_model = character.GetCtrlRigModel(body_node_id)
                    except Exception:
                        fk_model = None
                    if fk_model is not None:
                        entry = {
                            "character": character,
                            "control_set": control_set,
                            "kind": "fk",
                            "model": fk_model,
                            "body_node_id": body_node_id,
                            "body_part": body_part,
                            "body_part_name": body_part_name,
                        }
                        add_target(entry)
                        node_control_map[_enum_int(body_node_id)] = fk_model
                    try:
                        skeleton_model = character.GetModel(body_node_id)
                    except Exception:
                        skeleton_model = None
                    if skeleton_model is not None:
                        add_target(
                            {
                                "character": character,
                                "control_set": control_set,
                                "kind": "skeleton",
                                "model": skeleton_model,
                                "body_node_id": body_node_id,
                                "body_part": body_part,
                                "body_part_name": body_part_name,
                            }
                        )
            if control_set is not None:
                for index in range(FK_MODEL_LIMIT):
                    try:
                        model = control_set.GetFKModel(index)
                    except Exception:
                        model = None
                    if model is None:
                        continue
                    model_key = _component_key(model)
                    if model_key in seen_fk:
                        continue
                    seen_fk.add(model_key)
                    models.append(model)
                    try:
                        fk_name = control_set.GetFKName(index)
                    except Exception:
                        fk_name = ""
                    matching = None
                    for candidate in targets.get(model_key, ()):
                        if (
                            candidate.get("kind") == "fk"
                            and _same_component(candidate.get("model"), model)
                        ):
                            matching = candidate
                            break
                    if matching is None:
                        body_part_name = _infer_body_part_name(model, fk_name)
                        matching = {
                            "character": character,
                            "control_set": control_set,
                            "kind": "fk",
                            "model": model,
                            "fk_index": index,
                            "fk_name": fk_name,
                            "body_node_id": None,
                            "body_part": _body_part_value(
                                sdk,
                                body_part_name,
                            ),
                            "body_part_name": body_part_name,
                        }
                        add_target(matching)
                    controls.append(matching)
                fk_models[id(control_set)] = tuple(models)
            character_controls[character_key] = tuple(controls)
            node_controls[character_key] = node_control_map
        self._signature = signature
        self._effectors = effectors
        self._character_effectors = character_effectors
        self._fk_models = fk_models
        self._targets = targets
        self._character_controls = character_controls
        self._node_controls = node_controls

    def find_effector(self, context, model):
        self._ensure(context)
        for entry in self._effectors.get(_component_key(model), ()):
            if _same_component(entry["model"], model):
                return entry
        return None

    def character_effectors(self, context, character):
        self._ensure(context)
        return self._character_effectors.get(_component_key(character), ())

    def fk_models(self, context, control_set):
        self._ensure(context)
        return self._fk_models.get(id(control_set), ())

    def find_target(self, context, model):
        self._ensure(context)
        entries = self._targets.get(_component_key(model), ())
        priority = {"ik": 0, "fk": 1, "skeleton": 2}
        for entry in sorted(
            entries,
            key=lambda item: priority.get(item.get("kind"), 99),
        ):
            if _same_component(entry.get("model"), model):
                return entry
        return None

    def character_controls(self, context, character, body_parts=None):
        self._ensure(context)
        controls = self._character_controls.get(
            _component_key(character),
            (),
        )
        if body_parts is None:
            return controls
        names = set(str(value) for value in body_parts if value)
        return tuple(
            entry
            for entry in controls
            if entry.get("body_part_name") in names
        )

    def control_for_body_node(self, context, character, body_node_id):
        self._ensure(context)
        return self._node_controls.get(
            _component_key(character),
            {},
        ).get(_enum_int(body_node_id))

    def body_part_driver(self, context, character, body_part_name):
        self._ensure(context)
        expected = BODY_PART_DRIVER_EFFECTORS.get(
            str(body_part_name or ""),
            (),
        )
        indexed = self.character_effectors(context, character)
        for member_name in expected:
            member = _enum_member(
                _sdk(),
                "FBEffectorId",
                member_name,
            )
            if member is None:
                continue
            for effector_id, model, _part, _part_name in indexed:
                if _enum_int(effector_id) == _enum_int(member):
                    return model
        for _effector_id, model, _part, part_name in indexed:
            if part_name == body_part_name:
                return model
        return None

    def begin_manipulation(self, context, operation, snapshots):
        return HIKManipulationSession(
            context,
            self,
            operation,
            snapshots,
        )

    def current_keying_state(self, context, models=()):
        selected = []
        character = None
        for model in tuple(models or ()):
            info = self.find_target(context, model)
            if info is None:
                continue
            if character is None:
                character = info.get("character")
            if _same_component(character, info.get("character")):
                part = info.get("body_part_name")
                if part:
                    selected.append(part)
        if character is None:
            try:
                character = context.application.CurrentCharacter
            except Exception:
                character = None
        if character is None:
            return {
                "character": None,
                "keying_mode": None,
                "keying_mode_label": None,
                "body_parts": (),
            }
        policy = HIKManipulationPolicy(
            _sdk(),
            character,
            selected,
        )
        return {
            "character": character,
            "keying_mode": policy.keying_mode,
            "keying_mode_label": policy.label,
            "body_parts": tuple(sorted(policy.body_parts)),
        }


def _find_effector(context, model):
    sdk = _sdk()
    reach_property = _find_property(model, "IK Reach Translation")
    if reach_property is None:
        return None
    for character in _characters(context):
        control_set = _current_control_set(character)
        if control_set is None:
            continue
        for numeric_effector_id in range(EFFECTOR_ID_LIMIT):
            effector_id = _enum_value(
                sdk.FBEffectorId,
                numeric_effector_id,
            )
            try:
                candidate = character.GetEffectorModel(effector_id)
            except Exception:
                candidate = None
            if _same_component(candidate, model):
                return {
                    "character": character,
                    "control_set": control_set,
                    "effector_id": effector_id,
                    "reach_property": reach_property,
                    "original_reach": _numeric_value(reach_property),
                }
            for numeric_set_id in range(1, EFFECTOR_SET_LIMIT):
                set_id = _enum_value(
                    sdk.FBEffectorSetID,
                    numeric_set_id,
                )
                try:
                    candidate = character.GetEffectorModel(
                        effector_id,
                        set_id,
                    )
                except Exception:
                    candidate = None
                if _same_component(candidate, model):
                    return {
                        "character": character,
                        "control_set": control_set,
                        "effector_id": effector_id,
                        "reach_property": reach_property,
                        "original_reach": _numeric_value(reach_property),
                    }
    return None


class HIKManipulationPolicy(object):
    """Frozen keying/body-part policy for one interactive transform."""

    def __init__(
        self,
        sdk,
        character,
        selected_body_parts=(),
    ):
        self.sdk = sdk
        self.character = character
        self.raw_keying_mode = _read_keying_mode(sdk, character)
        self.keying_mode = _keying_mode_name(
            sdk,
            self.raw_keying_mode,
        )
        self.active_body_parts = _active_body_parts(character)
        selected_names = set(
            str(value)
            for value in selected_body_parts
            if value
        )
        active_names = set()
        for name in BODY_PART_ENUM_NAMES:
            value = _body_part_value(sdk, name)
            index = _enum_int(value)
            if (
                0 <= index < len(self.active_body_parts)
                and self.active_body_parts[index]
            ):
                active_names.add(name)
        # Selection-derived body parts win. Character Controls can update its
        # active flags one UI turn after an FK control selection.
        self.body_parts = selected_names or active_names

    @property
    def scope(self):
        if self.keying_mode == KEYING_SELECTION:
            return KEYING_SELECTION
        if self.keying_mode == KEYING_BODY_PART:
            return KEYING_BODY_PART
        return KEYING_FULL_BODY

    @property
    def label(self):
        return {
            KEYING_SELECTION: "Selection",
            KEYING_BODY_PART: "Body Part",
            KEYING_FULL_BODY_NO_PULL: "Full Body No Pull",
            KEYING_FULL_BODY: "Full Body",
        }.get(self.keying_mode, "Full Body")

    def affects_body_part(self, body_part):
        if self.scope == KEYING_SELECTION:
            return False
        if self.scope == KEYING_FULL_BODY:
            return True
        name = (
            body_part
            if isinstance(body_part, str)
            else _body_part_name(self.sdk, body_part)
        )
        return bool(name and name in self.body_parts)

    def pin_affects(self, effector_id, body_part=None):
        if self.scope == KEYING_SELECTION:
            return False
        if body_part is None:
            try:
                body_part = self.sdk.FBGetEffectorBodyPart(effector_id)
            except Exception:
                body_part = None
        return self.affects_body_part(body_part)


def _pin_affects(character, effector_id, policy=None):
    sdk = _sdk()
    frozen = policy or HIKManipulationPolicy(sdk, character)
    return frozen.pin_affects(effector_id)


def _capture_pins(character, indexed_effectors=None, policy=None):
    result = []
    sdk = _sdk()
    frozen = policy or HIKManipulationPolicy(sdk, character)
    if indexed_effectors is None:
        indexed_effectors = []
        for numeric_effector_id in range(EFFECTOR_ID_LIMIT):
            effector_id = _enum_value(
                sdk.FBEffectorId,
                numeric_effector_id,
            )
            try:
                model = character.GetEffectorModel(effector_id)
            except Exception:
                model = None
            try:
                body_part = sdk.FBGetEffectorBodyPart(effector_id)
            except Exception:
                body_part = None
            indexed_effectors.append(
                (
                    effector_id,
                    model,
                    body_part,
                    _body_part_name(sdk, body_part),
                )
            )
    for indexed in indexed_effectors:
        effector_id = indexed[0]
        model = indexed[1]
        body_part = indexed[2] if len(indexed) > 2 else None
        if (
            model is None
            or not frozen.pin_affects(effector_id, body_part)
        ):
            continue
        try:
            translation_pinned = bool(
                character.IsTranslationPin(effector_id)
            )
        except Exception:
            translation_pinned = False
        try:
            rotation_pinned = bool(character.IsRotationPin(effector_id))
        except Exception:
            rotation_pinned = False
        if not translation_pinned and not rotation_pinned:
            continue
        translation = (
            _find_property(model, "IK Reach Translation")
            if translation_pinned
            else None
        )
        rotation = (
            _find_property(model, "IK Reach Rotation")
            if rotation_pinned
            else None
        )
        pull = (
            _find_property(model, "IK Pull")
            if translation_pinned
            else None
        )
        result.append(
            {
                "effector_id": effector_id,
                "model": model,
                "body_part": body_part,
                "body_part_name": (
                    indexed[3]
                    if len(indexed) > 3
                    else _body_part_name(sdk, body_part)
                ),
                "translation_pinned": translation_pinned,
                "rotation_pinned": rotation_pinned,
                "translation": translation,
                "translation_value": (
                    _numeric_value(translation)
                    if translation is not None
                    else None
                ),
                "rotation": rotation,
                "rotation_value": (
                    _numeric_value(rotation)
                    if rotation is not None
                    else None
                ),
                "pull": pull,
                "pull_value": (
                    _numeric_value(pull)
                    if pull is not None
                    else None
                ),
            }
        )
    return result


def _capture_fk(control_set, indexed_models=None):
    sdk = _sdk()
    result = []
    seen = set()
    if indexed_models is None:
        indexed_models = []
        for index in range(FK_MODEL_LIMIT):
            try:
                model = control_set.GetFKModel(index)
            except Exception:
                model = None
            indexed_models.append(model)
    for model in indexed_models:
        if model is None:
            continue
        key = _component_key(model)
        if key in seen:
            continue
        try:
            translation = model_vector(
                model,
                sdk.FBModelTransformationType.kModelTranslation,
                False,
            )
            rotation = model_vector(
                model,
                sdk.FBModelTransformationType.kModelRotation,
                False,
            )
        except Exception:
            continue
        seen.add(key)
        result.append(
            {
                "key": key,
                "model": model,
                "translation": translation,
                "rotation": rotation,
            }
        )
    return result


def _vectors_differ(left, right):
    return any(
        abs(float(left[index]) - float(right[index])) > CHANGE_EPSILON
        for index in range(3)
    )


def _capture_changed(context):
    sdk = _sdk()
    changed = []
    candidates = context["previous_changed"] or context["fk_baselines"]
    for candidate in candidates:
        baseline = context["fk_by_key"].get(candidate["key"], candidate)
        model = baseline["model"]
        translation = model_vector(
            model,
            sdk.FBModelTransformationType.kModelTranslation,
            False,
        )
        rotation = model_vector(
            model,
            sdk.FBModelTransformationType.kModelRotation,
            False,
        )
        if not (
            _vectors_differ(translation, baseline["translation"])
            or _vectors_differ(rotation, baseline["rotation"])
        ):
            continue
        changed.append(
            {
                "key": baseline["key"],
                "model": model,
                "translation": translation,
                "rotation": rotation,
            }
        )
    return changed


def _apply_fk(states):
    sdk = _sdk()
    for state in states:
        state["model"].SetVector(
            sdk.FBVector3d(*state["translation"]),
            sdk.FBModelTransformationType.kModelTranslation,
            False,
        )
        state["model"].SetVector(
            sdk.FBVector3d(*state["rotation"]),
            sdk.FBModelTransformationType.kModelRotation,
            False,
        )


def _matrix3_multiply(left, right):
    return [
        [
            sum(
                float(left[row][index]) * float(right[index][column])
                for index in range(3)
            )
            for column in range(3)
        ]
        for row in range(3)
    ]


def _rotation_matrix(model):
    sdk = _sdk()
    matrix = sdk.FBMatrix()
    model.GetMatrix(
        matrix,
        sdk.FBModelTransformationType.kModelRotation,
        True,
    )
    return [
        [float(matrix[0]), float(matrix[4]), float(matrix[8])],
        [float(matrix[1]), float(matrix[5]), float(matrix[9])],
        [float(matrix[2]), float(matrix[6]), float(matrix[10])],
    ]


def _set_rotation_matrix(model, matrix3):
    sdk = _sdk()
    matrix = sdk.FBMatrix()
    for index in range(16):
        matrix[index] = 0.0
    matrix[15] = 1.0
    for row in range(3):
        for column in range(3):
            matrix[column * 4 + row] = float(matrix3[row][column])
    model.SetMatrix(
        matrix,
        sdk.FBModelTransformationType.kModelRotation,
        True,
    )


def _unique_models(models):
    result = []
    for model in models:
        if model is None:
            continue
        if any(_same_component(model, existing) for existing in result):
            continue
        result.append(model)
    return tuple(result)


class HIKManipulationSession(object):
    """One transform's frozen HIK mode, pin, reach, solve, and cleanup state."""

    def __init__(self, context, index, operation, snapshots):
        self.context = context
        self.index = index
        self.operation = str(operation or "").strip().lower()
        self.snapshots = tuple(snapshots)
        self.bindings = {}
        self.groups = ()
        self._closed = False
        self._capture()

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        record = getattr(diagnostics, "record", None)
        if callable(record):
            try:
                record(event, feature_id="transform.hik", **data)
            except Exception:
                pass

    def _target_info(self, model):
        try:
            return self.index.find_target(self.context, model)
        except Exception:
            pass
        fallback = _find_effector(self.context, model)
        if fallback is not None:
            fallback = dict(fallback)
            fallback.setdefault("kind", "ik")
            try:
                fallback["body_part"] = _sdk().FBGetEffectorBodyPart(
                    fallback["effector_id"]
                )
            except Exception:
                fallback["body_part"] = None
            fallback["body_part_name"] = _body_part_name(
                _sdk(),
                fallback["body_part"],
            )
        return fallback

    def _driver(self, binding):
        info = binding["info"]
        model = binding["snapshot"].model
        if self.operation == "move" and info.get("kind") != "ik":
            driver = self.index.body_part_driver(
                self.context,
                info["character"],
                info.get("body_part_name"),
            )
            if driver is not None:
                return driver
        if self.operation == "rotate" and info.get("kind") == "skeleton":
            driver = self.index.control_for_body_node(
                self.context,
                info["character"],
                info.get("body_node_id"),
            )
            if driver is not None:
                return driver
        return model

    def _capture(self):
        sdk = _sdk()
        by_character = {}
        for snapshot in self.snapshots:
            info = self._target_info(snapshot.model)
            if info is None or info.get("character") is None:
                continue
            character_key = _component_key(info["character"])
            group = by_character.setdefault(
                character_key,
                {
                    "character": info["character"],
                    "control_set": info.get("control_set"),
                    "bindings": [],
                    "policy": None,
                    "pins": [],
                    "fk_baselines": [],
                    "fk_by_key": {},
                    "previous_changed": [],
                    "overrides": [],
                    "overrides_active": False,
                },
            )
            binding = {
                "snapshot": snapshot,
                "info": info,
                "managed": False,
                "driver": None,
                "driver_info": None,
                "driver_translation": None,
                "driver_rotation": None,
            }
            group["bindings"].append(binding)
            self.bindings[id(snapshot)] = binding

        for group in by_character.values():
            selected_parts = tuple(
                binding["info"].get("body_part_name")
                for binding in group["bindings"]
                if binding["info"].get("body_part_name")
            )
            policy = HIKManipulationPolicy(
                sdk,
                group["character"],
                selected_parts,
            )
            group["policy"] = policy
            for binding in group["bindings"]:
                part_name = binding["info"].get("body_part_name")
                managed = (
                    self.operation in ("move", "rotate")
                    and policy.scope != KEYING_SELECTION
                    and (
                        policy.scope == KEYING_FULL_BODY
                        or policy.affects_body_part(part_name)
                    )
                )
                if not managed:
                    continue
                driver = self._driver(binding)
                if driver is None:
                    continue
                binding["managed"] = True
                binding["driver"] = driver
                binding["driver_info"] = self._target_info(driver)
                try:
                    binding["driver_translation"] = model_vector(
                        driver,
                        sdk.FBModelTransformationType.kModelTranslation,
                        True,
                    )
                except Exception:
                    binding["driver_translation"] = None
                try:
                    binding["driver_rotation"] = _rotation_matrix(driver)
                except Exception:
                    binding["driver_rotation"] = None

            if not any(
                binding["managed"] for binding in group["bindings"]
            ):
                continue
            body_parts = (
                None
                if policy.scope == KEYING_FULL_BODY
                else policy.body_parts
            )
            try:
                control_entries = self.index.character_controls(
                    self.context,
                    group["character"],
                    body_parts,
                )
            except Exception:
                control_entries = ()
            control_models = [entry.get("model") for entry in control_entries]
            control_models.extend(
                binding["snapshot"].model
                for binding in group["bindings"]
                if (
                    binding["managed"]
                    and binding["info"].get("kind") == "fk"
                )
            )
            group["fk_baselines"] = _capture_fk(
                group["control_set"],
                _unique_models(control_models),
            ) if group["control_set"] is not None else []
            group["fk_by_key"] = dict(
                (state["key"], state)
                for state in group["fk_baselines"]
            )
            try:
                indexed_effectors = self.index.character_effectors(
                    self.context,
                    group["character"],
                )
            except Exception:
                indexed_effectors = None
            group["pins"] = _capture_pins(
                group["character"],
                indexed_effectors,
                policy,
            )
            self._capture_overrides(group)

        self.groups = tuple(by_character.values())
        self._record(
            "hik_manipulation_captured",
            operation=self.operation,
            target_count=len(self.bindings),
            managed_count=sum(
                1
                for binding in self.bindings.values()
                if binding["managed"]
            ),
            modes=sorted(
                set(group["policy"].keying_mode for group in self.groups)
            ),
            body_parts=sorted(
                set(
                    part
                    for group in self.groups
                    for part in group["policy"].body_parts
                )
            ),
        )

    @staticmethod
    def _add_override(group, prop):
        if prop is None:
            return
        if any(item["property"] is prop for item in group["overrides"]):
            return
        group["overrides"].append(
            {
                "property": prop,
                "original": _numeric_value(prop),
            }
        )

    def _capture_overrides(self, group):
        selected_property = {
            "move": "IK Reach Translation",
            "rotate": "IK Reach Rotation",
        }.get(self.operation)
        if selected_property:
            for binding in group["bindings"]:
                if not binding["managed"]:
                    continue
                self._add_override(
                    group,
                    _find_property(binding["driver"], selected_property),
                )
        # Pins are immutable user state. Only the corresponding reach is
        # temporarily raised so the solver honors the pin; Pull remains exactly
        # as authored, including Full Body No Pull behavior.
        for pin in group["pins"]:
            if pin["translation_pinned"]:
                self._add_override(group, pin["translation"])
            if pin["rotation_pinned"]:
                self._add_override(group, pin["rotation"])

    @property
    def has_hik_targets(self):
        return bool(self.bindings)

    @property
    def active(self):
        return any(
            binding["managed"]
            for binding in self.bindings.values()
        )

    @property
    def status_suffix(self):
        labels = []
        for group in self.groups:
            label = group["policy"].label
            parts = sorted(group["policy"].body_parts)
            if label == "Body Part" and parts:
                label += " " + "/".join(
                    part.replace("_", " ").title()
                    for part in parts
                )
            if label not in labels:
                labels.append(label)
        return " | HIK " + ", ".join(labels) if labels else ""

    @property
    def undo_models(self):
        models = []
        for binding in self.bindings.values():
            if binding["managed"]:
                models.extend(
                    (
                        binding["snapshot"].model,
                        binding["driver"],
                    )
                )
        for group in self.groups:
            models.extend(
                state["model"] for state in group["fk_baselines"]
            )
        return _unique_models(models)

    def handles(self, snapshot):
        binding = self.bindings.get(id(snapshot))
        return bool(binding and binding["managed"])

    @staticmethod
    def _set_overrides(group, active):
        if bool(group.get("overrides_active")) == bool(active):
            return
        for item in group["overrides"]:
            prop = item["property"]
            try:
                prop.Data = 100.0 if active else item["original"]
            except Exception:
                pass
        group["overrides_active"] = bool(active)

    def _evaluate(self, resolve=False, deformations=True):
        if resolve:
            try:
                self.context.scene.CandidateEvaluationAndResolve()
            except Exception:
                pass
        self.context.evaluation.flush_now()
        if deformations:
            try:
                self.context.scene.EvaluateDeformations()
            except Exception:
                pass

    def _begin_solve(self):
        for group in self.groups:
            if not any(
                binding["managed"] for binding in group["bindings"]
            ):
                continue
            previous = [
                group["fk_by_key"][state["key"]]
                for state in group["previous_changed"]
                if state["key"] in group["fk_by_key"]
            ]
            _apply_fk(previous)
            self._set_overrides(group, True)

    def _finish_solve(self):
        managed_groups = [
            group
            for group in self.groups
            if any(binding["managed"] for binding in group["bindings"])
        ]
        if not managed_groups:
            return False
        try:
            self._evaluate(resolve=False, deformations=False)
            solved = [
                (group, _capture_changed(group))
                for group in managed_groups
            ]
        finally:
            for group in managed_groups:
                self._set_overrides(group, False)
        for group, changed in solved:
            _apply_fk(changed)
            group["previous_changed"] = changed
        self._evaluate(resolve=True)
        return True

    def apply_translation(self, targets):
        pairs = tuple(targets)
        if not self.active:
            return self.finish_direct_preview()
        self._begin_solve()
        written = []
        try:
            for snapshot, target in pairs:
                binding = self.bindings.get(id(snapshot))
                if not binding or not binding["managed"]:
                    continue
                driver = binding["driver"]
                if any(_same_component(driver, model) for model in written):
                    continue
                if _same_component(driver, snapshot.model):
                    driver_target = list(target)
                else:
                    origin = binding["driver_translation"]
                    if origin is None:
                        continue
                    delta = [
                        float(target[index]) - float(snapshot.original[index])
                        for index in range(3)
                    ]
                    driver_target = [
                        float(origin[index]) + delta[index]
                        for index in range(3)
                    ]
                set_world_translation(driver, driver_target)
                written.append(driver)
            return self._finish_solve()
        except Exception:
            for group in self.groups:
                self._set_overrides(group, False)
            raise

    def apply_rotation(self, targets):
        pairs = tuple(targets)
        if not self.active:
            return self.finish_direct_preview()
        self._begin_solve()
        written = []
        try:
            for snapshot, target, delta in pairs:
                binding = self.bindings.get(id(snapshot))
                if not binding or not binding["managed"]:
                    continue
                driver = binding["driver"]
                if any(_same_component(driver, model) for model in written):
                    continue
                if _same_component(driver, snapshot.model):
                    driver_target = target
                else:
                    original = binding["driver_rotation"]
                    if original is None:
                        continue
                    driver_target = _matrix3_multiply(delta, original)
                _set_rotation_matrix(driver, driver_target)
                written.append(driver)
            return self._finish_solve()
        except Exception:
            for group in self.groups:
                self._set_overrides(group, False)
            raise

    def finish_direct_preview(self):
        if not self.has_hik_targets:
            return False
        # Selection-mode manipulation intentionally does not synchronize the
        # complete Control Rig. Scale likewise has no HIK Reach/pin solve.
        self._evaluate(resolve=False)
        return True

    def restore(self):
        if not self.has_hik_targets:
            return False
        for group in self.groups:
            self._set_overrides(group, False)
            _apply_fk(group["fk_baselines"])
            group["previous_changed"] = []
        restored = []
        for binding in self.bindings.values():
            if not binding["managed"]:
                continue
            driver = binding["driver"]
            if any(_same_component(driver, model) for model in restored):
                continue
            if (
                self.operation == "move"
                and binding["driver_translation"] is not None
            ):
                set_world_translation(
                    driver,
                    binding["driver_translation"],
                )
            elif (
                self.operation == "rotate"
                and binding["driver_rotation"] is not None
            ):
                _set_rotation_matrix(
                    driver,
                    binding["driver_rotation"],
                )
            restored.append(driver)
        self._evaluate(resolve=self.active)
        return True

    def close(self):
        if self._closed:
            return
        for group in self.groups:
            self._set_overrides(group, False)
        self._closed = True
        self._record(
            "hik_manipulation_closed",
            operation=self.operation,
        )
