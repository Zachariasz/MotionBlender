# Task: Reveal selected object in hierarchy

Status: active  
Last updated: 2026-08-14  
Owner/context: Codex desktop task

## Goal

From the 3D Viewer Quick Favorites menu, reveal the current selected model in
the Navigator by expanding its hierarchy parents and centering the selected row.

## Acceptance criteria

- [x] `objects.find_in_hierarchy` is a manager-native command while preserving
  its stable ID and ActionScript slot 44.
- [x] The Viewer Quick Favorites default and a one-time user-settings migration
  expose the command.
- [x] Focused offline tests pass.
- [x] The command opens the built-in Navigator and synchronizes selection.
- [x] Live manager dispatch triggers native `Expand To Selection`.
- [x] Visual confirmation shows the selected hierarchy path expanded.
- [x] Manager documentation and the live checklist are updated.

## Scope

Included:

- `objects.find_in_hierarchy`, its manager-native implementation, the Viewer
  Quick Favorites configuration, catalog metadata, and focused tests.

## Non-goals

- Refactoring unrelated legacy Object/Scene commands or replacing other native
  Scene Browser behavior.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/features/find_in_hierarchy.py` | Main-thread Navigator opening, selection-sync, and Qt-tree fallback command. |
| `Scripts/mobu_tools_manager/catalog.py` | Stable feature metadata and slot 44. |
| `Scripts/mobu_tools_manager/quick_favorites/settings.py` | Default and one-time favorite migration. |
| `Scripts/tests/test_find_in_hierarchy.py` | Focused offline behavior coverage. |

## Starting state

`objects.find_in_hierarchy` was a legacy adapter for
`custom/FindSelectedInHierarchy.py` and was not part of the default 3D Viewer
Quick Favorites menu. An existing saved Quick Favorites configuration does not
receive new defaults automatically.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- |
| 2026-08-14 | Preserve stable ID and ActionScript slot 44 while migrating the command to a manager-native module. | Existing shortcuts/wrappers remain compatible and native code follows the manager’s lifecycle and main-thread contract. | Introducing a second command or menu-only launcher. |
| 2026-08-14 | Use a versioned one-time Quick Favorites migration. | Existing users receive the new menu item, while later removal in the editor remains respected. | Re-adding the favorite on every manager start. |
| 2026-08-14 | Open Navigator through its checked Window action before sending `HardSelect`. | The live session had no Navigator tree until the built-in action was triggered; `HardSelect` refreshes selection but does not itself expand the native hierarchy. | Treating the native widget as `QTreeView` or claiming a selection refresh is a reveal. |
| 2026-08-14 | Target Navigator's existing `Expand To Selection` operation. | This is the exact native hierarchy command requested by the user and confirmed in `ktbrowsing.dll`. | Reimplementing native hierarchy traversal or using Viewer double-click projection. |
| 2026-08-14 | Recreate the native popup with a focused Navigator row plus the Windows context-menu key, then trigger its exact Qt action. | The popup has no owner and its action is destroyed when closed; the tested two-stage sequence safely creates and invokes it on MotionBuilder's main thread. | Caching the volatile action, retaining the native popup, or linking to internal C++ symbols. |

## Progress

### Completed

- Loaded manager, catalog, Quick Favorites, testing, and MotionBuilder UI guidance.
- Verified the previous legacy script’s hierarchy-tree discovery behavior.
- Added the native feature, settings migration, metadata, tests, docs, and live checklist.
- Passed focused hierarchy (5) and settings (6) tests.
- Ran the full suite: 190/193 tests passed; the three failures are unrelated to
  this feature.
- Live bridge inspection found that the Navigator is an internal proprietary
  tree with no exposed Qt model or expansion API. `HardSelect` only refreshes
  selection; it does not reveal the selected row.
- Confirmed the native Navigator context menu contains `Expand To Selection`.
  The action is created dynamically by the Kt browsing control and is not a
  persistent `QAction` or `pyfbsdk` entrypoint.
- Implemented the manager-owned short-lived timer that polls for the recreated
  popup, invokes `Expand To Selection`, closes the popup, and cleans itself up.
- Live automatic dispatch completed with `expand_triggered=true`; visual
  inspection confirmed the full path through `Neck` to `Head` was expanded.

### In progress

- None for the requested MotionBuilder configuration and current layout.

### Next action

1. User verifies the same command from the Viewer Quick Favorites menu during
   normal picker use.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/features/find_in_hierarchy.py` | Opens Navigator, recreates its context popup, invokes native `Expand To Selection`, and retains the Qt-tree fallback. | Focused and live tests passed. |
| `Scripts/mobu_tools_manager/catalog.py` | Native metadata for existing ID/slot. | Static assertion passed; catalog suite blocked by unrelated files. |
| `Scripts/mobu_tools_manager/quick_favorites/settings.py` | Viewer default and one-time migration. | Settings tests passed. |
| `Scripts/mobu_tools_manager/manager.py` | Preserve Quick Favorites schema version on editor saves. | Settings tests passed. |
| `Scripts/mobu_tools_manager/quick_favorites/editor.py` | Retain schema version while editing favorites. | Not run live. |
| `Scripts/tests/test_find_in_hierarchy.py` | Focused command tests. | Passed (6 tests). |
| `Scripts/tests/test_catalog.py` | Native metadata assertion. | Blocked by unrelated missing files. |
| `Scripts/tests/test_settings.py` | Default/migration assertions. | Passed (6 tests). |
| `Scripts/mobu_tools_manager/README.md` | Native feature count and command map. | Reviewed. |
| `docs/PROJECT_STATUS.md` | Native feature/test-count snapshot. | Counts verified. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Live acceptance steps. | Not run. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Focused hierarchy command tests | Bundled Python 3 | passed | 6 tests passed. |
| Settings tests | Bundled Python 3 | passed | 6 tests passed. |
| Catalog tests | Bundled Python 3 | failed, unrelated | Four pre-existing `custom/MoveKeys*.py` inputs are absent. |
| Full offline suite | Bundled Python 3 | failed, unrelated | 190/193 passed; missing `features/camera_cycle.py` plus the same four legacy inputs. |
| Navigator open and selection sync | MotionBuilder 2026 bridge | passed | Built-in Navigator action checked; selected `Head` received one `HardSelect` update. |
| Automatic native action | MotionBuilder 2026 bridge | passed | Clean manager dispatch reported `expand_triggered=true`; timer removed itself. |
| Visual Navigator reveal | MotionBuilder 2026 | passed | Navigator expanded the complete hierarchy path through `Neck` to `Head`. |

## Blockers and open questions

- The public Python SDK does not expose the hierarchy operation directly. The
  implementation intentionally invokes MotionBuilder's existing popup action
  and cleans up its short-lived timer on success, timeout, reload, or shutdown.
