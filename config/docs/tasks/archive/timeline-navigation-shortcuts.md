# Task: Timeline navigation shortcuts

Status: complete  
Last updated: 2026-08-11

## Goal

Provide manager-owned shortcuts for bounded current-take timeline navigation and take-local marker jumps.

## Acceptance criteria

- [x] All eight requested keyboard actions dispatch stable manager feature IDs.
- [x] Frame jumps clamp to the current take and FPS jumps use the rounded current transport FPS.
- [x] Marker jumps use current-take markers and safely report when none exists in the requested direction.
- [x] Focused offline tests pass.
- [x] Live MotionBuilder verification is recorded.
- [x] Catalog, keyboard mapping, and current documentation are updated.

## Scope

Included:

- `animation.timeline_*` feature IDs, native navigation command module, ActionScript wrappers, Blender key map, and focused tests.

## Non-goals

- Global-marker navigation, timeline UI changes, and changes to unrelated keyboard profiles.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/features/timeline_navigation.py` | Navigation behavior. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable IDs and action slots. |
| `Keyboard/Blender.txt` | Active profile default bindings. |

## Starting state

- The Blender profile already bound Shift+Left/Right to native start/end actions; slots 45-52 were unused. Slot 44 remains assigned to Find Selected in Hierarchy.
- MotionBuilder SDK references confirm `FBTime.SetFrame`, `FBPlayerControl.Goto`, transport FPS access, and take-local time-mark navigation APIs.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-11 | Use eight manager-native commands sharing one module. | Each shortcut stays independently editable and observable while the timeline SDK logic stays cohesive. | A separate global Qt hook would compete with manager input ownership; standalone scripts would bypass the catalog. |
| 2026-08-11 | Clamp frame movement to current-take bounds and use take-local markers. | Matches the requested current-take semantics and avoids jumps into another take's range. | Global marks would cross take-specific intent. |
| 2026-08-11 | Route modifier-arrow shortcuts through the shared input router. | Live probes proved MotionBuilder was not dispatching the configured ActionScript slots. | Relying on the host ActionScript registry would leave the requested shortcuts nonfunctional. |

## Progress

### Completed

- Read manager routing, catalog, runtime, shortcut, documentation, and MotionBuilder SDK references.
- Added the native navigation module, eight catalog features, ActionScript wrappers, and Blender bindings in slots 45-52.
- Restored slot 44 to its existing Find Selected in Hierarchy dispatch after discovering its catalog reservation.
- Ran the focused offline navigation suite successfully with the bundled Python interpreter.
- Narrowed shortcut validation to G/R/S transform features after the live manager rejected timeline Shift bindings.
- Added the resident shared-input service after live native-action and standalone ActionScript probes both failed to execute from the configured slots.
- Reloaded the service through the bridge and verified its live Shift+Up callback moved frame 3 to 13, then restored frame 3.
- Confirmed the installed physical shortcuts work after the resident service reload.

### In progress

None.

### Next action

None. If desired, perform a visual marker-direction check later in an isolated take containing time marks.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/features/timeline_navigation.py` | Added bounded frame, take-boundary, FPS, take-marker navigation helpers, and reload-safe resident hotkey service. | Passed focused tests and live callback check |
| `Scripts/tests/test_timeline_navigation.py` | Added focused offline coverage, including profile/wrapper mappings and hotkey-service lifecycle. | 8 tests passed |
| `Scripts/mobu_tools_manager/generated_actions/Script45.py` through `Script52.py` | Added eight stable-ID dispatch wrappers. | Passed mapping test |
| `Scripts/mobu_tools_manager/catalog.py` | Added eight native timeline feature records in slots 45-52. | Passed slot/wrapper checks; broad catalog check blocked by pre-existing missing legacy files |
| `Scripts/mobu_tools_manager/manager.py` | Restricts precision/reserved-key shortcut validation to the G/R/S transform features. | Focused regression suite passed |
| `Scripts/tests/test_manager_shutdown.py` | Added validation-scope regression coverage. | 6 tests passed |
| `Scripts/mobu_tools_manager/runtime.py` | Added shared modifier-arrow hotkey routing. | Passed focused input-router tests |
| `Scripts/ActionScript.txt`, `Keyboard/Blender.txt` | Registered wrappers and assigned requested shortcuts. | Passed mapping test |
| `Scripts/mobu_tools_manager/README.md`, `docs/PROJECT_STATUS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Documented behavior, router ownership, counts, tests, and live procedure. | Updated |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Bundled Python: `-m unittest discover -s tests -p "test_timeline_navigation.py" -v` | Codex shell | passed | 8 tests passed |
| `test_catalog.CatalogTests.test_action_slots_are_unique` and `test_action_script_uses_wrappers_and_preserves_unmanaged` | Bundled Python | passed | Direct targeted invocation after slot repair |
| Bundled Python: `-m unittest discover -s tests -p "test_cursor_coordinator.py" -v` | Codex shell | passed | 30 tests passed, including modifier-arrow routing guards |
| Bundled Python: `-m unittest discover -s tests -p "test_manager_shutdown.py" -v` | Codex shell | passed | 6 tests passed, including timeline shortcut validation scope |
| Full `test_catalog.py` | Bundled Python | blocked | Pre-existing missing `custom/MoveKeysRight.py`, `MoveKeysLeft.py`, `MoveKeysValueUp.py`, and `MoveKeysValueDown.py` cause validation/entrypoint failures; no changes made to them |
| Shared router Shift+Up | MotionBuilder bridge | passed | Frame 3 moved to 13 and restored to 3; callback was consumed |
| Native ActionScript / standalone probe | MotionBuilder bridge | failed as expected | The host received `script45` but did not execute either project-mapped script; shared router now bypasses this host limitation |
| Physical navigation shortcuts | MotionBuilder | passed | User confirmed the installed shortcuts work after service reload |
| Physical marker shortcuts | MotionBuilder take with markers | not run | Current take has zero markers; unit coverage validates both directions |

## Blockers and open questions

- MotionBuilder is not available in the Codex shell, so live shortcut behavior must be verified in an isolated scene.
- The complete catalog module cannot pass until its four pre-existing missing legacy `MoveKeys*.py` inputs are restored or their historical catalog records are reconciled in separate work.
