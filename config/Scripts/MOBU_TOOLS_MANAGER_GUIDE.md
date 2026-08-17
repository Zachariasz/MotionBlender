# MotionBuilder Tools Manager Guide

## Installation and startup

The manager code lives in:

`<UserConfigPath>/Scripts/mobu_tools_manager`

MotionBuilder starts it through the single file:

`<UserConfigPath>/PythonStartup/000_MobuToolsManagerBootstrap.py`

The bootstrap adds the sibling `Scripts` directory to `sys.path` and calls the
reload-safe bootstrap API. Re-running it shuts down the previous manager before
creating another, preventing duplicated callbacks, menu handlers, event
filters, timers, hooks, or helpers.

The manager registers exactly one `FBApplication.OnFileExit` callback.
MotionBuilder documents this event as occurring before application objects are
destroyed. The callback immediately cancels interactions, stops resident
features, removes SDK callbacks and Qt event filters, closes manager-owned
windows/overlays, restores cursors, stops timers/helpers, and processes only Qt
`DeferredDelete` events while Qt is still valid. Individual features must not
register another application-exit callback.

The previous eight in-scope startup loaders are moved to:

`<UserConfigPath>/MotionBuilderToolsManager/backups/<timestamp>/PythonStartup`

The excluded spine startup file remains in `PythonStartup`. Loose launcher
copies remain in `Scripts` as audited recovery sources.

Open the modeless manager from **Python Tools > MotionBuilder Tools Manager**.
The entry is a Qt menu action that opens the manager window directly; it does
not create a separate native MotionBuilder tool window.

## Recovery

Before migration, the installer backs up:

- `Scripts/ActionScript.txt`
- the active interaction-mode keyboard file
- all eight replaced startup loader files

To recover manually:

1. Exit MotionBuilder so no startup service is active.
2. Restore `ActionScript.txt` and the keyboard file from the timestamped backup.
3. Remove `000_MobuToolsManagerBootstrap.py`.
4. Move the eight archived startup loaders back into `PythonStartup`.
5. Start MotionBuilder again.

Do not overwrite `CustomSpineBonePicker.py` or
`CustomSpineBonePickerWindowMenu_v1_1.py`; neither belongs to this manager.

## Settings and profiles

Personal settings are stored at:

`FBSystem().UserConfigPath/MotionBuilderToolsManager/settings.json`

They contain enabled states and bindings keyed by interaction-mode name. On
first run the manager imports the effective state from the current
`ActionScript.txt` and active keyboard profile. Invalid JSON is copied to an
`.invalid-<timestamp>` recovery file and replaced with safe defaults. Writes
are atomic.

Feature code and the catalog can be shared; settings remain personal. Shortcut
changes affect only the interaction mode active when the edit is made.

## Managing features

The manager lists features under Transform, FCurves, Objects/Scene,
Animation/Story, Input/UI, Pickers, and Developer. Search includes the display
name, stable ID, category, and all represented physical files.

Available actions:

- **Run / Stop** dispatches an inactive feature or stops a running feature
  through the manager's normal cleanup path without changing its enabled state.
- **Enable / Disable** changes availability immediately.
- **Reload** stops owned resources, discards only that feature’s retained
  namespace, and reloads its cached code when required.
- **Edit Shortcut** accepts native MotionBuilder syntax and multiple bindings
  separated with `|`, for example `{CTRL:J*DN}|{CTRL:J*UP}`.
- **Reset Shortcut** restores the imported/default binding.
- **Export Diagnostics** writes timings and recent errors to JSON. No hot-path
  disk log is written automatically.

Feature operations are exposed from the feature row's right-click menu.
**Run** becomes **Stop** while the manager reports the feature as active;
stopping releases the feature's owned resources but leaves it enabled. The
same menu contains the current **Enable** or **Disable** action, **Reload**,
and the shortcut actions. Double-clicking an ActionScript-backed row opens the
shortcut editor. Category rows have no context menu. The manager window's lower
row is reserved for **Quick Favorites...** and **Export Diagnostics**.

