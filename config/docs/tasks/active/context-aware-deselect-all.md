# Task: Context-Aware Deselect All & Timeline Deselection Limitations

Status: active  
Last updated: 2026-08-27  
Feature: `selection.deselect_all` (ActionScript slot 54, Shortcut `{NONE:A*DN}`)

## Goal

Provide a robust, cursor-isolated "Deselect All" (`A`) behavior across MotionBuilder editor contexts (3D Viewport, FCurve Editor, Timeline, Navigator) while preventing global whole-scene deselection and avoiding severe FCurve performance degradation.

---

## What Is Wrong With Timeline Deselection & Known SDK Limitations

### 1. The Core Issue
In MotionBuilder, deselecting animation keys while the cursor is over the **Timeline** does not work in an isolated, pure timeline manner because MotionBuilder's C++ UI architecture couples Timeline key displays directly to the **FCurves tab property channel selection**.

### 2. Technical Causes

1. **Private C++ Drawing Routines for Timeline Tracks**:
   - The native Timeline control (`Transport Controls` / `TimeBar` / `Action`) renders key tick indicators based on internal C++ state.
   - `pyfbsdk` provides no SDK class or method to query, inspect, or clear the native Timeline's internal key-selection marquee or active track selection.
2. **Coupling with FCurves Channel Focus**:
   - Key ticks appearing in the timeline are directly projected from whichever property channels (e.g. `Lcl Translation`, `Lcl Rotation`) are currently focused (`IsFocused() == True` or `IsFocusedChild() == True`) in the FCurves tree view.
   - Even when every `FBFCurveKey` object has `Selected = False` set in the SDK, the native Timeline control continues to render active key indicators as long as the parent property remains focused in the FCurves tree.
3. **The Only Way to Clear Timeline Keys Is Whole FCurve Deselection**:
   - To truly clear the key ticks from the Timeline, the script must explicitly unfocus and deselect the entire FCurve from the FCurves tab using `FBProperty.SetFocus(False)` and `FBFCurve.Selected = False`.
4. **Re-Focus on Viewport Interaction**:
   - When 3D models or character bones remain selected in the 3D Viewport, MotionBuilder's native selection listener automatically re-focuses the model's primary transformation channels upon any subsequent viewport interaction or navigation, causing the key indicators to reappear.

---

## Acceptance Criteria

- [x] Cursor-aware context resolution distinguishes `viewer`, `fcurve`, `timeline`, and `navigator`.
- [x] Application-level global deselect (`action.global.deselect`) removed to prevent whole-scene wipes.
- [x] FCurve key deselection optimized using C++ index scanning and `EditBegin()` / `EditEnd()` batching (reduced execution time from >600ms to ~78ms on 274,000 keys).
- [x] Timeline context deselects whole FCurves and unfocuses FCurve tab properties while keeping 3D bones selected.
- [x] Offline unit tests pass across all contexts (`tests/test_deselect_all.py`).
- [x] Documentation updated detailing timeline deselection behavior and SDK constraints.

---

## Scope

Included:
- `mobu_tools_manager/features/deselect_all.py`
- `mobu_tools_manager/catalog.py`
- `tests/test_deselect_all.py`
- `mobu_tools_manager/README.md`
- `docs/PROJECT_STATUS.md`

Non-goals:
- Hooking private unexported C++ Qt paint events on the native TimeBar widget.

---

## Important Files

| File | Why it matters |
| --- | --- |
| `mobu_tools_manager/features/deselect_all.py` | Context resolution and per-domain deselection execution. |
| `mobu_tools_manager/catalog.py` | Registration of `selection.deselect_all` as resident service on slot 54. |
| `tests/test_deselect_all.py` | 14 isolated unit tests covering all contexts. |
| `mobu_tools_manager/README.md` | Feature reference and timeline limitation documentation. |

---

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-27 | Remove `_dispatch_native_deselect` | Calling `action.global.deselect` caused global whole-scene deselect across all domains simultaneously. | Dispatching native action before domain logic. |
| 2026-08-27 | Default fallback to `"viewer"` | Unknown or ambiguous contexts should only deselect 3D models, never wiping all 4 domains. | Default fallback to `"all"`. |
| 2026-08-27 | Index-first C++ key scanning with `EditBegin`/`EditEnd` | Eliminates pure Python wrapper allocation over dense curves (560ms -> 39ms). | Iterating `[k for k in curve.Keys]`. |
| 2026-08-27 | Unfocus FCurve tab properties on Timeline deselect | The only way to clear timeline key ticks while preserving 3D model selection in MotionBuilder. | Relying on `key.Selected = False` alone (did not clear timeline UI). |

---

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `py -m unittest discover -s tests -p "test_deselect_all.py"` | Python 3.10 / Windows | passed | 14/14 tests OK in 0.019s |
| Live Viewport Deselect | MotionBuilder 2026 Live | passed | Models deselected, curves/keys untouched |
| Live FCurve Deselect | MotionBuilder 2026 Live | passed | Keys/tangents cleared, models/curves preserved |
| Live Timeline Deselect | MotionBuilder 2026 Live | passed | FCurves unfocused & deselected, models preserved |
| FCurve Deselect Benchmark | MotionBuilder 2026 Live | passed | ~78ms latency on 274,000 keys |
