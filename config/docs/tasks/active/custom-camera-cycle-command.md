# Task: Custom camera cycle command

Status: blocked  
Last updated: 2026-08-11

## Goal

Provide a manager-native command that advances the Viewer to the next custom
scene camera without invoking MotionBuilder's native keyboard action.

## Acceptance criteria

- [x] The command skips Producer/native cameras and wraps to the first custom camera.
- [x] It uses the manager-owned Viewer label, Camera Switcher, and shared evaluation scheduler only.
- [ ] Focused offline coverage passes.
- [ ] One isolated live MotionBuilder switch is verified before any repeated or delayed sequence. **Blocked:** both direct-SDK detection paths selected the first custom camera.
- [ ] Catalog and status documentation are updated.

## Scope

Included:

- `viewer.cycle_custom_camera` manager-native command and its debug launcher.
- Catalog metadata, focused tests, and project status.

## Non-goals

- Retrying `action.viewer.camera.perspective` through keyboard mapping or synthetic input.
- Changing Quick Favorites or existing native actions.

## Starting state

- Direct camera switching through Camera Switcher can set a custom camera.
- Triggering `action.viewer.camera.perspective` through the native-action dispatcher froze MotionBuilder.
- Quick Favorites' FCurve Add Key is a manager feature (`fcurves.add_key`), not a native-action replay.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-11 | Implement one direct-SDK camera step first. | Synthetic native-action dispatch froze the host. | More key timing, rescan, or synthetic-input variations. |
| 2026-08-11 | Use the Viewer toolbar's active-camera label before falling back to Camera Switcher state. | The initial live check always selected the first custom camera, proving the switcher state was stale. | Retrying NumPad 0 or another synthetic-key route. |

## Progress

### Completed

- Inspected the Quick Favorites dispatch boundary and the native-action incident guidance.
- Added `viewer.cycle_custom_camera`, which selects the next custom
  `Scene.Cameras` entry, enables Camera Switcher in Viewer pane 0, and requests
  one shared evaluation.
- Added focused coverage for next, wrap-around, native-active, and no-custom
  camera cases.
- Replaced the debug launcher with one isolated dispatch of the new feature.
- The first live check always selected the first custom camera. The command now
  reads the active Viewer label from the manager-owned Viewer toolbar before it
  resolves the next custom scene camera.
- The Viewer-label follow-up also selected the first custom camera. Per the
  failed-check stop rule, no further camera-switch or synthetic-key variations
  will be attempted without new host evidence.

### Next action

1. Obtain new MotionBuilder evidence for the real active Viewer camera, such
   as an Autodesk-supported API, a native UI action identifier, or a host trace
   showing the state transition.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `docs/tasks/active/custom-camera-cycle-command.md` | Task handoff created. | Not applicable |
| `Scripts/mobu_tools_manager/viewer/camera_cycle.py` | Direct-SDK custom-camera cycling helper. | Focused test not run |
| `Scripts/mobu_tools_manager/features/camera_cycle.py` | Native command entrypoint. | Catalog test not run |
| `Scripts/mobu_tools_manager/viewer/toolbar.py` | Public active Viewer camera-label accessor. | Viewer test not run |
| `Scripts/mobu_tools_manager/catalog.py` | Added `viewer.cycle_custom_camera`. | Catalog test not run |
| `Scripts/tests/test_camera_cycle.py` | Focused camera-cycle coverage. | Not run; no local Python interpreter |
| `Scripts/DebugSceneCameraViewport.py` | One-shot isolated live launcher. | Live check pending |
| `Scripts/tests/test_catalog.py` | Catalog metadata assertion and feature count. | Not run; no local Python interpreter |
| `Scripts/mobu_tools_manager/README.md` | Native feature inventory/count update. | Reviewed |
| `docs/PROJECT_STATUS.md` | Current catalog/module/test counts and feature inventory. | File counts confirmed |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -m unittest discover -s tests -p "test_camera_cycle.py" -v` | Local Python | Not run | No `python` or `py` command is available |
| `python -m unittest discover -s tests -p "test_catalog.py" -v` | Local Python | Not run | No `python` or `py` command is available |
| First `DebugSceneCameraViewport.py` invocation | Isolated MotionBuilder scene | Failed | Always switched to first custom camera |
| One `DebugSceneCameraViewport.py` invocation after Viewer-label fix | Isolated MotionBuilder scene | Failed | Still selected the first custom camera |

## Blockers and open questions

- The exact native Perspective action behavior is not replicated; this command intentionally cycles custom scene cameras only.
- Both direct-SDK active-camera detection paths selected the first custom camera. Further implementation is blocked pending new host evidence; do not retry NumPad 0, native actions, direct pane-camera APIs, or further detection/timing variants.
