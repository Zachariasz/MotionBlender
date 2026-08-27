# Agent Instructions (MotionBuilder 2024–2027 Python Scripting Rules)

## 1. Research & MotionBuilder Context First
- Before changing or writing Python scripts, inspect existing script patterns, scene hierarchy conventions, and target MotionBuilder SDK features (`pyfbsdk`, `pyfbsdk_add_in`).
- Target **Python 3** specifications compliant with VFX Reference Platform standards (Python 3.10–3.13 across MotionBuilder 2024–2027).
- If a `pyfbsdk` class property, method signature, or enum behavior is ambiguous, inspect official Autodesk MotionBuilder SDK documentation or stub files (`pyfbsdk-stubs` / `motionbuilder-stubs`) instead of guessing.
- Keep file and symbol searches precise. Avoid scanning unrelated pipeline repos when the script target is localized.

## 2. Efficient Work & Performance
- Focus reasoning effort on main-thread execution, C++ object lifecycles, memory safety, clean undo transactions, scene evaluation overhead, and edge cases.
- Do not repeatedly read the same script file in a single session; retain and reuse relevant context.
- If the same script edit or bridge execution fails three consecutive times, stop and report: `I have entered a decision loop due to [reason]`.
- Prefer the smallest, cleanest implementation. Avoid unnecessary, speculative compatibility abstractions for legacy Python 2.x or obsolete SDK calls.

## 3. MotionBuilder Python & SDK Standards (MB 2024–2027)
- **Environment & Type Safety**:
  - Write clean Python 3 code with standard type hints. Utilize `pyfbsdk-stubs` / `motionbuilder-stubs` for IDE autocompletion and static analysis.
  - Handle exceptions explicitly; never catch-and-silence critical `pyfbsdk` or system exceptions without logging.
- **Main UI Thread Execution Safety**:
  - `pyfbsdk` is non-thread-safe. All SDK calls MUST execute strictly on MotionBuilder's main UI thread.
  - When invoked from external sockets, background threads, or async workers, queue executions to the main thread (e.g., via `FBExecuteInMainThread`, main-thread timers, or Qt signal-slot mechanisms).
- **C++ Wrapper Lifecycles & Memory Management**:
  - MotionBuilder Python objects are thin wrappers around underlying C++ components (`FBModel`, `FBComponent`, `FBConstraint`, `FBStoryTrack`, `FBCharacter`, etc.).
  - Explicitly call `.FBDelete()` when destroying scene components to ensure proper C++ cleanup rather than relying solely on Python garbage collection.
  - Scene operations like `FBApplication().FileNew()` or `.FBDelete()` invalidate existing Python object wrappers. Always check `.IsValid()` or verify existence before referencing scene objects.
- **Scene Evaluation & Undo Transactions**:
  - Wrap multi-step scene mutations in undo blocks using `FBSystem().Scene.TransactionBegin("Action Name")` and `FBSystem().Scene.TransactionEnd()`.
  - Trigger `FBSystem().Scene.Evaluate()` after structural or transform modifications when updated scene matrix/attribute states are immediately required.
  - Avoid calling `FBSystem().Scene.Evaluate()` inside tight execution loops to prevent severe performance bottlenecks.
- **UI & PySide Tools Integration**:
  - Use PySide6 (or PySide2 depending on MotionBuilder release) for tool interfaces.
  - Parent dialogs to MotionBuilder's main window handle to prevent windows from opening behind the application or being prematurely garbage collected.
  - Clean up event filters, timer objects, and signal connections when custom windows or tools are closed.
  - For buttons added beside MotionBuilder native controls, follow the manager-owned container pattern documented in `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md`. Treat native toolbar rows and their children as volatile geometry references only; never parent a managed button directly to a native toolbar or cache those native wrappers.
  - Identify a native row by an exact accessible-name/control signature, copy its geometry into Python primitives inside a `try...except RuntimeError` block, and parent one owned `QWidget` container to the stable pane above the native row. Reacquire that stable pane from the owned container after native UI rebuilds.
  - Use the manager's shared Qt event observer and an owned, bounded single-shot startup retry. On shutdown or invalidation, stop timers, unregister observers, detach the owned container, and queue it for deletion. Do not call nested `processEvents()` to force attachment.
  - For root menubar tabs (e.g., topbar menus), use the official SDK `FBMenuManager().InsertBefore(None, "Help", name)` contract. Passing `None` as the menu path registers a native C++ root menu with `tooldesktop.dll`. Never call `QMainWindow.menuBar()` or mutate Qt `QMenuBar` directly on MotionBuilder's main window, which causes `tooldesktop.dll` Access Violation crashes.
