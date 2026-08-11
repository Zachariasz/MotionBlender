# MotionBuilder Script Audit

Audit date: 2026-07-29  
Scope: 60 Python files (39 in `Scripts/custom`, 13 loose files in `Scripts`, and 8 files formerly in `PythonStartup`).

The following files are explicitly excluded and are not modified or managed:

- `Scripts/CustomSpineBonePicker.py`
- `PythonStartup/CustomSpineBonePickerWindowMenu_v1_1.py`

## Catalog mapping

Every in-scope physical file appears exactly once below. “Primary” is the file
invoked by the compatibility adapter. “Resident” files register startup
behavior. “Legacy launcher” files are retained in `Scripts` for recovery or
archived from `PythonStartup`; the manager does not execute them.

| Feature ID | Kind | Physical scripts and role |
|---|---|---|
| `objects.rename_selected` | command | `custom/RenameSelected.py` — primary |
| `objects.remove_selected` | command | `custom/RemoveSelectedComponent.py` — primary; repairs malformed old Script6 path |
| `transform.reset_translation` | command | `custom/ResetLocalTranslation.py` — tiny cached-bytecode command |
| `transform.reset_rotation` | command | `custom/ResetLocalRotation.py` — tiny cached-bytecode command |
| `transform.reset_scale` | command | `custom/ResetLocalScale.py` — tiny cached-bytecode command |
| `objects.set_namespace` | command | `custom/SetNamespace.py` — primary |
| `objects.remove_namespace` | command | `custom/RemoveNamespace.py` — primary |
| `objects.export_custom` | command | `custom/ExportCustom.py` — primary; explicit entrypoint because its old autorun condition is name-dependent |
| `fcurves.select_displayed_keys` | command | `custom/SelectFCurve.py` — primary |
| `fcurves.move_keys_right` | command | `custom/MoveKeysRight.py` — primary |
| `fcurves.move_keys_left` | command | `custom/MoveKeysLeft.py` — primary; legacy function is still named `shift_selected_keys_right` |
| `fcurves.move_values_up` | command | `custom/MoveKeysValueUp.py` — primary |
| `fcurves.move_values_down` | command | `custom/MoveKeysValueDown.py` — primary; legacy function is still named `move_selected_keys_value_up` |
| `fcurves.infinite_repetition` | command | `custom/SetSelectedFCurvesInfiniteRepetition.py` — primary |
| `story.bake_clips_to_takes` | command | `custom/BakeStoryClipsToTakes.py` — primary |
| `objects.duplicate` | command | `custom/Duplicate.py` — primary |
| `objects.hide` | command | `custom/HideSelectedObjects.py` — primary |
| `objects.unhide` | command | `custom/UnHideSelectedObjects.py` — primary |
| `objects.change_type` | command | `custom/ChangeSelectedObjectType.py` — primary |
| `transform.move_camera_plane` | command | `custom/MoveSelectedAlongCameraView.py` — primary |
| `transform.rotate_mouse_orbit` | command | `custom/RotateSelectedByMouseOrbit.py` — primary |
| `transform.precision` | tool | `custom/PrecisionTransformGizmo.py` — primary UI; `custom/PrecisionTransformShiftRMB.py` — resident input helper; `custom/PrecisionTransformHoldShift.py` — archived alternative implementation; `custom/PrecisionTransformShiftRMBHelper.py` — child helper |
| `transform.scale_mouse_distance` | command | `custom/ScaleSelectedByMouseDistance.py` — primary |
| `pose.paste_selected` | command | `custom/PasteSelectedPose.py` — primary |
| `pose.copy_selected` | command | `custom/CopySelectedPose.py` — primary |
| `objects.add_asset` | command | `custom/AddAssetDropdown.py` — primary |
| `fcurves.apply_filter` | command | `custom/ApplyFilterToSelectedFCurves.py` — primary |
| `ui.quick_favorites` | command | `custom/QuickFavoritesMenu.py` — primary |
| `objects.lock_camera` | command | `custom/LockCameraToSelected.py` — primary |
| `fcurves.tangents_menu` | command | `custom/SelectedKeyTangentsMenu.py` — primary |
| `animation.toggle_layer_mute` | command | `custom/ToggleCurrentAnimationLayerMute.py` — primary |
| `input.alt_wheel_preview_speed` | service | `custom/AltWheelPreviewSpeed.py` — primary service; `AltWheelPreviewSpeedStartup.py` — loose legacy launcher; `PythonStartup/AltWheelPreviewSpeedStartup.py` — archived duplicate launcher |
| `input.ctrl_wheel_frame_scrub` | service | `custom/CtrlWheelFrameScrub.py` — primary service; `CtrlWheelFrameScrubStartupLauncher.py` — loose legacy launcher; `PythonStartup/CtrlWheelFrameScrubStartupLauncher.py` — archived duplicate launcher |
| `input.block_alt_menu_focus` | service | `custom/BlockAltMenuFocus.py` — primary service; `BlockAltMenuFocusStartup.py` — loose legacy launcher; `PythonStartup/BlockAltMenuFocusStartup.py` — archived duplicate launcher |
| `scene.grid_axis_lines` | service | `CreateGridAxisLines.py` — grid implementation; `GridAxisLinesAutoStart.py` — primary service; `GridAxisLinesAutoStartLauncher.py` — loose legacy launcher; `PythonStartup/GridAxisLinesAutoStartLauncher.py` — archived duplicate launcher |
| `pickers.full_body` | tool | `CustomFullBodyBonePicker.py` — picker UI; `CustomFullBodyBonePickerWindowMenu.py` — resident menu/auto-open adapter; `CustomFullBodyPickerCharacterMenuWarmup.py` — resident warm-up; `PythonStartup/CustomFullBodyBonePickerWindowMenu.py` — archived duplicate; `PythonStartup/000_CustomFullBodyPickerCharacterMenuWarmup.py` — archived duplicate |
| `pickers.hand` | tool | `CustomHandBonePicker.py` — picker UI; `CustomHandBonePickerWindowMenu.py` — resident menu/auto-open adapter; `PythonStartup/CustomHandBonePickerWindowMenu.py` — archived duplicate |
| `developer.codex_bridge` | service | `CodexMotionBuilderBridge.py` — bridge service; `CodexMotionBuilderBridgeTool.py` — primary resident launcher; `PythonStartup/CodexMotionBuilderBridgeToolStartup.py` — archived launcher |
| `developer.camera_viewport_debug` | service, disabled by default | `custom/CameraViewportDebug.py` — diagnostic monitor; `custom/CameraViewportDebug.jsonl` is runtime output, not a script |
| `fcurves.key_reducing_precision` | service, disabled by default | `custom/KeyReducingPrecisionDefault.py` — service; `custom/KeyReducingGeneralTitleReference.png` and `custom/KeyReducingPrecisionInputHelper.vbs` are non-Python dependencies |

