# Task: Timeline Toggle Local Marker Command (`Ctrl+M`)

Status: active  
Last updated: 2026-08-16  
Owner/context: Antigravity / Pair Programming

## Goal

Provide a manager-integrated timeline command and `Ctrl+M` hotkey that toggles local time marks (markers) on the current take at the active playhead frame:
- If no local marker exists at the current frame, creates a new local time mark.
- If a local marker already exists at the current frame, deletes that marker.
- Operates inside an undo transaction (`Add Local Marker` / `Remove Local Marker`) and requests scene evaluation.

## Acceptance criteria

- [x] Command `animation.timeline_add_local_marker` (alias `toggle_local_marker`) implemented under `mobu_tools_manager.features.timeline_navigation`.
- [x] ActionScript slot 53 wrapper created at `mobu_tools_manager/generated_actions/Script53.py`.
- [x] Mapped in `ActionScript.txt` (`Script53`) and `Keyboard/Blender.txt` (`action.global.script53 = {CTRL:M*DN}`).
- [x] Shared Qt input router in `runtime.py` decodes ASCII key codes with `ControlModifier` so `Ctrl+M` (which produces `\r` in `event.text()`) reliably dispatches the feature.
- [x] All offline unit tests in `tests/test_timeline_navigation.py` pass cleanly.
- [x] Documentation updated in `mobu_tools_manager/README.md` and `docs/PROJECT_STATUS.md`.

## Scope

Included:

- `mobu_tools_manager/features/timeline_navigation.py`
- `mobu_tools_manager/runtime.py` (`InputRouter._key_name`, `_try_timeline_navigation_launcher`)
- `mobu_tools_manager/catalog.py` (`animation.timeline_add_local_marker`)
- `mobu_tools_manager/generated_actions/Script53.py`
- `ActionScript.txt`
- `Keyboard/Blender.txt`
- `tests/test_timeline_navigation.py`
- `mobu_tools_manager/README.md`
- `docs/PROJECT_STATUS.md`

## Non-goals

- Refactoring unrelated timeline navigation or character keying hotkeys.
- Modifying global markers or story tracks (feature strictly targets `context.take` local time marks).

## Important files

| File | Why it matters |
| --- | --- |
| `mobu_tools_manager/features/timeline_navigation.py` | Implementation of `add_local_marker` / `toggle_local_marker` and `HOTKEY_FEATURES` mapping. |
| `mobu_tools_manager/runtime.py` | Shared `InputRouter._key_name` ASCII decoding and navigation launcher whitelist. |
| `mobu_tools_manager/catalog.py` | Declarative feature spec for `animation.timeline_add_local_marker`. |
| `mobu_tools_manager/generated_actions/Script53.py` | ActionScript fallback wrapper. |
| `tests/test_timeline_navigation.py` | Offline regression test suite for timeline navigation and marker manipulation. |

## Starting state

- Previously, timeline navigation hotkeys only supported frame steps (10 frames, 1 second), take start/end, and jumping between existing markers.
- `Ctrl+M` was unassigned in `Keyboard/Blender.txt`.
- ActionScript slot 53 was empty.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-14 | Use `context.take.AddTimeMark(target_time)` and `take.DeleteTimeMark(index)` | Standard MotionBuilder OpenReality SDK methods for local time marks on `FBTake`. | Global marker manipulation (user requested local markers). |
| 2026-08-15 | Decode printable ASCII range in `InputRouter._key_name` | `QKeyEvent.text()` returns `\r` (ASCII 13) for `Ctrl+M` on Windows; decoding `event.key()` ensures robust hotkey matching across all modifier states. | Relying on `event.text()` or maintaining ad-hoc character maps. |
| 2026-08-15 | Implement toggle behavior in `add_local_marker` | Matches intuitive user workflow where pressing `Ctrl+M` on an existing marker removes it. | Creating separate add vs remove commands requiring separate shortcuts. |

## Progress

### Completed

- Implemented `add_local_marker` / `toggle_local_marker` with frame-based marker detection, addition, and deletion.
- Fixed `InputRouter._key_name` to decode `0x20 <= key_value <= 0x7E` ASCII characters when modifiers are held.
- Registered feature spec in `catalog.py` (Slot 53, `{CTRL:M*DN}`).
- Generated `Script53.py` ActionScript wrapper.
- Updated `ActionScript.txt` and `Keyboard/Blender.txt`.
- Added unit tests in `tests/test_timeline_navigation.py` for adding, deleting, undo scoping, evaluation requests, and `Ctrl+M` event decoding.
- Updated documentation in `mobu_tools_manager/README.md` and `docs/PROJECT_STATUS.md`.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `mobu_tools_manager/features/timeline_navigation.py` | Added marker toggle logic and `Ctrl+M` mapping | Passed (`test_timeline_navigation.py`) |
| `mobu_tools_manager/runtime.py` | Key decoding and `"M"` whitelist in navigation launcher | Passed (`test_timeline_navigation.py`, `test_runtime_services.py`) |
| `mobu_tools_manager/catalog.py` | FeatureSpec for `animation.timeline_add_local_marker` | Passed |
| `mobu_tools_manager/generated_actions/Script53.py` | ActionScript wrapper | Passed |
| `ActionScript.txt` | Mapped `Script53` | Passed |
| `Keyboard/Blender.txt` | Bound `action.global.script53 = {CTRL:M*DN}` | Passed |
| `tests/test_timeline_navigation.py` | Added 3 new unit tests covering toggle & key decoding | Passed (11/11 tests) |
| `mobu_tools_manager/README.md` | Updated feature count and timeline shortcuts table | Passed |
| `docs/PROJECT_STATUS.md` | Updated feature counts and native feature list | Passed |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `py -3 -m unittest discover -s tests -p "test_timeline_navigation.py" -v` | Python 3.12 | passed | 11/11 tests passed in 0.003s |
| `py -3 -m unittest discover -s tests -p "test_runtime_services.py" -v` | Python 3.12 | passed | 11/11 tests passed in 0.001s |
| `py -3 -m unittest discover -s tests -p "test_shortcuts.py" -v` | Python 3.12 | passed | 5/5 tests passed in 0.025s |
| Live bridge marker dispatch | MotionBuilder 2026 via Antigravity bridge | passed | Verified marker creation and take count updates |

## Handoff notes

- The entrypoint name remains `add_local_marker` with alias `toggle_local_marker` so catalog slot bindings and existing dispatches remain backwards compatible.
