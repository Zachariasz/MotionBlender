# Development Guide

## Supported environment

- MotionBuilder 2024-2027.
- Python 3.10-3.13, depending on the MotionBuilder release.
- `pyfbsdk` and `pyfbsdk_additions` from MotionBuilder.
- PySide6/Shiboken6 with PySide2/Shiboken2 fallback where supported by the
  package.
- Windows for native input/cursor operations that use `ctypes`.
- `ffmpeg` with the `qtrle` encoder only for Fast Render.

Use MotionBuilder stubs or official Autodesk SDK documentation when a property,
signature, enum, or object lifetime is unclear.

## Before editing

1. Confirm the requested file is inside the maintained project boundary.
2. Identify the affected stable feature ID, if any.
3. Inspect the feature's `FeatureSpec`, native `implementation_files`, external
   `files`, dependencies, action slot, lifecycle, and warmup policy.
4. Read the relevant source and test files once and retain that context.
5. Read only the detailed reference routed by [`README.md`](README.md).
6. If the work spans contexts, create or update an active task file.

Do not use a broad workspace scan to infer ownership. The MotionBuilder config
contains unrelated creator scripts and host-generated data.

## Change-impact map

| Change | Inspect together | Minimum documentation impact |
| --- | --- | --- |
| Public package API | `__init__.py`, wrappers/callers | Package README |
| Startup or Python Tools menu | `bootstrap.py`, bootstrap template, active PythonStartup copy, bootstrap tests | Architecture, integration checklist |
| Manager lifecycle/dispatch | `manager.py`, adapters, runtime, shutdown tests | Architecture, manager guide |
| Runtime service | `runtime.py`, its consumers, runtime/cursor/interaction tests | Architecture, manager guide |
| Catalog entry | `catalog.py`, ActionScript, generated wrapper, `test_catalog.py` | Package README/status if counts or native list change |
| Native feature | `features/<name>.py`, helper subpackage, catalog, focused tests | Relevant subsystem docs |
| Legacy adapter behavior | `legacy.py`, catalog flags, legacy tests | Architecture/manager guide |
| Shortcut behavior | `shortcuts.py`, manager binding methods, ActionScript, shortcut tests | Package README/testing |
| Viewer/Story UI | controller, runtime UI observer, feature dispatch, UI tests | Manager guide and live checklist |
| G/R/S or FCurves | feature entrypoint, interaction framework, strategy, HIK/tangent helpers | Transform/FCurve standard and testing |
| Codex Bridge | native bridge feature, bootstrap menu, compatibility launchers, bridge tests | Codex Bridge doc, architecture, checklist |
| Antigravity Bridge | `features/antigravity_bridge.py`, `antigravity_mobu_client.py`, launchers, bootstrap menu, bridge tests | Antigravity Bridge doc, architecture, testing |
| Settings schema/defaults | settings store, validators, manager accessors, settings tests | Package README/status, migration behavior |

## Core development rules

### Main-thread execution

Every `pyfbsdk` call and access to MotionBuilder-owned Qt widgets runs on the
main UI thread. A worker, native hook, or external producer may pass primitive
data into the manager, but it must not retain or dereference SDK/Qt wrappers.

The Codex and Antigravity Bridges satisfy this rule by executing commands from
their respective Qt timers, not from external client writers or background threads.

### Wrapper lifetime

Assume MotionBuilder wrappers can become invalid after file open/new, take
replacement, component destruction, or native UI rebuild. Reacquire through
`CommandContext`, validate Qt objects with the matching Shiboken runtime, and
catch `RuntimeError` at native UI access boundaries.

Do not retain native toolbar rows or their controls. Retain only manager-owned
objects and copied primitive geometry.

### Undo and evaluation

Use `context.undo` and balanced transaction scopes. Every commit, cancel, and
exception path must close or cancel the transaction.

Use `context.evaluation` to coalesce scene/FCurve updates. Do not call
`Scene.Evaluate()` on every mouse event.

