# Object Transform and FCurve Interaction Migration Standard

Status: normative implementation and review specification  
Applies to: object Move/Rotate/Scale, native-gizmo precision, FCurve key
movement, tangent rotation, key/tangent scaling, and discrete FCurve nudges.

This document is normative. When a migrated tool disagrees with this document,
the shared interaction standard wins unless the standard itself is deliberately
revised for every tool.

## 1. Objective

Rebuild the existing transform and FCurve tools on one interaction framework so
they feel like three modes of the same tool rather than separate scripts.

The required result is:

- `G` starts Move in the context under the cursor.
- `R` starts Rotate in the context under the cursor.
- `S` starts Scale in the context under the cursor.
- Held **Shift** means precision in every interactive Move, Rotate, and Scale
  operation.
- Held **Ctrl** means snapping in every interactive operation.
- The same commit, cancel, axis, numeric-input, overlay, cursor, undo, and
  cleanup behavior is used everywhere.
- Viewport, Timeline, and FCurve behavior share infrastructure while keeping
  domain-appropriate math.

The precision modifier is a global interaction preference. Individual features
must not assign a different meaning to Shift.

## 2. Existing scripts covered

### Object and contextual transform tools

- `custom/MoveSelectedAlongCameraView.py`
- `custom/RotateSelectedByMouseOrbit.py`
- `custom/ScaleSelectedByMouseDistance.py`
- `custom/PrecisionTransformGizmo.py`
- `custom/PrecisionTransformShiftRMB.py`
- `custom/PrecisionTransformHoldShift.py`
- `custom/PrecisionTransformShiftRMBHelper.py`

The first three scripts already switch behavior according to the UI under the
cursor. They must remain the stable `G`, `R`, and `S` features while their
internal code is replaced.

### FCurve commands and tangent support

- `custom/MoveKeysRight.py`
- `custom/MoveKeysLeft.py`
- `custom/MoveKeysValueUp.py`
- `custom/MoveKeysValueDown.py`
- `custom/SelectFCurve.py`
- `custom/SelectedKeyTangentsMenu.py`
- `custom/SetSelectedFCurvesInfiniteRepetition.py`
- `custom/ApplyFilterToSelectedFCurves.py`

The selection, curve discovery, mutation, undo, and refresh code from these
commands must be consolidated into the same FCurve services used by interactive
`G`, `R`, and `S`.

## 3. Problems that must not survive the migration

- Viewport Move currently uses Ctrl as a 0.2× slow modifier and Shift as a 5×
  fast modifier, while Rotate and Scale use Shift as 0.1× precision.
- FCurve Move currently has no shared precision implementation.
- FCurve tangent Scale currently uses Shift for the right tangent and Ctrl for
  the left tangent, conflicting with precision and snapping.
- Rotate, Scale, and Move duplicate curve discovery, graph calibration,
  selection capture, cursor management, overlays, timers, mouse handling,
  numeric input, and cleanup.
- Several FCurve commands scan the complete scene instead of starting with
  properties displayed in the FCurve editor.
- FCurve Scale accepts stale `MarkedForManipulation` flags as selection while
  Move and Rotate correctly reject them.
- Each tool owns a 16 ms polling timer and a global Qt event filter.
- Graph screenshots, marker fitting, and axis-label analysis are duplicated and
  may run during interaction.
- Preview paths call `Scene.Evaluate()` or editor refresh functions more often
  than one event-loop update requires.
- Precision-mode changes can alter the result discontinuously when the
  calculation is still based on the original cursor anchor.

## 4. Global interaction policy

There is one manager-owned `InteractionPolicy` shared by all migrated tools.
The initial settings are:

```python
precision_modifier = "Shift"
precision_multiplier = 0.1
snap_modifier = "Control"
tangent_side_cycle_key = "T"
commit_buttons = ("LeftMouse", "Enter")
cancel_buttons = ("RightMouse", "Escape")
axis_keys = ("X", "Y", "Z")
```

These settings belong under the manager’s personal settings, not in feature
modules. Changing the precision modifier or multiplier changes every
interactive transform feature together.

### Reserved meanings

| Input | Meaning during every active interaction |
|---|---|
| Hold Shift | Precision, 0.1× response |
| Hold Ctrl | Snap to the operation’s configured increment |
| Shift + Ctrl | Precise response with snapping applied afterward |
| Left mouse or Enter | Commit |
| Right mouse or Escape | Cancel and restore |
| X, Y, Z | Axis constraint |
| Digits, decimal, minus, Backspace | Exact numeric input |
| T in an FCurve tangent operation | Cycle Both → Left → Right |

Shift must no longer mean “fast Move” or “right tangent.” Ctrl must no longer
mean “slow Move” or “left tangent.”

### Modifier transitions must not jump

Pressing or releasing Shift during a gesture must not change the current
preview value at the moment of transition.

Every strategy implements segmented rebasing:

1. Apply the current preview.
2. Save that preview as the new segment base.
3. Save the current cursor as the new segment anchor.
4. Change the segment sensitivity to 1.0 or 0.1.
5. Calculate later previews from the new base and anchor.

The same rule applies to object translation, object rotation, object scaling,
FCurve key movement, tangent rotation, and key/tangent scaling.

Ctrl snapping is a deliberate quantization transition. Pressing Ctrl must
immediately round the complete current operation result, including motion made
before Ctrl was pressed. Releasing Ctrl keeps the last snapped preview as the
new continuous base; it must not restore the earlier unsnapped value. Therefore
every modifier transition previews the exact event payload in the old mode,
rebases, changes the modifier state, and previews that same payload once in the
new mode.

Within one segment, targets are always calculated from the segment base rather
than compounded from the preceding tick. This prevents drift.

The input payload used for a continuous rebase is part of the contract. Before
changing a modifier or an FCurve tangent/scale constraint, preview the exact
payload cursor once with the old mode, then capture the resulting base and
cursor anchor, then enable the new mode. Rebasing an older preview against a
newer cursor loses motion even if the transition appears not to jump in a
simple test.

Viewer object-axis changes intentionally use a restart rather than a continuous
rebase. After validating X/Y/Z, advance the global/local/off constraint cycle
and set the segment anchor to the exact axis-key cursor. Move retains only the
existing displacement projected onto the newly active axis, Rotate retains only
the current angular twist about that axis, and Scale retains only the current
scale factor on that axis; all other components return to their operation-start
values. Cycling any transform to the unconstrained/off state restores all
components. This applies to the first axis lock, a different axis, and repeated
presses that change global/local/off state.

FCurve Move axis changes use the same restart principle. In the graph, X keeps
the current time displacement and restores every key value; Y keeps the current
value displacement and restores every key time. Repeating the active axis
unlocks it and restores both time and value to their operation-start values.
The next segment is anchored at the axis-key cursor. This applies only to
FCurve Move; FCurve tangent and scale constraints continue to rebase.

Scale must finish one bounded shared evaluation after writing its retained
local scale channel and before the session calls `begin_segment()`. MotionBuilder
can otherwise return the pre-reset free-scale values from the immediate SDK
reread, making the new segment restore all three preview channels. This is a
single axis-transition synchronization point, not permission to evaluate in a
mouse-move loop. Do not also queue a redundant deferred evaluation.

An unsupported constraint key, such as Z in the FCurve graph, is a true no-op:
it must not change the cursor anchor, segment base, numeric input, or preview
signature. A valid axis change must retain numeric input and reinterpret that
exact value under the new constraint. Axis changes must not silently clear the
number the animator typed.

### Calculation order

Every operation uses the same order:

