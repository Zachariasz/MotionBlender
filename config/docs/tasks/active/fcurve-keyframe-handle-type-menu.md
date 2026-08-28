# Task: FCurves Set Keyframe Handle Type 'V' Menu

Status: completed  
Last updated: 2026-08-28  
Owner/context: FCurves / Tangent Handling

## Goal

Provide a Blender-style "Set Keyframe Handle Type" popup menu in MotionBuilder's FCurves editor when pressing `V`, containing all 5 keyframe handle types: Free, Aligned, Vector, Automatic, and Auto Clamped, each mapped directly to Autodesk MotionBuilder's native tangent modes and tangent weighting behaviors.

## Acceptance criteria

- [x] 'V' popup menu in FCurves contains all 5 options in order: Free, Aligned, Vector, Automatic, Auto Clamped.
- [x] Free sets MotionBuilder Break Tangents (`kFBTangentModeBreak`, `TangentBreak=True`).
- [x] Aligned sets Spline Tangents (`kFBTangentModeTimeIndependent`, `TangentBreak=False`), unweights tangents, and performs Unify Tangents as the final step.
- [x] Vector initializes Smooth Tangents (`kFBTangentModeAuto`), breaks tangents (`TangentBreak=True`), calculates and applies Discontinuity Left & Right slopes to neighbor keys, unweights tangents, and retains Smooth Tangent mode so keys automatically target neighbors when moved.
- [x] Automatic sets Smooth Tangents (`kFBTangentModeAuto`, `TangentBreak=False`), weights tangents (`kFBTangentWeightModeBoth`), and performs Unify Tangents as the final step.
- [x] Auto Clamped sets Auto Tangents (`kFBTangentModeClampProgressive`, `TangentBreak=False`) and weights tangents (`kFBTangentWeightModeBoth`).
- [x] Vector SVG icons created and loaded for all options.
- [x] Menu actions contain accelerator mnemonics (`&Free`, `&Aligned`, `&Vector`, `A&utomatic`, `Auto &Clamped`) and right-aligned `'V'` shortcut hints.
- [x] Automated test suite in `tests/test_selected_key_tangents_menu.py` executed and passing under MotionBuilder Python.

## Scope

Included:
- `custom/SelectedKeyTangentsMenu.py` (`fcurves.tangents_menu`)
- `custom/icons/handle_free.svg`
- `custom/icons/handle_aligned.svg`
- `custom/icons/handle_automatic.svg`
- `custom/icons/handle_autoclamped.svg`
- `custom/icons/2handle_vector.svg`
- `tests/test_selected_key_tangents_menu.py`
- `tests/test_fcurve_mutation.py`

## Important files

| File | Why it matters |
| --- | --- |
| `custom/SelectedKeyTangentsMenu.py` | Implementation of tangent operations, icon binding, and `SelectedKeyTangentsMenu` Qt menu widget. |
| `custom/icons/*.svg` | Vector icons for keyframe handle types rendered in menu rows. |
| `tests/test_selected_key_tangents_menu.py` | Unit tests for all 5 handle modes, derivative math, weighting, and UI action binding. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-28 | Map Blender handle types directly to MotionBuilder SDK tangent modes and weight modes. | Ensures full fidelity with Blender muscle memory while using MotionBuilder's C++ curve evaluation. | Custom mathematical curves overriding native FCurves evaluation. |
| 2026-08-28 | Aligned and Automatic execute `_unify_key_tangents` as their final action. | Guarantees that previously broken or asymmetric handles become unified and continuous. | Leaving left/right derivatives divergent. |
| 2026-08-28 | Vector tangents retain `kFBTangentModeAuto` with `TangentBreak=True`. | Allows keys when moved in the editor to dynamically target neighbor keys while remaining independently broken on left and right sides. | Setting static `kFBTangentModeBreak` which prevents dynamic neighbor targeting on move. |

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `custom/icons/handle_free.svg` | Created vector SVG icon for Free handle. | Passed (mobupy) |
| `custom/icons/handle_aligned.svg` | Created vector SVG icon for Aligned handle. | Passed (mobupy) |
| `custom/icons/handle_automatic.svg` | Created vector SVG icon for Automatic handle. | Passed (mobupy) |
| `custom/icons/handle_autoclamped.svg` | Created vector SVG icon for Auto Clamped handle. | Passed (mobupy) |
| `custom/SelectedKeyTangentsMenu.py` | Added 5 handle setters, unify helper, and rebuilt menu UI. | Passed (mobupy) |
| `tests/test_selected_key_tangents_menu.py` | Created unit test suite covering all 5 modes, icons, and menu actions. | Passed (mobupy) |
| `tests/test_fcurve_mutation.py` | Fixed SDK mock typing for shiboken support. | Passed (mobupy) |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `& "mobupy.exe" -m unittest tests.test_selected_key_tangents_menu` | MotionBuilder 2026 / Python 3.11 | passed | Ran 7 tests in 0.166s, OK |
| `& "mobupy.exe" -m unittest tests.test_fcurve_mutation tests.test_fcurve_add_key tests.test_selected_key_tangents_menu` | MotionBuilder 2026 / Python 3.11 | passed | Ran 18 tests in 0.142s, OK |