### Cleanup

For every resource acquired, define its release path at design time:

- SDK callbacks;
- shared UI observers;
- Qt signals, timers, event filters, widgets, and `deleteLater()` objects;
- native hooks and mouse/keyboard grabs;
- cursor and overlay ownership;
- helper processes and temporary bindings;
- scene or HIK state overrides;
- cached C++ wrappers.

`stop()` and `close()` must be idempotent and safe after partial startup.

## Adding a manager-native feature

1. Select a stable ID using the existing category namespace.
2. Place a thin lifecycle entrypoint in `features/`.
3. Put reusable or complex behavior in a focused subpackage.
4. Use one of the native contracts:

   - command: `execute(context)`;
   - tool: `show(context)` plus `close()`;
   - service: `start(context)`, `stop()`, and `status()`.

5. Add a `FeatureSpec` with explicit metadata.
6. Add native modules/helpers to `implementation_files`.
7. Use `files` only for external legacy/launcher/startup inventory.
8. If the feature has an ActionScript slot, add/update the two-line generated
   wrapper and preserve unmanaged slots.
9. Add focused offline tests and update catalog assertions.
10. Complete live MotionBuilder verification before replacing an active legacy
    implementation.

Feature modules must not run work at import time or create an independent
application lifecycle.

## Modifying the catalog

`catalog.py` and `test_catalog.py` form a pair. Preserve:

- unique stable IDs;
- unique managed ActionScript slots;
- valid dependency references;
- valid primary entrypoints;
- exactly represented external physical paths;
- declared native implementation files;
- the intentional unmanaged action slots.

Do not inflate `files` with manager implementation modules. That field exists
for legacy/startup audit coverage; `implementation_files` exists for native
code and shared helpers.

Update dated counts in `PROJECT_STATUS.md` when the catalog changes.

## Working on G/R/S and FCurves

Read the complete
[Transform and FCurve Interaction Migration Standard](../Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md)
before changing input semantics, mode handoff, snapping, precision, pivots,
tangents, HIK behavior, cursor/overlay behavior, mutation ordering, undo, or
evaluation.

Do not implement a private interaction loop inside a feature. Strategies plug
into the shared interaction session and presentation services.

## Working on native UI

Use `story/toolbar.py` as the canonical manager-owned lifecycle pattern and
`viewer/toolbar.py` as the Viewer-row example.

Required pattern:

1. Discover an exact native row/control signature.
2. Validate wrappers and copy geometry to integers.
3. Parent one owned container to the stable pane.
4. Dispatch stable feature IDs from owned controls.
5. Use the shared UI observer and bounded single-shot retry.
6. Reposition or reattach after native rebuilds without duplication.
7. Stop timers/observers, detach, queue deletion, and clear references.

Never use nested `processEvents()` to force attachment.

## Working on the Codex Bridge

Read [`CODEX_BRIDGE.md`](CODEX_BRIDGE.md). Preserve the file protocol unless a
task explicitly versions it. Changes require at least:

- `test_codex_bridge.py`;
- `test_bootstrap_menu.py` if menu behavior changes;
- live status, heartbeat, command/result, error, stop, badge, and cleanup checks.

The bridge executes trusted arbitrary Python inside MotionBuilder. It must not
be exposed as an unauthenticated remote service.

## Compatibility launchers

Compatibility launchers should contain only stable dispatch or a deliberately
preserved callable facade. Do not add feature state, event filters, callbacks,
UI controllers, or business logic to them.

New integrations import from the package root:

```python
from mobu_tools_manager import dispatch

dispatch("stable.feature_id")
```

## Documentation and task completion

Before finishing a substantial change:

- update the relevant docs listed in the change-impact table;
- update the active task with exact files and verification state;
- record new lasting architectural rationale as an ADR;
- report tests as passed only if executed;
- distinguish offline verification from live MotionBuilder verification;
- leave the next action explicit if work remains.

