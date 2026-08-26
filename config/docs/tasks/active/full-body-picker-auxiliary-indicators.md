# Task: Full-body picker auxiliary indicators and pull delegation

Status: active  
Last updated: 2026-08-26  

## Goal

Make auxiliary effectors in the Custom Full Body Bone Picker visually indicate
Reach Translation and Reach Rotation with dynamic green-to-red color blending
based on IK Pull, delegate the auxiliary effector's `IK Pull` slider to the
connected base effector model, and prevent `NotImplementedError` when reading
or writing unsupported property wrappers in `pyfbsdk`.

## Acceptance criteria

- [x] Auxiliary effectors draw proportional half-circle fills for Reach Translation
  (left half) and Reach Rotation (right half).
- [x] Auxiliary effector fill color blends dynamically from green (0% pull) to
  red (100% pull) based on the connected base effector's IK Pull ratio.
- [x] Adjusting the `IK Pull` slider on an auxiliary effector delegates the change
  to the connected base effector model.
- [x] Changing `IK Pull` on either the base effector or its auxiliary effector
  synchronizes the visual indicator color across both markers simultaneously.
- [x] Property reads and writes use safe access helpers (`is_property_accessible`,
  `set_property_float`) to avoid `NotImplementedError` crashes on unsupported
  `FBProperty` types.
- [x] Focused offline unit tests pass (15/15 tests).
- [x] Live MotionBuilder script execution and probe verification pass.
- [x] Documentation and integration checklist updated.

## Scope

Included:

- Managed legacy feature `pickers.full_body` (`Scripts/CustomFullBodyBonePicker.py`).
- Effector slider popup and property retrieval logic.
- Auxiliary effector drawing and base effector mapping.
- Focused unit tests in `Scripts/tests/test_full_body_picker.py`.
- Integration checklist and package README documentation.

## Non-goals

- Refactoring the hand or spine pickers.
- Altering the Character Controls XML parsing or base anchor coordinate system.
- Changing pinning presets or bake algorithms.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | Implementation of picker drawing, slider popup, and property handling. |
| `Scripts/tests/test_full_body_picker.py` | Focused unit tests for picker behavior and regression safety. |
| `Scripts/mobu_tools_manager/README.md` | Feature documentation for the full-body picker. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Integration test checklist for live MotionBuilder verification. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-26 | Use `base_effector_model_for_model` to resolve parent IK effector for auxiliary models. | Auxiliary `FBModelMarker` instances do not maintain their own independent `IK Pull` solver property in MotionBuilder; pull is solved at the limb/effector level. | Disabling the Pull slider entirely on auxiliary effectors without delegating to base effector. |
| 2026-08-26 | Implement `is_property_accessible(prop)` and `set_property_float(prop, value)`. | Querying `.Data` or assigning `.Data` on unsupported `FBProperty` instances in `pyfbsdk` throws `NotImplementedError: Unable to access the data for this type of property.`. | Allowing raw `.Data` assignments inside unchecked `try...except` blocks in the UI layer. |
| 2026-08-26 | Compute auxiliary fill color from `base_model`'s `IK Pull` value. | Matches native Character Controls visual feedback and ensures consistent color synchronization between parent and auxiliary markers. | Forcing auxiliary markers to always be static green or static blue. |

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | Added half-circle fills and pull-ratio color blending to `draw_auxiliary`, added `base_effector_model_for_model`, delegated `IK Pull` in `get_effector_slider_properties`, added `is_property_accessible` and `set_property_float`. | 15 unit tests passed; live bridge execution succeeded. |
| `Scripts/tests/test_full_body_picker.py` | Added `test_auxiliary_drawing_renders_reach_and_pull_fills`, `test_property_accessibility_and_safe_setting`, and `test_auxiliary_effector_delegates_pull_to_base_effector`. | 15 unit tests passed. |
| `Scripts/mobu_tools_manager/README.md` | Documented auxiliary effector reach/pull indicator and connected base effector pull delegation. | Reviewed. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Added live verification steps for auxiliary effector sliders and indicator synchronization. | Reviewed. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `py -3 -m unittest discover -s tests -p "test_full_body_picker.py" -v` | Python 3.12 (Workspace) | passed | 15 tests passed in 0.57s. |
| `antigravity_mobu_client.py exec CustomFullBodyBonePicker.py` | MotionBuilder 2026 (Live Bridge) | passed | Script executed successfully in 120ms. |
| `antigravity_mobu_client.py probe scene` | MotionBuilder 2026 (Live Bridge) | passed | Validated character `Main` with `RightWristEffectorAux1`. |