Disabling a command removes its native binding but retains the saved preference
for re-enabling. Disabling a tool closes its UI. Disabling a resident service
removes its known callbacks, filters, timers, hooks, helper processes, and menu
resources. Dependencies are enabled first and dependent features are disabled
before their dependency.

## Shortcut implementation

Managed ActionScript slots point to tiny wrappers:

```python
from mobu_tools_manager import dispatch
dispatch("stable.feature_id")
```

These wrappers remain the fallback launch path. Manager-owned no-modifier
`G`, `R`, and `S` transforms launch synchronously from the resident shared Qt
event filter before MotionBuilder schedules the ActionScript wrapper. A
successful resident launch consumes the key press, records the last processed
mouse-event position as the transform origin, and enters `ACTIVE` immediately.
If the resident launch cannot start, the filter returns `False` and the normal
ActionScript binding remains available.

Unmanaged slots are preserved. The active keyboard profile is scanned across
every action, not only Python actions. Conflicts are blocked by default.
“Replace existing” explicitly removes the conflicting binding from its previous
action. Multiple bindings use MotionBuilder’s native `|` syntax and retain
`*DN` or `*UP`.

After successful changes the manager calls:

- `FBActionManager.RescanPythonShortcuts()` for ActionScript mapping changes.
- `FBActionManager.RescanCurrentInteractionModeShortcuts()` for keyboard
  changes.

The edited file is backed up first. If a rescan raises an error, the backup is
restored and the rescan is attempted again.

## Stable public manager API

```python
from mobu_tools_manager import (
    dispatch,
    show_manager,
    enable,
    disable,
    reload_feature,
)
```

Use stable feature IDs rather than paths. Wrappers and other integrations should
never import an implementation script directly.

## Catalog schema

Entries are `FeatureSpec` objects in `mobu_tools_manager/catalog.py` with:

- `id`: permanent machine-facing ID.
- `name`: UI name.
- `category`: manager grouping.
- `kind`: `command`, `tool`, `service`, or `auxiliary`.
- `files`: the original in-scope legacy, launcher, startup, and archived source
  files represented by the feature. Manager package implementation files do not
  go in this audited collection; its total remains exactly 60 for this release.
- `primary`: implementation loaded by the adapter.
- `module`: optional dotted import path for a manager-native implementation.
- `implementation_files`: required native-module and shared-helper dependency
  metadata for Details, diagnostics, and dependency-aware reload. Add this
  catalog field before activating a native feature; do not inflate `files` to
  approximate it.
- `entrypoint`: retained callable used after the first load.
- `stop_entrypoint`: optional callable for service shutdown.
- `resume_entrypoint`: optional nested callable used to resume a stopped legacy
  tool without rereading or recompiling its source.
- `dependencies`: other stable feature IDs.
- `action_slot`: stable native ActionScript slot or `None`.
- `default_enabled` and `default_shortcut`.
- `warmup`: `startup`, `idle`, or `never`.
- `context_requirements`: shared services needed by the future native version.
- compatibility fields for top-level autorun, cached-bytecode re-execution,
  resident files, and owned resources.

Run the offline catalog test after every catalog edit. IDs, slots, dependency
references, entrypoints, and physical-file coverage must remain valid. The audit
asserts 60 unique legacy/startup paths separately from native implementation
metadata.

## Native feature contract

New or migrated feature modules contain no autorun code.

Commands:

```python
def execute(context):
    ...
```

Tools:

```python
def show(context):
    ...

def close():
    ...
```

Services:

```python
def start(context):
    ...

def stop():
    ...

def status():
    return {"running": True}
```

The manager owns module lifetime and calls these functions. A feature may keep
immutable constants and pure-data caches, but it must not store lifecycle
objects in `builtins`, retain SDK/Qt wrappers outside runtime invalidation, or
keep a shared cache that manager reload and file/take/editor invalidation cannot
clear.

## Manager-owned Story UI integration

Story toolbar controls and Story context-menu actions are owned by the one
manager Story UI controller. They observe the runtime's existing Qt application
filter; an individual Story feature must not install another filter.

To extend MotionBuilder's native Story context menu:

