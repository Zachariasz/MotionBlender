# Task: G/R/S axis and rotation-mode restart

Status: active; axis-component preservation and guide-centering fixes implemented; live interaction verification pending  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2026 Viewer transforms

## Goal

Make Viewer transforms retain only the pre-lock component on the newly selected
axis: displacement for Move, angular twist for Rotate, and scale factor for
Scale. Restore all other components. Make a later axis selection apply the same
rule, and make the second R discard the first rotation before switching
orbit/trackball mode. Different G/R/S mode launches must continue to cancel the
previous operation before the replacement captures. Frozen axis guides must
also remain visually centered on the selected pivot when perspective puts a
500-unit endpoint behind the camera.

## Acceptance criteria

- [x] Viewer Move keeps only the current displacement, Rotate only the angular
  twist, and Scale only the scale factor on their newly active axis; every other
  component restores on valid X/Y/Z presses.
- [x] Changing axis or cycling global/local/off starts at the new key cursor
  and retains only that new axis's matching component.
- [x] The second R restores original rotations before switching rotation mode.
- [x] All six different G/R/S handoffs remain cancel-then-start transitions.
- [x] FCurve constraint and tangent-side rebase behavior is unchanged.
- [x] Behind-camera axis endpoints are rejected and the valid half is mirrored
  around the projected pivot.
- [x] Unequal perspective halves are balanced so the pivot is the exact visual
  midpoint.
- [x] Focused offline verification passes.
- [ ] Live MotionBuilder Viewer verification passes in an isolated scene.
- [x] Interaction documentation is updated.

## Scope

Included:

- `transform.move_camera_plane`
- `transform.rotate_mouse_orbit`
- `transform.scale_mouse_distance`
- Shared session handling for optional strategy restart hooks
- Viewer object Move/Rotate/Scale strategies and focused tests

## Non-goals