1. Calculate raw mouse delta, angle, or factor.
2. Apply the current precision multiplier.
3. Apply the active axis or tangent-side constraint.
4. Apply Ctrl snapping.
5. If numeric input is active, replace the mouse result with the exact typed
   value.
6. Preview from the immutable session or segment base.

Numeric input is exact. Shift and Ctrl do not modify a typed value.

### Snapping quantizes the total operation

Snapping is measured from the immutable operation-start values, never only from
the latest segment base, the cursor distance travelled while Ctrl was held, or
the delta accumulated after an axis/modifier change.

- Free Move rounds each X/Y/Z component of the complete world-space
  displacement independently. It must work in the camera view plane with no
  axis lock. Do not snap only the vector magnitude.
- Axis-constrained Move rounds the complete signed distance along the active
  world/local axis and preserves displacement already established on the other
  components.
- Unconstrained Rotate rounds the complete accumulated orbit/trackball angle
  while preserving its rotation axis. Axis-constrained Rotate rounds the
  complete signed angle around the active axis.
- Unconstrained uniform Scale rounds the complete multiplicative factor.
  Constrained or non-uniform Scale rounds every enabled axis factor
  independently. Precision still applies to deviation from `1.0` before this
  rounding.
- FCurve Move rounds complete time/value displacement from the captured key
  values; tangent Rotate and key/tangent Scale round their complete angle or
  factor in the same way.

For example, with translation snap `1.0`, a free displacement of
`(2.37, -0.62, 0.18)` becomes `(2, -1, 0)` as soon as Ctrl is pressed. With
rotation snap `10`, `23.6` degrees becomes `20` degrees. With scale snap `0.1`,
a factor of `1.26` becomes `1.3`.

## 5. Shared interaction session

Implement one manager-owned `InteractionSession`. Feature modules provide a
strategy containing domain math; they do not create independent event filters,
hooks, modal loops, or repeating timers.

Suggested interface:

```python
class InteractionStrategy:
    def capture(self, context, invocation):
        """Return immutable original state and the first segment base."""

    def preview(self, session, input_state):
        """Calculate and apply a preview from the current segment base."""

    def rebase(self, session, input_state):
        """Make the current preview the next segment base without committing."""

    def commit(self, session):
        """Finalize one undoable operation."""

    def cancel(self, session):
        """Restore the exact original snapshot."""

    def status(self, session):
        """Return structured overlay information."""
```

The session state machine is:

```text
CREATED → ARMING → ACTIVE → COMMITTING → CLOSED
                         ↘ CANCELLING ↗
```

`ARMING` waits until keys and mouse buttons used to launch the tool are
released. Launcher modifiers do not leak into the interaction. This matters for
legacy bindings that contain Shift.

Only one interaction session may own input at a time. Starting another
transform cancels the previous uncommitted session before capturing new state.

### Atomic G/R/S mode handoff

`G`, `R`, and `S` are global transform-mode launchers even while another
transform session is active. They are handled by the manager-owned interaction
coordinator before strategy-specific key handling.

If the requested operation differs from the active operation, perform one
atomic **cancel-then-start** handoff:

1. Consume the non-auto-repeat launcher press so MotionBuilder does not also
   execute its native action.
2. Freeze the requested operation and reuse the active session's frozen domain
   and canonical surface. Moving the cursor outside that surface during a
   gesture must not accidentally switch the next operation to another editor.
3. Cancel the active session. Restore its immutable original snapshot; do not
   commit its preview.
4. Completely close its undo transaction and release input, overlay, cursor,
   HIK overrides, callbacks, and evaluation ownership.
5. Confirm that the coordinator has no active owner.
6. Dispatch the requested operation using a fresh target snapshot, but the same
   validated domain/surface.
7. For a resident shared-filter launch, activate the replacement immediately
   from the launcher press. Keep `ARMING` only for fallback launch paths that
   cannot consume the press synchronously.

Consuming a launcher press does not authorize consuming its matching release.
The replacement session must observe and queue the `G`, `R`, or `S` key-up so it
can complete any fallback `ARMING` state, but the shared Qt event filter must
return `False` for that same key-up. MotionBuilder must receive the release to
clear the keyboard state owned by its current interaction profile.

Examples:

- `G`, move, then `R` restores the pre-Move state and starts Rotate.
- `R`, rotate, then `S` restores the pre-Rotate state and starts Scale.
- `S`, scale, then `G` restores the pre-Scale state and starts Move.

At no point may both sessions own data or resources. The new strategy must not
capture until the old strategy's Cancel and cleanup have completed. If Cancel
or cleanup fails, do not start the requested operation; report the failure and
force coordinator cleanup.

Pressing the launcher for the already-active operation is consumed and never
creates a second session. G during Viewer Move, S during Viewer Scale, and all
same-operation FCurve launches are no-ops. R during Viewer Rotate is the one
documented mode cycle: restore the immutable rotation snapshot, clear any axis
constraint, anchor at the R-key cursor, and switch orbit/trackball mode inside
the same session. Rotation previewed before the second R must not survive.

If the frozen domain does not support the requested operation—for example R or
S during Timeline Move—the current operation is still canceled, no replacement
session starts, and the overlay/status reports that the requested mode is not
available in that domain. Never fall back silently to Viewer.

### Input and main-thread rule

- Use `context.input` as the only input router.
- One Qt event filter and, when still required, one native hook feed the router.
- When no interaction owns input, the resident shared filter handles
  no-modifier G/R/S before MotionBuilder defers the ActionScript callback. Use
  the last processed mouse event as the launch origin, consume the press only
  when a session starts, and enter `ACTIVE` immediately. Keep the ActionScript
  wrapper as a fallback when the resident route returns no session.
- Native callbacks enqueue primitive values only.
- All MotionBuilder API reads and writes occur on the main thread.
- Drain input once per event-loop turn.
- Do not run a nested `QEventLoop`.
- Do not use a private 16 ms timer in each feature.
- Launcher key-up is a shared observation event, not an exclusively owned
  event. Queue it for the session, then return `False` from the application
  event filter when its key matches the active session's `launcher_key`.
  This applies to initial launch, different-mode handoff, and repeated-launcher
  handling for G, R, and S.
- Do not use `GetAsyncKeyState` as proof that MotionBuilder received key-up.
  Windows can report the physical key as released while MotionBuilder's
  interaction profile remains latched because its Qt key-release event was
  swallowed.
- The router must prove that pointer movement is delivered while no mouse button
  is held in Viewer, FCurve, and Timeline surfaces. If a MotionBuilder widget
  does not emit hover `MouseMove`, enable mouse tracking at the shared boundary
  or use the manager-owned native input source. Do not add feature polling as a
  workaround.
- The router/session boundary catches every unexpected exception from capture,
  preview, status, commit, and input handling. It immediately takes the Cancel
  path, restores captured state, closes undo, and releases all resources.
  Exceptions must never escape a queued Qt callback while a session remains
  active.

The required router shape is:

```python
payload = translate_qt_event(event)
queue_for_session(payload)
if payload["type"] == "key_release":
    launcher_key = active_session.launcher_key
    released_key = payload.get("key")
    if (
        (launcher_key and released_key == launcher_key)
        or released_key in (
            "SHIFT",
            "CONTROL",
            "CTRL",
            "ALT",
            "META",
            "D",
            "G",
            "R",
            "S",
            "X",
            "Y",
            "Z",
        )
    ):
        return False  # observed by the session and delivered to MotionBuilder
return True           # exclusively owned in-session input
```

Do not call `event.accept()` on that launcher or modifier release. A common
failure signature is that session ownership, Qt grabs, native capture, and cursor
state all look clean after close, but no-modifier camera navigation remains
disabled or host modifier state remains latched until the user deactivates and
reactivates MotionBuilder. In that case verify launcher/modifier key pairing and
ensure chained/programmatic launches specify `activate_immediately=True` and
`launcher_key=None` before adding more mouse-capture cleanup.

