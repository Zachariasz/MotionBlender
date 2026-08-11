"""Lifecycle, dispatch, shortcut, and diagnostics orchestration."""

from __future__ import absolute_import

import builtins
import os
import time
import traceback

from .catalog import FEATURES, FEATURE_BY_ID
from .diagnostics import Diagnostics
from .legacy import LegacyAdapter
from .native import NativeAdapter
from .settings import SettingsStore
from .shortcuts import (
    NativeActionDispatcher,
    ShortcutManager,
    find_keyboard_profile,
    keyboard_actions,
    parse_profile_name,
    read_text,
    split_bindings,
)


class MotionBuilderToolsManager(object):
    TRANSFORM_FEATURES = {
        "move": "transform.move_camera_plane",
        "rotate": "transform.rotate_mouse_orbit",
        "scale": "transform.scale_mouse_distance",
    }
    LEGACY_TRANSFORM_CONTROLLERS = {
        "rotate": "_rotate_selected_by_mouse_orbit_active_controller",
        "scale": "_scale_selected_by_mouse_distance_active_controller",
    }

    def __init__(self, scripts_root=None):
        self.scripts_root = os.path.abspath(
            scripts_root or os.path.dirname(os.path.dirname(__file__))
        )
        self.diagnostics = Diagnostics()
        self.adapters = {}
        self.resident_adapters = {}
        self.runtime = None
        self.settings = None
        self.shortcut_manager = None
        self.native_action_dispatcher = None
        self.started = False
        self.ui = None
        self.story_toolbar = None
        self.viewer_toolbar = None
        self.menu_launcher = None
        self.keyboard_path = None
        self.profile_name = ""
        self._idle_callback = self._on_idle_warmup
        self._warmup_queue = []
        self._idle_event = None
        self._idle_registered = False
        self._idle_remove_error_reported = False
        self._file_exit_callback = self._on_file_exit
        self._file_exit_application = None
        self._file_exit_registered = False
        self._shutting_down = False
        self._last_feature_timings = {}
        self._feature_errors = {}
        self._quick_favorites_last_used = {}

    def _record(self, event, feature_id=None, **data):
        return self.diagnostics.record(event, feature_id, **data)

    def _sdk(self):
        import pyfbsdk

        return pyfbsdk

    def _initialize_paths(self):
        sdk = self._sdk()
        user_config = os.path.abspath(sdk.FBSystem().UserConfigPath)
        settings_dir = os.path.join(user_config, "MotionBuilderToolsManager")
        self.settings = SettingsStore(settings_dir)
        self.settings.load()
        backup_dir = os.path.join(settings_dir, "backups", "runtime")
        self.shortcut_manager = ShortcutManager(
            os.path.join(self.scripts_root, "ActionScript.txt"),
            backup_dir,
            rescan_callback=self._rescan_shortcuts,
        )

        action_manager = sdk.FBActionManager()
        try:
            self.profile_name = str(action_manager.CurrentInteractionMode)
        except Exception:
            self.profile_name = self.settings.data.get("active_profile") or "Blender"
        self.keyboard_path = find_keyboard_profile(
            user_config,
            os.path.abspath(sdk.FBSystem().ConfigPath),
            self.profile_name,
        )
        self.settings.data["active_profile"] = self.profile_name

    def _import_first_run_state(self):
        if self.settings.data.get("initialized"):
            return
        actions = {}
        if self.keyboard_path and os.path.isfile(self.keyboard_path):
            actions = keyboard_actions(read_text(self.keyboard_path))
            parsed_profile = parse_profile_name(
                read_text(self.keyboard_path), self.profile_name
            )
            if parsed_profile:
                self.profile_name = parsed_profile
                self.settings.data["active_profile"] = parsed_profile
        for feature in FEATURES:
            self.settings.set_enabled(feature.id, feature.default_enabled)
            binding = feature.default_shortcut
            if feature.action_slot is not None:
                action = actions.get(
                    "action.global.script%s" % feature.action_slot
                )
                if action is not None:
                    binding = action["value"]
            self.settings.set_binding(self.profile_name, feature.id, binding)
        self.settings.data["initialized"] = True
        self.settings.save()
        self._record("first_run_imported", profile=self.profile_name)

    def start(self):
        if self.started:
            return self
        started = time.perf_counter()
        self._initialize_paths()
        self._import_first_run_state()

        from .runtime import RuntimeServices

        self.runtime = RuntimeServices(
            self.diagnostics,
            self.settings.data.get("interaction"),
            self.settings.data.get("story"),
        )
        self.runtime.start()
        native_action_backups = os.path.join(
            self.settings.directory,
            "backups",
            "native-actions",
        )
        self.native_action_dispatcher = NativeActionDispatcher(
            self.keyboard_path,
            native_action_backups,
            lambda: self._rescan_shortcuts(False, True),
            self.runtime.input.QtCore,
        )
        self.runtime.interactions.configure_transform_coordinator(
            self._dispatch_transform_mode,
            self._legacy_transform_records,
        )
        self.runtime.input.configure_transform_launcher(
            self._dispatch_transform_key
        )
        from .story.toolbar import StoryToolbarController

        self.story_toolbar = StoryToolbarController(
            self,
            self.runtime.ui,
        )
        self.story_toolbar.start()
        try:
            from .viewer.toolbar import ViewerToolbarController

            self.viewer_toolbar = ViewerToolbarController(
                self,
                self.runtime.ui,
            )
            self.viewer_toolbar.start()
        except Exception:
            self.viewer_toolbar = None
            self._record(
                "viewer_toolbar_start_error",
                error=traceback.format_exc(),
            )
        self.started = True
        self._register_file_exit()

        for feature in FEATURES:
            if self.is_enabled(feature.id) and feature.resident:
                try:
                    self._start_resident(feature)
                except Exception:
                    self._set_error(feature.id)

        self._schedule_idle_warmup()
        try:
            from .bootstrap import ManagerMenuLauncher

            self.menu_launcher = ManagerMenuLauncher(self)
        except Exception:
            self._record("manager_menu_error", error=traceback.format_exc())
        duration = (time.perf_counter() - started) * 1000.0
        self._record("manager_started", duration_ms=duration)
        return self

    def _register_file_exit(self):
        if self._file_exit_registered:
            return True
        application = (
            self.runtime.application
            if self.runtime is not None
            else self._sdk().FBApplication()
        )
        try:
            application.OnFileExit.Add(self._file_exit_callback)
        except Exception:
            self._record(
                "manager_file_exit_registration_error",
                error=traceback.format_exc(),
            )
            return False
        self._file_exit_application = application
        self._file_exit_registered = True
        self._record("manager_file_exit_registered")
        return True

    def _unregister_file_exit(self):
        application = self._file_exit_application
        if self._file_exit_registered and application is not None:
            try:
                application.OnFileExit.Remove(self._file_exit_callback)
            except Exception:
                self._record(
                    "manager_file_exit_removal_error",
                    error=traceback.format_exc(),
                )
        self._file_exit_application = None
        self._file_exit_registered = False

    def _on_file_exit(self, control, event):
        if self._shutting_down or not self.started:
            return
        self._record("manager_application_exit_requested")
        self.shutdown(application_exit=True)

    def _flush_qt_deferred_deletes(self):
        """Destroy queued Python-owned Qt objects before Qt itself shuts down."""
        try:
            try:
                from PySide6 import QtCore
            except ImportError:
                from PySide2 import QtCore

            application = QtCore.QCoreApplication.instance()
            if application is None:
                return False
            event_container = getattr(
                QtCore.QEvent,
                "Type",
                QtCore.QEvent,
            )
            deferred_delete = getattr(
                event_container,
                "DeferredDelete",
            )
            QtCore.QCoreApplication.sendPostedEvents(
                None,
                deferred_delete,
            )
            self._record("manager_qt_deferred_deletes_flushed")
            return True
        except Exception:
            self._record(
                "manager_qt_deferred_delete_flush_error",
                error=traceback.format_exc(),
            )
            return False

    def is_enabled(self, feature_id):
        feature = self.feature(feature_id)
        if self.settings is None:
            return feature.default_enabled
        return self.settings.enabled(feature_id, feature.default_enabled)

    @staticmethod
    def feature(feature_id):
        try:
            return FEATURE_BY_ID[feature_id]
        except KeyError:
            raise KeyError("unknown MotionBuilder feature: " + str(feature_id))

    def _path(self, relative):
        return os.path.join(self.scripts_root, *relative.split("/"))

    def _adapter(self, feature):
        adapter = self.adapters.get(feature.id)
        if adapter is None:
            if feature.uses_native:
                adapter = NativeAdapter(
                    feature.id,
                    feature.module,
                    entrypoint=feature.entrypoint or "execute",
                    stop_entrypoint=feature.stop_entrypoint,
                    diagnostics=self.diagnostics,
                    dependency_modules=self._implementation_modules(feature),
                )
            else:
                adapter = LegacyAdapter(
                    feature.id,
                    self._path(feature.primary),
                    entrypoint=feature.entrypoint,
                    stop_entrypoint=feature.stop_entrypoint,
                    autorun_on_load=feature.autorun_on_load,
                    reexec=feature.reexec,
                    diagnostics=self.diagnostics,
                )
            self.adapters[feature.id] = adapter
        return adapter

    @staticmethod
    def _implementation_modules(feature):
        modules = []
        for path in feature.implementation_files:
            normalized = path.replace("\\", "/")
            if not normalized.endswith(".py"):
                continue
            module = normalized[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            if module not in modules:
                modules.append(module)
        if feature.module and feature.module not in modules:
            modules.insert(0, feature.module)
        return tuple(modules)

    def _resident_adapter(self, feature, relative_path):
        key = (feature.id, relative_path)
        adapter = self.resident_adapters.get(key)
        if adapter is None:
            adapter = LegacyAdapter(
                feature.id,
                self._path(relative_path),
                diagnostics=self.diagnostics,
            )
            self.resident_adapters[key] = adapter
        return adapter

    def _start_resident(self, feature):
        for dependency in feature.dependencies:
            if not self.is_enabled(dependency):
                self.enable(dependency)
        resource = None
        if feature.resident_files:
            for relative_path in feature.resident_files:
                self._resident_adapter(feature, relative_path).load()
        else:
            adapter = self._adapter(feature)
            if feature.uses_native:
                resource = adapter.invoke(self.runtime.context)
                adapter.track_resource(resource)
            else:
                adapter.load()
            self._capture_resources(feature, adapter)
        self._record("feature_resident_started", feature.id)
        return resource

    def _transform_invocation(self, operation):
        snapshot = dict(self.runtime.context.ui_context or {})
        domain = str(snapshot.get("hovered") or "other").lower()
        launcher_key = {
            "move": "G",
            "rotate": "R",
            "scale": "S",
        }[str(operation).lower()]
        launch_cursor = self.runtime.context.input.cursor_position()
        return {
            "operation": str(operation).lower(),
            "launcher_key": launcher_key,
            "domain": domain,
            "ui_context": domain,
            "surface": snapshot.get("surface"),
            "focus_widget": (
                snapshot.get("hovered_widget")
                or snapshot.get("surface")
            ),
            "surface_generation": snapshot.get("surface_generation", 0),
            "launch_cursor": launch_cursor,
        }

    def _dispatch_transform_key(self, launcher_key, payload):
        operation = {
            "G": "move",
            "R": "rotate",
            "S": "scale",
        }.get(str(launcher_key).upper())
        if operation is None:
            return None
        invocation = self._transform_invocation(operation)
        launch_cursor = dict(payload or {}).get("cursor")
        if launch_cursor is not None:
            invocation["launch_cursor"] = launch_cursor
        invocation["activate_immediately"] = True
        invocation["launch_payload"] = dict(payload or {})
        return self.runtime.interactions.route_transform_launch(
            operation,
            invocation,
            self._dispatch_transform_mode,
        )

    def _dispatch_transform_mode(self, operation, invocation):
        feature_id = self.TRANSFORM_FEATURES.get(str(operation).lower())
        if feature_id is None:
            return None
        return self.dispatch(
            feature_id,
            invocation=invocation,
            _coordinated=True,
        )

    def _legacy_transform_records(self):
        records = []
        seen = set()
        for operation, attr in self.LEGACY_TRANSFORM_CONTROLLERS.items():
            controller = getattr(builtins, attr, None)
            feature_id = self.TRANSFORM_FEATURES[operation]
            adapter = self.adapters.get(feature_id)
            namespace = adapter.namespace if adapter is not None else None
            if controller is None and namespace:
                callback = namespace.get("_get_active_controller")
                if callable(callback):
                    try:
                        controller = callback()
                    except Exception:
                        controller = None
            if (
                controller is None
                or getattr(controller, "finished", True)
                or id(controller) in seen
            ):
                continue
            seen.add(id(controller))
            invocation = dict(
                getattr(controller, "_manager_invocation", {}) or {}
            )
            if not invocation:
                graph_widget = getattr(controller, "graph_widget", None)
                domain = "fcurve" if graph_widget is not None else "viewer"
                invocation = {
                    "domain": domain,
                    "ui_context": domain,
                    "surface": graph_widget,
                }

            def cancel(owner=controller):
                owner._finish(False)
                return bool(getattr(owner, "finished", False))

            def force_cleanup(
                owner=controller,
                controller_attr=attr,
                script_namespace=namespace,
            ):
                stop = getattr(owner, "_stop_interaction", None)
                if callable(stop):
                    stop()
                try:
                    owner.finished = True
                except Exception:
                    pass
                clear = (
                    script_namespace.get("_clear_active_controller")
                    if script_namespace
                    else None
                )
                if callable(clear):
                    clear(owner)
                elif getattr(builtins, controller_attr, None) is owner:
                    setattr(builtins, controller_attr, None)
                try:
                    owner.setParent(None)
                except Exception:
                    pass

            records.append(
                {
                    "kind": "legacy",
                    "operation": operation,
                    "owner": controller,
                    "invocation": invocation,
                    "cancel": cancel,
                    "force_cleanup": force_cleanup,
                }
            )
        return records

    def dispatch(self, feature_id, invocation=None, _coordinated=False):
        feature = self.feature(feature_id)
        if not self.is_enabled(feature_id):
            self._record("dispatch_disabled", feature_id)
            return None
        operation = next(
            (
                name
                for name, candidate in self.TRANSFORM_FEATURES.items()
                if candidate == feature_id
            ),
            None,
        )
        if operation is not None and not _coordinated:
            launch = invocation or self._transform_invocation(operation)
            return self.runtime.interactions.route_transform_launch(
                operation,
                launch,
                self._dispatch_transform_mode,
            )
        started = time.perf_counter()
        try:
            if feature.run_resource_method:
                if feature.run_resource_attr:
                    resource = getattr(builtins, feature.run_resource_attr, None)
                    if resource is None:
                        self._adapter(feature).load()
                        resource = getattr(
                            builtins,
                            feature.run_resource_attr,
                            None,
                        )
                else:
                    resource = self._feature_resource(feature)
                    if resource is None and feature.resident:
                        self._start_resident(feature)
                        resource = self._feature_resource(feature)
                if resource is None:
                    raise RuntimeError(
                        "feature resource was not created: " + feature.id
                    )
                result = getattr(resource, feature.run_resource_method)()
            elif feature.kind == "service" and feature.resident:
                resource = self._feature_resource(feature)
                if resource is None:
                    self._start_resident(feature)
                    resource = self._feature_resource(feature)
                result = resource
                if resource is not None:
                    for status_name in ("status", "status_payload"):
                        status_callback = getattr(resource, status_name, None)
                        if callable(status_callback):
                            result = status_callback()
                            break
            else:
                adapter = self._adapter(feature)
                self._resume_if_needed(feature, adapter)
                if feature.uses_native:
                    if operation is not None:
                        result = adapter.invoke(
                            self.runtime.context,
                            invocation,
                        )
                    elif invocation is not None:
                        result = adapter.invoke(
                            self.runtime.context,
                            invocation,
                        )
                    else:
                        result = adapter.invoke(self.runtime.context)
                    if feature.kind == "service":
                        adapter.track_resource(result)
                elif operation is not None:
                    result = adapter.invoke(invocation)
                else:
                    result = adapter.invoke()
            self._capture_resources(feature, self._adapter(feature))
            elapsed = (time.perf_counter() - started) * 1000.0
            self._last_feature_timings[feature_id] = elapsed
            self._feature_errors.pop(feature_id, None)
            adapter_status = self._adapter(feature).status()
            self._record(
                "dispatch_complete",
                feature_id,
                duration_ms=elapsed,
                adapter_overhead_ms=adapter_status.get(
                    "last_dispatch_overhead_ms"
                ),
                feature_execution_ms=adapter_status.get(
                    "last_execution_ms"
                ),
            )
            self._refresh_ui()
            return result
        except Exception:
            self._set_error(feature_id)
            self._show_error(feature.name, self._feature_errors[feature_id])
            raise

    def enable(self, feature_id):
        feature = self.feature(feature_id)
        if self.is_enabled(feature_id):
            return True
        for dependency in feature.dependencies:
            self.enable(dependency)
        old_value = self.settings.enabled(feature_id, feature.default_enabled)
        old_native_binding = self._current_native_binding(feature)
        self.settings.set_enabled(feature_id, True)
        try:
            if feature.action_slot is not None:
                self._apply_saved_binding(feature)
            if feature.resident:
                self._start_resident(feature)
            self.settings.save()
            self._record("feature_enabled", feature_id)
            self._refresh_ui()
            return True
        except Exception:
            if feature.resident:
                try:
                    self._stop_feature(feature)
                except Exception:
                    pass
            if feature.action_slot is not None:
                try:
                    self._write_binding(
                        feature,
                        split_bindings(old_native_binding),
                        replace_existing=False,
                    )
                except Exception:
                    pass
            self.settings.set_enabled(feature_id, old_value)
            self._set_error(feature_id)
            raise

    def disable(self, feature_id):
        feature = self.feature(feature_id)
        if not self.is_enabled(feature_id):
            return True
        for candidate in FEATURES:
            if (
                feature_id in candidate.dependencies
                and self.is_enabled(candidate.id)
            ):
                self.disable(candidate.id)
        old_value = self.settings.enabled(feature_id, feature.default_enabled)
        old_native_binding = self._current_native_binding(feature)
        self.settings.set_enabled(feature_id, False)
        try:
            if feature.action_slot is not None:
                self._write_binding(feature, (), replace_existing=False)
            self._stop_feature(feature)
            self.settings.save()
            self._record("feature_disabled", feature_id)
            self._refresh_ui()
            return True
        except Exception:
            if feature.action_slot is not None:
                try:
                    self._write_binding(
                        feature,
                        split_bindings(old_native_binding),
                        replace_existing=False,
                    )
                except Exception:
                    pass
            self.settings.set_enabled(feature_id, old_value)
            self._set_error(feature_id)
            raise

    def reload_feature(self, feature_id):
        feature = self.feature(feature_id)
        was_enabled = self.is_enabled(feature_id)
        self._stop_feature(feature)
        if self.runtime is not None and feature.uses_native:
            self.runtime.invalidate_all("feature_reload:" + feature.id)
        adapter = self.adapters.pop(feature_id, None)
        if adapter:
            adapter.unload()
        for key in [key for key in self.resident_adapters if key[0] == feature_id]:
            self.resident_adapters.pop(key).unload()
        if was_enabled and feature.resident:
            self._start_resident(feature)
        self._record("feature_reloaded", feature_id)
        self._refresh_ui()
        return True

    def _stop_feature(self, feature):
        if self.runtime is not None:
            try:
                self.runtime.interactions.cancel_owner(feature.id)
            except Exception:
                pass
        adapter = self.adapters.get(feature.id)
        if adapter is not None:
            try:
                adapter.stop()
            except Exception:
                self._record(
                    "feature_stop_entry_error",
                    feature.id,
                    error=traceback.format_exc(),
                )
            namespace = adapter.namespace
            if namespace:
                self._cleanup_namespace(feature, namespace)
        for key, resident in list(self.resident_adapters.items()):
            if key[0] != feature.id:
                continue
            try:
                resident.stop()
            except Exception:
                pass
            if resident.namespace:
                self._cleanup_namespace(feature, resident.namespace)
        for attr in feature.resource_attrs:
            self._cleanup_builtin_resource(attr)
        if feature.kind == "service" or feature.resident:
            if adapter is not None:
                adapter.unload()
            for key, resident in list(self.resident_adapters.items()):
                if key[0] == feature.id:
                    resident.unload()
        self._record("feature_stopped", feature.id)

    def _cleanup_namespace(self, feature, namespace):
        for callback_name in ("destroy_existing_picker",):
            callback = namespace.get(callback_name)
            if callable(callback):
                try:
                    callback()
                except Exception:
                    pass

        timer = namespace.get("_STARTUP_TIMER")
        if timer is not None:
            self._cleanup_object(timer)

        application = namespace.get("_APP")
        for callback in tuple(namespace.get("_FILE_CALLBACKS", ())):
            if application is not None:
                try:
                    application.OnFileOpenCompleted.Remove(callback)
                except Exception:
                    pass

        menu_specs = (
            ("MENU_PATH", "MENU_ITEM_ID", "on_menu_activate"),
            (
                "LAYOUT_MENU_PATH",
                "LAYOUT_MENU_ITEM_ID",
                "on_layout_menu_activate",
            ),
        )
        try:
            menu_manager = self._sdk().FBMenuManager()
        except Exception:
            menu_manager = None
        for path_name, id_name, callback_name in menu_specs:
            menu_path = namespace.get(path_name)
            item_id = namespace.get(id_name)
            callback = namespace.get(callback_name)
            if menu_manager is None or menu_path is None:
                continue
            try:
                menu = menu_manager.GetMenu(menu_path)
            except Exception:
                menu = None
            if menu is None:
                continue
            if callable(callback):
                try:
                    menu.OnMenuActivate.Remove(callback)
                except Exception:
                    pass
            if item_id is not None:
                try:
                    item = menu.GetItem(item_id)
                    if item is not None:
                        menu.DeleteItem(item)
                except Exception:
                    pass

        window = namespace.get("_PRECISION_TRANSFORM_GIZMO")
        if window is not None:
            self._cleanup_object(window)

    def _cleanup_builtin_resource(self, attr):
        resource = getattr(builtins, attr, None)
        if resource is None:
            return
        self._cleanup_object(resource)
        try:
            setattr(builtins, attr, None)
        except Exception:
            pass

    def _feature_resource(self, feature):
        for attr in feature.resource_attrs:
            resource = getattr(builtins, attr, None)
            if resource is not None:
                return resource
        adapter = self.adapters.get(feature.id)
        if adapter is not None:
            for resource in adapter.resource_handles:
                if resource is not None:
                    return resource
        return None

    @staticmethod
    def _capture_resources(feature, adapter):
        for attr in feature.resource_attrs:
            adapter.track_resource(getattr(builtins, attr, None))

    def _resume_if_needed(self, feature, adapter):
        if (
            not feature.resume_entrypoint
            or not adapter.loaded
            or self._feature_resource(feature) is not None
        ):
            return
        target = adapter.namespace
        parts = feature.resume_entrypoint.split(".")
        for part in parts[:-1]:
            if isinstance(target, dict):
                target = target.get(part)
            else:
                target = getattr(target, part, None)
            if target is None:
                break
        if isinstance(target, dict):
            callback = target.get(parts[-1])
        else:
            callback = getattr(target, parts[-1], None)
        if not callable(callback):
            raise RuntimeError(
                "%s resume entrypoint is unavailable: %s"
                % (feature.id, feature.resume_entrypoint)
            )
        callback()

    @staticmethod
    def _cleanup_object(resource):
        tool = getattr(resource, "tool", None)
        if tool is not None:
            for event_name, callback_name in (
                ("OnPreShow", "on_pre_show"),
                ("OnShow", "on_show"),
            ):
                try:
                    getattr(tool, event_name).Remove(
                        getattr(resource, callback_name)
                    )
                except Exception:
                    pass
            try:
                tool.Visible = False
            except Exception:
                pass
        for method_name in ("stop", "uninstall", "close"):
            method = getattr(resource, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        for method_name in ("deleteLater", "FBDelete"):
            method = getattr(resource, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def binding(self, feature_id):
        feature = self.feature(feature_id)
        return self.settings.binding(
            self.profile_name, feature_id, feature.default_shortcut
        )

    def interaction_settings(self):
        if self.settings is None:
            return {}
        return dict(self.settings.data.get("interaction") or {})

    def update_interaction_settings(self, values):
        if (
            self.runtime is not None
            and self.runtime.interactions.active is not None
        ):
            raise RuntimeError(
                "Finish or cancel the active interaction before changing "
                "interaction settings."
            )
        from .interactions.policy import InteractionPolicy

        policy = InteractionPolicy(values)
        validated = policy.as_dict()
        self.settings.data["interaction"] = validated
        self.settings.save()
        if self.runtime is not None:
            self.runtime.policy = policy
        self._record("interaction_settings_updated", values=validated)
        self._refresh_ui()
        return validated

    def story_settings(self):
        if self.settings is None:
            return {}
        return dict(self.settings.data.get("story") or {})

    def update_story_settings(self, values):
        from .story.settings import validate_story_settings

        validated = validate_story_settings(values)
        self.settings.data["story"] = validated
        self.settings.save()
        if self.runtime is not None:
            self.runtime.story_settings = dict(validated)
        self._record("story_settings_updated", values=validated)
        self._refresh_ui()
        return validated

    def quick_favorites_settings(self):
        from .quick_favorites.settings import (
            validate_quick_favorites_settings,
        )

        if self.settings is None:
            return validate_quick_favorites_settings()
        return validate_quick_favorites_settings(
            self.settings.data.get("quick_favorites")
        )

    def update_quick_favorites_settings(self, values):
        from .quick_favorites.settings import (
            validate_quick_favorites_settings,
        )

        validated = validate_quick_favorites_settings(values)
        for entries in validated["contexts"].values():
            for entry in entries:
                if entry["kind"] != "feature":
                    continue
                target = entry["target"]
                if target not in FEATURE_BY_ID:
                    raise ValueError(
                        "Unknown managed feature ID: " + target
                    )
        self.settings.data["quick_favorites"] = validated
        self.settings.save()
        self._record("quick_favorites_updated", values=validated)
        self._refresh_ui()
        return validated

    def remember_quick_favorite(self, context, key):
        self._quick_favorites_last_used[str(context)] = str(key)

    def last_quick_favorite(self, context):
        return self._quick_favorites_last_used.get(str(context), "")

    def native_action_exists(self, action_name):
        dispatcher = self.native_action_dispatcher
        return bool(
            dispatcher is not None
            and dispatcher.action_exists(action_name)
        )

    def dispatch_native_action(self, action_name):
        dispatcher = self.native_action_dispatcher
        if dispatcher is None:
            raise RuntimeError("Native action dispatch is not available.")
        self._record("native_action_dispatch", action=str(action_name))
        return dispatcher.dispatch(action_name)

    def _validate_interaction_shortcut(self, feature, bindings):
        if not feature.uses_native:
            return
        precision = "SHFT"
        if self.runtime is not None:
            name = self.runtime.policy.precision_modifier.upper()
            precision = {
                "SHIFT": "SHFT",
                "CONTROL": "CTRL",
                "ALT": "ALT",
            }.get(name, name)
        reserved_keys = set("XYZT0123456789")
        reserved_keys.update(("BACKSPACE", "RETURN", "ENTER", "ESC"))
        for binding in bindings:
            value = str(binding).strip().upper().strip("{}")
            chord, _separator, _rest = value.partition(":")
            if _separator and precision in chord.replace("+", " ").split():
                raise ValueError(
                    "A migrated interaction shortcut cannot contain the "
                    "precision modifier."
                )
            launch = (_rest if _separator else chord).split("*", 1)[0]
            launch = launch.strip()
            if launch in reserved_keys:
                raise ValueError(
                    "The launcher key is reserved for active interaction input: "
                    + launch
                )

    def _current_native_binding(self, feature):
        if (
            feature.action_slot is None
            or not self.keyboard_path
            or not os.path.isfile(self.keyboard_path)
        ):
            return ""
        try:
            actions = keyboard_actions(read_text(self.keyboard_path))
            record = actions.get(
                "action.global.script%s" % feature.action_slot
            )
            return record["value"] if record else ""
        except Exception:
            return ""

    def edit_shortcut(self, feature_id, binding_text, replace_existing=False):
        feature = self.feature(feature_id)
        if feature.action_slot is None:
            raise ValueError("feature does not own an ActionScript slot")
        bindings = split_bindings(binding_text)
        self._validate_interaction_shortcut(feature, bindings)
        self._write_binding(
            feature, bindings, replace_existing=replace_existing
        )
        self.settings.set_binding(
            self.profile_name, feature_id, "|".join(bindings)
        )
        self.settings.save()
        self._record(
            "shortcut_edited",
            feature_id,
            binding="|".join(bindings),
            profile=self.profile_name,
        )
        self._refresh_ui()

    def reset_shortcut(self, feature_id):
        feature = self.feature(feature_id)
        return self.edit_shortcut(feature_id, feature.default_shortcut)

    def _apply_saved_binding(self, feature):
        binding = self.settings.binding(
            self.profile_name, feature.id, feature.default_shortcut
        )
        self._write_binding(feature, split_bindings(binding), False)

    def _write_binding(self, feature, bindings, replace_existing):
        if not self.keyboard_path:
            raise RuntimeError(
                "active keyboard interaction-mode file was not found: "
                + self.profile_name
            )
        return self.shortcut_manager.edit_binding(
            self.keyboard_path,
            feature.action_slot,
            bindings,
            replace_existing=replace_existing,
        )

    def _rescan_shortcuts(self, action_script, interaction_mode):
        action_manager = self._sdk().FBActionManager()
        if action_script:
            action_manager.RescanPythonShortcuts()
        if interaction_mode:
            action_manager.RescanCurrentInteractionModeShortcuts()

    def _schedule_idle_warmup(self):
        queue = []
        for feature in FEATURES:
            if (
                self.is_enabled(feature.id)
                and feature.warmup == "idle"
                and not feature.resident
            ):
                queue.append(self._adapter(feature))
        self._warmup_queue = queue
        if not queue:
            return
        try:
            idle_event = self.runtime.system.OnUIIdle
            idle_event.Add(self._idle_callback)
            self._idle_event = idle_event
            self._idle_registered = True
            self._idle_remove_error_reported = False
            self._record("idle_warmup_registered", count=len(queue))
        except Exception:
            self._idle_event = None
            self._idle_registered = False

    def _on_idle_warmup(self, control, event):
        if not self._warmup_queue:
            self._remove_idle_warmup()
            return
        adapter = self._warmup_queue.pop(0)
        try:
            adapter.precompile()
        except Exception:
            self._set_error(adapter.feature_id)
        if not self._warmup_queue:
            self._remove_idle_warmup()

    def _remove_idle_warmup(self):
        if not self._idle_registered:
            self._warmup_queue = []
            self._idle_event = None
            return
        try:
            idle_event = self._idle_event or self.runtime.system.OnUIIdle
            idle_event.Remove(self._idle_callback)
        except Exception as exc:
            if not self._idle_remove_error_reported:
                self._record(
                    "idle_warmup_remove_failed",
                    error="{}: {}".format(type(exc).__name__, exc),
                )
                self._idle_remove_error_reported = True
            return
        self._idle_registered = False
        self._idle_event = None
        self._idle_remove_error_reported = False
        self._warmup_queue = []
        self._record("idle_warmup_finished")

    def feature_status(self, feature_id):
        feature = self.feature(feature_id)
        adapter = self.adapters.get(feature_id)
        status = adapter.status() if adapter else {
            "compiled": False,
            "loaded": False,
            "last_execution_ms": None,
            "last_error": None,
        }
        status.update(
            {
                "enabled": self.is_enabled(feature_id),
                "binding": self.binding(feature_id)
                if feature.action_slot is not None
                else "",
                "last_total_ms": self._last_feature_timings.get(feature_id),
                "last_error": self._feature_errors.get(feature_id)
                or status.get("last_error"),
            }
        )
        return status

    def export_diagnostics(self, path):
        statuses = dict(
            (feature.id, self.feature_status(feature.id)) for feature in FEATURES
        )
        return self.diagnostics.export(
            path,
            {
                "manager": {
                    "scripts_root": self.scripts_root,
                    "profile": self.profile_name,
                    "keyboard_path": self.keyboard_path,
                },
                "features": statuses,
            },
        )

    def _set_error(self, feature_id):
        details = traceback.format_exc()
        self._feature_errors[feature_id] = details
        self._record("feature_error", feature_id, error=details)
        self._refresh_ui()

    def _show_error(self, title, details):
        try:
            self._sdk().FBMessageBox(
                "MotionBuilder Tools Manager - " + title,
                details[-2000:],
                "OK",
            )
        except Exception:
            print(details)

    def show_manager(self):
        if self.ui is None:
            from .ui import ManagerWindow

            self.ui = ManagerWindow(self)
        self.ui.refresh()
        self.ui.show()
        self.ui.raise_()
        self.ui.activateWindow()
        return self.ui

    def _refresh_ui(self):
        if self.menu_launcher is not None:
            try:
                self.menu_launcher.sync_bridge_state()
            except Exception:
                pass
        if self.ui is not None:
            try:
                self.ui.refresh()
            except Exception:
                pass
        if self.viewer_toolbar is not None:
            try:
                self.viewer_toolbar.refresh()
            except Exception:
                pass

    def shutdown(self, application_exit=False):
        if not self.started or self._shutting_down:
            return
        self._shutting_down = True
        self._unregister_file_exit()
        try:
            self._remove_idle_warmup()
            if self.viewer_toolbar is not None:
                try:
                    self.viewer_toolbar.stop()
                except Exception:
                    self._record(
                        "viewer_toolbar_stop_error",
                        error=traceback.format_exc(),
                    )
                self.viewer_toolbar = None
            if self.story_toolbar is not None:
                try:
                    self.story_toolbar.stop()
                except Exception:
                    self._record(
                        "story_toolbar_stop_error",
                        error=traceback.format_exc(),
                    )
                self.story_toolbar = None
            if self.ui is not None:
                try:
                    self.ui.close()
                    self.ui.deleteLater()
                except Exception:
                    pass
                self.ui = None
            if self.menu_launcher is not None:
                try:
                    self.menu_launcher.stop()
                except Exception:
                    pass
                self.menu_launcher = None
            if self.native_action_dispatcher is not None:
                try:
                    self.native_action_dispatcher.stop()
                except Exception:
                    self._record(
                        "native_action_restore_error",
                        error=traceback.format_exc(),
                    )
                self.native_action_dispatcher = None
            for feature in reversed(FEATURES):
                if feature.resident or feature.id in self.adapters:
                    try:
                        self._stop_feature(feature)
                    except Exception:
                        self._record(
                            "shutdown_feature_error",
                            feature.id,
                            error=traceback.format_exc(),
                        )
            if self.runtime is not None:
                try:
                    self.runtime.stop()
                except Exception:
                    self._record(
                        "shutdown_runtime_error",
                        error=traceback.format_exc(),
                    )
                self.runtime = None
            # All manager-owned top-level widgets and QObject services have
            # queued deleteLater() by this point. Process only DeferredDelete,
            # not arbitrary UI/input events, while MotionBuilder's Qt runtime
            # is still alive.
            self._flush_qt_deferred_deletes()
            self.started = False
            self._record(
                "manager_stopped",
                application_exit=bool(application_exit),
            )
        finally:
            self.started = False
            self._shutting_down = False