1. Record a context-menu request only when its source is inside the validated
   Story pane. MotionBuilder's Story `KtOpenGL` canvas may emit a right-button
   release followed by `QMenu` Show without emitting `QContextMenuEvent`, so
   support both request paths through the shared observer.
2. Wait for the native `QMenu` Show event and add a short-lived `QAction`; do
   not replace the native popup.
3. Dispatch a stable feature ID from the action. The action must not import an
   implementation module directly.
4. If the command needs a contextual MotionBuilder key action, wait for that
   exact popup's `aboutToHide` signal, then use a manager-owned single-shot
   timer. Verify the pointer is still inside Story before dispatching the key.
5. Remove and delete the action and separator when the popup hides and during
   manager shutdown. Repeated popup use, manager reload, enable/disable, and
   Story UI rebuilds must never duplicate actions or retain old callbacks.

The controller may retain the currently visible popup and its owned actions
only until Hide or shutdown. It must not retain Story SDK wrappers between
commands. Compare rebuilt native Qt panes by their validated native object
pointer or reacquire them from a manager-owned child; Python wrapper identity
is not stable across MotionBuilder UI rebuilds.

## Manager-owned buttons beside native toolbars

Use `mobu_tools_manager/story/toolbar.py` as the canonical lifecycle pattern
and `mobu_tools_manager/viewer/toolbar.py` as the Viewer-row example. Native
MotionBuilder toolbar widgets are C++-owned and volatile. A row can remain
readable through PySide briefly after MotionBuilder has deleted the underlying
`QWidget`, or it can be rebuilt after manager startup. Therefore, a native row
is a discovery and geometry reference only. It is never an ownership parent.

### Required discovery and ownership pattern

1. Use the manager runtime's existing `QApplication` and shared Qt event
   observer. Do not create another application or install a feature-specific
   application event filter.
2. Locate the native row by an exact signature, preferably its accessible name
   plus the accessible names of its direct child controls. For the Viewer row,
   the validated MotionBuilder 2026 signature is `ButtonBarWithRightBar` with
   direct children `View`, `Display`, and `Renderer`.
3. Read the row, target control, and stable parent pane inside
   `try...except RuntimeError`. Validate every wrapper with the matching
   Shiboken `isValid()` implementation before access.
4. Copy all placement data into Python primitives: row `x`/`y`, target-control
   right edge and height, and stable-parent width. Do not return or cache the
   native row or native child control from discovery.
5. Create one manager-owned `QWidget` container as a child of the stable pane
   returned by `native_row.parentWidget()`. Put the `QToolButton` and its layout
   inside that container. Store the container and button on the manager-owned
   controller, not in `builtins` or the feature module.
6. Position the container from the primitive snapshot and clamp its right edge
   to the stable parent's width. To place a button after `Renderer`, use:

   ```python
   x_position = row_x + renderer_right + gap
   maximum_x = host_width - container.width() - margin
   container.move(min(x_position, maximum_x), renderer_y)
   ```

7. Connect the button to a controller method that dispatches a stable feature
   ID through the manager. The UI controller may gather safe UI context for the
   invocation, but it must not import and execute the implementation script
   directly.

The essential ownership shape is:

```python
host = native_row.parentWidget()       # stable pane
snapshot = {
    "x": int(native_row.geometry().x()),
    "y": int(native_row.geometry().y()) + int(target.geometry().y()),
    "target_right": int(target.geometry().right()) + 1,
    "target_height": int(target.geometry().height()),
    "host_width": int(host.width()),
}

container = QtWidgets.QWidget(host)    # manager-owned child
layout = QtWidgets.QHBoxLayout(container)
layout.setContentsMargins(0, 0, 0, 0)
button = QtWidgets.QToolButton(container)
layout.addWidget(button)
```

Do not replace `host` with `native_row`. Parenting the managed control directly
to the native row is unsafe because MotionBuilder can delete and recreate that
row independently of the manager.

### Refresh, rebuild, and cleanup lifecycle

- Schedule refresh through `QTimer.singleShot(0, ...)`, matching the Story
  controller, so widget creation and positioning stay on the main UI thread.
