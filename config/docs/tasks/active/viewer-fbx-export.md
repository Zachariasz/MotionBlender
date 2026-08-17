# Task: Viewer FBX Export

Status: completed  
Last updated: 2026-08-14

## Goal

Add a Viewer-toolbar Export split control that exports configured hierarchy
objects to FBX and stores its behavior settings in the source scene FBX.

## Acceptance criteria

- [x] Export appears 25 px to the right of Fast Render with a touching narrow
  down-arrow settings button.
- [x] The settings dialog edits folder, file name, one-take-per-file, and exact
  hierarchy objects.
- [x] Settings use custom properties on a root-level `ExportPreset` model Null
  that is force-selected into every exported FBX.
- [x] Export restores the pre-export model selection on success and failure.
- [x] Focused offline behavior and toolbar tests pass.
- [x] Live MotionBuilder UI, persistence, and exported-FBX contents pass with
  the scene-model `ExportPreset` implementation.
- [x] Documentation updated.

## Scope

Included:

- `scene.export_fbx`, manager-owned Viewer controls, FBX settings/storage,
  export execution, tests, and documentation.

## Non-goals

- Changing Fast Render behavior.
- Editing the older `custom/ExportCustom.py` legacy feature.
- Removing namespaces or mutating hierarchy objects before export.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/viewer/toolbar.py` | Owns the combined Viewer controls. |
| `Scripts/mobu_tools_manager/exporting/fbx.py` | Scene properties and FBX export behavior. |
| `Scripts/mobu_tools_manager/exporting/dialog.py` | Export settings UI. |
| `Scripts/mobu_tools_manager/features/export_fbx.py` | Stable command entrypoint. |
| `Scripts/tests/test_export_fbx.py` | Focused persistence/export behavior coverage. |

## Starting state

The Viewer controller owned only Fast Render. The catalog also contains an
unrelated legacy `objects.export_custom` entry, but its script is not the
manager-native Viewer export requested here.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-14 | Finalize the root-level `ExportPreset` model Null as the persistence owner. | A controlled retest after explicitly resetting the manager confirmed that `FBUserObject` is not serialized into FBX at all in this workflow; the Null implementation persists correctly after reload. | `FBUserObject` and per-model properties both failed live FBX reload tests. |
| 2026-08-14 | Retest the named `FBUserObject` as the sole persistence owner after explicitly resetting the manager feature. | The user confirmed the Null version works and identified that earlier tests may have exercised a stale loaded module. | Keeping both owners would make the controlled live result ambiguous. |
| 2026-08-14 | Make one root-level `ExportPreset` Null the exported settings owner and force-select it during export. | Live use proved both the scene user object and properties on ordinary exported models were unreliable persistence owners. A selected model Null is part of the exact export set and can carry the whole preset in one place. | Continuing to distribute settings across checked models failed the user's reload test. |
| 2026-08-14 | Store settings and membership as custom properties on every checked model; keep reading the named `FBUserObject` for migration. | Live use proved the user object was omitted from selected-model export, while checked models are the objects guaranteed to travel. | A standalone user object does not survive this export path; per-user JSON would not travel with the FBX. |
| 2026-08-14 | Persist model `LongName` strings and reacquire models for every export. | Wrapper lifetime is finite and names preserve namespaces/hierarchy identity better than display names. | Retaining `FBModel` wrappers across file/UI invalidation is unsafe. |
| 2026-08-14 | Use `FBMotionFileExportOptions` with `kFBSelectedModels`. | It directly supports exact model selection and one-take-per-file FBX output. | `FileSave` is Save As and changes the current scene file; `FileExport` exports only the current take with default options. |

## Progress

### Completed

- Added manager-native settings storage, hierarchy dialog, export feature,
  catalog entry, combined toolbar controls, focused tests, and documentation.
- A live user check found that the original user-object-only settings did not
  survive reopening an exported FBX.
- Migrated persistence to custom properties on every checked model and added
  automatic migration immediately before export.
- A second live user check found that the per-model properties also did not
  survive reload. The `ExportPreset` Null then passed live use.
- A controlled retest after resetting the manager confirmed that
  `FBUserObject` is not saved into FBX at all. The user reverted to the working
  scene-model `ExportPreset` implementation, which is now final.
- Focused export and Viewer toolbar suites pass (9 and 4 tests).
- Live testing confirmed the final `ExportPreset` implementation persists and
  the controlled `FBUserObject` alternative does not save into FBX at all.
- The full suite ran 184 tests; 181 passed. Its three failures are existing
  missing camera-cycle modules and four missing legacy key-move scripts.

### In progress

- None.

### Next action

1. No required implementation work remains. Repeat the integration checklist
   only after future exporter or MotionBuilder-version changes.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/exporting/` | New FBX settings/export subsystem. | Focused test passed |
| `Scripts/mobu_tools_manager/features/export_fbx.py` | New native command entrypoint. | Import/behavior coverage pending full suite |
| `Scripts/mobu_tools_manager/viewer/toolbar.py` | Export split control. | Focused test passed |
| `Scripts/mobu_tools_manager/catalog.py` | Added `scene.export_fbx`. | Catalog blocked by four pre-existing missing legacy files |
| `Scripts/tests/test_export_fbx.py` | Focused behavior coverage for `ExportPreset` reload, legacy cleanup, forced inclusion, and exact selection. | Passed, 9 tests |
| `Scripts/tests/test_viewer_toolbar.py` | Split-control dispatch/layout/cleanup assertions. | Passed |
| `Scripts/mobu_tools_manager/README.md`, `docs/**` | Usage, architecture, counts, tests, live gates. | Reviewed |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -m unittest discover -s tests -p "test_export_fbx.py" -v` | Bundled Python 3 | passed | 9 tests |
| `python -m unittest discover -s tests -p "test_viewer_toolbar.py" -v` | Bundled Python 3 | passed | 4 tests |
| `python -m unittest discover -s tests -p "test_catalog.py" -v` | Bundled Python 3 | blocked | Four existing `Scripts/custom/MoveKeys*.py` integration inputs are missing; count expectation reconciled to 59 |
| `python -m unittest discover -s tests -v` | Bundled Python 3 | failed | 184 run, 181 passed; missing camera-cycle modules and four missing legacy key-move files |
| Viewer FBX Export persistence check | MotionBuilder 2026 | passed | User confirmed `ExportPreset` survives FBX reload; reset-manager `FBUserObject` retest failed |

## Blockers and open questions

- Live MotionBuilder confirmed that `FBUserObject` is not serialized into FBX
  at all in this workflow and that the scene-model `ExportPreset` approach
  works after reopening the FBX.
- Catalog validation is independently blocked by missing legacy integration
  inputs: `MoveKeysRight.py`, `MoveKeysLeft.py`, `MoveKeysValueUp.py`, and
  `MoveKeysValueDown.py` under `Scripts/custom/`.
- `test_camera_cycle.py` is independently blocked because the catalog/test
  references `features/camera_cycle.py` and `viewer/camera_cycle.py`, but those
  files are absent in the current workspace.

## Handoff notes

The export feature never retains SDK wrappers. The settings dialog enumerates
the current `RootModel` hierarchy while hiding `ExportPreset`. Saving settings
writes folder, filename, take behavior, and checked long names to that model
Null; export repeats the write to migrate old scenes, temporarily selects the
configured models plus the preset, calls `FileExportWithOptions`, and restores
selection in `finally`. A legacy `FBUserObject` can be accepted only as an
in-memory migration source and is deleted after the preset is written; it is
never considered persistent scene data.