- FCurve axis or tangent-side semantics
- Cursor/focus/surface-rebinding work reverted earlier on 2026-08-11
- New transform modes or changed snapping/precision behavior

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/interactions/session.py` | Selects restart versus continuous rebase for in-session key transitions. |
| `Scripts/mobu_tools_manager/object_transforms/move.py` | Restores captured translations without closing the session. |
| `Scripts/mobu_tools_manager/object_transforms/rotate.py` | Restores rotations and zeroes orbit/trackball accumulators. |
| `Scripts/mobu_tools_manager/object_transforms/scale.py` | Restores captured scales and scale preview state. |
| `Scripts/mobu_tools_manager/object_transforms/targets.py` | Projects and centers the shared frozen Viewer axis guide. |
| `Scripts/tests/test_interactions.py` | Covers all three axis restarts, double-R restart, and G/R/S handoffs. |

## Starting state

Different G/R/S operations already used atomic cancel-then-start handoff and
were covered in both Viewer and FCurve domains. Viewer axis keys formerly
restarted every transform from its initial snapshot. Viewer Move, Rotate, and
Scale now preserve only their matching component on the new axis. The Object
Rotate R handler likewise used to rebase the current rotation before switching
orbit/trackball mode.

This file previously recorded a reverted cursor/focus cancellation task. The
user explicitly requested this new, narrower transform-preview restart behavior
on 2026-08-11; none of the earlier reverted cursor/focus work was reapplied.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-11 | Add an optional `restart_from_original` strategy hook used by Viewer object transforms. | It restores mutable scene state while preserving the one active undo/input/presentation session. | Full cancel-and-recapture on each axis key would churn ownership and risk stale wrappers. |
| 2026-08-11 | Leave strategies without the hook on continuous rebase behavior. | This keeps FCurve axis and tangent-side contracts unchanged. | Applying the Viewer restart globally would silently change graph editing behavior. |
| 2026-08-11 | Keep numeric input across a restart. | Existing shared policy requires typed values to survive and be reinterpreted under the new constraint. | Clearing typed input would violate the established numeric-input contract. |
| 2026-08-16 | Preserve only the newly locked-axis component when restarting every Viewer transform. | Locking an axis should discard off-axis preview without undoing matching-axis movement, rotation, or scale. | Restoring all components made axis-locking discard useful selected-axis changes. |
| 2026-08-16 | Reset and retain Scale through local channels during axis restart. | MotionBuilder's global-scale write can retain unrelated preview channels. | A global-only reset did not reliably clear the free-scale preview. |
| 2026-08-16 | Flush evaluation before Scale captures its next segment base. | Live probing showed that an immediate SDK reread can return the pre-reset free-scale values and reapply all channels. | A queued evaluation runs too late because `begin_segment()` rereads scale synchronously after the restart hook. |
| 2026-08-11 | Balance the projected guide around its pivot and reject negative clip W. | A live Cube/global-Z probe put one endpoint behind the camera and the projected pivot outside the drawn segment (`t=-0.266`). | Drawing both raw +/-500 projections preserves nominal endpoints but can place the entire screen segment away from the object. |

## Progress

### Completed

- Added restart-aware session transitions for valid constraint and
  strategy-handled keys.
- Added non-terminal original-state restoration to Viewer Move, Rotate, and
  Scale.
- Kept `cancel()` routed through the same restoration implementation.
- Added focused interaction tests for G/R/S axis restart and double-R rotation
  restart.
- Added direct restoration-state tests for object Move, Rotate, and Scale.
- Changed Viewer axis restarts to retain only the newly active axis component:
  displacement for Move, twist for Rotate, and scale factor for Scale. Move,
  Rotate, and Scale all fully reset when switched off.
- Made the Scale restart reset and reapply only the retained local-axis value
  so unrelated free-scale channels cannot survive a global or local lock.
- Flushes the one axis-transition evaluation before Scale recaptures its segment
  base, preventing stale pre-reset channel values from being reapplied.
- Reloaded the live Scale feature and verified a temporary Null transitions
  from `(1.4, 1.4, 1.4)` to `(1.4, 1.0, 1.0)` on X lock, including the
  immediate post-lock preview.
- User confirmed the corrected live Scale gesture, then requested the durable
  transform and testing documentation update.
- Added perspective-balanced axis projection and behind-camera rejection.
- Added regression tests for negative clip W, one valid half, and unequal
  perspective halves.
- Updated the transform standard and testing index.
- Reconciled package instructions, the public README, the manager guide, and
  the live integration checklist with the Viewer restart, double-R, handoff,
  and FCurve rebase rules.
- Ran the complete offline suite; 162 of 163 tests passed. The sole failure is
  the pre-existing `ActionScript.txt` catalog mismatch for empty Script44 and is
  outside this transform change.
- Reloaded all three transform features in MotionBuilder and verified the same
  Cube/global-Z case now has zero pixel error between the selected pivot and
  the balanced guide midpoint.

### In progress

- Perform live Viewer verification.

### Next action

1. In an isolated MotionBuilder scene, reload the manager and test a free
   Viewer Move/Rotate/Scale preview to X/Y/Z: only the newly locked-axis
   displacement, twist, or scale factor must remain. Test X preview to Y,
   repeated-axis global/local/off cycling, double R, and all different-mode
   handoffs before both commit and cancel. Include a translated off-center
   object with global/local Z crossing behind the camera and confirm the object
   remains at the guide midpoint.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/interactions/session.py` | Supports a strategy-specific axis restart after selecting the new axis state. | 21 interaction tests passed. |
