# Task Handoffs

Task files preserve volatile work state across fresh or compacted contexts.
They complement `AGENTS.md` and architecture documentation; they do not replace
them.

## When to create one

Create an active task file when work:

- is likely to span more than one context;
- involves several subsystems or files;
- contains unresolved design decisions;
- requires offline plus live MotionBuilder verification;
- is blocked on a host state, approval, or external dependency;
- would be costly to rediscover.

Small, completed one-turn changes do not need a permanent task file.

## Workflow

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to
   `active/<short-kebab-case-name>.md`.
2. Fill the goal, acceptance criteria, scope, important files, and initial
   verification plan before editing.
3. Update decisions and status at meaningful checkpoints.
4. Record exact test commands and results; use `not run` explicitly.
5. Before pausing, write one exact next action that another context can execute.
6. When complete, either delete the temporary handoff or move it to `archive/`
   if it contains useful history.

## Resume protocol

A fresh context should:

1. Read the workspace and package instructions.
2. Read the named active task.
3. Reconcile its changed-file/status claims with the current filesystem.
4. Recheck any external state that can change, such as MotionBuilder liveness,
   bridge heartbeat, or test environment.
5. Continue from the recorded next action.

Do not redo completed work unless the current files contradict the handoff.