## Existing bindings preserved

Managed ActionScript slots are 1, 6, 10–15, 17–31, and 33–40. Their old
interaction-mode bindings are imported on first run, including unbound slots.
Slots 2–5, 7–9, 16, 32, and 41–99 remain unmanaged. This preserves the existing
IK/FK, effector, key-selected, take-navigation, mirror-pose, and other external
actions.

Each managed slot now points to a two-line wrapper under
`mobu_tools_manager/generated_actions`. The wrapper imports the already-cached
manager and dispatches a stable feature ID.

## Performance findings

- Native shortcuts previously read, parsed, compiled, and ran a complete Python
  file on every key press.
- FCurve commands repeatedly traverse `FBSystem().Scene.Components`, animation
  nodes, and layers even when the FCurve editor already exposes the displayed
  properties.
- Transform tools independently recalculate selection, camera, viewport, input
  state, overlays, and scene evaluation.
- The legacy tools install several Qt application event filters and multiple
  Win32 input hooks.
- Active polling intervals include 10–30 ms loops for interactive tools,
  100–250 ms diagnostic/bridge/picker loops, and a 1 ms selection/input loop in
  `PrecisionTransformHoldShift.py`.
- Startup launchers duplicated seven loose scripts byte-for-byte and could
  multiply callbacks on manual reload.

## Changes in this release

- A reload-safe manager singleton owns startup and lifecycle.
- Enabled resident features start once; disabling them removes known callbacks,
  timers, Qt filters, menu handlers, hooks, windows, and helper resources.
- Legacy source is read and compiled once per adapter. The first invocation
  preserves old top-level behavior; later invocations call the retained
  function. The three reset commands re-execute cached bytecode because they do
  not expose a reusable function.
- Idle warm-up compiles one enabled lazy command per `OnUIIdle` callback and
  removes the callback when the queue is empty. It never executes a command.
- Diagnostics stay in a bounded memory buffer until the user exports them.
- Shared selection, scene-index, displayed-FCurve, UI-context, input-routing,
  overlay, evaluation, and undo services are available for the next migration
  phases.

The legacy algorithms are intentionally unchanged. Their whole-scene scans and
polling remain until each feature is migrated to the native contract described
in `MOBU_TOOLS_MANAGER_GUIDE.md`.
