# Task: Full-body picker responsiveness

Status: active  
Last updated: 2026-08-26

## Goal

Make the Custom Full Body Bone Picker respond promptly when an IK or auxiliary
effector is right-clicked, while preserving selection, slider, and Viewer
manipulator behavior.

## Acceptance criteria

- [x] The RMB effector path does not refresh unrelated bake or toolbar UI before
  the popup can paint.
- [x] Periodic picker refreshes reuse one Character Controls keying-mode scan.
- [x] Normal selection avoids redundant hard-selection work and retains a safe
  fallback.
- [x] Focused offline verification passes.
- [ ] Responsiveness and selection behavior are verified in MotionBuilder.
- [x] Documentation and the live checklist are updated.

## Scope

Included:

- Managed legacy feature `pickers.full_body`.
- Effector RMB slider popup and picker periodic UI refresh.
- Full-body picker focused tests and live verification guidance.

## Non-goals

- Migrating the legacy picker to a manager-native feature.
- Changing slider values, keying behavior, bake behavior, or popup layout.
- Refactoring the hand or spine pickers.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | RMB handling, selection, slider popup, and periodic refresh. |
| `Scripts/tests/test_full_body_picker.py` | Focused offline regression coverage. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Required live responsiveness and selection checks. |

## Starting state

- The user observed about a one-second delay after right-clicking an effector.
- The RMB handler refreshed the popup, bake row, and toolbar synchronously
  before returning to Qt.
- Each 150 ms periodic refresh independently scanned the complete Qt widget tree
  three times for the same Character Controls keying mode.
- Selection always called both `FBSetLastSelectedModel()` and `HardSelect()` even
  though the Autodesk API defines the first call as selecting the model and
  making it the last Viewer manipulator target.
- No MotionBuilder process was running, and the bridge status and heartbeat were
  stale from 2026-08-24, so no live probe was sent.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-26 | Remove bake and toolbar refreshes from the RMB effector branch. | They do not affect the slider popup and delayed Qt painting. The existing timer refreshes them. | Deferring the whole slider refresh could expose stale interactive controls. |
| 2026-08-26 | Compute keying mode once per periodic refresh and pass it to both UI sections. | `read_keying_mode_from_ui()` walks every Qt widget and its ancestors; repeated scans returned the same snapshot. | Retaining SDK or Qt wrappers across invalidation boundaries. |
| 2026-08-26 | Return after successful `FBSetLastSelectedModel()` and use `HardSelect()` only on failure. | Autodesk documents that the API selects the model and moves the Viewer manipulator to it. | Removing the compatibility fallback entirely. |

## Progress

### Completed

- Optimized the RMB critical path and periodic UI refresh.
- Added focused regression coverage.
- Ran the focused suite successfully with the bundled workspace Python.

### In progress

- Live MotionBuilder responsiveness and selection verification.

### Next action

1. Reload `pickers.full_body` in MotionBuilder and run the new RMB checks in the
   integration checklist with Character Controls hidden.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | Removed unrelated synchronous RMB refreshes, shared periodic keying-mode state, and made hard selection fallback-only. | Focused suite passed; live check not run. |
| `Scripts/tests/test_full_body_picker.py` | Added selection-fallback, refresh-snapshot, and RMB critical-path tests. | 10 tests passed. |
| `Scripts/mobu_tools_manager/README.md` | Documented responsiveness behavior. | Reviewed. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Added live responsiveness and selection checks. | Not run. |
| `docs/TESTING.md` | Updated focused and live coverage descriptions. | Reviewed. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Bundled Python `-m unittest discover -s tests -p test_full_body_picker.py -v` | Codex bundled Python | passed | 10 tests passed in 0.311 seconds. |
| Bundled Python `-m unittest discover -s tests -v` | Codex bundled Python | failed, unrelated | 286 tests ran: 4 failures and 31 errors. All 10 picker tests passed; remaining failures include existing catalog/input/FCurve regressions, while many errors are caused by the sandbox having no writable temporary directory. |
| Syntax compile of `CustomFullBodyBonePicker.py` | Codex bundled Python | passed | `syntax ok`. |
| Live RMB picker check | MotionBuilder 2026 | not run | MotionBuilder was not running and the bridge heartbeat was stale; use the integration checklist. |

## Blockers and open questions

- The real host-side latency improvement still needs timing or direct visual
  confirmation in MotionBuilder.

## Handoff notes

- Do not send a bridge payload until `status.json` and `heartbeat.txt` are fresh
  and MotionBuilder is visibly responsive.
