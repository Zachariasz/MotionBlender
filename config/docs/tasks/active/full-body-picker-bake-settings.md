# Task: Full-body picker bake settings

Status: completed  
Last updated: 2026-08-14

## Goal

Make the Custom Full Body Bone Picker bake at the active MotionBuilder transport
frame rate and expose persistent, per-destination plot settings through the
picker and blue Character Controls menus.

## Acceptance criteria

- [x] Skeleton and Control Rig/Body Part bakes sample once per active transport frame.
- [x] The picker is launched through managed feature `pickers.full_body`.
- [x] The picker `...` menu and blue menu open plot settings for Skeleton and Control Rig.
- [x] The open picker's `...` settings entries are verified active through the Codex Bridge.
- [x] Focused offline verification and documentation updates are complete.
- [ ] Bake results at 30 and 60 FPS are inspected on an isolated MotionBuilder scene.

## Scope

Included:

- `pickers.full_body` legacy-backed implementation and its Window-menu bridge.
- Current-transport plot sampling and per-destination persistent plot settings.
- Live bridge inspection/reload of the picker UI.

Excluded:

- Migrating the legacy picker to a manager-native Qt feature.
- Repairing unrelated full-suite failures.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | Picker UI, bake operations, FPS sampling, settings dialog. |
| `Scripts/CustomFullBodyBonePickerWindowMenu.py` | Window-menu/startup dispatch into `pickers.full_body`. |
| `Scripts/tests/test_full_body_picker.py` | Focused offline coverage. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Required host verification. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- |
| 2026-08-14 | Use `FBPlayerControl().GetTransportFps()` as `FBTime`'s time mode for `FBPlotOptions.PlotPeriod`. | Supports the active transport mode, including 30, 60, and custom frame rates. | Mapping only 30 and 60 would fail for other configured rates. |
| 2026-08-14 | Make `...` entries open settings, not immediate duplicate bake commands. | Matches the original blue-menu intent and allows separate persistent settings per destination. | Duplicate commands did not provide configurable plot options. |
| 2026-08-14 | Keep `...` settings entries enabled when a current character exists. | Settings are useful before a Control Rig is ready; the actual bake still validates its destination. | Mirroring direct-button eligibility made the configuration menu inaccessible. |

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/CustomFullBodyBonePicker.py` | Active-FPS plot period, plot settings dialog, safe live menu state, and `...` settings launcher. | Focused tests passed; bridge checked live UI. |
| `Scripts/CustomFullBodyBonePickerWindowMenu.py` | Dispatches `pickers.full_body` instead of executing source directly. | Focused tests passed. |
| `Scripts/tests/test_full_body_picker.py` | Covers FPS mode, manager dispatch, and settings-menu contract. | 4 tests passed. |
| `Scripts/mobu_tools_manager/README.md` | Documents public picker bake behavior. | Updated. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Adds picker bake/settings host checks. | Updated. |
| `docs/TESTING.md` | Adds focused coverage and live verification description. | Updated. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -S -B -m unittest discover -s tests -p test_full_body_picker.py -v` | MotionBuilder 2026 bundled Python | passed | 4 tests passed. |
| Syntax compile of `CustomFullBodyBonePicker.py` | MotionBuilder 2026 bundled Python | passed | `syntax ok`. |
| Live bridge probe | MotionBuilder 2026 | passed | Reloaded/reopened `pickers.full_body`; button and both `...` actions reported enabled. |
| Full offline suite | MotionBuilder 2026 bundled Python | failed, unrelated | 175/178 passed; missing camera-cycle module, missing `MoveKeysRight.py`, stale 59-vs-58 catalog assertion. |
| 30/60 FPS result inspection | Isolated MotionBuilder scene | not run | Must inspect resulting key spacing. |

## Next action

1. In an isolated scene, run Skeleton and Control Rig bakes at 30 then 60 transport FPS and inspect the resulting key spacing.