| `Scripts/mobu_tools_manager/object_transforms/move.py` | Preserves only selected-axis translation during Move-axis restart; cancellation and Move-off fully restore. | 20 runtime tests passed; live pending. |
| `Scripts/mobu_tools_manager/object_transforms/rotate.py` | Preserves selected-axis twist during axis restart; cancellation and Rotate-off fully restore. | 20 runtime and 8 rotation tests passed; live pending. |
| `Scripts/mobu_tools_manager/object_transforms/scale.py` | Resets and preserves the selected local scale channel during axis restart; cancellation and Scale-off fully restore. | 20 runtime and 8 scale tests passed; live pending. |
| `Scripts/mobu_tools_manager/object_transforms/targets.py` | Rejects behind-camera projection and balances the shared guide around its pivot. | Focused tests passed; bounded live geometry probe confirmed the failure geometry. |
| `Scripts/tests/test_interactions.py` | Viewer Move-axis, Rotate/Scale, and double-R regressions. | 21 tests passed. |
| `Scripts/tests/test_transform_runtime.py` | Move/Rotate/Scale axis preservation, restoration, and perspective/behind-camera guide tests. | 20 tests passed. |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Documents Viewer restart semantics and R-cycle exception. | Documentation review completed. |
| `Scripts/mobu_tools_manager/AGENTS.md` | Defines restart, rebase, and handoff rules for future implementation work. | Documentation review completed. |
| `Scripts/mobu_tools_manager/README.md` | Summarizes user-visible Viewer transform transitions. | Documentation review completed. |
| `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md` | Documents session ownership and guide capture ordering. | Documentation review completed. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Adds all Viewer axis-component preservation, double-R, handoff, and FCurve-rebase checks. | Documentation review completed. |
| `docs/TESTING.md` | Records focused coverage and the required transition distinctions. | Documentation review completed. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -m unittest discover -s tests -p "test_interactions.py" -v` | Bundled CPython | passed | 20 tests, OK. |
| `python -m unittest discover -s tests -p "test_transform_rotate.py" -v` | Bundled CPython | passed | 8 tests, OK. |
| `python -m unittest discover -s tests -p "test_transform_scale.py" -v` | Bundled CPython | passed | 6 tests, OK. |
| `python -m unittest discover -s tests -p "test_transform_runtime.py" -v` | Bundled CPython | passed | 17 tests, OK. |
| `python -m unittest discover -s tests -p "test_interactions.py" -v` | Bundled CPython | passed | 21 tests, OK (2026-08-16). |
| `python -m unittest discover -s tests -p "test_transform_runtime.py" -v` | Bundled CPython | passed | 18 tests, OK (2026-08-16). |
| `python -m unittest discover -s tests -p "test_transform_runtime.py" -v` | Bundled CPython | passed | 20 tests, OK (2026-08-16). |
| `python -m unittest discover -s tests -p "test_transform_rotate.py" -v` | Bundled CPython | passed | 8 tests, OK (2026-08-16). |
| `python -m unittest discover -s tests -p "test_transform_scale.py" -v` | Bundled CPython | passed | 8 tests, OK (2026-08-16). |
| Reload Scale and run evaluated temporary-Null X-lock probe | MotionBuilder 2026 bridge | passed | Restart and immediate post-lock preview both produced `(1.4, 1.0, 1.0)` from free preview `(1.4, 1.4, 1.4)`; temporary Null deleted. |
| User Viewer Scale retest | MotionBuilder 2026 | passed | User confirmed the corrected behavior after the live feature reload. |
| Read-only live selected-axis projection probe | MotionBuilder 2026 current scene | passed (diagnosis) | Cube/global-Z center `(636.0, 306.5)` lay outside raw endpoint segment (`t=-0.266`); positive endpoint had clip W `-170.6`. |
| `python -m unittest discover -s tests -v` | Bundled CPython sandbox | blocked | 241 run; focused Move tests passed, but 28 tests could not create temporary files or import PySide6, and two unrelated tests failed (`test_launcher_key_release_is_observed_but_passes_to_motionbuilder`, `test_visible_focused_children_exclude_hidden_selected_key_curves`). |
| Live MotionBuilder Viewer checklist | MotionBuilder 2026 isolated scene | not run | Required before final production acceptance. |
| Reload G/R/S and verify selected Cube/global-Z guide math | MotionBuilder 2026 current scene, read-only geometry after reload | passed | Behind-camera endpoint rejected; balanced midpoint and projected Cube pivot both `(636.0, 306.5)`, error `(0.0, 0.0)`; bridge result `20260811_184500_reload_and_verify_axis_center_20260811_184205.json`. |

## Blockers and open questions

- Live MotionBuilder behavior remains unverified; offline fakes cannot prove
  SDK wrapper, HIK, undo-stack, or native input behavior.

## Handoff notes

- The workspace does not expose `python` on `PATH`; offline tests use the Codex
  bundled Python runtime.
- Unrelated untracked workspace files observed before this task were left
  untouched.
