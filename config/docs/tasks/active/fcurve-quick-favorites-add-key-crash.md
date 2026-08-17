# Task: Fix Quick Favorites FCurve Add Key crash

Status: active  
Last updated: 2026-08-11  
Owner/context: Codex desktop task

## Goal

Pressing `Add Key` in the FCurves Quick Favorites menu inserts keys on the
selected displayed curves without freezing or crashing MotionBuilder.

## Acceptance criteria

- [x] `Add Key` uses a manager-native FCurve command and no synthetic keyboard
  event or keyboard-profile rescan.
- [x] Existing saved `action.fcurve.insert_key` favorite entries migrate to the
  new stable feature ID automatically.
- [x] Targeted offline tests pass.
- [x] Full offline suite result is recorded, including unrelated failures.
- [ ] Live MotionBuilder verification is completed in an isolated scene.
- [x] Manager documentation is updated.

## Scope

Included:

- `fcurves.add_key` stable feature ID and implementation.
- Fresh selected-property discovery through the shared FCurve service.
- Quick Favorites default and saved-setting migration.
- Removal of the failed direct-key replay exception.
- Focused tests and manager documentation.

## Non-goals

- Repairing unrelated catalog/ActionScript slot inconsistencies.
- Refactoring other native-action dispatch paths.
- Editing Autodesk or unrelated personal configuration files.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/runtime.py` | Owns shared FCurve discovery, undo, and evaluation services. |
| `Scripts/mobu_tools_manager/fcurves/add_key.py` | Manager-native key insertion implementation. |
| `Scripts/mobu_tools_manager/features/fcurve_add_key.py` | Stable feature entrypoint. |
| `Scripts/mobu_tools_manager/quick_favorites/settings.py` | Default button and legacy-setting migration. |
| `Scripts/mobu_tools_manager/catalog.py` | Declares the stable feature ID. |

## Starting state

The original Quick Favorites entry dispatched MotionBuilder's native
`action.fcurve.insert_key` through a temporary keyboard binding and profile
rescan. A first attempted mitigation replayed the existing Shift+I shortcut
without a rescan. The user restarted MotionBuilder and reported that it still
crashed. Synthetic input from the popup is therefore excluded from the new
implementation.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-11 | Implement `fcurves.add_key` with `FBFCurve.KeyInsert()` on freshly queried selected properties. | Both native-action dispatch variants crashed; direct SDK mutation can use manager-owned undo and coalesced evaluation. | Temporary keyboard-map dispatch and direct Shift+I replay both reproduced the host crash. |
| 2026-08-11 | Migrate saved legacy native-action entries during settings normalization. | Existing user settings otherwise keep invoking the unsafe path after the default changes. | Requiring users to delete settings manually. |
| 2026-08-11 | Document the popup/native-action crash boundary as ADR-0003 and a reusable incident runbook. | Future work must not repeat keyboard timing/rescan experiments after the same host crash recurs. | Leaving the rationale only in chat or this temporary task file. |
| 2026-08-11 | Update the active manager source first; transfer archives are optional only. | This workspace is the active configuration and the user expects changes to be installed directly. | Treating a ZIP as the primary delivery. |

## Progress

### Completed

- Reproduced the unsafe architectural boundary from the user's restart test.
- Read manager instructions, README, docs routing, FCurve runtime, catalog, and
  relevant tests.
- Added `fcurves.add_key` with fresh selected-property discovery, direct
  `FBFCurve.KeyInsert()`, shared undo registration, existing-key detection, and
  one coalesced FCurve refresh.
- Changed the default favorite and normalized saved native Insert Key entries
  to the new feature ID.
- Removed the failed direct Shift+I dispatcher exception.
- Added focused command/runtime/settings/catalog tests and updated manager
  documentation/counts.
- Created `QuickFavorites_AddKey_Fix_2026-08-11.zip` with the seven required
  paste-over runtime files.
- Added ADR-0003, a reusable Quick Favorites incident-response procedure, the
  host-crash escalation rule, and a dedicated live Add Key checklist.

### In progress

- Waiting for one isolated live MotionBuilder verification after a full host
  restart.

### Next action

1. Extract `QuickFavorites_AddKey_Fix_2026-08-11.zip` over the MotionBuilder
   configuration root, fully restart MotionBuilder, and test Add Key once with
   selected FCurve properties in an isolated scene.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/shortcuts.py` | Removed the failed direct Shift+I mitigation. | `test_shortcuts.py` passed (5 tests). |
| `Scripts/mobu_tools_manager/runtime.py` | Added fresh selected-property FCurve query. | `test_runtime_services.py` passed (11 tests). |
| `Scripts/mobu_tools_manager/fcurves/discovery.py` | Added selected current-layer curve records. | Covered by Add Key tests. |
| `Scripts/mobu_tools_manager/fcurves/add_key.py` | Added direct key insertion transaction. | `test_fcurve_add_key.py` passed (3 tests). |
| `Scripts/mobu_tools_manager/features/fcurve_add_key.py` | Added native feature entrypoint. | Catalog entrypoint test passed. |
| `Scripts/mobu_tools_manager/quick_favorites/settings.py` | Default/migrate Add Key to stable feature ID. | `test_settings.py` passed (4 tests). |
| `Scripts/mobu_tools_manager/catalog.py` | Registered `fcurves.add_key`. | New catalog metadata/count checks passed. |
| `docs/decisions/0003-popup-native-actions-require-manager-features.md` | Recorded the lasting native-action boundary and persistence decision. | Local links resolved. |
| `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md` | Added reusable popup/native-action crash response workflow. | Local links resolved. |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Added the stop/reproduce/evidence escalation rule. | Local links resolved. |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Added exact FCurve Add Key live gates. | Live checks not run. |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Earlier focused shortcut tests | Bundled Python 3.12 | passed | 6 tests passed; did not prove host safety. |
| Earlier full suite | Bundled Python 3.12 | failed (unrelated existing state) | 154 tests: 152 passed; catalog path count and missing ActionScript slot 44 failed. |
| Direct Shift+I mitigation after full restart | MotionBuilder | failed | User reports MotionBuilder still crashes. |
| Focused Add Key/runtime/settings/shortcuts checks | Bundled Python 3.12 | passed | 23 tests passed. |
| Focused catalog checks | Bundled Python 3.12 | failed (unrelated existing state) | New metadata/count checks passed; only blank ActionScript slot 44 failed. |
| Full offline suite | Bundled Python 3.12 | failed (unrelated existing state) | 157 tests: 156 passed; only blank ActionScript slot 44 failed. |
| ZIP content and hash | Windows tar/PowerShell | passed | 7 expected runtime files; SHA-256 `AEB79651C6B03A448F1054BBC92F48CCF969484729DE3954A092349F89410CCA`. |
| Touched-document local link check | PowerShell | passed | Every local Markdown link in the touched documents resolves. |
| Documented implementation counts | Bundled Python 3.12 | passed | 49 features, 61 catalog paths, 14 native features, 95 package Python files, 24 test modules. |

## Blockers and open questions

- Final host verification requires a complete MotionBuilder restart after the
  new manager modules are copied into the active configuration.

## Handoff notes

Do not retry synthetic key injection for this action. If the direct SDK command
still crashes after one isolated live check, stop and collect the host crash
evidence before changing the implementation again.
