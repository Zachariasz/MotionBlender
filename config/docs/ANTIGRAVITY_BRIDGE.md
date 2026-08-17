# Antigravity MotionBuilder Bridge

## Purpose

The Antigravity MotionBuilder Bridge provides a robust, main-thread communication, testing, debugging, and development channel between external processes (such as Antigravity AI pair programming sessions, automated test runners, and developer scripts) and an active Autodesk MotionBuilder session.

Inspired by the project's internal Codex bridge, the Antigravity bridge enhances the architecture with specialized development and introspection features:
- Viewport frame captures (`capture_viewport`) for visual UI/3D inspection and verification;
- Direct scene introspection helpers (`get_scene_summary`, `get_selected_transforms`, `get_fcurve_summary`, `evaluate_scene`, `undo_transaction`);
- Full CLI & Python Client (`antigravity_mobu_client.py`) with rich commands: `ping`, `eval`, `exec`, `capture`, `probe`, and `stop`;
- Clean manager-owned lifecycle integration under `developer.antigravity_bridge` with an input-transparent Viewport HUD badge.

The active implementation is:

[`Scripts/mobu_tools_manager/features/antigravity_bridge.py`](../Scripts/mobu_tools_manager/features/antigravity_bridge.py)

Compatibility launchers:
- [`Scripts/AntigravityMotionBuilderBridge.py`](../Scripts/AntigravityMotionBuilderBridge.py)
- [`Scripts/AntigravityMotionBuilderBridgeTool.py`](../Scripts/AntigravityMotionBuilderBridgeTool.py)

CLI / Python SDK:
- [`Scripts/antigravity_mobu_client.py`](../Scripts/antigravity_mobu_client.py)

---

## Architecture & Queue Layout

The bridge uses an atomic file-based queue root located at:

```text
<UserConfigPath>/Scripts/.antigravity_mobu_bridge/
├── commands/
├── running/
├── done/
├── results/
├── captures/
├── logs/
│   └── bridge.log
├── status.json
└── heartbeat.txt
```

| Path | Meaning |
| --- | --- |
| `commands/` | Complete `.py` payloads waiting to execute on the main thread. |
| `running/` | A command claimed by the bridge service before execution. |
| `done/` | Archived commands with `.done.py` or `.error.py` appended. |
| `results/` | Structured JSON results containing execution status, return values, stdout/stderr, logs, and tracebacks. |
| `captures/` | Saved PNG viewport snapshot images. |
| `logs/bridge.log` | Append-only bridge lifecycle and command audit log. |
| `status.json` | Live service state, version, and last-command metadata. |
| `heartbeat.txt` | Last liveness timestamp (refreshed every 2 seconds). |

---

## Starting and Stopping

### From MotionBuilder UI (Python Tools Menu):
Open the **Python Tools** menu from the MotionBuilder menu bar:
- Click **Start Antigravity Bridge** to start the bridge service and show the Viewport status badge.
- Click **Stop Antigravity Bridge** to stop and disable the bridge service.

### From MotionBuilder Python:
```python
from mobu_tools_manager import dispatch, disable

# Start bridge:
dispatch("developer.antigravity_bridge")

# Stop bridge:
disable("developer.antigravity_bridge")
```

### From External CLI (`antigravity_mobu_client.py`):
```powershell
# Check liveness:
python antigravity_mobu_client.py ping

# Stop bridge:
python antigravity_mobu_client.py stop
```

---

## CLI & Client Usage

### 1. Check Liveness (`ping` / `status`)
```powershell
python antigravity_mobu_client.py ping
```
Output:
```text
[ONLINE] Bridge State: RUNNING
Heartbeat Age : 0.4s
Processed Cmds: 12
Bridge Root   : W:\Repo\MotionBlender\config\Scripts\.antigravity_mobu_bridge
```

### 2. Evaluate Expression (`eval`)
```powershell
python antigravity_mobu_client.py eval "FBSystem().Scene.RootModel.Children[0].Name"
```

### 3. Execute Script File (`exec`)
```powershell
python antigravity_mobu_client.py exec my_debug_script.py
```

### 4. Capture Viewport Snapshot (`capture`)
```powershell
python antigravity_mobu_client.py capture --output viewport_test.png
```

### 5. Probe Scene & Animation (`probe`)
```powershell
# Probe general scene overview (take, FPS, selected objects, cameras)
python antigravity_mobu_client.py probe scene

# Probe selected models and their transform values (translation, rotation, scale)
python antigravity_mobu_client.py probe selected

# Probe selected models' FCurves and key counts
python antigravity_mobu_client.py probe fcurves
```

### 6. Raw JSON Output (`--json`)
All commands support `--json` for direct parsing by automated tools or agent subagents:
```powershell
python antigravity_mobu_client.py probe scene --json
```

---

## Payload Execution Environment

Commands executed in the bridge receive a rich set of built-ins:

| Symbol | Description |
| --- | --- |
| `BRIDGE` / `bridge` | `AntigravityCommandContext` instance. |
| `set_result(value)` | Marks explicit JSON-serializable return value. |
| `bridge_log(*values)` | Logs to command output and prints to stdout. |
| `capture_viewport(output_path=None, width=1920, height=1080)` | Captures active viewport snapshot to PNG. |
| `get_scene_summary()` | Returns current take name, frame range, FPS, selected models, total models count, character count, camera names. |
| `get_selected_transforms()` | Returns translation, rotation, and scaling for all selected models. |
| `get_fcurve_summary(property_name=None)` | Summarizes animation curves and key counts on selected models. |
| `evaluate_scene()` | Triggers `FBSystem().Scene.Evaluate()`. |
| `undo_transaction(name)` | Context manager for safe undo transactions. |
| `RESULT` | Fallback variable read if `set_result()` was not explicitly called. |

---

## Viewport Status HUD

While running, the bridge displays an input-transparent, modern status badge ("Antigravity Bridge") in the top-left corner of the active Viewer window.

- **Mouse-Transparent**: `WA_TransparentForMouseEvents` ensures it never interferes with user clicks or navigation.
- **Dynamic Geometry**: Listens to shared Qt event stream to re-position on Viewer resize/move.
- **Interaction-Safe**: Automatically suppressed while transform interactions (Grab/Rotate/Scale) own the input router.

---

## Automated Verification

Run unit tests via standard Python:
```powershell
python -m unittest discover -s tests -p "test_antigravity_bridge.py" -v
```
