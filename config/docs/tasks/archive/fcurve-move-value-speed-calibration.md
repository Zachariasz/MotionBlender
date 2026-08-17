# Task: FCurve Move Value-Speed Calibration

Status: completed; focused tests and live calibration passed  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2026 live FCurve session

## Goal

Make `G` move selected FCurve keys at the visible graph's true pixel-to-value
rate, including multi-key selections where axis-label OCR admits an incorrect
but internally consistent scale.

## Acceptance criteria

- [x] Multi-key FCurve Move rejects the observed 4x axis-label OCR ambiguity.
- [x] Horizontal time movement and existing graph-calibration behavior remain unchanged.
- [x] Focused offline regression passes.
- [x] Live MotionBuilder calibration agrees with the graph marker/fallback evidence.
- [x] Documentation records the calibration selection rule.

## Scope

Included:

- `transform.move_camera_plane` FCurve graph mapping.
- Shared `FCurveViewTransform` calibration used by G/R/S.
- Focused transform-runtime tests and the normative transform/FCurve standard.

## Non-goals

- FCurve key mutation/collision policy.
- Viewer or Timeline transform math.
- Unrelated manager features or MotionBuilder configuration.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/fcurves/view_transform.py` | Selects the graph's pixels-to-value calibration. |
| `Scripts/tests/test_transform_runtime.py` | Focused graph-calibration regressions. |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Normative cached visual-calibration contract. |

## Starting state

The live bridge was healthy and MotionBuilder was responsive. One displayed
curve had two selected keys at values 950 and 1000. A fresh capture reported:

- axis-label OCR: `18.8235294118` value units/pixel;
- key-marker fit: `4.7157048083` value units/pixel;
- value-range fallback: `4.9180327869` value units/pixel.

The independent marker and fallback estimates agree while the chosen OCR
hypothesis is approximately four times larger. The major grid rows are at
`60, 102, 145, 187, 230`; the bad hypothesis implies an 800-unit major-grid
increment, while the corroborated scale implies the native 200-unit increment.
No modifier was physically held and no interaction was active during the
probe.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-16 | Prefer near-standard 1/2/5 major-grid increments among equally well-supported OCR hypotheses. | MotionBuilder's graph grid already follows the 1/2/5 cadence; this rejects the observed 800-unit digit ambiguity without adding another screenshot or marker-fit pass. | Always use the value-range fallback, which is invalid after manual vertical zoom; always run marker fitting, which adds avoidable work to every expensive capture. |

## Progress

### Completed

- Captured read-only live state and isolated the incorrect value calibration.
- Added 1/2/5 major-grid cadence validation to OCR hypothesis selection.
- Added a focused regression using the observed rows, values, and 4x ambiguity.
- Reloaded the shared FCurve G/R/S mapping modules in the current session.
- Repeated the live capture: chosen scale changed from `18.8235294118` to
  `4.6511627907`, agreeing with the independent marker fit
  (`4.7157048083`) and fallback (`4.9180327869`).
- Preserved horizontal mapping at `1364983.9571078431` ticks/pixel.

### In progress

- None.

### Next action

1. User acceptance can repeat the original multi-key `G` gesture in the already-reloaded session.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/fcurves/view_transform.py` | Rejects well-supported OCR scales that violate the native major-grid cadence when a cadence-aligned hypothesis exists. | focused and live passed |
| `Scripts/tests/test_transform_runtime.py` | Added the live-derived 4x OCR ambiguity regression. | 22/22 passed |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Documented the OCR cadence discriminator. | reviewed |
| `Scripts/mobu_tools_manager/README.md` | Documented the user-visible multi-key speed guarantee. | reviewed |
| `docs/ARCHITECTURE.md` | Documented calibration ownership and hypothesis selection. | reviewed |
| `docs/TESTING.md` | Recorded focused regression coverage and the live comparison rule. | reviewed |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Added the one-major-grid single/multi-key live gate. | reviewed |
| `docs/tasks/archive/fcurve-move-value-speed-calibration.md` | Recorded evidence, decision, and verification. | reviewed |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Focused transform-runtime suite | Codex bundled Python | passed | 22/22 tests |
| Full offline suite | Codex bundled Python | failed, unrelated | 245 tests: two existing failures and three missing/environmental modules; changed focused module passed |
| Read-only bridge liveness and selection probe | MotionBuilder 2026 | passed | `20260816_230500_fcurve_move_speed_probe_20260816_230607.json` |
| Axis/marker/fallback comparison | MotionBuilder 2026 | failed before fix | `20260816_230900_fcurve_value_calibration_probe_20260816_230830.json` |
| Module reload and fresh live calibration | MotionBuilder 2026 | passed | `20260816_231500_reload_fcurve_calibration_and_verify_20260816_231315.json` |

## Blockers and open questions

- The full suite remains red for unrelated workspace issues: missing
  `features/camera_cycle.py`, missing `custom/MoveKeysRight.py`, unavailable
  PySide6 in the external test runtime, and two existing input/visibility test
  assertions.

## Handoff notes

The fix is loaded in the current MotionBuilder process. The source modules,
focused tests, live calibration result, and normative documentation agree.
