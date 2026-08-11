"""Global transform interaction policy."""

from __future__ import absolute_import


DEFAULTS = {
    "precision_modifier": "Shift",
    "precision_multiplier": 0.1,
    "snap_modifier": "Control",
    "translation_snap": 1.0,
    "rotation_snap": 10.0,
    "scale_snap": 0.1,
    "fcurve_value_snap": 1.0,
    "tangent_side_cycle_key": "T",
    "object_pivot_mode": "individual",
    "fcurve_pivot_mode": "median",
}


class InteractionPolicy(object):
    def __init__(self, values=None):
        settings = dict(DEFAULTS)
        if isinstance(values, dict):
            settings.update(values)
        self.precision_modifier = str(settings["precision_modifier"])
        self.precision_multiplier = max(
            0.000001,
            float(settings["precision_multiplier"]),
        )
        self.snap_modifier = str(settings["snap_modifier"])
        if self.precision_modifier.lower() == self.snap_modifier.lower():
            raise ValueError(
                "Precision and snap modifiers must be different."
            )
        self.translation_snap = max(
            0.000001,
            float(settings["translation_snap"]),
        )
        self.rotation_snap = max(0.000001, float(settings["rotation_snap"]))
        self.scale_snap = max(0.000001, float(settings["scale_snap"]))
        self.fcurve_value_snap = max(
            0.000001,
            float(settings["fcurve_value_snap"]),
        )
        self.tangent_side_cycle_key = str(
            settings["tangent_side_cycle_key"]
        ).upper()
        self.object_pivot_mode = str(settings["object_pivot_mode"])
        self.fcurve_pivot_mode = str(settings["fcurve_pivot_mode"])

    def as_dict(self):
        return {
            "precision_modifier": self.precision_modifier,
            "precision_multiplier": self.precision_multiplier,
            "snap_modifier": self.snap_modifier,
            "translation_snap": self.translation_snap,
            "rotation_snap": self.rotation_snap,
            "scale_snap": self.scale_snap,
            "fcurve_value_snap": self.fcurve_value_snap,
            "tangent_side_cycle_key": self.tangent_side_cycle_key,
            "object_pivot_mode": self.object_pivot_mode,
            "fcurve_pivot_mode": self.fcurve_pivot_mode,
        }
