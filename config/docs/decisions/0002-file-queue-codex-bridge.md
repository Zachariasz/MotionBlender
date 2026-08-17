# ADR-0002: Main-Thread File-Queue Codex Bridge

Date: 2026-08-11  
Status: accepted

## Context

External tools need a way to execute diagnostic or automation payloads inside a
running MotionBuilder process. `pyfbsdk` and MotionBuilder-owned Qt objects are
not thread-safe, so a background socket/listener thread cannot safely execute
SDK work directly.

The bridge must also expose inspectable liveness, results, errors, and processed
payloads without adding another unmanaged global event filter or application
tool lifecycle.

## Decision

Use a trusted local file queue owned by the manager-native feature
`developer.codex_bridge`.

A MotionBuilder-main-thread Qt timer polls `Scripts/.codex_mobu_bridge/commands`
every 250 ms. It atomically claims one `.py` file, executes it synchronously on
the main thread, captures stdout/stderr and an explicit result, writes JSON,
archives the command, and updates status/heartbeat data.

The bridge uses the runtime's shared UI observer for one input-transparent
Viewer badge. Loose bridge scripts remain compatibility dispatch launchers.

## Consequences

- SDK payloads execute on the required main thread.
- Producers and results are observable through ordinary files.
- Commands must be written atomically and named uniquely.
- Only one command executes at a time.
- Long or blocking commands freeze MotionBuilder and heartbeat progress.
- The queue is trusted arbitrary-code execution; it is not sandboxed,
  authenticated, or suitable for remote/untrusted exposure.
- The protocol must preserve command archival, result schema, status,
  heartbeat, and cleanup behavior or be explicitly versioned.

## Alternatives considered

- Background socket thread executing payloads — rejected because direct SDK
  execution off the main UI thread can crash MotionBuilder.
- Socket listener that manually marshals every operation — not selected for the
  current implementation because the file queue is simpler, inspectable, and
  already provides main-thread dispatch through the manager timer.
- Execute loose bridge scripts directly — rejected because it recreates a
  parallel lifecycle and bypasses stable feature dispatch.

## References

- `Scripts/mobu_tools_manager/features/codex_bridge.py`
- `Scripts/mobu_tools_manager/bootstrap.py`
- `Scripts/tests/test_codex_bridge.py`
- `Scripts/tests/test_bootstrap_menu.py`
- `docs/CODEX_BRIDGE.md`

