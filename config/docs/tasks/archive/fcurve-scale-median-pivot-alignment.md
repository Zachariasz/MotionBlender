# Task: FCurve Scale median-pivot alignment

Status: complete  
Last updated: 2026-08-17  
Owner/context: Codex and live MotionBuilder 2026 session

## Goal

Keep the FCurve Scale dashed radial guide aimed at the graph-space median of
all selected keys, including graph layouts whose major grid rows alternate
between adjacent integer pixel gaps.

## Acceptance criteria

- [x] Median time/value capture remains unchanged.
- [x] Axis calibration matches labels by logical major-grid steps.
- [x] Targeted offline transform tests pass.
- [x] A live read-only probe places the calculated pivot at the selected-key
  guide midpoint in the current MotionBuilder session.
- [x] Equal-support OCR hypotheses prefer the closer 1/2/5 cadence and the
  newly reported live selection aligns.
- [x] Decimal-scale ties use independent multi-key horizontal-guide alignment.
- [x] Multi-key top/bottom selection bounds directly establish scale and
  origin, including the reported four-key selection.
- [x] Calibration behavior is documented.

## Scope

Included:

- `transform.scale_mouse_distance` FCurve graph calibration.
- Shared FCurve graph transform and its focused regression tests.
- Live read-only verification through the manager-owned Codex Bridge.

## Non-goals

- FCurve key-selection, mutation, tangent, or pivot-policy changes.
- Viewer object Scale behavior.
- Changes to the current scene or selected key data during verification.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/fcurves/view_transform.py` | Shared screen/value calibration used by FCurve G/R/S. |
| `Scripts/mobu_tools_manager/fcurves/scale.py` | Captures the selected-key median and maps it through the shared transform. |
| `Scripts/tests/test_transform_runtime.py` | Focused calibration regressions. |

## Starting state

The live graph contained selected values `640.6884` and `453.3757`; their
correct median was `547.0321`. The selected-key horizontal guides were near
image rows 94 and 133, so the pivot belonged near row 113.5. A fresh capture
instead selected `10.9375` value units per pixel and mapped the median to row
58.4. OCR had interpreted the visible 200-unit major grid as roughly 500 units.

After the first correction, a second live selection at values `527.6748` and
`108.2507` reproduced the offset. Their visible marker rows were 118 and 207
(median 162.5), while calibration mapped the value median to row 61.55. Both
the correct 200-unit hypothesis and a wrong near-1000-unit hypothesis matched
three labels; the wrong hypothesis won only because its OCR mask score was
`0.0044` lower even though its cadence error was more than three times larger.

A third live selection contained four values from `1365.5387` through
`1662.3936`. MotionBuilder drew horizontal selection bounds at rows 92 and 229.
OCR recovered the correct `2.1739` value-per-pixel spacing but chose origin
`1363.0435` instead of roughly `1862`, placing the median at Y `-71.27` while
the visible middle-key rows placed it near Y `159`.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-08-16 | Match label candidates by rounded logical major-grid steps, then linearly fit matched values to physical rows. | The live rows alternated between 42 and 43 pixels. Raw pair-distance prediction rejected later correct labels and awarded a coherent OCR misread more matches. | Tightening the 1/2/5 tolerance alone still permits exact but incorrect 100/500 hypotheses and does not address rasterization drift. |
| 2026-08-16 | For equal-support hypotheses, rank closeness to exact 1/2/5 cadence before OCR mask score. | The remaining live case had three matches for both hypotheses; correct cadence error was `0.0117`, wrong was `0.0390`, while the wrong OCR score was only slightly lower. | Reducing the global cadence tolerance could reject valid rasterized layouts and would not express the intended evidence ordering. |
| 2026-08-16 | Detect and use selected-key horizontal guide rows without requiring a vertical guide. | After cadence ranking, a wrong 1000-unit interval and the correct 200-unit interval had the same normalized cadence error. The visible selected rows 118/207 uniquely identify the correct mapping. | Cadence cannot distinguish valid decimal multiples; raw OCR remains ambiguous. |
| 2026-08-17 | Derive multi-key scale and origin directly from top/bottom selection bounds and selected value extrema. | The four-key case had correct OCR spacing but a 500-unit origin shift; bound rows 92/229 and values 1365.5387/1662.3936 determine both quantities without label ambiguity. | OCR score/cadence cannot detect a pure integer-offset origin error. |

## Progress

### Completed

- Reproduced the offset through a read-only live bridge probe.
- Preserved evidence in
  `Scripts/.codex_mobu_bridge/results/20260816_232200_fcurve_pivot_cache_probe.png`.
- Implemented logical-row hypothesis matching and the observed-layout test.
- Updated the package overview and normative transform standard.
- Passed 23 focused transform-runtime tests and 8 Scale tests.
- Reloaded the affected G/R/S modules in MotionBuilder and cleared the old
  graph-transform cache.
- Verified the corrected pivot at Y `113.506` against selected-key marker
  midpoint Y `114.0`, an error of `-0.494` pixel.
- Added independent detection of strong selected-key horizontal guide rows and
  made multi-key alignment the strongest decimal-scale discriminator.
- Passed 25 focused transform-runtime tests and reran all 8 Scale tests.
- Reloaded the final correction and verified the reported second selection at
  pivot Y `162.104` versus marker midpoint Y `162.5`, an error of `-0.396`
  pixel.
- Added cadence-validated scale/origin derivation from multi-key top/bottom
  selection bounds and value extrema.
- Passed 26 focused transform-runtime tests and reran all 8 Scale tests.
- Reloaded the current four-key case and verified every mapped key row against
  its visible marker; pivot Y `158.649` versus marker median Y `159.0`, an
  error of `-0.351` pixel.
- Updated architecture, offline-testing, and live-integration documentation
  with the three preserved calibration failure layouts and acceptance gates.

### In progress

- None.

### Next action

1. User can retry S on the current four-key selection; the corrected modules
   are loaded and the reported geometry passes.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/fcurves/view_transform.py` | Uses logical grid steps, cadence evidence, independent horizontal guides, and multi-key bounds. | 26 focused runtime tests passed; all three live cases below 0.5 px |
