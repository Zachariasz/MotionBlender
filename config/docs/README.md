# Documentation Index

This directory is the durable context map for the MotionBuilder Tools Manager
and its Codex MotionBuilder Bridge. Use it to choose the minimum documentation
needed for a task.

## New-context startup

For any manager or bridge task:

1. Read [`../AGENTS.override.md`](../AGENTS.override.md).
2. Read [`../Scripts/mobu_tools_manager/AGENTS.md`](../Scripts/mobu_tools_manager/AGENTS.md).
3. Read the [package README](../Scripts/mobu_tools_manager/README.md).
4. Read [Project Status](PROJECT_STATUS.md).
5. Select the task-specific references below.
6. If continuing work, read the named file under [`tasks/active/`](tasks/active/).

Do not read every long document by default. The engineering guide and transform
standard are intentionally detailed and should be loaded only for relevant
work.

## Task routing

| Task | Required references |
| --- | --- |
| General orientation or repository mapping | [Project Structure](PROJECT_STRUCTURE.md), [Architecture](ARCHITECTURE.md) |
| Manager startup, reload, dispatch, enable/disable, shutdown | [Architecture](ARCHITECTURE.md), [Manager Guide](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md) |
| Catalog, stable IDs, native/legacy adapters, ActionScript | [Development](DEVELOPMENT.md), package README, `catalog.py`, `test_catalog.py` |
| Runtime caches, evaluation, input, overlays, undo, HIK | [Architecture](ARCHITECTURE.md), [Manager Guide](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md) |
| G/R/S, Viewer transforms, FCurves, tangents | [Transform/FCurve Standard](../Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md), [Testing](TESTING.md) |
| Story commands, context menu, Story toolbar | [Manager Guide](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md), relevant `story/` modules, [Testing](TESTING.md) |
| Viewer or Story native-toolbar UI | Native-toolbar section of the [Manager Guide](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md), `test_viewer_toolbar.py` |
| Quick Favorites, popup-triggered native-action freeze/crash | Package README, Quick Favorites and incident-response sections of the [Manager Guide](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md), Quick Favorites boundary in the [Transform/FCurve Standard](../Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md), [ADR-0003](decisions/0003-popup-native-actions-require-manager-features.md), `quick_favorites/`, and `features/quick_favorites.py` |
| Save Options Templates | `features/save_options_templates.py`, [Testing](TESTING.md), package README |
| Fast Render or FBX Export | `features/render_two_cameras.py`, `features/export_fbx.py`, `exporting/`, `viewer/toolbar.py`, [Testing](TESTING.md) |
| Codex Bridge implementation or use | [Codex Bridge](CODEX_BRIDGE.md), `features/codex_bridge.py`, `test_codex_bridge.py` |
| Antigravity Bridge implementation or use | [Antigravity Bridge](ANTIGRAVITY_BRIDGE.md), `antigravity_mobu_client.py`, `features/antigravity_bridge.py`, `test_antigravity_bridge.py` |
| Offline or live verification | [Testing](TESTING.md), [Integration Checklist](../Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md) |
| Documentation changes | [Documentation Maintenance](DOCUMENTATION_MAINTENANCE.md) |
| Multi-context task continuation | [Task Handoffs](tasks/README.md) and the active task file |
| Architectural decision | [Decision Records](decisions/README.md) |

## Documentation set

- [Project Structure](PROJECT_STRUCTURE.md) — owned source tree, direct
  integrations, entrypoints, and exclusions.
- [Architecture](ARCHITECTURE.md) — startup, manager/runtime ownership,
  dispatch, adapters, interaction routing, persistence, and shutdown.
- [Development](DEVELOPMENT.md) — safe change workflows and extension rules.
- [Codex Bridge](CODEX_BRIDGE.md) — current file-queue protocol and operational
  safety for the Codex bridge.
- [Antigravity Bridge](ANTIGRAVITY_BRIDGE.md) — main-thread execution, viewport capture,
  scene introspection, and Python/CLI client SDK for Antigravity AI workflows.
- [Testing](TESTING.md) — test commands, subsystem matrix, live gates, and known
  gaps.
- [Project Status](PROJECT_STATUS.md) — dated implementation counts, current
  boundaries, and unverified state.
- [Documentation Maintenance](DOCUMENTATION_MAINTENANCE.md) — sources of truth,
  update triggers, link checking, and staleness rules.
- [Task Handoffs](tasks/README.md) — active-task workflow and template.
- [Decision Records](decisions/README.md) — durable architectural rationale.

## Existing long-form references

- [`Scripts/MOBU_TOOLS_MANAGER_GUIDE.md`](../Scripts/MOBU_TOOLS_MANAGER_GUIDE.md)
  is the detailed normative lifecycle, UI-ownership, migration, and cleanup
  guide.
- [`Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md`](../Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md)
  is the normative G/R/S and FCurve interaction contract.
- [`Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`](../Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md)
  is the live MotionBuilder verification gate.
- [`Scripts/MOBU_SCRIPT_AUDIT.md`](../Scripts/MOBU_SCRIPT_AUDIT.md) is a dated
  2026-07-29 migration inventory. It is historical evidence, not the current
  catalog source of truth.

The older `docs/PROJECT_MAP.md` predates this structure and contains obsolete
paths. Use [Project Structure](PROJECT_STRUCTURE.md) instead.

## Source-of-truth priority

When documents disagree, use this order:

1. Current code and tests.
2. Package `AGENTS.md` safety and ownership rules.
3. Current architecture, bridge, development, and testing documents.
4. Long-form manager and transform standards.
5. Dated audits, backups, and historical notes.

Never silently resolve a contradiction. Record it in the active task and update
the stale document as part of the change when authorized.
