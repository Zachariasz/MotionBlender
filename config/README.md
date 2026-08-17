# MotionBuilder Tools Manager Development Workspace

This workspace contains a MotionBuilder user configuration, but the maintained
software project is the reload-safe **MotionBuilder Tools Manager** and its
manager-owned **Codex MotionBuilder Bridge**.

## Project boundary

Primary source code:

- [`Scripts/mobu_tools_manager/`](Scripts/mobu_tools_manager/)

Direct integration surfaces:

- [`PythonStartup/000_MobuToolsManagerBootstrap.py`](PythonStartup/000_MobuToolsManagerBootstrap.py)
- [`Scripts/ActionScript.txt`](Scripts/ActionScript.txt)
- [`Scripts/CodexMotionBuilderBridge.py`](Scripts/CodexMotionBuilderBridge.py)
- [`Scripts/CodexMotionBuilderBridgeTool.py`](Scripts/CodexMotionBuilderBridgeTool.py)
- manager compatibility launchers and transform cursor assets
- [`Scripts/tests/`](Scripts/tests/)
- [`Scripts/MOBU_TOOLS_MANAGER_GUIDE.md`](Scripts/MOBU_TOOLS_MANAGER_GUIDE.md)
- [`Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md`](Scripts/MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md)

Other scripts and MotionBuilder configuration files in this directory may come
from Autodesk, other creators, older tools, or machine-local state. They are not
part of this project unless explicitly listed by the manager catalog or included
by the user for a specific task.

## Start here

- [Package README](Scripts/mobu_tools_manager/README.md) - installation, public
  API, module map, features, shortcuts, settings, and verification.
- [Documentation index](docs/README.md) - task-oriented routing for developers
  and new Codex contexts.
- [Project map](docs/PROJECT_STRUCTURE.md) - source tree, ownership, entry
  points, and external boundaries.
- [Architecture](docs/ARCHITECTURE.md) - startup, dispatch, runtime services,
  adapters, UI ownership, and shutdown.
- [Codex Bridge](docs/CODEX_BRIDGE.md) - file-queue protocol, liveness, payloads,
  results, and safety.
- [Testing](docs/TESTING.md) - offline suite, live MotionBuilder gates, and
  current coverage boundaries.
- [Project status](docs/PROJECT_STATUS.md) - dated implementation snapshot and
  known documentation/testing gaps.

## MotionBuilder startup

MotionBuilder executes the single bootstrap in `PythonStartup`. The bootstrap
adds `Scripts` to `sys.path`, shuts down any previous manager instance, and
starts one replacement.

Open the manager from:

```text
Python Tools > MotionBuilder Tools Manager
```

Start or stop the bridge from the short-lived Python Tools menu action, or
dispatch `developer.codex_bridge` through the package API.

## Development commands

From the `Scripts` directory, run the offline suite with a compatible Python 3
interpreter:

```text
python -m unittest discover -s tests -v
```

Live scene and UI verification is defined in
[`Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md`](Scripts/tests/MOTIONBUILDER_INTEGRATION_CHECKLIST.md).

## Context continuity

Persistent rules live in [`AGENTS.override.md`](AGENTS.override.md). Subsystem
knowledge lives in `docs/` and the package README. Long-running work should
maintain a task handoff under `docs/tasks/active/` so a fresh context can recover
the goal, decisions, verification state, blockers, and next action without
relying on chat history.

