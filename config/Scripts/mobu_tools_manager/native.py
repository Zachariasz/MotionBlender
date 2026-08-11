"""Import-once adapter for manager-native feature modules."""

from __future__ import absolute_import

import importlib
import sys
import time
import traceback


class NativeAdapter(object):
    def __init__(
        self,
        feature_id,
        module_name,
        entrypoint="execute",
        stop_entrypoint=None,
        diagnostics=None,
        dependency_modules=(),
    ):
        self.feature_id = feature_id
        self.module_name = str(module_name)
        self.entrypoint = entrypoint
        self.stop_entrypoint = stop_entrypoint
        self.diagnostics = diagnostics
        self.dependency_modules = tuple(
            dict.fromkeys(
                [self.module_name]
                + [str(name) for name in dependency_modules]
            )
        )
        self.module = None
        self.import_count = 0
        self.invoke_count = 0
        self.last_load_ms = None
        self.last_dispatch_overhead_ms = None
        self.last_execution_ms = None
        self.last_error = None
        self.resource_handles = []

    @property
    def compiled(self):
        return self.module is not None

    @property
    def loaded(self):
        return self.module is not None

    @property
    def namespace(self):
        if self.module is None:
            return None
        return vars(self.module)

    def _record(self, event, **data):
        if self.diagnostics is not None:
            self.diagnostics.record(
                event,
                self.feature_id,
                module=self.module_name,
                **data
            )

    def precompile(self):
        return self.load()

    def load(self):
        if self.module is not None:
            return self.module
        started = time.perf_counter()
        try:
            self.module = importlib.import_module(self.module_name)
            self.import_count += 1
            self.last_load_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = None
            self._record("native_imported", duration_ms=self.last_load_ms)
            return self.module
        except Exception:
            self.last_error = traceback.format_exc()
            self._record("native_import_error", error=self.last_error)
            raise

    def track_resource(self, resource):
        if resource is not None and all(
            existing is not resource for existing in self.resource_handles
        ):
            self.resource_handles.append(resource)
        return resource

    def invoke(self, *args, **kwargs):
        invoke_started = time.perf_counter()
        self.invoke_count += 1
        module = self.load()
        callback = getattr(module, self.entrypoint, None)
        if not callable(callback):
            raise RuntimeError(
                "%s does not export callable %s"
                % (self.module_name, self.entrypoint)
            )
        started = time.perf_counter()
        self.last_dispatch_overhead_ms = (started - invoke_started) * 1000.0
        try:
            result = callback(*args, **kwargs)
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = None
            self._record("native_invoked", duration_ms=self.last_execution_ms)
            return result
        except Exception:
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = traceback.format_exc()
            self._record(
                "native_invoke_error",
                duration_ms=self.last_execution_ms,
                error=self.last_error,
            )
            raise

    def stop(self):
        if self.module is None or not self.stop_entrypoint:
            return None
        callback = getattr(self.module, self.stop_entrypoint, None)
        if callable(callback):
            return callback()
        return None

    def unload(self):
        self.module = None
        self.resource_handles = []
        for module_name in sorted(
            self.dependency_modules,
            key=lambda name: (name.count("."), len(name)),
            reverse=True,
        ):
            sys.modules.pop(module_name, None)
        importlib.invalidate_caches()

    def status(self):
        return {
            "compiled": self.compiled,
            "loaded": self.loaded,
            "compile_count": self.import_count,
            "execute_count": self.invoke_count,
            "invoke_count": self.invoke_count,
            "last_compile_ms": self.last_load_ms,
            "last_load_ms": self.last_load_ms,
            "last_dispatch_overhead_ms": self.last_dispatch_overhead_ms,
            "last_execution_ms": self.last_execution_ms,
            "last_error": self.last_error,
            "resource_count": len(self.resource_handles),
            "native": True,
        }