- If the manager starts before the native row exists, use an owned single-shot
  retry timer with a bounded attempt count. Stop it immediately after a valid
  row is found. After the bound is exhausted, rely on the shared Show,
  ChildAdded, LayoutRequest, Resize, FocusIn, and WindowActivate observations.
- When MotionBuilder rebuilds only the native row, keep the existing owned
  container on the stable pane and update its position from a fresh primitive
  snapshot.
- Reacquire the stable pane from `owned_container.parentWidget()` before using
  a cached pane wrapper. If the pane or owned container is invalid, discard the
  references and attach a new container to the newly discovered stable pane.
- Catch `RuntimeError` around native wrapper access and attachment. Detach the
  owned container and schedule a fresh discovery instead of continuing with a
  zombie wrapper.
- `stop()` must stop retry timers, unregister the shared-event observer, clear
  stored widget references, hide and detach the owned container, and call
  `deleteLater()`. Repeated refresh, reload, layout changes, and manager restart
  must never create duplicate buttons.

### Styling

Apply styling to the owned `QToolButton`, not to a native MotionBuilder widget.
Keep exact requested colors in one constant so tests can verify them. Example:

```python
BUTTON_STYLE = (
    "QToolButton {"
    " background-color: #5c5c5c;"
    " border: 1px solid transparent;"
    " }"
    " QToolButton:hover {"
    " border-color: palette(highlight);"
    " }"
)
button.setStyleSheet(BUTTON_STYLE)
```

### Required offline regression tests

At minimum, test all of the following with PySide fakes:

- manager startup before the native row exists, followed by successful retry
- exact native row/direct-child signature and placement after the target
- right-edge clamping inside the stable parent pane
- native row deletion and reconstruction while reusing the owned container
- stable pane deletion followed by attachment to the replacement pane
- repeated refresh without duplicate containers, buttons, or signal callbacks
- exact object names, text, tooltip, enabled state, and requested style values
- dispatch of the stable feature ID with the expected invocation context
- shutdown cleanup of the observer, timer, container, button references, and
  queued deletion

Run these offline before any live MotionBuilder check. A live UI verification
may inspect container parentage, visibility, and geometry on the main thread,
but it must not trigger the feature action (rendering, scene mutation, or other
crash-sensitive work) without explicit approval.

### Known failed approaches

Do not repeat these patterns:

- parenting a managed button directly to the native toolbar row
- retaining the native row or native target-control wrapper between refreshes
- performing only one immediate refresh during manager startup
- using the widest same-row descendant as the target edge; full-width native
  backing widgets can place the button beyond the pane and clip it completely
- using nested/per-frame `processEvents()` to force widget creation
- using an unbounded private polling timer instead of shared events plus bounded
  startup retries

## CommandContext

`CommandContext` lazily exposes:

- `system`, `application`, `player_control`, `action_manager`, and `scene`
- the MotionBuilder Qt application
- current take and current animation layer
- cached selection snapshot
- active and hovered UI classification
- displayed-FCurve service and scene index
- coalesced evaluation scheduler
- input router and overlay coordinator
- undo helper
- `character_keying_state` and
  `begin_character_manipulation(operation, snapshots)` for manager-owned HIK
  keying-mode, body-part, pin, Reach, solve, and deformation behavior

The runtime installs one filtered scene-change callback and one Qt application
event filter. File open/new, take changes, component destruction, and wrapper
access errors invalidate the relevant wrapper caches. The manager core has no
repeating idle timer.

## Quick Favorites integration

Quick Favorites is the native manager tool `ui.quick_favorites`. ActionScript
slot 37 and its default `Q` binding dispatch that stable ID. The legacy file
`custom/QuickFavoritesMenu.py` is now only a compatibility launcher; it must
not contain a second popup, context detector, keyboard-map editor, application
event filter, or `builtins` lifecycle state.

Configure entries from **MotionBuilder Tools Manager -> Quick Favorites...**.
The editor owns three ordered lists:

- **3D Viewer** when the manager UI context is `viewer`
- **FCurves** when the manager UI context is `fcurve`
- **General / Other** for every remaining surface

