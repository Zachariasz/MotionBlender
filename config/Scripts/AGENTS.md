# Scripts Scope Instructions

The maintained project under this directory is `mobu_tools_manager` plus its
direct startup, bridge, ActionScript, compatibility-launcher, asset, test, and
engineering-document integrations.

Before working on that project, read:

1. `mobu_tools_manager/AGENTS.md`
2. `mobu_tools_manager/README.md`
3. `../docs/README.md`

Do not treat every file under `Scripts` as project-owned. Unrelated creator
scripts, quarantined scripts, legacy utilities, and machine-local outputs are
read-only unless the user explicitly includes them. A path listed in
`mobu_tools_manager/catalog.py` is an integration input, not blanket permission
to refactor that file.

The active manager tests are under `tests/`. The active MotionBuilder startup
loader is in `../PythonStartup/000_MobuToolsManagerBootstrap.py`. Bridge behavior
belongs to `mobu_tools_manager/features/codex_bridge.py`; the two loose bridge
files are compatibility launchers only.

All MotionBuilder SDK calls and MotionBuilder-owned Qt access must remain on the
main UI thread. Use manager-owned runtime services and deterministic cleanup.

