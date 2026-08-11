"""Bake the active character's skeleton Hips Z motion to an RM null.

The resulting Relation constraint is:

    RM Translation
        -> Vector to Number (Z)
        -> Number to Vector (Z)
        -> skeleton Hips Translation

Both model boxes use global transforms.  Consequently, RM stays at world
X = 0 and Y = 0 while carrying the skeleton Hips world-Z motion.
"""

import traceback

from pyfbsdk import (
    FBApplication,
    FBBodyNodeId,
    FBConnect,
    FBConstraintRelation,
    FBFindModelByLabelName,
    FBMessageBox,
    FBModelNull,
    FBPlayerControl,
    FBPlotOptions,
    FBSystem,
    FBTime,
    FBVector3d,
)


TOOL_NAME = "Bake Hips Z to RM"
RM_NAME = "RM"
RELATION_NAME = "RM drives Hips Z"
TEMP_RELATION_NAME = "__Bake Hips Z to RM__"


def _find_animation_node(parent_node, name):
    if parent_node is None:
        return None

    for node in parent_node.Nodes:
        if str(node.Name) == name:
            return node

    return None


def _require_animation_node(parent_node, name, box_label):
    node = _find_animation_node(parent_node, name)
    if node is not None:
        return node

    available = []
    if parent_node is not None:
        try:
            available = [str(child.Name) for child in parent_node.Nodes]
        except Exception:
            available = []

    raise RuntimeError(
        "Could not find the {0!r} connector on {1}. Available connectors: {2}".format(
            name,
            box_label,
            ", ".join(available) if available else "(none)",
        )
    )


def _connect(source_node, destination_node, description):
    result = FBConnect(source_node, destination_node)
    if result is False:
        raise RuntimeError("MotionBuilder could not connect " + description + ".")


def _write_number(node, value):
    """Set an unconnected Number-to-Vector input to an explicit constant."""
    try:
        node.WriteData([float(value)])
    except Exception:
        # Number-to-Vector inputs default to zero, so this is only a defensive
        # assignment and is safe to skip on bindings that reject WriteData here.
        pass


def _unique_component_name(base_name):
    existing = set()
    for component in FBSystem().Scene.Components:
        try:
            existing.add(str(component.Name))
        except Exception:
            pass

    if base_name not in existing:
        return base_name

    index = 1
    while True:
        candidate = "{0} {1}".format(base_name, index)
        if candidate not in existing:
            return candidate
        index += 1


def _create_z_translation_relation(name, source_model, receiver_model):
    """Create an inactive global-space Z-only translation relation."""
    relation = FBConstraintRelation(name)

    try:
        relation.Active = False

        source_box = relation.SetAsSource(source_model)
        receiver_box = relation.ConstrainObject(receiver_model)
        vector_to_number = relation.CreateFunctionBox(
            "Converters", "Vector to Number"
        )
        number_to_vector = relation.CreateFunctionBox(
            "Converters", "Number to Vector"
        )

        if source_box is None:
            raise RuntimeError("Could not create the Relation sender box.")
        if receiver_box is None:
            raise RuntimeError("Could not create the Relation receiver box.")
        if vector_to_number is None:
            raise RuntimeError("Could not create the Vector to Number box.")
        if number_to_vector is None:
            raise RuntimeError("Could not create the Number to Vector box.")

        source_box.UseGlobalTransforms = True
        receiver_box.UseGlobalTransforms = True

        relation.SetBoxPosition(source_box, 0, 100)
        relation.SetBoxPosition(vector_to_number, 300, 100)
        relation.SetBoxPosition(number_to_vector, 600, 100)
        relation.SetBoxPosition(receiver_box, 900, 100)

        source_translation = _require_animation_node(
            source_box.AnimationNodeOutGet(),
            "Translation",
            "sender",
        )
        vector_input = _require_animation_node(
            vector_to_number.AnimationNodeInGet(),
            "V",
            "Vector to Number",
        )
        source_z = _require_animation_node(
            vector_to_number.AnimationNodeOutGet(),
            "Z",
            "Vector to Number",
        )
        receiver_z = _require_animation_node(
            number_to_vector.AnimationNodeInGet(),
            "Z",
            "Number to Vector",
        )
        vector_result = _require_animation_node(
            number_to_vector.AnimationNodeOutGet(),
            "Result",
            "Number to Vector",
        )
        receiver_translation = _require_animation_node(
            receiver_box.AnimationNodeInGet(),
            "Translation",
            "receiver",
        )

        number_x = _require_animation_node(
            number_to_vector.AnimationNodeInGet(),
            "X",
            "Number to Vector",
        )
        number_y = _require_animation_node(
            number_to_vector.AnimationNodeInGet(),
            "Y",
            "Number to Vector",
        )
        _write_number(number_x, 0.0)
        _write_number(number_y, 0.0)

        _connect(
            source_translation,
            vector_input,
            "sender Translation to Vector to Number V",
        )
        _connect(
            source_z,
            receiver_z,
            "Vector to Number Z to Number to Vector Z",
        )
        _connect(
            vector_result,
            receiver_translation,
            "Number to Vector Result to receiver Translation",
        )

        return relation
    except Exception:
        try:
            relation.Active = False
        except Exception:
            pass
        try:
            relation.FBDelete()
        except Exception:
            pass
        raise