An entry is JSON-safe and has one of these forms:

```json
{"kind": "feature", "label": "Duplicate", "target": "objects.duplicate"}
{"kind": "native_action", "label": "Hide Gizmo", "target": "action.viewer.pick_mode_object"}
{"kind": "separator"}
```

`feature` targets are stable catalog IDs. To expose another Python script or
function, first register it as a managed feature with the appropriate native or
legacy adapter, then add that feature through the editor. Do not store source
paths, callable objects, implementation-module names, or ad-hoc `exec` targets
in Quick Favorites settings. This keeps renames, enable/disable, reload,
diagnostics, undo policy, and later native migrations under manager control.

`native_action` targets are MotionBuilder keyboard-map action names beginning
with `action.`. They are executed only by the manager-owned native-action
dispatcher. That service backs up the active keyboard profile, applies an
unused temporary function-key binding, rescans, sends a complete key-down and
key-up pair on a later host event-loop turn, and restores only its own binding.
A feature module must never reproduce that dispatch path.

FCurves **Add Key** is deliberately not a native-action favorite. It dispatches
the stable manager feature `fcurves.add_key`, queries the FCurve editor for
freshly selected properties, inserts at the current time through
`FBFCurve.KeyInsert()`, registers property owners in one undo transaction, and
requests one coalesced FCurve refresh. It never edits/rescans the keyboard map
or emits a synthetic key. Saved Quick Favorites entries that still target
`action.fcurve.insert_key` are normalized to `fcurves.add_key` when loaded.

The configuration is validated and atomically saved under the
`quick_favorites.contexts` object in the manager settings file. Invalid kinds,
empty labels/targets, recursive `ui.quick_favorites` entries, leading/trailing
separators, and unknown managed feature IDs are rejected or normalized by the
manager. Menu availability also reflects disabled/missing features and native
actions absent from the active keyboard map.

The popup follows the shared input and lifecycle rules:

- it snapshots the manager-owned hovered UI context before opening;
- it observes the manager's single Qt event filter and never installs its own;
- it waits for every launcher key to be physically released without consuming
  the editor's matching key-up;
- an outside LMB, MMB, or RMB dismiss is consumed as one complete press/release
  pair, so no half-gesture reaches Viewer or FCurves;
- it restores the source editor before dispatch and after a plain dismissal;
- it remembers the last selected entry separately per context; on the next
  opening that row is vertically centered under the cursor and the cursor sits
  at five-sixths of the menu width so it does not cover the label;
- `close()` removes observers, stops pending timers, closes the popup, and is
  called by manager reload, disable, and shutdown.

After changing this feature, run the settings, shortcut, catalog, and full
offline suites. The MotionBuilder integration gate must additionally cover all
three contexts, outside dismissal with LMB/MMB/RMB, repeated `Q` launches,
native action execution/restoration, focus recovery, and immediate Viewer
camera plus FCurve MMB interaction after the menu closes.

### Incident response: native action freezes or crashes from a popup

Treat a freeze/crash that occurs only when an editor action is launched from a
popup, deferred timer, or synthetic shortcut as an invocation-boundary failure.
Do not assume that the underlying editor operation is defective merely because
its normal keyboard shortcut works.

Use this sequence:

1. Reproduce once in an isolated scene and record the MotionBuilder version,
   editor context, stable feature/native action target, and whether the normal
   native shortcut works outside the popup.
2. Inspect the complete route: popup close/focus restoration, manager dispatch,
   keyboard-profile rescan, synthetic input, and persisted Quick Favorites
   settings. Changing a default does not change an existing saved entry.
3. Make one bounded mitigation that removes profile mutation/rescan. If the
   same host crash repeats after a full process restart, stop using synthetic
   input for that action; do not try more key timing, modifier, focus, or delay
   variations.
4. Add a stable manager-native feature that performs the supported SDK
   operation on MotionBuilder's main UI thread. Reacquire editor properties,
   curves, time, layer, and Qt wrappers at execution time. Use shared undo and
   coalesced evaluation, and guarantee transaction closure on every path.