### Shared UI resources

- Claim cursor ownership through the shared cursor/overlay coordinator.
- The coordinator applies the cached cursor to both the Qt application override
  and the canonical MotionBuilder surface when available. It verifies the
  active cursor, reasserts it if MotionBuilder resets it during the gesture, and
  records a diagnostic if neither path succeeds. Cursor failures are never
  silently swallowed.
- The coordinator owns one reusable, modeless overlay widget for all
  domain/operation combinations. Do not construct and destroy a new top-level
  widget for every G/R/S invocation.
- Cache cursor pixmaps and scaled cursor objects once. No icon file check,
  pixmap load, or scaling belongs on the interaction-start path.
- Cursor assets and the real system-cursor override are manager presentation
  behavior, not strategy behavior. A feature strategy returns only structured
  geometry such as `cursor_point`, `cursor_angle`, and an optional variant. It
  must not load a pixmap, create a `QCursor`, push an application override, or
  restore the Windows cursor. The shared mapping uses the four-arrow Move asset,
  the two-sided `custom/icons/2arrow.png` Scale asset, and the manager's
  Rotate variants.
- Viewer Rotate publishes the orbit presentation angle for the vertical
  two-arrow asset. Pass that value unchanged to `QPainter.rotate()`; do not
  negate it at the presentation boundary. Trackball keeps its unrotated
  four-arrow asset. Cursor geometry uses the y-down screen-space formula
  `atan2(dy, dx)`, while object orbit accumulation separately uses the
  mathematical formula `atan2(-dy, dx)`; never reuse one for the other.
- Both Rotate cursor variants are rendered at two-thirds of their previous
  size (a 1.5 divisor). Trackball retains its existing 0.725 size relative to
  the orbit variant before the shared divisor is applied.
- Before showing the reusable overlay for a new owner, clear its complete prior
  status, apply the new operation's cursor style, install the new owner's first
  complete status, and only then show and synchronously repaint it. On release,
  replace the status with an empty frame and synchronously repaint the
  translucent backing store before hiding. A queued `update()` followed by
  `hide()` is insufficient because Qt can remap the previous backing-store frame.
  Otherwise Scale's last dashed radial line or a previous operation's cursor can
  appear briefly during G/R/S handoff.
- Cursor identity must survive manager reloads: compare pixmap pixels, size, and
  hotspot when Qt cache keys differ. On manager startup and MotionBuilder
  `WindowActivate`, when no interaction owns the cursor, remove any explicit
  surface/application cursor matching a manager asset and repeat the check on
  the next event-loop turn after MotionBuilder has rebuilt its Viewer widgets.
  Never run this scrub while a transform session owns the cursor.
- Overlay text is structured from operation, context, constraint, modifier,
  numeric input, and current result.
- Axis colors are always X red, Y green, and Z blue.
- The overlay must explicitly display `PRECISION ×0.1`, `SNAP`, tangent side,
  and numeric input when active.
- The overlay is transparent for input, has no focus policy, shows without
  activating, and never changes the active MotionBuilder editor. Verify focus
  before show, during preview, and after close.

Every exit path restores the cursor and releases input, overlay, mouse capture,
callbacks, timers, and hooks.

### Terminal cleanup and immediate camera release

Ending a transform must make Viewer navigation available on the very next new
mouse gesture. LMB/Enter commits; RMB/Escape cancels. For mouse termination, the
manager consumes the terminal press/release pair belonging to the transform,
then releases ownership immediately after the release. It must not continue
swallowing later Viewer presses or movement.

Launcher pairing and terminal mouse pairing are different contracts:

- The launcher key press may be consumed.
- The launcher key release is queued for `ARMING` and passed through to
  MotionBuilder.
- The terminal LMB/RMB press and matching release are consumed by the transform
  to prevent selection changes or a context menu.
- Only the context-menu event generated by the same RMB cancel may be guarded
  after close.

The shared close sequence is mandatory for Commit, Cancel, G/R/S handoff,
exception, unsupported handoff, Disable, Reload, file open/new, take change,
surface destruction, and object destruction:

1. Commit the strategy or restore its immutable snapshot.
2. Commit or roll back the one undo transaction.
3. Release the input owner, callback, cancel callback, queued events, mouse
   capture, keyboard capture, and native hook ownership.
4. Clear all reusable overlay status, hide the overlay, and release accidental
   Qt grab/focus before cursor restoration processes Qt events.
5. Clear the interaction's complete application override stack, restore the
   canonical surface's previous cursor state, and force the native Windows arrow
   after the stack is empty. Recheck only transient Wait/Busy overrides on the
   immediate and short post-close event turns; do not leave a repeating timer.
6. Remove HIK/reach/pin overrides, close strategy resources, and cancel or flush
   only the evaluation work owned by the session.
7. Set the session to `CLOSED` and clear the coordinator's active owner.

After step 7, the shared event filter returns `False` for the next Viewer mouse
press/move/release so MotionBuilder can orbit, pan, or dolly normally. The short
RMB terminal guard may suppress only the context-menu event generated by the
same cancel click; it must not consume a later mouse press, mouse move, modifier,
or camera gesture. No repeating timer, delayed modal loop, cursor override,
overlay window, or stale callback may survive the close sequence.

## 6. Context routing

Resolve the target context and canonical editor surface once at dispatch through
`context.ui_context`. Freeze both for the lifetime of the session.

Priority:

1. Hovered FCurve graph.
2. Hovered Timeline/key strip.
3. Viewer/viewport.
4. Otherwise, abort without changing data and show a short status message.

The UI-context service, not `transform_move.py`, owns accessible-name matching,
ancestor/descendant lookup, geometry validation, and cache invalidation. A
feature entrypoint must not implement its own `_description`, `_matches`, or
`findChildren()` fallback. Do not walk `QApplication.allWidgets()` or a
top-level widget's descendants in a feature. Use the canonical cached
graph/timeline/viewer surface returned in the context snapshot.

| Context | G | R | S |
|---|---|---|---|
| Viewer | Move selected objects | Rotate selected objects | Scale selected objects |
| FCurve graph | Move selected keys in time/value | Rotate selected cubic tangents | Scale selected keys and tangent geometry |
| Timeline | Move selected keys in time | Not applicable | Not applicable |

If a context does not support an operation, do not silently fall back to the
Viewer.

## 7. Object transform standard

### Shared target capture

At session start:

- Get selection through `context.selection`; never call
  `FBGetSelectedModels()` every tick.
- Resolve transformable models once.
- Capture stable model identity, starting global/local TRS, parent transform,
  current camera, viewport rectangle, view axes, pivot, and relevant HIK state.
- Derive local axes from the evaluated global transform matrix (with normalized
  basis vectors and the required handedness handling), not by applying a fixed
  XYZ Euler formula to `model.Rotation`. Rotation order, pre/post rotation,
  constraints, and parent transforms make the Euler shortcut incorrect.
- Reacquire or cancel if a wrapper becomes invalid.
- If selection changes while active, keep the captured target set. Do not add
  newly selected objects mid-gesture.
- If a captured object is destroyed, cancel safely.
- Parent/child selections are order independent. Apply world-space targets in a
  hierarchy-safe order or compensate for selected ancestors. Selecting the same
  parent and child in the opposite selection order must produce the same final
  world transforms.

HIK effectors, pinned reach values, FK baselines, and constraint-sensitive
targets must use one shared target resolver. Do not keep Move-only copies of HIK
logic when Rotate or Scale need the same ownership and restoration guarantees.

