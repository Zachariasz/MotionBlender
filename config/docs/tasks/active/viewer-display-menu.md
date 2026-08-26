# Task: Viewer display menu

Status: active; feature disabled after live crash investigation  
Last updated: 2026-08-24  
Owner/context: MotionBuilder Viewer / manager shared input

## Goal

Pressing `Z` over a 3D Viewer opens a display menu with the requested native
Viewer actions, without affecting other MotionBuilder contexts.

## Acceptance criteria

- [x] `Z` opens the requested four-option menu only over a 3D Viewer.
- [x] Each menu choice dispatches its requested native Viewer action after the
  popup has closed.
- [x] The shared input route and transient menu have deterministic cleanup.
- [x] Focused offline verification passes.
- [ ] Live MotionBuilder verification passes.
- [x] Documentation is updated.

## Scope

Included:

- `viewer.display_mode_menu`
- shared `InputRouter` Viewer-only `Z` route
- native-action timing, remembered-row positioning, tests, and live
  checklist

## Non-goals

- Editing a keyboard-profile default.
- Changing Viewer reference mode, shading, or picking behavior outside the
  four requested host actions.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/features/viewer_display_menu.py` | Menu, dispatch, and resident-service lifecycle. |
| `Scripts/mobu_tools_manager/runtime.py` | One shared `Z` input route. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable feature metadata. |
| `Scripts/tests/test_viewer_display_menu.py` | Focused offline behavior coverage. |

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-24 | Restrict `Z` to the 3D Viewer context. | Viewer display actions must not consume input in Timeline, FCurves, or general UI. | A global `Z` menu. |
| 2026-08-24 | Apply Viewer state after the Qt menu closes. | Keeps the transient popup from owning focus while the Viewer changes. | Changing Viewer state during the active popup. |
| 2026-08-24 | Reuse Quick Favorites' remembered-row positioning rules. | The last selected display command is the fastest next choice without obscuring its label. | Always opening at the cursor's top-left. |
| 2026-08-24 | Restore the Viewer focus before closing and dispatching a menu action. | Native Viewer shortcuts need the Viewer as their destination after the popup releases focus. | Dispatching after close without an explicit focus handoff. |
| 2026-08-24 | Do not call `FBRenderer.SetViewingOptions()` from this feature. | The 2026 host crashed with an `fbsdk.dll` access violation from the deferred Python callback; the crash dump showed an invalid MotionBuilder wrapper address. | Direct `FBViewingOptions` mutation. |
| 2026-08-24 | Queue dispatch from the selected action callback, never `aboutToHide`. | Qt can hide a `QMenu` before its action's external `triggered` callback; hide-time pending state therefore dropped valid selections. | Storing the selection for `aboutToHide` to dispatch. |
| 2026-08-24 | Use the manager-owned native action dispatcher for all four rows. | These are the exact action IDs requested, and the dispatcher owns temporary binding, rescan, key delivery, restoration, and cleanup. | Global Qt label matching; all discovered Wire/Shaders actions belonged to unrelated Character Controls/popup owners. |

## Progress

### Completed

- Added the native resident feature, catalog entry, shared input route, focused
  tests, documentation, and live verification gate.
- Matched Quick Favorites positioning: the last selected row is vertically
  centered under the cursor, horizontally placed at five-sixths of menu width,
  constrained to the active screen, then realigned after popup layout.
- Restored the same source-Viewer focus handoff as Quick Favorites before a
  selected native action is queued.
- Removed all direct renderer viewing-option calls after dump analysis tied the
  crash to an `fbsdk.dll` access violation in a deferred Python timer callback.
- Verified live that the only exposed Wire/Shaders Qt actions belong to
  unrelated Character Controls, picker, and popup owners.
- Restored the exact native action IDs through the manager-owned dispatcher;
  its temporary keyboard binding restored, but synthetic delivery did not
  produce trustworthy visual proof.
- Fixed the popup signal-order bug that allowed `aboutToHide` to run before the
  selected action callback and silently discard every choice. The action
  callback now closes the popup and queues its own native action, matching
  Quick Favorites' execution boundary.

### Next action

1. Keep the feature disabled. Reproduce the requested action manually in an
   isolated host and identify a host-supported execution interface before any
   further implementation or live test.

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -B -m unittest discover -s tests -p "test_viewer_display_menu.py" -v` | Bundled CPython | passed | 8 tests, OK, including all declared action IDs and hide-before-trigger signal ordering. |
| `python -B -m unittest discover -s tests -p "test_playback_frame_mode.py" -v` | Bundled CPython | passed | 4 tests, OK. |
| `python -B -m unittest discover -s tests -p "test_reference_mode.py" -v` | Bundled CPython | passed | 6 tests, OK. |
| `python -B -m unittest discover -s tests -p "test_catalog.py" -v` | Bundled CPython | blocked | Pre-existing missing legacy MoveKeys files, empty unmanaged slots, and Deselect metadata-order mismatch. |
| `python -B -m unittest discover -s tests -v` | Bundled CPython | failed (unrelated) | 274 tests; 4 failures and 30 errors. Sandbox has no writable temporary directory; catalog/action-script and existing module regressions also fail. The Viewer Display Menu module passed. |
| Z menu and native Viewer actions | MotionBuilder 2026 isolated scene | blocked | Feature disabled; no tested host execution interface currently changes Viewer shading safely. |
| Direct Viewer `Wire` QAction through Codex Bridge | MotionBuilder 2026 | invalidated | The discovered action belonged to an unrelated picker command and did not change Viewer shading. |
| Reload `viewer.display_mode_menu` through Codex Bridge | MotionBuilder 2026 | passed | `reload_feature()` returned `True`; result serialization then errored because it was incorrectly treated as a service object. |
| Direct renderer read/change probe after live restart | MotionBuilder 2026 | failed/crashed | CER dump `1787567384830` shows access violation `0xc0000005` in `fbsdk.dll` through `pyfbsdk` from a Python `QTimer`; the implementation was removed. |
| Native Wire dispatch through manager | MotionBuilder 2026 | failed visual gate | Action present and temporary binding restored, but global and targeted synthetic delivery did not provide a verified wireframe result. |
| Targeted Viewer key/capture experiment | MotionBuilder 2026 | failed/crashed | CER dump `1787568216505` shows `0xc0000005` in `Qt6Widgets!QWidget::~QWidget` through a Python application event filter; this test-only path retained/used volatile Qt state and is removed. |

## Blockers and open questions

- No host-supported execution path is both verified effective and crash-safe.
  Direct viewing options, global Qt action matching, and synthetic targeted
  input are rejected by the evidence above.

## Handoff notes

- Both picking entries dispatch `action.viewer.cycle_picking_mode`, as
  requested; the host owns its cycle state.
- The shared route blocks text fields, modal dialogs, and popups before the
  Viewer-only service receives `Z`.
- `viewer.display_mode_menu` is disabled in settings and defaults disabled in
  the catalog. Do not enable it until a safe host execution path is proven.