- **Animation, Character & Story Systems**:
  - Safely validate Takes (`FBTake`), Animation Layers (`FBAAnimationLayer`), Story Tracks (`FBStoryTrack`), and Characterization nodes (`FBCharacter`) before property assignment or keyframing.

## 4. Codex & Antigravity MotionBuilder Bridges

### Codex MotionBuilder Bridge (`CodexMotionBuilderBridge.py`)
- **Location & Architecture**:
  - The bridge script `CodexMotionBuilderBridge.py` resides under the project's `Scripts/` folder (`Scripts/CodexMotionBuilderBridge.py`).
  - It acts as the local file queue execution bridge allowing Codex / AI assistants and external editors to send Python payloads into an active MotionBuilder session.

### Antigravity MotionBuilder Bridge (`antigravity_mobu_client.py` / `developer.antigravity_bridge`)
- **Location & Architecture**:
  - Main feature: `mobu_tools_manager/features/antigravity_bridge.py` (`developer.antigravity_bridge`).
  - Standalone Client / CLI: `Scripts/antigravity_mobu_client.py`.
  - Queue directory: `Scripts/.antigravity_mobu_bridge/`.
  - UI control: **Python Tools > Start/Stop Antigravity Bridge** and Viewport HUD badge.
- **Antigravity Tool Capabilities**:
  - `python antigravity_mobu_client.py ping` — verify bridge liveness and heartbeat.
  - `python antigravity_mobu_client.py probe scene` — retrieve current take, frame range, FPS, selected objects, and cameras.
  - `python antigravity_mobu_client.py capture` — capture active MotionBuilder viewport snapshot to PNG for visual inspection.
  - `python antigravity_mobu_client.py eval "<code>"` — evaluate Python expressions safely on the main thread.
  - `python antigravity_mobu_client.py exec <script.py>` — execute multi-line scripts.

- **Bridge Scripting & Execution Rules**:
  - **Self-Contained Payloads**: Ensure code snippets or commands sent over the bridge are self-contained or explicitly import accessible module paths.
  - **Main Thread Dispatch**: All incoming execution requests from the bridge listener must be safety-dispatched to MotionBuilder's main thread via Qt timers to prevent instant desktop crashes.
  - **Structured Responses**: Wrap bridge script executions in `try...except` blocks that catch and format tracebacks into clean JSON / string outputs sent back to the client listener.
  - **Connection Liveness**: Check bridge status and heartbeat before triggering bulk script executions or batch scene updates.

## 5. Automated Testing & Verification Gates
- **Test Suite Structure**:
  - Maintain all automated scripts and unit tests under the root `Tests/` directory.
  - Structure test names using `MethodName_StateUnderTest_ExpectedBehavior` and adhere to the Arrange, Act, Assert pattern.
- **Execution Modes**:
  - **Headless Mode**: Run standalone logic, pipeline tools, and pure Python verification using MotionBuilder in batch mode (`motionbuilder.exe -batch -File <test_runner.py>`).
  - **Live Bridge Mode**: Run integration and scene-dependent tests against an open MotionBuilder instance via `antigravity_mobu_client.py` or `CodexMotionBuilderBridge.py`.
- **Test Isolation & Scene Cleanliness**:
  - Use isolated temporary scenes (`FBApplication().FileNew()`), temporary FBX assets, and temporary export folders. Never overwrite live user scenes or production assets during automated tests.
  - Reset scene state in test teardowns.
- **Verification Criteria**:
  - Run static analysis (`flake8`, `ruff`, or `mypy` with MotionBuilder stubs) for type and syntax verification.
  - Validate scene evaluation, object destruction (no memory leaks or dangling C++ references), and undo stack integrity.
  - Native-toolbar tests must cover delayed UI creation, native row destruction/rebuild, stable-pane reattachment, duplicate prevention, exact placement and styling, and complete controller cleanup.
  - If a script execution or test fails after a code change, make at most ONE targeted attempt to fix it. If it fails again, stop, analyze logs, and report findings instead of entering a retry loop.


## Documentation routing

Before modifying code:

- Read `README.md` and `docs/PROJECT_MAP.md`.
- For bridge work, read `docs/ANTIGRAVITY_BRIDGE.md` and `docs/CODEX_BRIDGE.md`.
- For native toolbar or PySide integration, read
  `Scripts/MOBU_TOOLS_MANAGER_GUIDE.md`.
- For testing or live MotionBuilder execution, read `docs/TESTING.md`.
- When continuing existing work, read the task file named by the user under
  `docs/tasks/active/`.
- Do not read every document indiscriminately; load only documentation relevant
  to the requested work.

## Documentation maintenance

- Update documentation when commands, architecture, behavior, or supported
  MotionBuilder versions change.
- For substantial work, maintain an active task file containing completed work,
  decisions, verification results, blockers, and the next action.
- Never mark a test as passing unless it was actually executed.