The shared HIK resolver maintains an invalidation-driven effector/control-set
index. Do not brute-force every effector ID and effector-set ID separately for
every selected object on every invocation. FK membership may be indexed between
sessions, while mutable reach, pin, FK transform, keying-mode, and active-body-
part values are captured fresh at operation start. Preview work is limited to
the affected character controls; it must not enumerate the complete FK control
set on every mouse event.

### Manager-owned HIK manipulation contract

HIK behavior is manager policy, not Move-, Rotate-, or Scale-script policy.
Every Viewer transformation strategy must use:

```python
state = context.character_keying_state
hik = context.begin_character_manipulation(operation, snapshots)
```

`character_keying_state` is a read-only current snapshot for UI and
diagnostics. `begin_character_manipulation()` captures a frozen interaction
session containing:

- the current character and Control Rig;
- the current `FBCharacter.KeyingMode`;
- selection-derived and Character Controls active body parts;
- selected IK effectors, FK controls, and characterized skeleton bones;
- IK/FK/skeleton-to-character and body-part mappings;
- pin flags, Reach values, FK baselines, and required undo models.

Read this mutable state once at transformation capture. Do not read
`KeyingMode`, pins, or active body parts on every mouse event. The captured mode
does not change in the middle of a drag. A manager invalidation, character
replacement, take/file change, or destroyed control cancels the interaction;
the next G/R/S invocation captures the new state.

#### Required keying-mode semantics

| MotionBuilder keying mode | Manager manipulation scope |
|---|---|
| Full Body | Use the selected control as the driver and run the complete character solve. All character pins can participate. |
| Full Body No Pull | Use the Full Body solve while preserving the No Pull mode and every authored Pull value. |
| Body Part | Derive the body part from every selected IK, FK, or skeleton control. Solve and bake only those body parts. Pins outside the selected body parts do not participate. |
| Selection | Do not expand the target or run the shared full/body-part solve. Transform only explicitly selected controls, matching the native possibility of locally breaking or desynchronizing the rig. |

Selection-derived body parts take precedence over temporarily stale Character
Controls active-body-part flags. This is mandatory for selecting an FK forearm,
upper arm, thigh, or similar control immediately before launching G/R/S.

For Move in Full Body or Body Part mode, an FK or characterized skeleton
selection must never receive raw world translation that stretches or disconnects
the rig. The manager redirects the displacement to the anatomical driver
effector:

- arm -> wrist effector;
- leg -> ankle effector;
- hand -> hand effector;
- foot -> foot effector;
- chest -> chest-end/origin effector;
- head -> head effector;
- hips -> hips effector.

The same displacement is applied from the driver's captured start transform,
then the HIK result is resolved and baked back to the affected FK controls. For
example, G on an FK forearm in Body Part mode drives the wrist and solves the
whole arm; G on the same FK forearm in Selection mode changes only the selected
control and may break the rig like the native gizmo.

For Rotate, selected IK effectors are solved through IK Reach Rotation, selected
FK controls remain the rotation driver, and characterized skeleton selections
are redirected to their corresponding Control Rig FK control. Full Body and
Body Part determine the affected solve/bake scope; Selection remains selected-
control-only.

HIK pinning is immutable user state:

- read `IsTranslationPin()` and `IsRotationPin()` fresh at capture;
- never call `SetTranslationPin()` or `SetRotationPin()` as part of a transform;
- temporarily raise only the corresponding Reach properties required to honor
  selected drivers and applicable pins;
- never force `IK Pull` to 100;
- preserve Full Body No Pull and every authored Pull value;
- restore every temporary Reach value in `finally`, Cancel, Commit cleanup,
  G/R/S handoff, exception, reload, disable, and manager shutdown paths.

Scale is not an HIK Reach/pin solve. S keeps its explicit selected-control scale
semantics in every keying mode, but it must still create the shared HIK session
for classification, status, lifecycle cleanup, and synchronous character
deformation refresh. A transformation script must not invent "full-body scale"
by scaling all bones or effectors. A future character-scale feature requires a
separate, explicitly specified rig-scale policy.

#### Transformation-strategy integration

Move captures once:

```python
self.hik = context.begin_character_manipulation("move", self.snapshots)
```

Its preview builds complete `(snapshot, world_translation)` pairs. Apply raw
targets only where `self.hik.handles(snapshot)` is false, then call:

```python
evaluated = self.hik.apply_translation(pairs)
return False if evaluated else None
```

Rotate builds `(snapshot, target_matrix3, delta_matrix3)` tuples and follows the
same ownership rule:

```python
evaluated = self.hik.apply_rotation(rotation_targets)
return False if evaluated else None
```

Scale applies its selected-control targets, then calls:

```python
evaluated = self.hik.finish_direct_preview()
return False if evaluated else None
```

Returning `False` tells the interaction session that the HIK service already
performed synchronous evaluation. Do not also request a deferred evaluation for
that preview.

Every strategy must additionally:

1. Add `self.hik.undo_models` to `undo_models()`.
2. Restore its explicit selected snapshots on Cancel.
3. Call `self.hik.restore()` after restoring those snapshots.
4. Call `self.hik.close()` from `close()` on every exit path.
5. Append `self.hik.status_suffix` to Viewer status text so the frozen HIK mode
   and Body Part scope are visible during the interaction.

The manager performs one preliminary solve evaluation only when it must capture
changed FK controls, followed by `CandidateEvaluationAndResolve()`, one final
scene evaluation, and `EvaluateDeformations()`. Do not add a second strategy-
owned evaluation or deformation pass. Selection-only HIK manipulation and HIK
Scale use one scene-evaluation/deformation pass without
`CandidateEvaluationAndResolve()`, preserving Selection mode's intentionally
unsynchronized behavior.

Do not copy any of the following into a feature script:

- effector-ID or effector-set enumeration;
- FK model enumeration or body-part-name heuristics;
- `KeyingMode` or active-body-part branching;
- pin filtering;
- Reach or Pull overrides;
- FK baseline capture/bake;
- `CandidateEvaluationAndResolve()` or `EvaluateDeformations()` calls.

Those are exclusively owned by
`mobu_tools_manager.object_transforms.hik.HIKManipulationSession`.

### Move

- Unconstrained movement occurs in the captured camera view plane.
- X/Y/Z constrain to a world or local axis.
- Move, Rotate, and Scale must use the manager-owned `FrozenAxisGuide`; a
  strategy must not calculate or draw its own constraint line.
- The Viewer axis-lock guide samples an exact 1000-world-unit line, with 500
  units on each side of the pivot captured when that lock state is triggered,
  to determine its frozen screen direction and scale.
- Freeze both the world-space center and world-space direction for the complete
  lock state. Object movement, rotation, scaling, HIK evaluation, deformation,
  and overlay repainting must not move or rotate the displayed line.
- Entering another axis or another global/local state captures a new center and
  direction. Unlocking clears the capture, so triggering an axis again creates
  a new guide at the then-current position.
- The projected pivot is always the exact visual midpoint of the guide.
  Perspective can make equal world-space halves project to unequal pixel
  lengths, so use the shorter valid projected half for both screen halves.
- Reject a sample endpoint behind the camera instead of dividing its negative
  homogeneous W. If only one 500-unit endpoint is projectable, mirror that
  valid screen half around the projected pivot. If neither half defines a
  usable direction, hide the guide for that paint while retaining the frozen
  world-space capture. Never fall back to the old short projection sample.
- Axis cycling is consistent:
  `none → global axis → local axis → none`.
- All selected objects receive the same world-space displacement unless a
  future pivot mode explicitly defines another behavior.
- On each axis-state restart, Move retains only the current displacement
  projected onto the newly active axis and restores the perpendicular
  components. Unlocking restores all movement to the operation-start state.
