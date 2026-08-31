# Task: Timeline Alternate Range Toggle

Status: active  
Last updated: 2026-08-31  
Owner/context: Codex

## Goal

Provide a manager-integrated Timeline Quick Favorite that swaps the active
take's main and alternate start/end ranges, remembers edits to both ranges
independently per take, and persists them in a source FBX custom property.

## Acceptance criteria

- [x] Stable command is registered and exposed in Timeline Quick Favorites.
- [x] First-click, swap, edit-capture, invalid-state, Quick Favorites checked
  state, undo, evaluation, and migration behavior have focused offline coverage.
- [ ] Live MotionBuilder UI, undo, per-take persistence, and FBX reopen checks
  are completed.
- [x] Package/status/checklist documentation is updated.

## Scope

Included:

- `animation.timeline_toggle_alt_range`
- `features/timeline_alt_range.py`
- Quick Favorites settings, catalog, focused tests, package/status docs, and
  integration checklist.

## Non-goals

- Changing animation data, transport shortcuts, native Timeline controls, or
  unrelated Viewer/Story toolbar behavior.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/features/timeline_alt_range.py` | Persistent range state and swapping command. |
| `Scripts/mobu_tools_manager/quick_favorites/settings.py` | Timeline-only Quick Favorite default and settings migration. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable feature IDs and lifecycle declarations. |
| `Scripts/tests/test_timeline_alt_range.py` | Offline persistence and swapping regressions. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Required host-side verification. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-31 | Store one JSON string custom property on each `FBTake`. | FBTime ticks exceed safe 32-bit frame-property storage; one property keeps ranges and active side together and serializes with the take. | Per-user settings, scene Null, and 32-bit frame fields would not meet per-take FBX persistence. |
| 2026-08-31 | First click enters alternate mode without changing the range. | It gives the user a direct native Timeline range to edit, while preserving the original main range. | Opening a separate range editor or inventing defaults for the alternate side. |
| 2026-08-31 | Expose the command through Timeline Quick Favorites. | The native Timeline control was not reliably visible; the contextual menu is stable and already owned by the manager. | A resident native Timeline button. |
| 2026-08-31 | Use Quick Favorites' optional checked-state callback. | The checkmark reflects the current take's persisted active range whenever the menu opens. | A UI-only remembered toggle that can drift from the FBX-backed state. |

## Progress

### Completed

- Added custom-property persistence, undo-scoped range swapping, and coalesced
  evaluation.
- Added catalog records, offline tests, documentation, and live checklist.
- Replaced the invisible native Timeline button with a Timeline-specific Quick
  Favorite and one-time settings migration for existing users.
- Added state-driven checked/unchecked feedback for the Timeline Quick Favorite.

### Next action

1. Execute the isolated MotionBuilder checklist, including Quick Favorites
   context verification and save/reopen of an FBX with at least two takes.

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `test_timeline_alt_range.py` | MotionBuilder 2026 Python 3.11 | passed | 6 tests passed, including Quick Favorites checked-state transitions. |
| `test_settings.py` (Quick Favorites cases) | MotionBuilder 2026 Python 3.11 | passed | Existing-user migration and manager-save tests passed; direct checks also covered new defaults and preserved v3 empty lists. The full file remains blocked by the host's unavailable temporary directory. |
| `test_timeline_navigation.py` | MotionBuilder 2026 Python 3.11 | passed | 15 tests passed. |
| `test_timeline_marker_labels.py` | MotionBuilder 2026 Python 3.11 | passed | 8 tests passed. |
| `test_catalog.py` | MotionBuilder 2026 Python 3.11 | failed (pre-existing) | New catalog assertions passed; unrelated missing `custom/MoveKeysRight.py` and obsolete `Script2` mapping assertions failed. |
| `validate_catalog()` | MotionBuilder 2026 Python 3.11 | passed | 69 features; no structural catalog errors. |
| Live Timeline/FBX workflow | MotionBuilder 2024-2027 | not run | Requires isolated host scene. |

## Blockers and open questions

- No active MotionBuilder host verification has been performed in this context.
