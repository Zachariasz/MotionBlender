# Task: Playback frame-mode menu

Status: active; implementation complete, live verification pending  
Last updated: 2026-08-14  
Owner/context: MotionBuilder transport / manager shared input

## Goal

The backtick key opens a menu that changes MotionBuilder's native playback
frame-replay behavior.

## Acceptance criteria

- [x] Backtick opens a four-option menu: No Snap, Snap on Frames, Play on
  Frames, and Snap & Play on Frames.
- [x] Selecting an option assigns the matching `FBPlayerControl.SnapMode`.
- [x] The menu and input route have deterministic cleanup.
- [x] Focused offline verification passes.
- [ ] Live MotionBuilder verification passes.
- [x] Documentation is updated.

## Scope

Included:

- `animation.playback_frame_mode_menu`
- shared `InputRouter` backtick route
- manager-native menu and focused tests

## Non-goals

- Editing or rescanning MotionBuilder keyboard-profile files.
- Changing playback speed, loop mode, or timeline navigation.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/features/playback_frame_mode.py` | Menu, transport assignment, and service lifecycle. |
| `Scripts/mobu_tools_manager/runtime.py` | Single shared input route. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable feature metadata. |
| `Scripts/tests/test_playback_frame_mode.py` | Focused offline behavior coverage. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-14 | Use a resident shared-input backtick route. | It works without rewriting or rescanning the active keyboard profile. | An ActionScript slot would require an uncertain profile-specific physical-key token and a profile rescan. |
| 2026-08-14 | Write `FBPlayerControl.SnapMode` directly. | This is the documented host setting for all four requested behaviors. | Tracking an independent manager setting would not change the transport. |

## Progress

### Completed

- Added the transient checked menu and direct native transport assignment.
- Added idempotent input registration, cleanup, catalog metadata, docs, and
  focused offline tests.
- Documented the shared-input ownership and no-profile-rescan behavior in the
  architecture reference.

### Next action

1. Restart MotionBuilder, press backtick in a temporary scene, and verify all
   four choices change the real Transport Controls behavior.

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -B -m unittest discover -s tests -p test_playback_frame_mode.py -v` | Bundled CPython | passed | 4 tests, OK. |
| `python -B -m unittest discover -s tests -p test_runtime_services.py -v` | Bundled CPython | passed | 11 tests, OK. |
| `python -B -m unittest discover -s tests -p test_catalog.py -v` | Bundled CPython | blocked | Pre-existing missing legacy `custom/MoveKeys*.py` files make the unrelated catalog physical-file check fail. |
| Backtick menu and transport behavior | MotionBuilder 2026 | not run | Requires an isolated scene. |

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/features/playback_frame_mode.py` | Native transport-mode menu and resident service. | Focused test passed. |
| `Scripts/mobu_tools_manager/runtime.py` | Shared unmodified-backtick route and cleanup. | Runtime regression test passed. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable feature ID and resident metadata. | Catalog feature metadata reviewed; full catalog check blocked by legacy files. |
| `Scripts/tests/test_playback_frame_mode.py` | Frame mode and input-route coverage. | 4 tests passed. |
| `Scripts/mobu_tools_manager/README.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/PROJECT_STATUS.md`, `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Public use, ownership, counts, offline coverage, and live gate. | Reviewed. |

## Handoff notes

- The menu uses MotionBuilder's documented `FBTransportSnapMode` enum values
  through `FBPlayerControl.SnapMode`.
- A text editor, modal dialog, or popup blocks the shared launcher.
