# Task: Visible FCurve action scope

Status: active  
Last updated: 2026-08-16  
Owner/context: MotionBuilder 2024-2027 FCurve actions

## Goal

Make every FCurve action target only the focused, visible curve channels in the
FCurve editor, even when hidden curves retain selected keys.

## Acceptance criteria

- [ ] Move, Rotate, and Scale ignore hidden vector siblings.
- [ ] FCurve selection, infinite repetition, and filters use the same scope.
- [ ] Partial visible vector groups cannot cause a filter to mutate hidden siblings.
- [ ] Offline test and live isolated-scene verification are recorded.
- [x] The transform/FCurve standard and routed engineering docs document the rule.

## Scope

Included: shared FCurve discovery and the managed legacy FCurve commands.

## Non-goals

- Changing non-FCurve scene-selection behavior.
- Applying a vector filter to a partial channel group.

## Important files

| File | Why it matters |
| --- | --- |
| `Scripts/mobu_tools_manager/fcurves/discovery.py` | Canonical visible-channel selector. |
| `Scripts/custom/ApplyFilterToSelectedFCurves.py` | Filter target discovery and vector-group safety. |
| `Scripts/tests/test_fcurve_visibility.py` | Offline scope regression coverage. |

## Starting state

Interactive discovery expanded every child of a displayed vector property, and
several legacy commands scanned the whole scene. Hidden selected keys could
therefore be mutated.

## Decisions

| Date | Decision | Reason | Alternatives rejected |
| --- | --- | --- |
| 2026-08-16 | Use `GetProperties(..., True)` with `IsFocusedChild`. | Autodesk exposes this as the focused/visible FCurve channel scope. | Whole-scene traversal and unfiltered child-node recursion can affect hidden channels. |
| 2026-08-16 | Skip partial vector filter groups. | Parent-node vector filters can mutate hidden siblings. | Applying the parent-node filter would violate visible-only scope. |

## Progress

### Completed

- Context, current implementation, and supported MotionBuilder API inspected.
- Applied the shared focused-channel selector to interactive transforms and the
  managed FCurve commands.
- Added focused-channel regression coverage and updated the normative standard.

### In progress

- Offline and host-specific verification are pending an available interpreter
  and an isolated MotionBuilder scene.

### Next action

1. Run the focused offline test and syntax checks, then perform the isolated-scene live check.

## Changed files

| File | Change | Verification |
| --- | --- | --- |
| `Scripts/mobu_tools_manager/fcurves/discovery.py` | Uses focused child nodes rather than recursively expanding vector properties. | Not run |
| `Scripts/custom/ApplyFilterToSelectedFCurves.py` | Uses the shared scope and protects hidden vector siblings. | Not run |
| `Scripts/custom/SetSelectedFCurvesInfiniteRepetition.py` | Restricts extrapolation to the shared scope. | Not run |
| `Scripts/custom/SelectFCurve.py` | Restricts key selection to the shared scope. | Not run |
| `Scripts/custom/SelectedKeyTangentsMenu.py` | Restricts tangent actions to the shared scope. | Not run |
| `Scripts/tests/test_fcurve_visibility.py` | Adds focused-channel regression coverage. | Not run |
| `Scripts/mobu_tools_manager/README.md` and `docs/ARCHITECTURE.md` | Document the shared visible-only scope. | Updated |
| `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md` and integration checklist | Document migration and live verification requirements. | Updated |

## Verification

| Check | Environment | Result | Evidence |
| --- | --- | --- | --- |
| `python -m unittest discover -s tests -p "test_fcurve_visibility.py" -v` | Codex PowerShell | blocked | `python` is not installed or on `PATH` |
| Isolated MotionBuilder scene | MotionBuilder 2024-2027 | Not run | Required after offline checks |

## Blockers and open questions

- Live MotionBuilder access is needed to verify the host-specific focused-child API and filter behavior.
