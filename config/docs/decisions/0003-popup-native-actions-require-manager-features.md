# ADR-0003: Popup-Unsafe Native Actions Require Manager Features

Date: 2026-08-11  
Status: accepted

## Context

Quick Favorites originally launched FCurves Add Key as MotionBuilder's native
`action.fcurve.insert_key`. The manager's normal native-action dispatcher
temporarily changed the active keyboard profile, rescanned it, and emitted a
complete temporary function-key pair. MotionBuilder froze or crashed when that
route was started from the FCurve popup.

Removing the profile rescan was insufficient: replaying the action's existing
Shift+I binding from the popup still crashed after a full MotionBuilder
restart. The repeated failure establishes that synthetic invocation of this
editor action from the popup is host-unsafe, not merely that rescanning is
slow.

Quick Favorites settings may persist old targets, so changing only the default
entry does not remove the unsafe path for existing users.

## Decision

When a MotionBuilder native editor action freezes or crashes through a manager
popup or deferred callback, and the failure remains after removing keyboard-map
rescan, the manager must stop synthesizing that action. The operation becomes a
stable manager-native feature implemented with the supported SDK on the main UI
thread.

For FCurves Add Key:

- the stable ID is `fcurves.add_key`;
- selected properties are queried fresh from `FBFCurveEditorUtility` at
  execution time;
- current-layer curves are reacquired and keyed with `FBFCurve.KeyInsert()` at
  the current time;
- property owners are registered in one shared undo transaction;
- evaluation/FCurve refresh is requested once through the shared scheduler;
- existing keys at the current time are a no-op;
- saved `action.fcurve.insert_key` favorites normalize to `fcurves.add_key`;
- neither Quick Favorites nor the feature emits a synthetic key or edits the
  keyboard profile.

This is a narrow exception based on reproduced host failure. Other
`native_action` favorites continue to use the manager-owned dispatcher until
evidence shows that a particular action is unsafe.

## Consequences

- Existing Quick Favorites configurations move to the safe path without manual
  settings deletion.
- The feature is independently testable and participates in manager
  enable/disable, diagnostics, undo, reload, and cleanup policies.
- A new native feature, catalog entry, tests, and persistence migration are
  required for each action moved off native dispatch.
- Offline fakes cannot establish C++ host safety; one isolated live test after a
  full process restart remains mandatory.
- If the same host crash repeats after one direct-SDK fix, work stops for crash
  evidence collection. Repeated speculative retries are prohibited.

## Alternatives considered

- Continue temporary keyboard-profile rescans: rejected because the original
  path froze/crashed MotionBuilder.
- Replay Shift+I without rescanning: rejected because it still crashed after a
  full restart.
- Change only the default favorite: rejected because saved settings would keep
  dispatching the unsafe native action.
- Put key insertion inside the compatibility launcher: rejected because it
  would bypass stable-ID dispatch and duplicate manager ownership.

## References

- `Scripts/mobu_tools_manager/catalog.py`
- `Scripts/mobu_tools_manager/fcurves/add_key.py`
- `Scripts/mobu_tools_manager/features/fcurve_add_key.py`
- `Scripts/mobu_tools_manager/quick_favorites/settings.py`
- `Scripts/tests/test_fcurve_add_key.py`
- `Scripts/tests/test_settings.py`
- `docs/tasks/active/fcurve-quick-favorites-add-key-crash.md`
