# Task: Viewer reference-mode hotkey

Status: active; implementation and offline documentation complete, live verification pending  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2026 Viewer / Codex Bridge

## Goal

Pressing X over the Viewer toggles MotionBuilder's Global and Local reference
modes without rewriting or rescanning the active MotionBuilder keyboard profile.

## Acceptance criteria

- [x] Manager owns one Viewer-only X input route.
- [x] The route sends native F5/F6 key pairs without rewriting the keyboard map.
- [x] Focused offline verification passes.
- [ ] Live MotionBuilder verification passes after a clean restart.
- [x] Catalog and user documentation are updated.

## Scope

Included:

- viewer.toggle_global_local_reference
- shared InputRouter
- reference-mode feature, catalog, and focused tests

## Non-goals

- Changing the user's MotionBuilder keyboard profile.
- Rewriting or rescanning MotionBuilder shortcut files while the application is running.

## Important files

| File | Why it matters |
| --- | --- |
| Scripts/mobu_tools_manager/features/reference_mode.py | Resident Viewer hotkey and native F5/F6 dispatch. |
| Scripts/mobu_tools_manager/runtime.py | Shared input-router registration and dispatch. |
| Scripts/mobu_tools_manager/catalog.py | Resident-service lifecycle metadata. |
| Scripts/tests/test_reference_mode.py | Focused behavior and cleanup coverage. |

## Starting state

The first command implementation used NativeActionDispatcher, which temporarily
rewrote the active keyboard map and requested a shortcut rescan. The rescan
crashed MotionBuilder. The active profile's Script32 binding was blank, so the
replacement deliberately avoids ActionScript slots and keyboard-profile writes.

## Decisions

| Date | Decision | Evidence/rationale | Alternative and why |
| --- | --- | --- | --- |
| 2026-08-14 | Use a resident shared-input-router service rather than an ActionScript slot. | The live profile was blank and profile writes/rescans are unsafe from the bridge. | Editing Script32 required protected-profile access and crashed during rescan. |
| 2026-08-14 | Send native F5/F6 key pairs directly. | The active profile confirmed Local=F5 and Global=F6; no rescan is needed. | NativeActionDispatcher dynamically rewrites and rescans the keyboard profile. |

## Progress

### Completed

- Reworked the feature into a resident service, active only over the Viewer.
- Added one reference-mode launcher to the shared input router with idempotent
  registration/removal.
- Removed Script32 and Blender-profile mappings to prevent duplicate dispatch.
- Retained Viewer action inspection/cache and a Global-first fallback when native
  UI actions are unavailable to Qt.

### In progress

- Record the post-restart live Viewer check for the resident input route.

### Next action

1. In an isolated scene, hover the Viewer and press `X` from Global and Local
   mode in turn. Confirm one toggle per press, the no-focus/no-popup safeguards,
   and reload cleanup. Do not write or rescan the keyboard profile.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| Scripts/mobu_tools_manager/runtime.py | Shared Viewer reference-mode launcher. | Focused feature test passed. |
| Scripts/mobu_tools_manager/features/reference_mode.py | Resident service and direct F5/F6 dispatch. | Focused feature test passed. |
| Scripts/mobu_tools_manager/catalog.py | Resident service metadata. | Static metadata check passed. |
| Scripts/tests/test_reference_mode.py | Viewer-only route and cleanup coverage. | 6 tests passed. |
| Scripts/mobu_tools_manager/README.md | Documents direct, no-rescan behavior. | Reviewed. |
| docs/TESTING.md | Updates focused test coverage. | Reviewed. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| python -B -m unittest discover -s tests -p test_reference_mode.py -v | Bundled CPython | passed | 6 tests, OK. |
| Catalog/source AST metadata check | Bundled CPython | passed | Resident service with start/stop, no ActionScript slot. |
| Initial bridge probe | MotionBuilder 2026 | passed | Feature known/enabled; active Script32 binding blank; F5/F6 native actions confirmed. |
| Shortcut rescan through bridge | MotionBuilder 2026 | failed | MotionBuilder crashed while the bridge command was busy. |
| No-rescan keyboard-profile write through bridge | MotionBuilder 2026 | not applicable | The resident implementation intentionally avoids profile writes. |
| Live Viewer toggle | MotionBuilder 2026 | not run | Requires a fresh post-fix restart. |

## Blockers and open questions

- No live Viewer-toggle result has been recorded after the restart. The bridge
  may be used for bounded diagnostics, but it cannot substitute for testing the
  physical Viewer-hover input route.

## Handoff notes

- The bridge root is Scripts/.codex_mobu_bridge/ in current code, despite the
  older user-config-path wording in docs/CODEX_BRIDGE.md.
- The new implementation intentionally avoids the active keyboard profile, so
  Script32 remaining blank is expected.
