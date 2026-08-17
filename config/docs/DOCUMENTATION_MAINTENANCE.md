# Documentation Maintenance

## Goal

Documentation must let a new developer or Codex context discover the project
boundary, current architecture, safe change workflow, verification state, and
next action without depending on previous chat history.

## Document roles

| Document | Role | Update when |
| --- | --- | --- |
| `AGENTS.override.md` | Mandatory workspace rules and routing. | Scope, safety, or required workflow changes. |
| `Scripts/mobu_tools_manager/AGENTS.md` | Package-specific implementation rules. | Feature contracts, ownership, or package gates change. |
| Root `README.md` | Human-facing project boundary and entry map. | Main entrypoints or document set changes. |
| Package `README.md` | Installation, API, package map, features, usage. | Public behavior, paths, features, or dependencies change. |
| `docs/README.md` | Task-to-document routing. | Documents are added, renamed, or superseded. |
| `PROJECT_STRUCTURE.md` | Owned tree and external boundaries. | Files/subpackages/entrypoints move. |
| `ARCHITECTURE.md` | Component ownership and data flow. | Startup, runtime, dispatch, persistence, or shutdown changes. |
| `DEVELOPMENT.md` | Safe implementation workflows. | Extension or contribution process changes. |
| `CODEX_BRIDGE.md` | Bridge protocol and operations. | Any bridge path, schema, lifecycle, helper, or timing changes. |
| `TESTING.md` | Offline/live gates and coverage. | Tests, commands, environments, targets, or gaps change. |
| `PROJECT_STATUS.md` | Dated implementation snapshot. | Counts, native set, known gaps, or environment state changes. |
| Active task file | Volatile work state. | At every meaningful task checkpoint. |
| ADR | Lasting rationale. | An architectural decision is accepted or superseded. |

## Sources of truth

Do not manually duplicate facts that can drift unless the duplication helps
orientation and has a clear update trigger.

- Feature IDs/counts/mappings: `catalog.py` and `test_catalog.py`.
- Public API: package `__init__.py`.
- Startup: bootstrap template plus active PythonStartup copy.
- Runtime ownership: `manager.py` and `runtime.py`.
- Bridge schema/timing: `features/codex_bridge.py`.
- Offline coverage: files under `Scripts/tests`.
- Live acceptance: MotionBuilder integration checklist.
- Historical migration coverage: dated script audit.

When code and docs disagree, verify the code and tests, update the docs, and note
the correction in the active task.

## Writing rules

- Put mandatory behavior in an instruction file once at the most relevant
  scope.
- Put explanations and rationale in documentation or ADRs.
- Use stable IDs and repository-relative paths.
- Label historical snapshots and dated counts.
- Separate offline evidence from live MotionBuilder evidence.
- Never claim a check passed when it was not run.
- Record known gaps directly instead of implying complete coverage.
- Keep compatibility behavior distinct from the target native architecture.
- Describe ownership and cleanup, not only successful execution.

## Task handoffs

Substantial work uses `docs/tasks/active/<task-name>.md` based on the template.
Update it after discovery, after a design decision, after edits, after tests, and
before ending with unfinished work.

An active task must contain:

- observable goal and acceptance criteria;
- scope and non-goals;
- important files and stable feature IDs;
- decisions with reasons;
- completed/current/next work;
- exact verification state;
- blockers and unresolved questions;
- last-updated date.

Archive completed tasks under `docs/tasks/archive/` when useful as project
history. Do not leave several contradictory “current” task files.

## Decision records

Use an ADR when a choice changes lasting ownership, protocol, public API,
persistence, compatibility, or verification behavior. Small implementation
details belong in code comments or the task file.

An ADR is immutable after acceptance except for status and supersession links.
Create a new ADR instead of rewriting history.

## Link and consistency checks

After documentation changes:

1. Check every local Markdown link resolves relative to its file.
2. Check paths use current capitalization and filenames.
3. Confirm instruction files remain comfortably below Codex's combined project
   instruction limit.
4. Confirm no obsolete document is presented as current.
5. Confirm feature/test counts against their sources.
6. Confirm bootstrap template and active startup copy remain identical when
   either changes.
7. Confirm bridge docs match constants and result/status fields in code.

## Context-compaction rule

Conversation history is not a project database. Decisions, changed files,
verification, blockers, and next steps belong in the active task file before a
long context is compacted or a task is handed off.

