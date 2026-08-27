# Task: Toggle Animation Layers Mute Multi-Selection Support

Status: active  
Last updated: 2026-08-27  
Owner/context: Antigravity / Pair Programming / Ollama Qwen 2.5 Coder 14B

## Goal

Enhance `custom/ToggleCurrentAnimationLayerMute.py` (catalog feature `animation.toggle_layer_mute`, default shortcut `M`) to mute or unmute all selected animation layers in the current take simultaneously, falling back to the active layer if no layers are explicitly selected.

## Acceptance criteria

- [x] If one or more animation layers are selected (`layer.Selected` is true), the script targets all selected layers.
- [x] If no animation layers are selected, the script falls back to the current active layer (`take.GetCurrentLayer()`).
- [x] Toggling logic: if any target layer is unmuted (`not layer.Mute`), all target layers become muted (`Mute = True`). If all target layers are already muted, all become unmuted (`Mute = False`).
- [x] Triggers `FBSystem().Scene.Evaluate()` immediately following state changes.
- [x] Outputs informative state messages to the console for each modified layer.
- [x] Offline unit test suite `tests/test_toggle_animation_layer_mute.py` created and all 7 tests passing.
- [x] Verified in live MotionBuilder 2026 session via the Antigravity bridge.
- [x] Documentation updated.

## Scope

Included:

- `custom/ToggleCurrentAnimationLayerMute.py`
- `tests/test_toggle_animation_layer_mute.py`
- `tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`
- `docs/PROJECT_STATUS.md`
- `docs/tasks/active/toggle-animation-layers-mute.md`

## Non-goals

- Altering take selection or story clip muting.
- Modifying layer weights, solo states, or lock states.

## Important files

| File | Why it matters |
| --- | --- |
| `custom/ToggleCurrentAnimationLayerMute.py` | Primary script implementing layer discovery and mute toggle logic. |
| `mobu_tools_manager/catalog.py` | Declarative catalog entry for `animation.toggle_layer_mute` (slot 40). |
| `mobu_tools_manager/generated_actions/Script40.py` | ActionScript wrapper dispatching `animation.toggle_layer_mute`. |
| `tests/test_toggle_animation_layer_mute.py` | Automated offline test suite covering multi-selection, fallback, toggle behavior, and error handling. |

## Starting state

- Previously, `ToggleCurrentAnimationLayerMute.py` only queried `take.GetCurrentLayer()` and toggled that single layer's `Mute` property.
- When an animator selected multiple layers (e.g. `AnimLayer2` and `AnimLayer3`) in the Animation Layer editor and pressed `M`, only the active layer was toggled.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-27 | Toggle rule: mute all if any unmuted, else unmute all | Standard DCC behavior (Photoshop/Blender/Maya/MotionBuilder) for bulk visibility/mute toggling across multi-selection. | Inverting each layer independently (causes desynchronized states when layers have mixed mute status). |
| 2026-08-27 | Fallback to `take.GetCurrentLayer()` when no layers are selected | Preserves single-layer hotkey workflow when animator has no explicit multi-selection. | Raising an error or doing nothing when no layers are selected. |
| 2026-08-27 | Use Ollama Qwen 2.5 Coder 14B for implementation design | Leveraged local LLM code generation and refined with MotionBuilder main-thread and scene evaluation safety rules. | Manual ad-hoc rewrite without model assistance. |

## Progress

### Completed

- Generated initial design using Ollama `qwen2.5-coder:14b`.
- Implemented `get_target_animation_layers(take)` and `toggle_current_animation_layer_mute()` in `custom/ToggleCurrentAnimationLayerMute.py`.
- Added comprehensive unit tests in `tests/test_toggle_animation_layer_mute.py`.
- Verified live on active MotionBuilder 2026 instance via the Antigravity bridge (`antigravity_mobu_client.py`).
- Updated integration checklist and project status documentation.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `custom/ToggleCurrentAnimationLayerMute.py` | Multi-layer selection discovery and bulk mute/unmute toggle logic. | Live MotionBuilder execution passed; offline unit tests passed. |
| `tests/test_toggle_animation_layer_mute.py` | Unit tests for multi-selection, active layer fallback, toggle states, and error handling. | `py -3 -m unittest tests.test_toggle_animation_layer_mute` (7/7 passed). |
| `tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Added integration checklist verification steps for layer mute multi-selection. | Manual inspection. |
| `docs/PROJECT_STATUS.md` | Updated status and verification notes. | Manual inspection. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `py -3 -m unittest tests.test_toggle_animation_layer_mute` | Python 3.12 (offline mock SDK) | passed | 7 tests ran in 0.010s, OK |
| Live multi-selection mute (`AnimLayer2`, `AnimLayer3`) | MotionBuilder 2026 via Antigravity Bridge | passed | Output: `Animation layer 'AnimLayer2' (index 2) is now muted.` / `Animation layer 'AnimLayer3' (index 3) is now muted.` |
| Live multi-selection unmute (`AnimLayer2`, `AnimLayer3`) | MotionBuilder 2026 via Antigravity Bridge | passed | Output: `Animation layer 'AnimLayer2' (index 2) is now unmuted.` / `Animation layer 'AnimLayer3' (index 3) is now unmuted.` |
| Live manager dispatch `animation.toggle_layer_mute` | MotionBuilder 2026 via Antigravity Bridge | passed | Dispatched cleanly through `mobu_tools_manager.dispatch("animation.toggle_layer_mute")` |

## Handoff notes

- The catalog entry `animation.toggle_layer_mute` uses `custom/ToggleCurrentAnimationLayerMute.py` via `LegacyAdapter`. When testing live in MotionBuilder after code edits, call `mobu_tools_manager.reload_feature("animation.toggle_layer_mute")` if the manager had already cached the module.
