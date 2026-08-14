"""Manager-native configurable FBX export command."""

from __future__ import absolute_import

from ..exporting.fbx import export_fbx


TOOL_NAME = "FBX Export"


def _sdk_module():
    import pyfbsdk

    return pyfbsdk


def _show_settings(context, sdk):
    from ..exporting.dialog import show_export_settings

    parent = None
    try:
        parent = context.qt_application.activeWindow()
    except Exception:
        pass
    return show_export_settings(
        context.system,
        context.application,
        sdk,
        parent=parent,
    )


def execute(context, invocation=None):
    sdk = _sdk_module()
    try:
        if bool((invocation or {}).get("show_settings")):
            return _show_settings(context, sdk)
        paths = export_fbx(context.system, context.application, sdk)
    except Exception as error:
        sdk.FBMessageBox(TOOL_NAME, str(error), "OK")
        return ()
    sdk.FBMessageBox(TOOL_NAME, "Exported:\n" + "\n".join(paths), "OK")
    return paths