| `Scripts/tests/test_transform_runtime.py` | Adds logical-row, equal-support, decimal-scale, and selection-bounds regressions. | Passed |
| `Scripts/mobu_tools_manager/README.md` | Documents robust row fitting. | Documentation review complete |
| `Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md` | Adds the calibration requirement. | Documentation review complete |
| `docs/ARCHITECTURE.md` | Documents calibration evidence ordering and multi-key bounds data flow. | Documentation review complete |
| `docs/TESTING.md` | Records the three focused regression layouts. | Documentation review complete |
| `Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md` | Adds two- and multi-key Scale-pivot live gates. | Documentation review complete |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| Live diagnostic before change | MotionBuilder 2026 bridge | failed | Median row 58.4 versus expected about 113.5; result `20260816_232200_fcurve_pivot_cache_probe_20260816_232203.json`. |
| `python -B -m unittest discover -s tests -p "test_transform_runtime.py" -v` | Bundled CPython | passed | 23 tests, OK. |
| `python -B -m unittest discover -s tests -p "test_transform_scale.py" -v` | Bundled CPython | passed | 8 tests, OK. |
| `python -B -m unittest discover -s tests -v` | Bundled CPython | failed outside changed scope | 246 tests ran; 2 unrelated focused failures and 28 environment/import errors, primarily unavailable writable temp storage and missing PySide6. The two failures reproduce independently in `test_cursor_coordinator.py` and `test_fcurve_visibility.py`. |
| Reload and live pivot probe | MotionBuilder 2026 | passed | Correct `4.7058` value/pixel calibration; calculated pivot Y `113.506`, marker midpoint Y `114.0`, error `-0.494` px. Result `20260816_233000_reload_fcurve_pivot_fix_and_verify_20260816_233110.json`. |
| Second live selection before equal-support fix | MotionBuilder 2026 | failed | Wrong `22.3491` value/pixel calibration; calculated median Y `61.55`, visible marker midpoint Y `162.5`. Result `20260816_234000_active_fcurve_scale_pivot_probe_20260816_233747.json`. |
| Second live selection after cadence-only ranking | MotionBuilder 2026 | failed | A wrong decimal-scale hypothesis had the same normalized cadence error; calculated median Y `54.65`, marker midpoint Y `162.5`. Result `20260816_234500_reload_equal_support_cadence_fix_20260816_234109.json`. |
| `python -B -m unittest discover -s tests -p "test_transform_runtime.py" -v` after horizontal-guide fix | Bundled CPython | passed | 25 tests, OK. |
| `python -B -m unittest discover -s tests -p "test_transform_scale.py" -v` after horizontal-guide fix | Bundled CPython | passed | 8 tests, OK. |
| Final reload and second-selection live probe | MotionBuilder 2026 | passed | Detected guide rows 118/207; correct `4.7057` value/pixel calibration; pivot Y `162.104`, marker midpoint Y `162.5`, error `-0.396` px. Result `20260816_235000_reload_horizontal_guide_fix_20260816_234341.json`. |
| Third four-key live selection before bounds fix | MotionBuilder 2026 | failed | Guide rows 92/229; OCR spacing `2.1739` was correct but origin was shifted by 500, mapping pivot to Y `-71.27` instead of about `159`. Result `20260816_235500_third_fcurve_pivot_case_probe_20260817_000019.json`. |
| `python -B -m unittest discover -s tests -p "test_transform_runtime.py" -v` after bounds fix | Bundled CPython | passed | 26 tests, OK. |
| `python -B -m unittest discover -s tests -p "test_transform_scale.py" -v` after bounds fix | Bundled CPython | passed | 8 tests, OK. |
| Final four-key reload and live probe | MotionBuilder 2026 | passed | Guide rows 92/229; all four mapped rows matched visible markers; pivot Y `158.649`, marker median Y `159.0`, error `-0.351` px. Result `20260817_000500_reload_multikey_bounds_fix_20260817_000354.json`. |

## Blockers and open questions

- The unrelated full-suite environment/import errors and two current
  focused failures remain outside this task. They do not occur in either
  changed-scope test module.

## Handoff notes

The fix changes only shared calibration math. The live reload and verification
refused to run during an interaction and did not mutate keys, selection, or the
scene.
