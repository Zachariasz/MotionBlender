# Task: FCurve Move Axis-Lock Restart

Status: completed; offline verification blocked, live verification pending  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2024-2027 FCurve Move

## Goal

Make FCurve Move (`G`) axis locking match Viewer Move: retain movement only on
the locked graph axis and restore the other component to its operation-start
position.

## Acceptance criteria

- [x] `X` retains selected keys' current time movement and restores values.
- [x] `Y` retains selected keys' current value movement and restores times.
- [x] Repeating the active axis unlocks and restores both time and value.
- [x] Unit coverage asserts all three reset targets.
- [x] The interaction contract and live checklist document the behavior.
- [ ] Targeted offline test executed with a compatible Python interpreter.
- [ ] Live MotionBuilder verification in an isolated scene.

## Scope

Included:

- FCurve Move strategy: `Scripts/mobu_tools_manager/fcurves/move.py`.
- Its unit coverage and FCurve interaction documentation.

## Non-goals

- Changing Timeline Move, which is permanently time-constrained.
- Changing FCurve tangent or Scale constraint rebasing.
- Changing Viewer transform behavior.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/fcurves/move.py` | Applies FCurve key time/value previews. |
| `Scripts/mobu_tools_manager/interactions/session.py` | Calls a strategy axis-restart hook after a valid axis change. |
| `Scripts/tests/test_transform_runtime.py` | Covers target states for FCurve Move axis restart. |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Normative FCurve interaction contract. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-16 | FCurve Move implements `restart_for_axis()`. | The shared session already recognizes this hook and uses it for Viewer-style restart semantics. | Keeping the former continuous rebase would preserve the unwanted unlocked-axis preview. |
| 2026-08-16 | Tangent and Scale constraints remain continuous rebases. | The request applies specifically to selected-key movement with `G`. | Broadly changing all FCurve constraint behavior would exceed scope. |

## Completed

- Added `FCurveMoveStrategy.restart_for_axis()`.
- Added target-state regression coverage for X, Y, and unlocked states.
- Updated package rules, package README, the migration standard, and the live
  integration checklist.

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -m unittest discover -s tests -p "test_transform_runtime.py" -v` | Workspace shell | blocked | `python` is not installed or available on `PATH`. |
| Axis-lock interaction check | MotionBuilder isolated scene | not run | Use the FCurve G checklist entry. |

## Handoff notes

The change is safe to exercise only in an isolated scene. Verify a visible
two-axis key preview, then press X, Y, and the same active axis again; confirm
the retained and restored components match the documented rule before commit
and after cancel.