- Numeric input is a signed scene-unit distance. With no constraint, use the
  last non-zero view-plane direction.
- Held Shift is 0.1× movement. Remove the old Shift 5× fast path.
- Held Ctrl uses the configured translation grid increment.
- Ctrl works both with and without an axis constraint. Free Move rounds each
  complete X/Y/Z displacement component; it never rounds only view-plane vector
  length or only movement made after Ctrl was pressed.

### Rotate

- Default Viewer mode preserves the current orbit/trackball behavior, but mode
  switching must be an explicit strategy option rather than a second
  controller.
- Pressing R during an active Viewer Rotate restores the captured original
  rotations before switching orbit/trackball mode. The new mode starts at the
  second R cursor and remains inside the same undo/input session.
- X/Y/Z use the same global/local/none axis cycle as Move and Scale.
- Every valid Viewer X/Y/Z press retains only the current angular twist about
  the newly active axis and restores the other rotation components. Unlocking
  restores the captured original rotation.
- X/Y/Z use the same frozen 1000-world-unit guide as Move; the line must not
  follow the rotating object or its changing local axes.
- Numeric input is signed degrees.
- Held Shift is 0.1× angular response.
- Held Ctrl snaps to the configured angular increment; initial default is
  10 degrees.
- Ctrl rounds the complete current angle immediately, including rotation made
  before Ctrl was pressed, in both constrained and unconstrained modes.
- Multi-object pivot behavior must be explicit. The compatibility default is
  individual object origins.

### Scale

- Mouse response is expressed around identity:
  `factor = 1 + deviation`.
- Precision applies to deviation, not the entire factor:
  `precise_factor = 1 + deviation × 0.1`.
- X/Y/Z use the same global/local/none axis cycle.
- X/Y/Z use the same frozen 1000-world-unit guide as Move and Rotate; legacy
  short axis samples are forbidden.
- Numeric input is an exact multiplicative factor; `1` means unchanged.
- Held Ctrl snaps the factor to the configured increment; initial default is
  0.1.
- Ctrl rounds the complete current factor immediately, including scaling made
  before Ctrl was pressed, in both constrained and unconstrained modes.
- The compatibility default scales each object around its own origin.
- Clamp only where MotionBuilder or project rules require it. The overlay must
  show when a clamp occurs.

### Native gizmo precision

The precision-transform feature must use the same policy:

- Shift is the only held precision modifier.
- Its effective response must match 0.1× across translation, rotation, and
  scaling.
- `PrecisionTransformHoldShift.py` and its 1 ms selection polling are retired.
- If MotionBuilder still requires the Shift-LMB-to-RMB compatibility helper,
  the manager’s single input router owns it.
- The helper starts and stops with the precision feature and cannot run while a
  custom interaction session owns the same mouse gesture.
- No helper process, hook, or service object survives Disable, Reload, or
  MotionBuilder shutdown.

## 8. FCurve discovery and view mapping

### Curve discovery

For graph operations:

1. Call `context.fcurves.displayed_properties()`.
2. Resolve their animation nodes for `context.animation_layer`.
3. Resolve the displayed FCurves for that layer.
4. Read selected-key flags fresh at session start.
5. Use whole-scene traversal only through the explicit lazy fallback and only
   when the operation is not tied to the displayed graph.

For vector properties, the displayed-property list alone is not precise
enough: resolve only the child animation nodes whose corresponding
``FBProperty.IsFocusedChild(index)`` is true. A selected key on a hidden X/Y/Z
sibling never brings that curve into an FCurve action. This is the shared scope
for interactive transforms, key-selection commands, extrapolation, tangents,
and filters. A vector filter may use its parent-node API only when every sibling
channel is in that visible scope; otherwise it must leave the partial group
unchanged.

Timeline discovery may use the scene index fallback, but it is performed once at
capture, not every tick.

Never use `MarkedForManipulation` as the selection source for a new operation.
It can remain set after the user changes the selection. Use
`KeyGetSelected(index)` or `Keys[index].Selected`.

### Shared graph transform

Create one `FCurveViewTransform` shared by G, R, and S. It maps:

- screen X ↔ time ticks/frames
- screen Y ↔ FCurve values
- derivative ↔ graph-space tangent angle
- tangent weight ↔ graph-space handle length

Resolution priority:

1. MotionBuilder FCurve editor APIs and displayed time span.
2. Stable Qt editor/view transforms when exposed.
3. One cached visual calibration fallback.

If visual calibration is unavoidable:

- Perform a cheap cache lookup before any `widget.grab()`, pixel copy, grid
  scan, OCR, or marker fit.
- Capture once when the graph generation changes, never once per invocation or
  tick.
- Share the result across G, R, and S.
- Key the cache by graph widget, geometry, DPI, time span, displayed-property
  signature, animation layer, and visible-range signature.
- Invalidate on zoom, pan, resize, DPI change, layer change, displayed-property
  change, or access error.
- When axis-label OCR yields several equally supported scales, prefer the
  hypothesis whose major-grid increment follows MotionBuilder's 1/2/5 decimal
  cadence. This prevents a consistent digit misread from changing mouse speed
  by an integer multiple; selected-key marker alignment remains the stronger
  discriminator when it is available.
- Match OCR labels by logical major-grid steps before fitting their values to
  physical image rows. Integer rasterization can alternate adjacent grid gaps
  between nearby pixel counts; do not treat one raw row-pair distance as the
  exact spacing or reject correct labels on later rows because of that drift.
- When equally supported hypotheses both fall inside the allowed 1/2/5 cadence
  tolerance and selected-key guide alignment cannot discriminate them, prefer
  the hypothesis closer to the exact cadence before comparing raw OCR mask
  scores. A small glyph-score advantage must not override materially stronger
  grid evidence.
- Detect strong selected-key horizontal guide rows independently of vertical
  guide detection and compare all selected value anchors with those rows.
  Multi-key horizontal alignment is stronger than cadence and OCR because
  different decimal scales can both follow the exact 1/2/5 sequence.
- For a multi-key selection that exposes only top and bottom horizontal bounds,
  derive value scale and origin directly from those rows and the captured
  minimum/maximum selected values, then validate the resulting major-grid
  increment against 1/2/5 cadence. Do not let OCR replace a valid bound-derived
  origin with an integer-offset label interpretation.
- Also clear the cache on file open/new, take change, manager reload, editor
  destruction, or SDK-wrapper error. Do not keep an unregistered module-global
  cache keyed only by `id(widget)`.
- Do not duplicate OCR, marker fitting, or screenshot logic in feature modules.
- Instrument the expensive path. Integration tests assert that `widget.grab()`
  is called at most once per graph generation across G, R, and S.

## 9. FCurve interaction standard

### FCurve Move (`G`)

- Capture selected keys from displayed curves.
- Preserve exact original time, value, selection, curve identity, and index
  recovery information.
- Unconstrained graph movement changes time and value.
- X constrains time; Y constrains value; repeated X/Y toggles the constraint
  off. On X, restore key values; on Y, restore key times; unlocking restores
  both time and value. Z is ignored.
- Timeline Move is permanently constrained to time.
- Numeric X/Timeline input is frames. Numeric Y input is value units.
- Without an axis constraint, numeric input defaults to time.
- Held Shift is 0.1× mouse response for both time and value.
- Graph time may be subframe during free movement. Held Ctrl snaps time to one
  frame and value to the configured value increment.
- The Timeline remains frame-domain; Shift increases the mouse travel needed
  per frame rather than creating subframe Timeline keys.
- When changing key time, update in direction-safe order and define collision
  behavior explicitly. Never rely on indexes remaining stable after mutation.