5. Migrate persisted unsafe targets during settings normalization, remove any
   action-specific dispatcher exception, and keep compatibility launchers thin.
6. Test success, no-selection/no-op, existing-result/no-op, exception rollback,
   settings migration, and the absence of synthetic dispatch. Then run the
   focused catalog tests and full offline suite.
7. Fully exit and reopen MotionBuilder before the live test; manager or feature
   reload alone is insufficient when catalog/runtime modules changed. Exercise
   the command repeatedly, Undo once, and immediately use the editor's native
   mouse interactions to detect leaked focus or capture.

If the direct-SDK implementation crashes in the same situation after that one
live attempt, stop. Preserve the scene reproduction steps, manager diagnostics,
Python console output, Autodesk CER identifier/logs, and Windows crash-module
details before making another change.

Edits must be made in the active manager-owned source tree. A ZIP or copied
bundle may be supplied only as an optional transfer artifact; it is not a
substitute for updating the workspace when that workspace is the active
MotionBuilder configuration.

## Stable and volatile data

Safe to reuse until invalidated:

- selected object membership
- scene membership/name index
- current editor and hovered/active window classification
- camera/viewport discovery within an interaction session
- property-to-FCurve discovery
- HIK character/Control Rig topology and IK/FK/skeleton membership

Always refresh at operation start, and during an interactive tick where
applicable:

- transforms
- selected-key flags
- current time
- mutable key values
- mouse/key button state
- HIK keying mode, active body parts, pin flags, Reach/Pull values, and affected
  FK baselines; freeze these for that interaction rather than polling them every
  mouse tick

Never retain an SDK wrapper after file open/new, take replacement, object
destruction, or an access error without reacquiring it through the context.

## FCurve migration recipe

1. Implement `execute(context)` with no top-level call.
2. Start from the FCurve editor's freshly selected/visible properties. Do not
   scan the scene merely to discover what the editor displays.
3. For a vector property, resolve only child animation nodes whose
   `IsFocusedChild(index)` state is true; do not recursively expand all X/Y/Z
   siblings. A hidden curve with selected keys is never an action target.
4. Resolve FCurves for `context.animation_layer`.
5. Enumerate selected-key flags fresh immediately before editing.
6. Build the complete edit plan before mutation.
7. Apply edits in one undo scope and batch any evaluation request through
   `context.evaluation.request()`.
8. Use `whole_scene_fcurves()` only as an explicit lazy fallback when displayed
   properties cannot represent the requested operation.
9. Export only `execute(context)`, then pass the MotionBuilder integration,
   equivalence, lifecycle, and performance gates before changing the active
   catalog implementation from legacy to native. Offline stub tests alone do
   not authorize the switch.

## Transform migration recipe

The normative interaction, first-rebuild review checklist, and modifier
specification is in
`MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md`. It defines the shared Shift
precision mode, Ctrl snapping, tangent-side handling, session lifecycle, and
acceptance tests for both Viewer and FCurve G/R/S tools.

For Viewer transformations the public character interfaces are:

```python
context.character_keying_state
context.begin_character_manipulation(operation, snapshots)
```

The returned HIK session owns keying-mode scope, IK/FK/skeleton classification,
Body Part expansion, pin participation, temporary Reach restoration, affected
FK baselines, character evaluation/deformation, and HIK undo models. Full Body,
Full Body No Pull, Body Part, and Selection behavior must never be reimplemented
inside an individual transformation feature. See **Manager-owned HIK
manipulation contract** in the migration standard for the exact Move, Rotate,
Scale, pin, cleanup, and acceptance rules.

All Viewer G/R/S strategies use
`mobu_tools_manager.object_transforms.targets.FrozenAxisGuide`. It captures the
pivot and world direction after an X/Y/Z restart, draws exactly 1000 world
units, and does not follow transformed objects or changing local axes. Move
keeps only the displacement along the newly active axis, Rotate its twist about
that axis, and Scale its factor on that axis before recapturing. Unlocking any
transform restores its original state and clears the capture. The projected
guide must remain balanced around the pivot, including when perspective puts one
sampled endpoint behind the camera. Feature modules must not implement a private
or short constraint line.