def _make_plot_options(time_mode):
    options = FBPlotOptions()
    options.PlotAllTakes = False
    options.PlotOnFrame = True
    options.PlotPeriod = FBTime(0, 0, 0, 1, 0, time_mode)
    options.PlotTranslationOnRootOnly = False
    options.UseConstantKeyReducer = False
    options.ConstantKeyReducerKeepOneKey = False

    for attribute_name, value in (
        ("PreciseTimeDiscontinuities", True),
        ("PlotLockedProperties", True),
    ):
        try:
            setattr(options, attribute_name, value)
        except Exception:
            pass

    return options


def _translation_z_key_count(model):
    try:
        translation_node = model.Translation.GetAnimationNode()
    except Exception:
        translation_node = None

    z_node = _find_animation_node(translation_node, "Z")
    if z_node is None:
        return None

    try:
        return int(z_node.KeyCount)
    except Exception:
        pass

    try:
        return len(z_node.FCurve.Keys)
    except Exception:
        return None


def _delete_component(component):
    if component is None:
        return

    try:
        component.Active = False
    except Exception:
        pass

    try:
        component.FBDelete()
    except Exception:
        pass


def bake_hips_z_to_rm():
    system = FBSystem()
    scene = system.Scene
    player = FBPlayerControl()
    character = FBApplication().CurrentCharacter

    if character is None:
        raise RuntimeError(
            "No active character is selected in Character Controls."
        )

    hips = character.GetModel(FBBodyNodeId.kFBHipsNodeId)
    if hips is None:
        raise RuntimeError(
            "The active character has no characterized skeleton Hips model."
        )

    take = system.CurrentTake
    if take is None:
        raise RuntimeError("No current take is available to bake.")

    if FBFindModelByLabelName(RM_NAME) is not None:
        raise RuntimeError(
            "A model named {0!r} already exists. Rename or delete it, then run "
            "the script again.".format(RM_NAME)
        )

    original_time = FBTime(system.LocalTime.Get())
    rm = None
    temporary_relation = None
    final_relation = None

    try:
        rm = FBModelNull(RM_NAME)
        rm.Show = True
        try:
            rm.Visibility = True
        except Exception:
            pass

        rm.Translation = FBVector3d(0.0, 0.0, 0.0)
        rm.Rotation = FBVector3d(0.0, 0.0, 0.0)
        rm.Scaling = FBVector3d(1.0, 1.0, 1.0)
        rm.Translation.SetAnimated(True)

        # First use the requested Z-only graph in the opposite direction as a
        # temporary bake driver: skeleton Hips -> RM.
        temporary_relation = _create_z_translation_relation(
            _unique_component_name(TEMP_RELATION_NAME),
            hips,
            rm,
        )
        temporary_relation.Active = True
        scene.Evaluate()

        time_mode = player.GetTransportFps()
        options = _make_plot_options(time_mode)
        take.PlotTakeOnObjects(options, [rm])

        _delete_component(temporary_relation)
        temporary_relation = None

        player.Goto(original_time)
        scene.Evaluate()

        key_count = _translation_z_key_count(rm)
        if key_count == 0:
            raise RuntimeError(
                "MotionBuilder did not create any Z-translation keys on RM."
            )

        # Build the permanent graph exactly as requested: RM -> skeleton Hips.
        final_relation = _create_z_translation_relation(
            _unique_component_name(RELATION_NAME),
            rm,
            hips,
        )
        final_relation.Active = True

        rm.Selected = True
        player.Goto(original_time)
        scene.Evaluate()

        return {
            "character": str(character.Name),
            "hips": str(hips.LongName),
            "take": str(take.Name),
            "rm": rm,
            "relation": final_relation,
            "z_key_count": key_count,
        }
    except Exception:
        _delete_component(temporary_relation)
        _delete_component(final_relation)
        _delete_component(rm)

        try:
            player.Goto(original_time)
            scene.Evaluate()
        except Exception:
            pass

        raise


def main():
    result = bake_hips_z_to_rm()
    key_text = (
        str(result["z_key_count"])
        if result["z_key_count"] is not None
        else "baked"
    )
    FBMessageBox(
        TOOL_NAME,
        "Created RM with {0} Z key(s) from:\n{1}\n\n"
        "Created and activated Relation constraint:\n{2}".format(
            key_text,
            result["hips"],
            result["relation"].Name,
        ),
        "OK",
    )
    return result


try:
    main()
except Exception:
    FBMessageBox(TOOL_NAME + " Error", traceback.format_exc()[-2200:], "OK")