- The initial policy is **block without commit**: a target that overlaps an
  unselected key or another selected target is not applied, the overlay reports
  the collision, and LMB/Enter does not commit the previous last-valid preview
  as if it were the blocked target. The session remains active until the cursor
  returns to a valid target or the user cancels. Any future merge/overwrite
  policy must be a named global policy with equivalent G/nudge behavior.

### FCurve Rotate (`R`)

- Rotate the tangent angles of selected cubic keys.
- Non-cubic keys are skipped unless the user explicitly opts into conversion.
- Default tangent side is Both.
- Press T to cycle `Both → Left → Right → Both`.
- Held Shift is 0.1× angular response.
- Held Ctrl snaps to the configured angular increment; initial default is
  10 degrees.
- Numeric input is signed degrees.
- For an unbroken tangent in Both mode, preserve unified behavior.
- Editing only Left or Right intentionally breaks the tangent at the first
  actual change, not merely when the session starts.
- Capture tangent mode, break state, TCB values, derivatives, weight mode, and
  weights so Cancel restores the key exactly.

Repeated R during an active FCurve tangent session follows the global
same-launcher rule: consume it as a no-op and do not create a second controller.

### FCurve Scale (`S`)

Scale is performed around one captured pivot. The default is the median
graph-space position of selected keys (the median time and value coordinates,
with even selections centered between the two middle keys). Retiming must
retain the selected-key set throughout preview, commit, and cancel.

- Unconstrained Scale changes both selected-key distribution and corresponding
  tangent geometry.
- X scales key time spacing and horizontal tangent-handle weight.
- Y scales key value spacing and tangent slope/angle.
- T cycles tangent side Both/Left/Right.
- Tangent-side choice affects handles, not selected-key positions.
- Held Shift applies 0.1× deviation from identity.
- Held Ctrl snaps the factor to 0.1 by default.
- Numeric input is an exact factor.
- Weighted-tangent values must stay inside the valid MotionBuilder range, and
  the overlay must show clamping.
- MotionBuilder’s right-weight and previous-key `NextLeft` storage must be
  handled by one shared tangent-weight helper.

Scale must use only fresh selected-key state. Remove the current fallback that
accepts stale `MarkedForManipulation`.

If MotionBuilder invalidates a tangent wrapper after a valid selected-key
retime, position scaling must continue and preserve the existing tangent
geometry. A tangent-resolution failure must not cancel the key Scale session
or clear the selected-key set.

### Tangent side policy

Shift and Ctrl are unavailable for tangent-side choice because they are global
precision and snap modifiers.

Both FCurve Rotate and Scale use:

```text
T: Both → Left → Right → Both
```

The current side is always visible in the overlay. Side mode is session-local
and starts as Both unless a later manager preference is deliberately added for
all tangent tools.

### Quick Favorites launch boundary

`ui.quick_favorites` is a manager-native tool and may launch transform or
FCurve features only through their stable catalog IDs. It must not import a
transform implementation module, call a legacy script/function directly, or
bypass `InteractionManager.route_transform_launch()`. Manager dispatch remains
the authority that resolves enablement, interaction ownership, invocation
capture, and native-versus-legacy implementation.

Quick Favorites uses the runtime's existing UI classification and single Qt
application event filter. Opening from a key-down shortcut is deferred until
the physical launcher key is up, while the source editor still receives the
matching key-release. The popup must never use a nested `QEventLoop` or install
an additional application event filter.

Outside LMB, MMB, and RMB dismissal is an input transaction: consume the press,
keep the popup active until the same button releases, consume the release, then
close and restore editor focus. Closing on the press alone is forbidden because
it can leak a half MMB gesture into FCurves key-offset or Viewer camera state.
After any dismissal or favorite launch, the next native mouse gesture must work
without changing applications, pressing a recovery key, or releasing a hidden
capture.

Native `action.*` favorites use the manager-owned native-action dispatcher,
which sends a complete temporary key pair and restores the active keyboard map.
FCurves Add Key is not routed through that dispatcher. Its stable feature ID is
`fcurves.add_key`; it queries freshly selected FCurve properties and calls
`FBFCurve.KeyInsert()` inside the shared undo/evaluation policy. It must never
edit/rescan the keyboard profile or emit a synthetic key. Legacy saved
`action.fcurve.insert_key` favorites are migrated to this feature during
settings normalization.
The Quick Favorites feature must not edit keyboard files or retain recovery
objects in `builtins`. Its `close()` contract removes the shared-event observer,
stops pending release timers, closes the menu, and leaves no mouse/keyboard
grab, override cursor, focus override, or pending callback that can mutate an
interaction after reload.

The ordered Viewer, FCurves, and General lists are manager settings edited from
the manager UI. Python tools are represented by catalog feature IDs, never by
source paths or callable objects. This ensures any G/R/S favorite still passes
through the same interaction coordinator and cleanup gates defined here.

#### Host-crash escalation rule

An editor action that crashes only through Quick Favorites is unsafe at the
launch boundary until proven otherwise. After one failed rescan-free synthetic
dispatch attempt and a full host restart, synthetic-key experimentation ends.
Replace that action with a stable manager-native SDK command, migrate persisted
favorite targets, and verify fresh wrapper discovery, undo closure, coalesced
evaluation, no-op behavior, and immediate post-popup editor input.

Only one isolated live check is allowed after the direct-SDK fix. If the same
crash repeats, preserve diagnostics/CER evidence and stop implementation work;
do not vary timers, focus delays, modifier ordering, or key injection APIs
without new crash evidence. The detailed procedure is in the Quick Favorites
incident-response section of `MOBU_TOOLS_MANAGER_GUIDE.md`, and the lasting
decision is `docs/decisions/0003-popup-native-actions-require-manager-features.md`.

## 10. Discrete FCurve commands

`MoveKeysRight`, `MoveKeysLeft`, `MoveKeysValueUp`, and `MoveKeysValueDown`
become thin commands around one `FCurveMutationService.nudge()` implementation.

They must:

- use displayed curves first
- use the current animation layer
- read selected flags fresh
- batch changes per curve
- use one undo transaction
- request one coalesced refresh/evaluation
- never duplicate scene traversal

After shortcut migration, the steps are:

- Left/Right: one frame
- Up/Down: one value unit
- Held Shift with the new Left/Right nudge shortcut: 0.1 frame
- Held Shift with the new Up/Down nudge shortcut: 0.1 value unit

Launcher modifiers are consumed during `ARMING`. A shortcut that contains Shift
must not make an interaction begin in precision mode.

For an instant nudge command, precision cannot be inferred reliably when Shift
is also part of its launcher chord. The current Shift+Arrow bindings therefore
must be changed before the migrated commands are enabled. Their base shortcuts
must not contain Shift; holding Shift with the new base shortcut selects the
0.1× step. The manager should block or explicitly warn about a transform
feature’s launcher binding that conflicts with the global precision modifier.

Interactive `G` remains the preferred precision movement path.

## 11. Mutation, undo, and evaluation

### Immutable original snapshot

Every session captures an original snapshot once. Cancel restores that snapshot
even after:

- precision changes
- axis changes
- tangent-side changes
- snap changes
- numeric input
- several rebased segments

Do not treat the last preview as the cancel baseline.

### Undo

- Open one undo transaction after capture and before the first mutation.
- Register all affected models/properties/curve data once.
- Preview updates remain inside that logical transaction.
- Commit closes one undoable action.
- Cancel restores originals and closes without leaving a user-visible transform
  step.
- Partial exceptions take the Cancel path.
- Merely calling `TransactionEnd()` after restoring values does not demonstrate
  cancel behavior. Verify the MotionBuilder undo-stack count and label before
  and after cancel; use the SDK's rollback/undo sequence required to leave no
  transform entry.