1. Create one interaction-session object per invocation.
2. Snapshot selection, camera, viewport, and start transforms once.
3. Subscribe through the shared input router; native hook callbacks may enqueue
   primitive numbers/flags only.
4. Do all MotionBuilder SDK work on the main thread.
5. Claim the manager-owned reusable overlay and cached cursor asset, and request
   coalesced scene evaluation.
6. Refresh mutable transforms/button state per interaction tick.
7. On commit, close the undo transaction and release input/overlay ownership.
8. On cancel, restore starting values.
9. In every exit path, unregister callbacks, restore the cursor, release mouse
   capture/hooks, hide the overlay, and clear the session.
10. Keep the legacy catalog entry active until MotionBuilder tests pass and all
    enabled G/R/S contexts use the same Shift-precision/Ctrl-snap meanings.
11. Treat G/R/S as manager-level mutually exclusive modes. Pressing a different
    launcher during an interaction atomically cancels and fully cleans the
    current session, restores its original state, then starts the requested
    operation on the same frozen domain/surface with a fresh target snapshot.
    The replacement cannot capture until the previous session has no remaining
    input, cursor, overlay, undo, HIK, callback, or evaluation ownership.
12. Repeating G during Viewer Move, S during Viewer Scale, or an active FCurve
    operation is a consumed no-op and never creates a second session. R during
    Viewer Rotate is the sole same-launcher exception: restore the immutable
    original rotations, clear the axis constraint, anchor at the R-key cursor,
    and toggle orbit/trackball mode inside the existing undo/input/presentation
    session. An unsupported switch, such as Timeline G to R/S, cancels the
    current session and starts nothing; it never falls back to Viewer.
13. Treat every valid Viewer X/Y/Z key as a non-terminal restart, not a
    continuous rebase. Retain typed numeric input and anchor the next segment
    at the exact key cursor. Move retains only the prior displacement on the
    newly active axis, Rotate only its twist about that axis, and Scale only its
    factor on that axis; all other components return to operation-start values.
    Cycling any transform to off restores every component. Apply this to the
    first lock, a different axis, and every global/local/off cycle. FCurve
    constraints and Shift/Ctrl modifier transitions remain continuous rebases.
    Scale must flush the shared evaluation service once after its local-channel
    reset and before `begin_segment()` rereads scale; otherwise MotionBuilder
    can return and reapply the stale free-scale preview. This exception is
    axis-transition-only and never belongs in the mouse-move preview loop.
14. Treat a transform launcher's press and release asymmetrically. The resident
    shared filter starts a no-modifier G/R/S transform directly from key press,
    consumes that press only after a session starts, and activates the session
    immediately. The ActionScript wrapper is a fallback and may still use
    `ARMING`. In both paths, the
    matching `G`, `R`, or `S` key release must be both queued to the active
    session and passed through to MotionBuilder by returning `False` from the
    shared event filter. A fallback session may use that queued release to leave
    `ARMING`; MotionBuilder always uses it to clear its internal keyboard state.
    Never infer that the host saw key-up merely because `GetAsyncKeyState`
    reports the key as up. Swallowing launcher or modifier key-up can disable
    no-modifier Viewer camera gestures or latch host modifier states until
    MotionBuilder is deactivated and reactivated.
    Consequently, `KeyRelease` events for modifier keys (`Shift`, `Control`,
    `Alt`, `Meta`), launcher keys (`D`, `G`, `R`, `S`), and axis constraint
    keys (`X`, `Y`, `Z`) must always pass through (`return False`).
    Programmatic or compound shortcut launches (such as `Shift+D` duplicate
    into move) must specify `activate_immediately=True` and `launcher_key=None`
    to enter `ACTIVE` state without stalling in `ARMING`.
