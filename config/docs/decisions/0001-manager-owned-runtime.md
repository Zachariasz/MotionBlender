# ADR-0001: One Manager-Owned Runtime

Date: 2026-07-29  
Status: accepted

## Context

The pre-manager tool collection contained independent startup launchers,
application event filters, callbacks, polling timers, input hooks, windows,
overlays, and process-global state. Manual reload or duplicated startup could
multiply resources, increase scene-evaluation cost, retain invalid C++ wrappers,
and make MotionBuilder shutdown unsafe.

ActionScript commands also reread and recompiled complete source files on hot
shortcut paths, while transform and FCurve tools independently rediscovered the
same selection, editor, camera, input, and UI state.

## Decision

Use one reload-safe `MotionBuilderToolsManager` singleton as the lifecycle and
dispatch owner.

The manager owns one early application-exit callback and one shared
`RuntimeServices` graph. Runtime services own selection/scene/FCurve caches, one
Qt application filter, input routing, interaction coordination, cursor/overlay
presentation, evaluation coalescing, undo helpers, graph transforms, and HIK
state.

Features are addressed by stable catalog IDs and run through native or legacy
adapters. Native features use explicit command/tool/service contracts and must
not create competing global owners.

## Consequences

- Re-running the bootstrap replaces the prior manager rather than duplicating
  it.
- Every feature resource must have deterministic manager-visible cleanup.
- Shared services become the required path for input, UI observation, undo,
  evaluation, overlays, and cached wrapper access.
- Legacy scripts can migrate incrementally through a compile-once adapter.
- A manager/runtime change has broad impact and requires shutdown, reload, and
  ownership regression tests.
- The manager singleton is intentionally stored in `builtins`; feature
  singletons are not.

## Alternatives considered

- Keep independent startup scripts — rejected because ownership and reload
  behavior remain fragmented.
- Let each feature install its own global services — rejected because duplicate
  filters/hooks/timers and shutdown ordering cannot be controlled reliably.
- Rewrite every legacy feature before introducing a manager — rejected because
  it prevents incremental migration and makes behavioral equivalence difficult
  to verify.

## References

- `Scripts/mobu_tools_manager/manager.py`
- `Scripts/mobu_tools_manager/runtime.py`
- `Scripts/mobu_tools_manager/catalog.py`
- `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md`
- `Scripts/tests/test_manager_shutdown.py`
- `Scripts/tests/test_runtime_services.py`