- Every mutated FCurve must have a valid registered undo owner or an explicitly
  supported curve-data undo path. A Timeline fallback record with
  `property is None` cannot be silently omitted from undo registration.

### FCurve batches

- Group selected keys by FCurve.
- Resolve the current indexes for the complete selected-key batch with one
  curve scan per preview. Do not rescan every curve for every selected key or
  repeat that scan separately for time, value, and selection restoration.
- Use `KeyModifyBegin()` / `KeyModifyEnd()` in balanced pairs for each batch
  where supported.
- Never keep a modify block open across an event-loop turn.
- Protect every begin with `try/finally`.
- Re-resolve indexes from stable key identity/time information if a time edit
  can reorder keys.
- An identity startup preview must not open a key or tangent edit transaction.

### Refresh

- Use `context.evaluation.request()` rather than direct repeated
  `Scene.Evaluate()`.
- Coalesce editor repaint and scene evaluation once per event-loop turn.
- Viewer Scale axis restart may call the shared `flush_now()` once before its
  immediate segment-base reread; it must not call `Scene.Evaluate()` directly
  or flush during ordinary preview movement.
- Skip preview mutation and refresh when the effective target signature has not
  changed.

## 12. Proposed module boundaries

Do not rebuild the three large scripts as three new monoliths.

Suggested package layout:

```text
mobu_tools_manager/
  interactions/
    policy.py
    session.py
    input_state.py
    numeric_input.py
    constraints.py
    cursor_overlay.py
  object_transforms/
    targets.py
    hik.py
    move.py
    rotate.py
    scale.py
  fcurves/
    discovery.py
    selection.py
    view_transform.py
    snapshots.py
    tangents.py
    mutation.py
    move.py
    rotate_tangents.py
    scale.py
  features/
    transform_move.py
    transform_rotate.py
    transform_scale.py
```

Feature entrypoints remain small:

```python
def execute(context):
    return context.interactions.start(
        operation="move",
        surface=context.ui_context["surface"],
    )
```

The entrypoint selects a strategy and starts it. It contains no Qt widget
classification, descendant scan, transform math, FCurve discovery, HIK logic,
overlay construction, event filter, timer, or hook.

Shared implementation modules are manager infrastructure, not legacy physical
sources. Keep the catalog's audited `files` collection limited to the original
in-scope legacy files so the 60-file audit remains stable. Record the native
module and its shared implementation dependencies in separate catalog metadata
for Details, reload, and diagnostics.

## 13. Manager integration

Add one **Interaction Settings** section to the manager:

- Precision modifier: Shift
- Precision multiplier: 0.1
- Snap modifier: Ctrl
- Translation snap
- Rotation snap
- Scale snap
- FCurve value snap
- Tangent side cycle key
- Object pivot mode
- FCurve pivot mode

Precision modifier and multiplier are global. The UI must not offer per-feature
precision controls.

The manager prevents or warns about:

- a migrated transform launcher whose chord contains the precision modifier
- a launcher whose chord conflicts with an in-session axis/numeric/tangent key
- changing the global interaction policy while a session is active

Disable or reload immediately cancels an active session owned by that feature
and performs full cleanup.

Native reload is dependency aware. Reloading Move after editing
`object_transforms`, `fcurves`, or `interactions` must not retain the old helper
module from `sys.modules`. Either unload the declared native dependency graph in
safe leaf-to-root order or expose an explicit full-manager development reload.

Do not activate a new native catalog entry merely because its module imports and
offline stub tests pass. The legacy entry remains active until the relevant
MotionBuilder integration, equivalence, lifecycle, and performance gates pass.
Because modifier meanings are global, do not ship native G alongside an enabled
legacy context in R or S that still uses Shift/Ctrl for tangent-side selection
or another conflicting meaning. Develop strategies separately, but activate
the consistent G/R/S interaction family as one compatibility-gated release.

## 14. Migration sequence

1. Build `InteractionPolicy`, `InteractionSession`, shared input state, numeric
   input, constraint state, cursor, and overlay.
2. Build shared FCurve discovery, fresh selection, view transform, snapshots,
   tangent math, mutation, undo, and refresh.
3. Migrate FCurve Move from the current contextual `G` implementation.
4. Migrate FCurve tangent Rotate.
5. Migrate FCurve key/tangent Scale and replace Shift/Ctrl tangent-side logic
   with T cycling.
6. Migrate Viewer Move and remove Ctrl-slow/Shift-fast behavior.
7. Migrate Viewer Rotate.
8. Migrate Viewer Scale.
9. Move native-gizmo precision onto the shared Shift policy and retire 1 ms
   polling.
10. Rebuild the four discrete nudge commands on the shared mutation service.
11. Remove duplicated graph calibration, event filters, timers, cursor code,
    overlays, and input polling from legacy files.
12. Change catalog entries to native feature modules only after equivalence
    tests pass.

Migrate one strategy at a time, but do not ship mixed modifier meanings.
During the transition, either all enabled G/R/S strategies use this policy or
the not-yet-migrated conflicting strategy remains disabled.

## 15. Required tests

### Shared interaction tests

- A successful resident G/R/S launch consumes the press, becomes `ACTIVE`
  without waiting for release, and preserves movement from the last mouse event
  processed before the press. The ActionScript fallback may remain in `ARMING`.
  For the matching launcher key-up in either path, assert both that the session
  receives the queued payload and that the shared Qt event filter returns
  `False`.
- Run initial G/R/S launch, repeated launcher, and all different-mode handoffs
  with a real key down/up pair. Assert MotionBuilder receives every launcher
  key-up after the manager has claimed input.
- LMB and Enter commit; RMB and Escape cancel.
- Cancel after every possible state transition restores exact originals.
- Only one session can own input, cursor, and overlay.
- Starting a second tool cancels the first without leaking resources.
- Test all six different-mode handoffs: `G→R`, `G→S`, `R→G`, `R→S`, `S→G`,
  and `S→R`. Run them in both `ARMING` and `ACTIVE`, in Viewer and FCurve.
- Before the replacement strategy captures, assert that the canceled strategy
  restored its exact original values and released every owner/resource.
- Repeating G during Viewer Move or S during Viewer Scale is a consumed no-op.
  Repeating R during Viewer Rotate leaves the same session active but restores
  original rotations before cycling orbit/trackball mode. Same-operation
  FCurve launchers remain consumed no-ops; no repeated launcher captures a
  second session.
- For Viewer Move/Rotate/Scale, verify that the first axis lock, a different
  axis, and each global/local/off cycle restore exact operation-start values,
  anchor at the axis-key cursor, and only then begin the new constrained
  segment.
- Timeline `G→R` and `G→S` cancel Timeline Move and start no fallback Viewer
  operation.
- A canceled first operation contributes no undo entry. If the replacement is
  committed, the user sees exactly one undo entry for the replacement.
- After every terminal path, send a new Viewer camera mouse press and movement.
  The input router must return `False`, no transform preview may run, and the
  camera must respond immediately.
- The MotionBuilder integration gate must use a control-and-treatment test:
  first prove the selected native camera gesture changes the current camera,
  then run G/R/S, finish with LMB or RMB, and send the identical gesture without
  deactivating the application. Compare camera transforms before and after.
  Run both LMB accept and RMB cancel. Also assert cancel restores the target and
  the application stayed foreground throughout.
- Include a regression where the router has an active callback when launcher
  key-up arrives. The key-up must be queued while `handle_qt_event()` returns
  `False`; an empty router after close is not sufficient evidence.