15. A terminal transform consumes only its own final click/key sequence. After
    close, the next Viewer mouse press/move/release must pass through the shared
    event filter to MotionBuilder so camera orbit, pan, and dolly work
    immediately. Replace the reusable overlay with an empty transparent frame,
    synchronously repaint it, and then hide it before restoring cursors; a queued
    update can leave stale dashed lines or cursor art in Qt's backing store.
    A replacement tool installs its own complete first status before showing the
    overlay. Then clear the application override stack, restore the canonical
    surface cursor, force the native Windows arrow, clear queued input/callback
    ownership, release Qt/native grabs, close HIK resources, and restore editor
    focus on every Commit, Cancel, handoff, exception, Disable, Reload, or
    invalidation. Cursor pixmaps and system-cursor handling belong to the manager
    presentation layer; feature strategies provide only cursor geometry and
    variants.
16. Ctrl snapping quantizes the complete operation result from its captured
    start values, including work done before Ctrl was pressed. It is not
    segment-relative. Viewer Move must also snap with no axis lock by rounding
    each complete X/Y/Z displacement component independently; never snap only
    the free-move vector length. Rotate rounds its complete angle and Scale its
    complete factor. Pressing Ctrl updates immediately without requiring more
    mouse movement; releasing it keeps the snapped result as the continuous
    base.

## Resident-service recipe

- `start(context)` must be idempotent.
- `stop()` must completely reverse `start()`, even after partial failure.
- Store callback objects so the exact same object can be removed.
- Prefer file/scene/UI events over idle polling.
- Stop timers when no interaction or monitoring needs them.
- Never touch MotionBuilder API objects from worker threads or native hook
  callbacks.
- If a child helper is used, record ownership and terminate it in `stop()`.
- Repeated enable/disable and manager reload must leave zero orphaned resources.
- `stop()` must be safe when called from the manager's early
  `FBApplication.OnFileExit` shutdown. Do not depend on Python or Qt wrapper
  finalizers running after MotionBuilder begins destroying its UI.
- Parentless widgets and QObject services must be queued for deletion before
  `stop()` returns. The manager, not an individual feature, flushes Qt
  `DeferredDelete` events after every owned feature and runtime service stops.

## Prohibited patterns

Migrated modules must not:

- execute at import time
- edit `ActionScript.txt` or keyboard files directly
- create a new `QApplication`
- install unmanaged global Qt event filters
- register a private `FBApplication.OnFileExit` handler
- store persistent lifecycle state in `builtins`
- parent manager-owned controls directly to native MotionBuilder toolbar rows
- retain native toolbar/control wrappers after copying their primitive geometry
- add a callback, timer, native hook, monkey patch, or helper without a matching
  removal path
- use unbounded UI-discovery polling or nested `processEvents()`
- perform routine whole-scene FCurve scans

## Migration order

1. FCurve selection, move, value, filter, tangent, and extrapolation commands.
2. Move/rotate/scale, precision transform, wheel, popup, input, and overlay
   tools.
3. Object/scene commands and pose tools.
4. Pickers, grid, bridge, and developer utilities.

## Verification

Offline:

```text
python -m unittest discover -s tests -v
```

Inside MotionBuilder, follow `tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`.
Measure warm dispatch before feature logic separately from legacy feature
execution. Targets are below 2 ms median and below 5 ms p95, no source read or
compilation after warm-up, one compile per idle callback, and zero manager
repeating timers.

For every manager-owned G/R/S interaction, perform a real Viewer input
regression, not only an offline event-filter test:

1. Verify a baseline native camera gesture changes the current camera.
2. Send the launcher key down and move immediately. Assert a successful
   resident launch consumes the press, enters `ACTIVE` without waiting for
   key-up, and uses the last mouse event processed before the press as its
   origin. Then assert the session observes key-up while the shared event filter
   returns `False` for it.
3. Move the target, finish once with LMB and once with RMB, then immediately
   repeat the same native camera gesture without changing application focus.
4. Assert the camera changes in both cases, RMB restores the target, and no
   input callback, queued event, cursor, overlay, grab, or session owner remains.

If camera movement works only after switching away from and back to
MotionBuilder, first check whether the launcher key-up was swallowed. Empty
manager ownership and `GetAsyncKeyState == up` do not prove that MotionBuilder's
internal interaction profile received the release.
