# Project Status

Snapshot date: **2026-08-27**

This file is a dated orientation aid. Code, the live catalog, and tests remain
the source of truth.

## Current implementation

- Primary package: `Scripts/mobu_tools_manager`.
- Active startup: `PythonStartup/000_MobuToolsManagerBootstrap.py`.
- Catalog: 67 features.
- Audited external/legacy/startup paths represented by the catalog: 67.
- Manager-native catalog features: 34.
- Package Python files excluding `__pycache__`: 120.
- Generated ActionScript wrappers within that count: 47.
- Non-generated package Python modules: 71.
- Offline `test_*.py` modules: 38.
- Active Codex Bridge: manager-native, on-demand, local file queue.
- Active Antigravity Bridge: manager-native, main-thread execution queue and viewport capture.

Current counts are asserted or derived from `catalog.py`, `test_catalog.py`, and
the package filesystem. Update this section when any of those change.

## Manager-native feature set

- `transform.move_camera_plane`
- `transform.rotate_mouse_orbit`
- `transform.precision`
- `transform.scale_mouse_distance`
- `fcurves.add_key`
- `objects.find_in_hierarchy`
- `ui.quick_favorites`
- `story.reset_selected_clips`
- `story.move_selected_clips_to_zero`
- `story.insert_current_take`
- `animation.render_side_front`
- `scene.export_fbx`
- `animation.timeline_go_to_next_take`
- `animation.timeline_go_to_previous_take`
- `animation.timeline_step_forward_10_frames`
- `animation.timeline_step_backward_10_frames`
- `animation.timeline_go_to_take_start`
- `animation.timeline_go_to_take_end`
- `animation.timeline_step_forward_fps`
- `animation.timeline_step_backward_fps`
- `animation.timeline_next_marker`
- `animation.timeline_previous_marker`
- `animation.timeline_add_local_marker`
- `input.timeline_navigation_hotkeys`
- `ui.save_options_templates`
- `input.alt_wheel_preview_speed`
- `input.character_keying_hotkeys`
- `animation.timeline_marker_labels`
- `selection.deselect_all`
- `viewer.toggle_global_local_reference`
- `viewer.display_mode_menu`
- `animation.playback_frame_mode_menu`
- `developer.codex_bridge`
- `developer.antigravity_bridge`

All other catalog features currently use the legacy compatibility adapter.

## Active architecture

- One reload-safe manager singleton.
- One manager application-exit callback.
- One runtime Qt application event filter.
- Shared selection, scene, FCurve, UI, evaluation, input, overlay, undo,
  interaction, graph-transform, and HIK services.
- Timeline Navigation Hotkeys uses the shared input router as the live shortcut
  path; its ActionScript wrappers remain catalog-compatible fallbacks.
- Viewer Reference Mode uses the shared input router for a Viewer-only `X`
  binding and sends the existing native F5/F6 shortcuts directly; it does not
  modify or rescan the active keyboard profile.
- Stable feature-ID dispatch through native or legacy adapters.
- The full-body picker's Window-menu, startup, and scene auto-open paths
  dispatch the legacy-backed `pickers.full_body` feature through the manager.
- Manager-owned Story and Viewer UI controllers.
- Per-user atomic settings and backed-up shortcut edits.
- Feature-row context actions with Run/Stop, Enable/Disable, Reload, and
  shortcut editing/reset; running state preserves the enabled preference.
- Trusted local file-queue bridge running payloads on the main UI thread.

## Documentation status

- Package README: current project overview.
- Root `docs/`: current routed documentation created for context continuity.
- `MOBU_TOOLS_MANAGER_GUIDE.md`: current detailed lifecycle reference.
- `MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md`: current normative interaction
  reference.
- `MOBU_SCRIPT_AUDIT.md`: historical 2026-07-29 migration inventory; its feature
  list and slot ranges do not describe all current native additions.
- Older `docs/PROJECT_MAP.md`: obsolete and superseded by
  `docs/PROJECT_STRUCTURE.md`.

## Known verification gaps

No dedicated focused offline behavior test currently covers:

- Quick Favorites popup/input lifecycle;
- Quick Favorites editor UI behavior;
- Save Options Templates UI/menu lifecycle;
- Story toolbar/context-menu controller lifecycle;
- full Story reset/alignment behavior;
- native TimeBar internal C++ marquee/range selection state (public SDK limitation in `selection.deselect_all`).

These areas require live checks and should receive focused tests when modified.

## Workspace state observed during this documentation pass

- The config directory was not a Git repository.
- A standalone `python` command was not available in the Codex shell. The
  bundled workspace CPython runtime is available for offline checks.
- On 2026-08-24, the focused Viewer Display Menu test passed (8 tests),
  including native-action declarations and hide-before-trigger ordering. The
  full offline suite completed with 4 failures and 30 errors: the sandbox has
  no writable temporary directory, and catalog/action-script inconsistencies
  plus unrelated existing test regressions remain. Live MotionBuilder checks
  were not run.
- On 2026-08-26, the focused full-body picker suite passed (12 tests), including
  RMB critical-path, coalesced slider-evaluation, and selection-fallback
  regressions. The full suite ran 288 tests with 4 failures and 31 errors; all
  picker tests passed. The remaining
  results reproduce unrelated catalog/input/FCurve regressions and sandbox
  temporary-directory failures. Live picker responsiveness was not run because
  MotionBuilder was not running and the Codex Bridge heartbeat was stale.
- On 2026-08-27, multi-layer mute toggling was implemented for
  `custom/ToggleCurrentAnimationLayerMute.py` (`animation.toggle_layer_mute`).
  The focused offline test suite `tests/test_toggle_animation_layer_mute.py`
  passed (7 tests) covering multi-selection, active-layer fallback, toggle states,
  and error handling. Live execution was verified on an active MotionBuilder
  2026 instance via the Antigravity Bridge with multiple selected animation
  layers.
- Local documentation links must be verified after all files are created.

Do not infer that code tests passed from this documentation pass.

## Next maintenance triggers

Update this status when:

- catalog/native feature counts change;
- generated wrapper or test-module counts change;
- the bridge protocol changes;
- a known test gap is closed;
- the workspace gains a canonical Git root or test interpreter;
- a long-form reference becomes historical or is replaced.
