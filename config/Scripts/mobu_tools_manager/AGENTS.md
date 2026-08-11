# MotionBuilder Tools Manager Package Instructions

## Sources of truth

- Package overview and public API: `README.md`
- Feature catalog: `catalog.py`
- Catalog executable specification: `../tests/test_catalog.py`
- Core lifecycle: `manager.py`, `runtime.py`, and `bootstrap.py`
- Detailed lifecycle and migration rules: `../MOBU_TOOLS_MANAGER_GUIDE.md`
- Transform/FCurve interaction contract:
  `../MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md`
- Codex Bridge protocol: `../../docs/CODEX_BRIDGE.md`
- Test routing and current gaps: `../../docs/TESTING.md`
- Live verification: `../tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`

Read `../../docs/README.md` and select only the references relevant to the
requested subsystem. Do not load the 60 KB transform standard for unrelated
catalog, bridge, settings, or Story work.

## Package boundary

This package is the authored core. Direct external integrations include the
active PythonStartup bootstrap, manager-owned ActionScript wrappers/mappings,
thin compatibility launchers, `../custom/icons/2arrow.png` and `4arrow.png`, and
tests that import this package. Other scripts are out of scope unless the user
explicitly says otherwise.

`../MOBU_SCRIPT_AUDIT.md` is a dated migration inventory, not the live catalog.
Use `catalog.py` and `test_catalog.py` for current counts and mappings.

## Required workflow

1. Identify the stable feature ID or core service affected.
2. Inspect its `FeatureSpec`, implementation files, direct dependencies, and
   relevant tests.
3. Determine ownership: manager core, runtime service, native feature, legacy
   adapter, UI controller, or compatibility launcher.
4. Make the smallest change that preserves lifecycle and reload behavior.
5. Run the narrowest relevant offline tests, then the full suite when feasible.
6. Perform live MotionBuilder checks when the change touches SDK state, native
   UI, shortcuts, input, HIK, Story, rendering, or the bridge.
7. Update documentation and the active task handoff when behavior or design
   changed.

## Main-thread and wrapper safety

- `pyfbsdk` and MotionBuilder-owned Qt widgets are main-thread only.
- Native hooks or background work may send primitive values to the main thread;
  they may not retain or dereference SDK/Qt wrappers.
- Treat `FBModel`, `FBComponent`, `FBCharacter`, `FBStory*`, animation objects,
  and native Qt widgets as C++-owned wrappers with finite validity.
- File open/new, take replacement, scene destruction, UI rebuild, and wrapper
  access errors require invalidation and reacquisition through `CommandContext`.
- Validate Qt objects through Shiboken inside guarded access. Copy native UI
  geometry into Python primitives before retaining it.
- Use `context.undo` and `context.evaluation`; do not create a competing undo or
  evaluation service. Finish or cancel every transaction on every exit path.

## Ownership invariants

- `builtins._motionbuilder_tools_manager` is the one intentional manager
  singleton.
- The manager owns one `FBApplication.OnFileExit` callback and the runtime owns
  one shared Qt application event filter.
- Features observe UI events through `context.add_ui_event_observer()`.
- `RuntimeServices` owns selection, scene, FCurve, UI, evaluation, input,
  overlay, HIK, interaction, and undo services.
- A feature must not add an unmanaged global filter, application-exit callback,
  repeating idle loop, cursor owner, input coordinator, or shared cache.
- Every resource acquired by `start()`, `show()`, or an interaction must have a
  deterministic, idempotent release path.

## Feature contracts

Native modules have no import-time execution.

Commands expose `execute(context)`. Tools expose `show(context)` and `close()`.
Services expose `start(context)`, `stop()`, and `status()`. `start()` must be
idempotent. `stop()` must be safe after partial startup and during early
application-exit shutdown.

External code dispatches stable IDs through `mobu_tools_manager`. Do not create
new launchers that import `features.*` directly. Compatibility launchers must
remain thin and lifecycle-free.

When adding a native catalog entry:

- keep `id` permanent and `name` user-facing;
- use `files` only for audited external/legacy physical paths;
- declare native modules and helpers in `implementation_files`;
- declare dependencies, action slot, shortcut, warmup, context requirements,
  resident state, entrypoint, and stop entrypoint explicitly;
