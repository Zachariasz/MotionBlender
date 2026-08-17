# Task: Active keyboard-profile synchronization

Status: complete  
Completed: 2026-08-17  
Owner/context: MotionBuilder Tools Manager / shortcut editing

## Goal

Use the keyboard interaction mode MotionBuilder has finished applying, rather
than the default mode visible during PythonStartup, for all manager shortcut
display, conflict, editing, enable/disable, and native-action paths.

## Acceptance criteria

- [x] The manager re-reads `FBActionManager.CurrentInteractionMode` before a
  shortcut-dependent action.
- [x] A changed profile reselects its keyboard file and imports only missing
  manager binding records for that profile.
- [x] The native-action dispatcher follows the changed profile when idle.
- [x] Focused offline coverage passes.
- [x] Live verification confirms Blender is displayed and edited after startup
  completes.
- [x] User and test-routing documentation are updated.

## Scope

Included:

- `mobu_tools_manager.manager`
- `tests/test_manager_shutdown.py`
- `tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`
- manager shortcut documentation and test routing

## Non-goals

- Changing the keyboard interaction mode selected by the user.
- Changing generic keyboard-profile rescan behavior outside this profile-sync
  bug.

## Starting state

The PythonStartup manager captured `CurrentInteractionMode` while MotionBuilder
still reported `MotionBuilder`, then retained that path for the whole session.
The user-selected Blender interaction mode became active later.

## Decisions

| Date | Decision | Evidence/rationale | Alternative and why |
| --- | --- | --- | --- |
| 2026-08-17 | Re-read the host interaction mode on shortcut-dependent paths. | Autodesk's keyboard editor uses the same `CurrentInteractionMode` property as the authoritative active keyboard mode. | Hard-code Blender: rejected because it would edit a non-active profile for users of other modes. |
| 2026-08-17 | Preserve existing saved bindings when a new profile is observed. | Only first-observation records should be imported from its keyboard file. | Reimport every time: rejected because it could overwrite manager-saved preferences. |

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/manager.py` | Active-profile synchronization and per-profile binding seeding. | Focused and live checks passed. |
| `Scripts/tests/test_manager_shutdown.py` | Startup-to-Blender profile refresh regression. | Passed. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Adds the active-profile live gate. | Reviewed. |
| `Scripts/mobu_tools_manager/README.md` | Documents profile refresh behavior. | Reviewed. |
| `docs/TESTING.md` | Records the added focused coverage. | Reviewed. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -B -m unittest discover -s tests -p "test_manager_shutdown.py" -v` | Bundled CPython | passed | 7 tests, including the new profile-refresh regression. |
| `python -B -m unittest discover -s tests -v` | Bundled CPython | failed | 257 tests ran; 3 failures and 3 errors from unrelated missing Camera Cycle/MoveKeysRight sources, unavailable PySide6, and catalog expectations for the removed Script2/Key IK mapping. |
| Active Blender profile after startup; shortcut update | User's MotionBuilder session | passed | The manager updated to Blender and the user reported successful shortcut updating with no crash. |

## Handoff notes

- The original freeze was reproduced while the manager retained the early
  `MotionBuilder` profile rather than the selected Blender profile.
- The full-suite failures were not changed or retried as part of this task.
