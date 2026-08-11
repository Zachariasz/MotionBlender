"""Compile-once compatibility adapter for existing MotionBuilder scripts."""

from __future__ import absolute_import

import os
import time
import traceback


class LegacyAdapter(object):
    def __init__(
        self,
        feature_id,
        path,
        entrypoint=None,
        stop_entrypoint=None,
        autorun_on_load=True,
        reexec=False,
        diagnostics=None,
    ):
        self.feature_id = feature_id
        self.path = os.path.abspath(path)
        self.entrypoint = entrypoint
        self.stop_entrypoint = stop_entrypoint
        self.autorun_on_load = bool(autorun_on_load)
        self.reexec = bool(reexec)
        self.diagnostics = diagnostics
        self.source = None
        self.code = None
        self.namespace = None
        self.compile_count = 0
        self.execute_count = 0
        self.invoke_count = 0
        self.last_compile_ms = None
        self.last_load_ms = None
        self.last_dispatch_overhead_ms = None
        self.last_execution_ms = None
        self.last_error = None
        self.resource_handles = []

    @property
    def compiled(self):
        return self.code is not None

    @property
    def loaded(self):
        return self.namespace is not None

    def _record(self, event, **data):
        if self.diagnostics is not None:
            self.diagnostics.record(event, self.feature_id, path=self.path, **data)

    def precompile(self):
        if self.code is not None:
            return self.code
        started = time.perf_counter()
        try:
            with open(self.path, "r", encoding="utf-8-sig") as stream:
                self.source = stream.read()
            self.code = compile(self.source, self.path, "exec")
            self.compile_count += 1
            self.last_compile_ms = (time.perf_counter() - started) * 1000.0
            self._record("legacy_compiled", duration_ms=self.last_compile_ms)
            return self.code
        except Exception:
            self.last_error = traceback.format_exc()
            self._record("legacy_compile_error", error=self.last_error)
            raise

    def _new_namespace(self):
        return {
            "__file__": self.path,
            "__name__": "__mobu_tools_legacy__",
            "__package__": None,
        }

    def _execute(self, retain=True):
        self.precompile()
        namespace = self._new_namespace()
        started = time.perf_counter()
        try:
            exec(self.code, namespace, namespace)
            self.execute_count += 1
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = None
            if retain:
                self.namespace = namespace
            self._record("legacy_executed", duration_ms=self.last_execution_ms)
            return namespace
        except Exception:
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = traceback.format_exc()
            self._record(
                "legacy_execute_error",
                duration_ms=self.last_execution_ms,
                error=self.last_error,
            )
            raise

    def load(self):
        if self.namespace is None:
            started = time.perf_counter()
            namespace = self._execute(retain=True)
            self.last_load_ms = (time.perf_counter() - started) * 1000.0
            return namespace
        return self.namespace

    def track_resource(self, resource):
        if resource is not None and all(
            existing is not resource for existing in self.resource_handles
        ):
            self.resource_handles.append(resource)
        return resource

    def invoke(self, *args, **kwargs):
        invoke_started = time.perf_counter()
        self.invoke_count += 1
        if self.reexec:
            self.last_dispatch_overhead_ms = None
            return self._execute(retain=False)

        first_load = self.namespace is None
        namespace = self.load()
        if first_load and self.autorun_on_load:
            self.last_dispatch_overhead_ms = None
            return None
        if not self.entrypoint:
            return None

        callback = namespace.get(self.entrypoint)
        if not callable(callback):
            raise RuntimeError(
                "%s does not export callable %s" % (self.path, self.entrypoint)
            )
        started = time.perf_counter()
        self.last_dispatch_overhead_ms = (started - invoke_started) * 1000.0
        try:
            result = callback(*args, **kwargs)
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = None
            self._record("legacy_invoked", duration_ms=self.last_execution_ms)
            return result
        except Exception:
            self.last_execution_ms = (time.perf_counter() - started) * 1000.0
            self.last_error = traceback.format_exc()
            self._record(
                "legacy_invoke_error",
                duration_ms=self.last_execution_ms,
                error=self.last_error,
            )
            raise

    def stop(self):
        if self.namespace is None or not self.stop_entrypoint:
            return None
        callback = self.namespace.get(self.stop_entrypoint)
        if callable(callback):
            return callback()
        return None

    def unload(self):
        self.namespace = None
        self.resource_handles = []

    def status(self):
        return {
            "compiled": self.compiled,
            "loaded": self.loaded,
            "compile_count": self.compile_count,
            "execute_count": self.execute_count,
            "invoke_count": self.invoke_count,
            "last_compile_ms": self.last_compile_ms,
            "last_load_ms": self.last_load_ms,
            "last_dispatch_overhead_ms": self.last_dispatch_overhead_ms,
            "last_execution_ms": self.last_execution_ms,
            "last_error": self.last_error,
            "resource_count": len(self.resource_handles),
        }
