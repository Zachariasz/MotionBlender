# Codex Instructions: MotionBuilder Tools Manager

This file intentionally overrides the older root `AGENTS.md`. It is the current
workspace instruction source for the manager project.

## Project boundary

The authored project in this MotionBuilder configuration is:

- `Scripts/mobu_tools_manager/**`
- the manager-owned Codex Bridge in
  `Scripts/mobu_tools_manager/features/codex_bridge.py`
- the active bootstrap `PythonStartup/000_MobuToolsManagerBootstrap.py`
- manager-owned ActionScript wrappers and mappings
- thin compatibility launchers that dispatch manager feature IDs
- `Scripts/tests/**` tests that exercise `mobu_tools_manager`
- manager engineering documentation and root `docs/**`

Other MotionBuilder configuration files and unrelated scripts may belong to
Autodesk, other creators, or older personal tools. Treat them as read-only and
out of scope unless the user explicitly includes them. Do not inventory or
refactor unrelated `Scripts/custom`, picker, task, layout, keyboard, preset,
backup, quarantined, or machine-specific configuration files merely because
they share this workspace.

Legacy files listed in `mobu_tools_manager.catalog.FEATURES` are integration
inputs. Inspect or change their internals only when a requested manager change
requires it. `MotionBuilderToolsManager/backups/**` is recovery history, never
the active implementation.

## Required context loading

For every task that touches the manager or bridge:

1. Read `Scripts/mobu_tools_manager/AGENTS.md`.
2. Read `Scripts/mobu_tools_manager/README.md` and `docs/README.md`.
3. Use the routing table in `docs/README.md` to load only the relevant detailed
   documents.
4. Inspect the exact implementation and tests before editing.
5. When continuing substantial work, read the named file under
   `docs/tasks/active/` and reconcile it with the current files before acting.

Do not load every long engineering reference for every task. The package
README and docs index are maps; detailed guides are conditional references.

## MotionBuilder target

- Target MotionBuilder 2024-2027 and Python 3.10-3.13.
- Use `pyfbsdk`, `pyfbsdk_additions`, and MotionBuilder's bundled PySide6 or
  PySide2 runtime.
- When an SDK signature or enum is uncertain, inspect Autodesk documentation or
  MotionBuilder stubs. Do not guess.
- Prefer the smallest implementation consistent with current architecture.
- Do not add Python 2 compatibility or abstractions for obsolete SDK behavior.

## Non-negotiable runtime safety

- `pyfbsdk` is not thread-safe. All SDK and MotionBuilder-owned Qt access must
  execute on the main UI thread.
- Worker or native-hook callbacks may enqueue primitive data only. They must not
  retain or access SDK wrappers.
- MotionBuilder Python objects wrap C++ objects. Reacquire them after file,
  take, scene, component, or UI invalidation. Validate Qt wrappers with the
  matching Shiboken runtime before access.
- Destroy owned scene components explicitly with `FBDelete()` when supported.
  Do not call `FBDelete()` on utility wrappers known to crash the current host.
- Use the manager's `CommandContext`, shared undo helper, coalesced evaluation
  scheduler, input router, UI observer, and overlay coordinator. Do not create
  competing global services.
- Never call `Scene.Evaluate()` in a tight interaction loop. Batch or coalesce
  evaluation requests.
- All mutation transactions must finish on every success, cancellation, and
  exception path. Do not leave an open undo transaction.

## Manager ownership rules

- Exactly one reload-safe manager singleton owns startup and shutdown.
- The manager owns the application-exit callback and shared Qt application
  event filter. Individual features must not add their own equivalents.
- Native feature modules have no autorun behavior. Commands, tools, and services
  follow the contracts in `Scripts/mobu_tools_manager/AGENTS.md`.
- Stable feature IDs are the external interface. New launchers import from
  `mobu_tools_manager` and dispatch IDs; they do not import implementation
  modules directly.
- Every callback, timer, hook, signal, helper process, widget, cursor, overlay,
  grab, and cached wrapper must have a deterministic removal path.
- Native toolbar rows are volatile geometry references only. Parent one
  manager-owned container to the stable pane, retain primitive geometry, and
  reacquire native UI after rebuilds.

## Codex Bridge rules

- The active bridge is the manager-native file-queue service documented in
  `docs/CODEX_BRIDGE.md`. It is not a socket listener.
- The service polls through a Qt timer on MotionBuilder's main thread, claims
  one `.py` command at a time, captures output, writes structured JSON, and
  archives the command.
- Before sending work, verify `status.json`, heartbeat freshness, and
  MotionBuilder responsiveness.
- Bridge payloads must be self-contained, bounded, and explicit about results.
  Do not perform long blocking work or touch production scenes without the
  user's authorization.
- Treat the command directory as trusted arbitrary-code execution. Do not
  expose it as a remote or untrusted interface.

## Verification

- Offline tests live in `Scripts/tests`, not a root `Tests` directory.
- Run tests from `Scripts` with:
  `python -m unittest discover -s tests -v`.
- For a targeted file use:
  `python -m unittest discover -s tests -p "test_name.py" -v`.
- Scene- and UI-dependent checks use
  `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` in an isolated scene.
- Never overwrite a live scene or production asset during testing.
- Report tests as passed only when they were actually executed. Distinguish
  unrun, blocked, failed, and passed checks.
- After one targeted fix for a failed code test or bridge execution, stop if the
  same check fails again. Analyze the evidence instead of entering a retry loop.

## Documentation and handoff

- Update the relevant documentation in the same change when architecture,
  behavior, commands, paths, feature IDs, settings, or verification gates
  change.
- Keep instruction files concise and mandatory. Put explanation in `docs/**` or
  the existing engineering standards.
- For substantial multi-context work, create or update a task file from
  `docs/tasks/TEMPLATE.md`. Record scope, decisions, changed files, tests run,
  blockers, and the exact next action.
- Record lasting architectural decisions under `docs/decisions/`.
- Never mark historical documents as current sources of truth. The live catalog
  is `Scripts/mobu_tools_manager/catalog.py`; its executable specification is
  `Scripts/tests/test_catalog.py`.

