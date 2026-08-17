# Project Structure

## Maintained project

The maintained software is the MotionBuilder Tools Manager package and its
manager-owned Codex Bridge:

```text
config/
├── AGENTS.override.md
├── README.md
├── docs/
│   ├── CODEX_BRIDGE.md
│   └── ANTIGRAVITY_BRIDGE.md
├── PythonStartup/
│   └── 000_MobuToolsManagerBootstrap.py
└── Scripts/
    ├── AGENTS.md
    ├── ActionScript.txt
    ├── AntigravityMotionBuilderBridge.py
    ├── AntigravityMotionBuilderBridgeTool.py
    ├── antigravity_mobu_client.py
    ├── CodexMotionBuilderBridge.py
    ├── CodexMotionBuilderBridgeTool.py
    ├── MOBU_SCRIPT_AUDIT.md
    ├── MOBU_TOOLS_MANAGER_GUIDE.md
    ├── MOBU_TRANSFORM_FCURVE_MIGRATION_STANDARD.md
    ├── mobu_tools_manager/
    ├── tests/
    └── custom/icons/
```

The broader directory is a live MotionBuilder user configuration. Other
scripts, layouts, keyboards, presets, caches, machine-specific text files, FBX
files, and backups are not automatically part of this project.

## Package tree

```text
Scripts/mobu_tools_manager/
├── AGENTS.md
├── README.md
├── __init__.py
├── bootstrap.py
├── bootstrap_template.py
├── catalog.py
├── diagnostics.py
├── legacy.py
├── manager.py
├── native.py
├── runtime.py
├── settings.py
├── shortcuts.py
├── ui.py
├── generated_actions/
├── features/
├── interactions/
├── object_transforms/
├── fcurves/
├── story/
├── viewer/
└── quick_favorites/
```

## Core ownership

| Area | Files | Owns |
| --- | --- | --- |
| Public API | `__init__.py` | Singleton lookup/restart and stable dispatch API. |
| Startup/menu | `bootstrap.py`, `bootstrap_template.py` | PythonStartup entry, direct Qt action for the modeless manager window, and short-lived bridge menu actions. |
| Orchestration | `manager.py` | Start/shutdown, feature state, dispatch, warmup, diagnostics, shortcut application. |
| Catalog | `catalog.py` | Stable IDs, categories, kinds, dependencies, entrypoints, slots, native/legacy mapping. |
| Runtime | `runtime.py` | Shared MotionBuilder and Qt service graph passed through `CommandContext`. |
| Adapters | `native.py`, `legacy.py` | Import-once native modules and compile-once legacy scripts. |
| Persistence | `settings.py`, `shortcuts.py` | Per-user settings, ActionScript mappings, keyboard-profile edits, backups, rescans. |
| Manager UI | `ui.py` | Search, feature controls, interaction settings, diagnostics export. |
| Diagnostics | `diagnostics.py` | Bounded memory records and explicit JSON export. |

## Functional packages

### `features/`

Manager-native entrypoints. Current native features include Viewer/FCurve G/R/S,
transform policy, Quick Favorites, Story commands, Fast Render, Save Options
Templates, Character keying hotkeys, Timeline marker labels, Codex Bridge,
and the Antigravity Bridge.

Feature modules are thin lifecycle entrypoints when complex behavior belongs in
a focused subpackage.

### `interactions/`

Shared event-driven interaction state:

- axis constraints;
- exact numeric input;
- global precision/snap policy;
- one interaction coordinator and session state machine;
- reusable cursor and overlay presentation.

### `object_transforms/`

Viewer object/HIK transformation implementation:

- target capture and camera projection;
- frozen 1000-unit axis guide;
- Move, Rotate, and Scale strategies;
- HIK topology, keying-mode policy, pin/Reach state, solve, and cleanup.

### `fcurves/`

Displayed-curve and selected-key operations:

- displayed property/curve discovery;
- immutable key/tangent snapshots;
- collision-aware mutation;
- cached screen/time/value transforms;
- Move, Scale, tangent Rotate, and tangent handling.

### `story/`

Story-specific commands and manager-owned native UI integration:

- clip timing;
- current-take insertion;
- selected-clip reset/alignment;
- personal Story settings;
- toolbar and native popup action ownership.

### `viewer/`

Manager-owned Viewer toolbar controls. The current controller owns the Fast
Render button and reattaches it safely across native UI rebuilds.

### `quick_favorites/`

Validated JSON-safe configuration and the manager-owned editor for per-context
Quick Favorites entries.

### `generated_actions/`

Checked-in two-line wrappers for manager-owned ActionScript slots. They are
integration glue, not feature implementations.

## Active entrypoints

| Entry point | Behavior |
| --- | --- |
| `PythonStartup/000_MobuToolsManagerBootstrap.py` | Adds `Scripts` to `sys.path` and calls the reload-safe bootstrap. |
| `mobu_tools_manager.bootstrap.bootstrap()` | Restarts the singleton manager. |
| `mobu_tools_manager.dispatch(feature_id)` | Runs or activates one stable catalog feature. |
| `mobu_tools_manager.show_manager()` | Opens the modeless manager UI. |
| `developer.codex_bridge` | Starts or reports the manager-native bridge service. |
| `Scripts/ActionScript.txt` | Maps MotionBuilder Python action slots to generated wrappers. |

## Direct external integrations

These files are in scope only as manager integration surfaces:

| Path | Role |
| --- | --- |
| `PythonStartup/000_MobuToolsManagerBootstrap.py` | Active startup copy of `bootstrap_template.py`. |
| `Scripts/ActionScript.txt` | Managed and unmanaged native action-slot mapping. |
| `Scripts/CodexMotionBuilderBridge.py` | Thin bridge dispatch compatibility launcher. |
| `Scripts/CodexMotionBuilderBridgeTool.py` | Thin `start_bridge()` compatibility launcher. |
| `Scripts/custom/QuickFavoritesMenu.py` | Quick Favorites compatibility launcher. |
| `Scripts/custom/ResetSelectedStoryClips.py` | Story reset compatibility launcher. |
| `Scripts/custom/InsertCurrentTakeToStory.py` | Story insertion compatibility launcher. |
| `Scripts/RenderSideFrontCameras.py` | Fast Render compatibility facade. |
| `Scripts/custom/icons/2arrow.png` | Scale cursor art. |
| `Scripts/custom/icons/4arrow.png` | Move cursor art. |
| `Scripts/tests/**` | Offline package tests and live checklist. |

Catalog-listed legacy source files are adapter inputs. Their presence in the
catalog does not make every neighboring script project-owned.

## Generated and personal data

Do not treat these as source:

```text
<UserConfigPath>/MotionBuilderToolsManager/settings.json
<UserConfigPath>/MotionBuilderToolsManager/save_options_templates.json
<UserConfigPath>/MotionBuilderToolsManager/backups/**
<UserConfigPath>/Scripts/.codex_mobu_bridge/**
Scripts/**/__pycache__/**
Scripts/**/*.pyc
```

The top-level `MotionBuilderToolsManager/backups/**` directory contains migration
recovery snapshots and archived startup files. Read it only for recovery or
historical comparison.

## Explicit exclusions

Unless the user says otherwise, exclude:

- unrelated creator scripts and Autodesk examples;
- custom spine picker files explicitly excluded by the migration audit;
- quarantined timeline-label experiments;
- machine-specific application/history/task/perforce files;
- Layouts, Keyboard, PinningPresets, CharacterTemplate, and FBX configuration;
- caches, logs, bridge queues, backups, and temporary upload folders.