- update `test_catalog.py` and generated ActionScript wrappers when applicable.

## Interactive transform rules

- G/R/S are manager-level mutually exclusive modes coordinated by
  `InteractionManager`.
- A different G/R/S launcher performs an atomic cancel-then-start handoff: the
  previous operation restores its original snapshot and releases every owner
  before the replacement captures.
- Repeating G during Viewer Move, S during Viewer Scale, or the active FCurve
  launcher is a consumed no-op. Repeating R during Viewer Rotate is the sole
  mode-cycle exception: restore original rotations, clear the axis constraint,
  anchor at the R-key cursor, and toggle orbit/trackball in the same session.
- Every valid Viewer X/Y/Z press is a non-terminal restart from the immutable
  operation-start snapshot. This includes the first lock, a different axis,
  and repeated presses cycling global/local/off. Discard the earlier preview,
  retain numeric input, and anchor the new segment at the axis-key cursor.
- FCurve constraint changes and Shift/Ctrl changes remain continuous rebases;
  do not apply the Viewer restart rule to them.
- Launcher key-up must pass through to MotionBuilder even when the resident
  key-down launch was consumed.
- Shift precision and Ctrl snapping use the shared policy. Snapping applies to
  the complete result from captured start values.
- Viewer and FCurve strategies use immutable starting snapshots, shared numeric
  input, shared overlay/cursor presentation, and complete terminal cleanup.
- HIK behavior belongs to `object_transforms/hik.py`, not individual feature
  modules.

Read the transform/FCurve migration standard before changing these semantics.

## Native UI rules

- Use the runtime's existing `QApplication` and shared event observer.
- Identify native controls by exact signatures and treat them as volatile.
- Parent one owned container to a stable pane, never to a native toolbar row.
- Use owned single-shot timers and bounded startup retries. Do not call nested
  `processEvents()`.
- On stop or invalidation, stop timers, unregister observers, disconnect owned
  signals, hide/detach owned widgets, call `deleteLater()`, and clear references.
- Repeated reload, enable/disable, and native UI rebuilds must not duplicate
  controls or callbacks.

## Codex Bridge rules

- `features/codex_bridge.py` is the active implementation. Loose bridge scripts
  dispatch `developer.codex_bridge` only.
- The bridge is a trusted local file queue polled by a main-thread Qt timer. It
  is not a socket server and provides no sandbox or authentication.
- Claim commands by moving them from `commands` to `running`; ignore temporary
  files; execute one command at a time; always write JSON results and archive
  the command to `done`.
- Preserve status, heartbeat, stdout/stderr capture, `set_result`, `RESULT`,
  `bridge_log`, and stop-request behavior unless intentionally versioning the
  protocol.
- Payloads must be bounded and self-contained. Long-running work blocks the
  MotionBuilder UI and is not acceptable.
- Stop must remove the poll timer, shared UI observer, badge, legacy bridge
  resources, and module service reference.

## Verification gates

From `Scripts`:

```text
python -m unittest discover -s tests -v
```

For a targeted module:

```text
python -m unittest discover -s tests -p "test_name.py" -v
```

Use descriptive test names of the form
`test_<unit>_<state>_<expected_behavior>` for new tests. Preserve existing names
unless a change requires touching them.

Offline tests do not authorize live activation by themselves. Use the
integration checklist for MotionBuilder-owned UI, scene state, HIK, Story,
shortcuts, rendering, and bridge behavior. Never run destructive scene tests in
a live production scene.

If a changed test fails, make at most one evidence-based targeted fix. If the
same test fails again, stop and report the failure and likely cause.

## Documentation and context handoff

- Update `README.md` for public usage or package-map changes.
- Update `../../docs/ARCHITECTURE.md` for ownership or data-flow changes.
- Update `../../docs/CODEX_BRIDGE.md` for bridge protocol or lifecycle changes.
- Update `../../docs/TESTING.md` and the live checklist when gates change.
- Update `../../docs/PROJECT_STATUS.md` when feature/test counts or known gaps
  change.
- Maintain substantial work in `../../docs/tasks/active/` using the task
  template. Never claim an unrun test passed.