- Verify that the application cursor and canonical surface cursor return to
  their exact pre-session states on Commit, Cancel, handoff, and exception.
- If handoff cancellation or cleanup raises, assert that the requested strategy
  never captures and that forced cleanup leaves no active owner.
- Disable, Reload, file open/new, take change, and object deletion cleanly end
  the session.
- Inject an exception from capture, preview, status, evaluation, commit, and
  cancel. Each case restores mutable data and leaves no active session, cursor,
  overlay, input owner, HIK override, or open undo transaction.
- Unsupported constraint keys are true no-ops. Valid constraint changes retain
  numeric input and use the exact event cursor: Viewer object transforms
  restart their segment, retaining only the newly selected-axis component:
  displacement for Move, angular twist for Rotate, and scale factor for Scale.
  FCurve transforms continuously rebase their current preview.

### Precision consistency

Run the same cursor path in normal and Shift modes.

- Move: precise displacement magnitude is 0.1× normal.
- Rotate: precise angle is 0.1× normal.
- Scale: `abs(precise_factor - 1)` is 0.1×
  `abs(normal_factor - 1)`.
- Apply those checks to Viewer Move/Rotate/Scale, FCurve key Move, tangent
  Rotate, key/tangent Scale, and the native-gizmo precision bridge.
- Press and release Shift at multiple points during each gesture. The preview
  must not jump at the transition.
- Shift+Ctrl must use the same precision multiplier before snapping.
- Press Ctrl after an unsnapped partial Move, Rotate, or Scale and verify that
  the current total result rounds immediately without further mouse movement.
- Viewer Move snapping must pass with no axis constraint: each total X/Y/Z
  displacement component is a multiple of the translation increment. It must
  not merely produce a vector whose length is a multiple of the increment.
- Releasing Ctrl preserves the last snapped result and subsequent unsnapped
  movement continues from it without a transition jump.

### FCurve correctness

- Only displayed/current-layer curves are affected in the graph.
- Selection is read fresh; stale `MarkedForManipulation` does nothing.
- Hidden curves and other layers remain unchanged.
- X/Y constraints, numeric input, frame/value snapping, and Timeline-only time
  movement are correct.
- Rightward and leftward time moves preserve all selected keys and use safe
  mutation order.
- Rotate and Scale test Both, Left, and Right tangent sides.
- Unified, broken, weighted, unweighted, TCB, first-key, and last-key cases
  commit and cancel correctly.
- Tangent weight `NextLeft` storage is updated correctly.
- One Undo restores the entire committed interaction.

### Object correctness

- Single and multiple object selections.
- Parent/child selections.
- Parent/child selections in both selection orders.
- Global and local X/Y/Z constraints.
- Perspective and orthographic cameras.
- HIK effectors, pinned controls, FK controls, and constrained models.
- Numeric Move/Rotate/Scale.
- Individual-origin compatibility pivot.
- Commit/cancel and selection/object deletion during interaction.
- Local-axis results on non-XYZ rotation orders, pre/post rotations, constrained
  models, rotated/scaled parents, and mirrored hierarchies.
- Full Body IK Move/Rotate with pins on the same and different body parts.
- Full Body No Pull without changing any `IK Pull` property.
- Body Part IK Move/Rotate with pins outside the active body part ignored.
- Body Part FK forearm Move driving and baking the complete arm rather than
  translating the FK forearm directly.
- Body Part characterized-skeleton Rotate redirecting to the matching FK
  Control Rig control.
- Selection-mode IK/FK/skeleton Move/Rotate affecting only explicit selection.
- Mode, pin, Reach, and active-body-part state frozen for the interaction and
  completely restored on Commit, Cancel, exception, and G/R/S handoff.
- Character deformation evaluated during preview without the temporary
  scrambled-skinned-mesh frame.

### Performance and ownership

- Warm start before capture stays within the manager dispatch target.
- No whole-scene FCurve scan in normal graph operations.
- No source reads or compilation after warm-up.
- No per-tick graph screenshot/OCR.
- No graph screenshot/OCR on a cache hit; one expensive calibration at most per
  invalidation generation shared by G/R/S.
- No per-invocation brute-force HIK effector-set scan for already indexed
  characters and no full FK enumeration per preview.
- No more than one coalesced evaluation and repaint per event-loop turn.
- No private repeating tool timer or application-wide event filter.
- Repeated sessions leave zero callbacks, filters, hooks, timers, cursors,
  overlays, undo transactions, or helper processes.
- Warm diagnostics separately report dispatch overhead, capture/start latency,
  preview p50/p95, commit/cancel latency, and total session duration. Returning
  immediately from `execute(context)` must not make an interactive feature look
  complete in timing diagnostics.

## 16. Completion criteria

This migration is complete only when:

- Shift produces the same 0.1× precision behavior in every interactive
  object/FCurve Move, Rotate, and Scale tool.
- Discrete key nudges are rebound away from Shift and use the same held Shift
  for 0.1× steps.
- Ctrl is snapping everywhere and has no slow-mode or tangent-side meaning.
- FCurve tangent sides use the same T cycle in Rotate and Scale.
- Modifier changes are continuous and produce no jumps.
- All sessions share input, overlay, cursor, undo, and evaluation ownership.
- G/R/S are mutually exclusive and use atomic cancel-then-start handoff for
  every different-mode switch.
- Every valid Viewer X/Y/Z press starts a new global/local/off constraint
  segment. Move retains only the preceding displacement on the newly active
  axis, Rotate its angular twist about that axis, and Scale its scale factor on
  that axis; switching any transform off restores the immutable start state.
- A second Viewer R restores original rotations before cycling orbit/trackball
  in the same session. Other same-operation launchers remain consumed no-ops.
- Every G/R/S launcher release is observed by the active session and passed
  through to MotionBuilder, and immediate native camera navigation works after
  both accept and cancel without changing application focus.
- Graph operations use displayed/current-layer curves and fresh key selection.
- Legacy behavior can be recovered, but no enabled migrated tool depends on its
  duplicated polling/event-filter implementation.
- The native catalog switch has passed MotionBuilder integration tests; offline
  Python stubs alone are not an activation gate.

## 17. First native Move rebuild review checklist

The first native Move pass established useful package boundaries, a manager
entrypoint, shared policy, event-driven session, fresh FCurve key selection,
direction-safe key mutation, and centralized input/overlay/undo objects. Keep
those decisions.

It is not accepted as production-ready until all of the following are true:

- `transform_move.py` is a router only and consumes a canonical surface from
  `context.ui_context`.
- Shift precision rebasing previews the exact transition cursor first; invalid
  axes do nothing; valid axes preserve numeric input.
- The shared input source is proven to deliver no-button mouse movement in all
  three MotionBuilder surfaces.
- The shared input source queues launcher key-up without consuming it, and a
  bridge-level Viewer test proves immediate camera movement after LMB and RMB.
- Preview/status/input exceptions are converted to a complete Cancel.
- Object destruction cancels a session before a stale wrapper is accessed.
- One reusable non-activating overlay and cached cursor asset are used.
- Local axes use evaluated matrices and parent/child results are selection-order
  independent.
- HIK lookup is indexed between sessions and preview touches only affected
  controls.
- FCurve calibration checks a manager-owned generation cache before screen
  capture and is invalidated with the runtime.
- Collision-blocked FCurve targets cannot commit the previous valid preview.
- Cancel leaves no undo-stack entry, and every edited curve has undo ownership.
- Feature reload includes shared native dependencies.
- The catalog audit still covers exactly the original 60 legacy/startup files;
  native implementation files are tracked separately.
- Native G is not enabled in a mixed-policy G/R/S installation.
- MotionBuilder integration and performance tests pass before the catalog points
  users at the native implementation.
