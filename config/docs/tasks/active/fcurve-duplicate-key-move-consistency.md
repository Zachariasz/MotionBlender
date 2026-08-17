# Task: FCurve Shift+D Duplicate Key Interactive Move & Focus Consistency

Status: completed; verified in unit tests and live MotionBuilder bridge session  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2024–2027 FCurve & Viewer transforms

## Goal

Ensure that duplicating FCurve keys via `Shift+D` invokes the exact same interactive movement session as pressing `'G'`, with 100% parity:
1. Displays the floating HUD box panel overlay with frame delta, value offset, and locked constraint axes.
2. Uses `FCurveViewTransform` for pixel-accurate mouse tracking across zoom levels.
3. Uses `FCurveMutationService` so moving keys cross adjacent keys cleanly without pushing them.
4. Restores native mouse, focus, and modifier states immediately upon commit/cancel without swallowing `Shift`/modifier key-up events or requiring an application switch.

## Acceptance criteria

- [x] Duplicating keys in FCurves via `Shift+D` starts an interactive move immediately.
- [x] Floating HUD box panel displays frame and value deltas during the move.
- [x] Keys cross existing keys cleanly without pushing them.
- [x] Pixel-to-frame mouse sensitivity matches pressing `'G'`.
- [x] Modifier and launcher `KeyRelease` events (`Shift`, `Control`, `Alt`, `Meta`, `D`, `G`, `R`, `S`, `X`, `Y`, `Z`) are never consumed by `InputRouter.handle_qt_event()`.
- [x] Interactive move sessions launched from compound shortcuts pass `activate_immediately=True` and `launcher_key=None` so they never stall in `ARMING`.
- [x] Committing or cancelling the move restores native mouse interaction, editor focus, and keyboard modifier state immediately.
- [x] Unit test suites pass (28/28 tests).
- [x] Documentation in `MOBU_TOOLS_MANAGER_GUIDE.md` and `MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` is updated.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/custom/Duplicate.py` | Routes duplicate move through `mobu_tools_manager.dispatch("transform.move_camera_plane")` with `activate_immediately=True`. |
| `Scripts/custom/MoveSelectedAlongCameraView.py` | Routes standalone move through manager when resident. |
| `Scripts/mobu_tools_manager/runtime.py` | `InputRouter.handle_qt_event()` passes through all modifier and launcher key-up events. |
| `Scripts/mobu_tools_manager/fcurves/mutation.py` | Manages direction-safe key moves and crossing logic. |
| `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md` | Documents Rule 14 for key-release pass-through and compound shortcut launches. |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Documents router shape, modifier release, and failure signature. |

## Root cause analysis & decisions

| Issue | Root Cause | Resolution |
| --- | --- | --- |
| Discrepant HUD / Mouse / Key Push | `Duplicate.py` previously executed standalone legacy script `MoveSelectedAlongCameraView.py` via `exec()`. | Routed `_run_move_script()` through `mobu_tools_manager.dispatch("transform.move_camera_plane")` using `mgr._transform_invocation("move")`. |
| Stuck `Shift` / Mouse behavior | `InputRouter.handle_qt_event()` returned `True` (consumed) on `KeyRelease` events, preventing MotionBuilder from receiving `Shift` and `D` key-ups. | Updated `handle_qt_event()` so `KeyRelease` events for modifiers (`Shift`, `Control`, `Alt`, `Meta`), launchers (`D`, `G`, `R`, `S`), and axes (`X`, `Y`, `Z`) return `False`. |
| `ARMING` latency | Passing `"launcher_key": "G"` on a `Shift+D` launch caused the session to wait for a `G` release. | Programmatic duplicate launches pass `activate_immediately=True` and `launcher_key=None`. |

## Verification results

- **Unit tests**: `test_fcurve_mutation.py`, `test_transform_scale.py`, `test_interactions.py` — **28/28 tests passed**.
- **Live MotionBuilder bridge**: Verified that duplicating an FCurve key starts an `InteractionSession` with `FCurveMoveStrategy` in `ACTIVE` state, updates the HUD box overlay, and commits cleanly to `CLOSED` state with immediate modifier/focus restoration.
