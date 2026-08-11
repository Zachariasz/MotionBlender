"""Manager-owned event-driven interaction session."""

from __future__ import absolute_import

import traceback

from .cursor_overlay import SessionPresentation
from .numeric_input import NumericInput


CREATED = "CREATED"
ARMING = "ARMING"
ACTIVE = "ACTIVE"
COMMITTING = "COMMITTING"
CANCELLING = "CANCELLING"
CLOSED = "CLOSED"

TRANSFORM_KEY_TO_OPERATION = {
    "G": "move",
    "R": "rotate",
    "S": "scale",
}
TRANSFORM_FEATURE_TO_OPERATION = {
    "transform.move_camera_plane": "move",
    "transform.rotate_mouse_orbit": "rotate",
    "transform.scale_mouse_distance": "scale",
}


class InteractionSession(object):
    def __init__(self, manager, feature_id, strategy, context, invocation=None):
        self.manager = manager
        self.feature_id = str(feature_id)
        self.strategy = strategy
        self.context = context
        self.invocation = dict(invocation or {})
        self.state = CREATED
        self.numeric = NumericInput()
        self.start_cursor = self.invocation.get("launch_cursor")
        if self.start_cursor is None:
            self.start_cursor = context.input.cursor_position()
        self.start_cursor = (
            float(self.start_cursor[0]),
            float(self.start_cursor[1]),
        )
        self.segment_anchor = self.start_cursor
        self.precision_active = False
        self.snap_active = False
        self.presentation = None
        self.undo_transaction = None
        self.error = None
        self.preview_signature = None
        self.pending_finish = None
        self.pending_finish_button = None
        self.capture_started = False

    @property
    def policy(self):
        return self.context.policy

    @property
    def precision_multiplier(self):
        if self.precision_active:
            return self.policy.precision_multiplier
        return 1.0

    @property
    def operation(self):
        operation = self.invocation.get("operation")
        if operation:
            return str(operation).lower()
        operation = TRANSFORM_KEY_TO_OPERATION.get(
            str(self.invocation.get("launcher_key") or "").upper()
        )
        if operation:
            return operation
        return TRANSFORM_FEATURE_TO_OPERATION.get(self.feature_id)

    @property
    def domain(self):
        return str(
            self.invocation.get("domain")
            or self.invocation.get("ui_context")
            or ""
        ).lower()

    def start(self):
        try:
            retire_precision = getattr(
                self.context,
                "retire_legacy_precision_services",
                None,
            )
            if callable(retire_precision):
                retire_precision()
            self.capture_started = True
            if not self.strategy.capture(self):
                self.state = CLOSED
                try:
                    self.strategy.close(self)
                except Exception:
                    pass
                return False
            self.undo_transaction = self.context.undo.begin(
                self.strategy.undo_label
            )
            for prop in self.strategy.undo_properties():
                self.undo_transaction.add_property(prop)
            for model in self.strategy.undo_models():
                self.undo_transaction.add_model_trs(model)
            self.presentation = SessionPresentation(
                self.context,
                self,
                self.strategy.overlay_rect(),
            )
            self.presentation.start()
            self.context.input.claim(
                self,
                self.handle_input,
                self.cancel,
                self.invocation.get("surface"),
            )
            self.state = ARMING
            if self.invocation.get("activate_immediately"):
                launch_payload = dict(
                    self.invocation.get("launch_payload") or {}
                )
                launch_payload.setdefault("cursor", self.start_cursor)
                self._activate(launch_payload)
            else:
                self._update_presentation()
            return True
        except Exception:
            self.error = traceback.format_exc()
            self._fail()
            raise

    def _launcher_released(self):
        launcher_key = self.invocation.get("launcher_key")
        if launcher_key and self.context.input.is_key_down(launcher_key):
            return False
        return not self.context.input.mouse_button_down("left") and not (
            self.context.input.mouse_button_down("right")
        )

    @staticmethod
    def _modifier_active(payload, name):
        normalized = str(name or "").strip().lower()
        key = {
            "ctrl": "control",
            "control": "control",
            "shift": "shift",
            "alt": "alt",
        }.get(normalized, normalized)
        return bool(payload.get(key))

    def _activate(self, payload):
        self.state = ACTIVE
        self.segment_anchor = self.start_cursor
        self.precision_active = self._modifier_active(
            payload,
            self.policy.precision_modifier,
        )
        self.snap_active = self._modifier_active(
            payload,
            self.policy.snap_modifier,
        )
        self.strategy.begin_segment(self)
        self._preview(payload, force=True)

    def _rebase(self, payload):
        self.strategy.rebase(self)
        self.segment_anchor = payload.get(
            "cursor",
            self.context.input.cursor_position(),
        )
        self.preview_signature = None

    def _handle_modifier_transition(self, payload):
        precision = self._modifier_active(
            payload,
            self.policy.precision_modifier,
        )
        snap = self._modifier_active(
            payload,
            self.policy.snap_modifier,
        )
        if (
            precision == self.precision_active
            and snap == self.snap_active
        ):
            return
        self._preview(payload, force=True)
        if self.state != ACTIVE:
            return
        self._rebase(payload)
        self.precision_active = precision
        self.snap_active = snap
        self.preview_signature = None
        # Re-evaluate the exact transition payload in the new mode.  Precision
        # strategies rebase so this is continuous; snapping strategies use the
        # immutable session start to quantize the complete result immediately.
        self._preview(payload, force=True)

    def _handle_key_press(self, payload):
        key = str(payload.get("key") or "").upper()
        if key in ("ESCAPE", "ESC"):
            self.cancel()
            return
        if key in ("ENTER", "RETURN"):
            self.commit()
            return
        if key in ("X", "Y", "Z"):
            axis = key.lower()
            if not self.strategy.constraint.accepts(axis):
                return
            self._preview(payload, force=True)
            if self.state != ACTIVE:
                return
            self._rebase(payload)
            if self.strategy.constraint.press(axis):
                self._preview(payload, force=True)
            return
        handles_key = getattr(self.strategy, "handles_key", None)
        handle_key = getattr(self.strategy, "handle_key_press", None)
        if (
            callable(handles_key)
            and callable(handle_key)
            and handles_key(self, payload)
        ):
            self._preview(payload, force=True)
            if self.state != ACTIVE:
                return
            self._rebase(payload)
            handle_key(self, payload)
            self._preview(payload, force=True)
            return
        if self.numeric.feed(key, payload.get("text", "")):
            self.preview_signature = None
            self._preview(payload, force=True)

    def handle_input(self, payload):
        try:
            return self._handle_input(payload)
        except Exception:
            self.error = traceback.format_exc()
            self._fail()
            return True

    def _handle_input(self, payload):
        if self.state == CLOSED:
            return False
        event_type = payload.get("type")
        if event_type == "key_press":
            launcher_key = str(payload.get("key") or "").upper()
            if launcher_key in TRANSFORM_KEY_TO_OPERATION:
                if not payload.get("auto_repeat"):
                    handles_key = getattr(
                        self.strategy,
                        "handles_key",
                        None,
                    )
                    strategy_handles_launcher = (
                        self.state == ACTIVE
                        and callable(handles_key)
                        and handles_key(self, payload)
                    )
                    if strategy_handles_launcher:
                        self._handle_key_press(payload)
                    else:
                        self.manager.handle_transform_launcher(
                            self,
                            launcher_key,
                            payload,
                        )
                return True
        if self.state == ARMING:
            if self._launcher_released():
                self._activate(payload)
            else:
                return True
        if self.state != ACTIVE:
            return True

        if event_type == "context_menu":
            return True
        if self.pending_finish is not None:
            if (
                event_type == "mouse_release"
                and payload.get("button") == self.pending_finish_button
            ):
                accepted = self.pending_finish
                button = self.pending_finish_button
                self.pending_finish = None
                self.pending_finish_button = None
                self.context.input.arm_terminal_guard(button)
                if accepted:
                    self.commit()
                else:
                    self.cancel()
            return True
        if event_type == "mouse_press":
            button = payload.get("button")
            if button == "left":
                self.pending_finish = True
                self.pending_finish_button = button
            elif button == "right":
                self.pending_finish = False
                self.pending_finish_button = button
            return True

        self._handle_modifier_transition(payload)
        if event_type == "key_press" and not payload.get("auto_repeat"):
            self._handle_key_press(payload)
        elif event_type in ("mouse_move", "key_release"):
            self._preview(payload)
        return True

    def _preview(self, payload, force=False):
        if self.state != ACTIVE:
            return
        signature = self.strategy.input_signature(self, payload)
        if not force and signature == self.preview_signature:
            self._update_presentation()
            return
        request_evaluation = self.strategy.preview(self, payload)
        self.preview_signature = signature
        if request_evaluation is not False:
            self.context.evaluation.request()
        self._update_presentation()

    def _update_presentation(self):
        if self.presentation is None:
            return
        status = dict(self.strategy.status(self) or {})
        tags = []
        if self.precision_active:
            tags.append(
                "PRECISION x%s"
                % ("%g" % self.policy.precision_multiplier)
            )
        if self.snap_active:
            tags.append("SNAP")
        if self.numeric.active:
            tags.append("INPUT %s" % self.numeric.text)
        text = str(status.get("text") or "")
        if tags:
            text = "%s  [%s]" % (text, " | ".join(tags))
        status["text"] = text
        self.presentation.update(status)

    def commit(self):
        if self.state not in (ARMING, ACTIVE):
            return False
        can_commit = getattr(self.strategy, "can_commit", None)
        if callable(can_commit) and not can_commit(self):
            self.pending_finish = None
            self.pending_finish_button = None
            self._update_presentation()
            return False
        self.state = COMMITTING
        try:
            self.strategy.commit(self)
            if self.undo_transaction is not None:
                self.undo_transaction.commit()
        except Exception:
            self.error = traceback.format_exc()
            self._fail()
            return False
        self._close(True)
        return True

    def cancel(self):
        if self.state in (CANCELLING, COMMITTING, CLOSED):
            return self.state == CLOSED
        succeeded = True
        self.state = CANCELLING
        try:
            self.strategy.cancel(self)
        except Exception:
            self.error = traceback.format_exc()
            succeeded = False
        finally:
            if self.undo_transaction is not None:
                try:
                    self.undo_transaction.cancel()
                except Exception:
                    if self.error is None:
                        self.error = traceback.format_exc()
                    succeeded = False
            if not self._close(False):
                succeeded = False
        return succeeded

    def _fail(self):
        if self.state == CLOSED:
            return
        self.state = CANCELLING
        if self.capture_started:
            try:
                self.strategy.cancel(self)
            except Exception:
                if self.error is None:
                    self.error = traceback.format_exc()
        if self.undo_transaction is not None:
            try:
                self.undo_transaction.cancel()
            except Exception:
                if self.error is None:
                    self.error = traceback.format_exc()
        self._close(False)

    def _close(self, accepted):
        succeeded = True
        try:
            self.context.input.release(self)
        except Exception:
            succeeded = False
            if self.error is None:
                self.error = traceback.format_exc()
        if self.presentation is not None:
            try:
                self.presentation.close()
            except Exception:
                succeeded = False
                if self.error is None:
                    self.error = traceback.format_exc()
            self.presentation = None
        restore_focus = getattr(
            self.context,
            "restore_editor_focus",
            None,
        )
        if callable(restore_focus):
            try:
                restore_focus(
                    self.invocation.get("surface"),
                    self.invocation.get("focus_widget"),
                )
            except Exception:
                succeeded = False
                if self.error is None:
                    self.error = traceback.format_exc()
        try:
            self.strategy.close(self)
        except Exception:
            succeeded = False
            if self.error is None:
                self.error = traceback.format_exc()
        finish_cursor_release = getattr(
            getattr(self.context, "overlays", None),
            "finish_cursor_release",
            None,
        )
        if callable(finish_cursor_release):
            try:
                finish_cursor_release(self.invocation.get("surface"))
            except Exception:
                succeeded = False
                if self.error is None:
                    self.error = traceback.format_exc()
        self.state = CLOSED
        self.pending_finish = None
        self.pending_finish_button = None
        self.manager._session_closed(self)
        return succeeded


class InteractionManager(object):
    def __init__(self, context):
        self.context = context
        self.active = None
        self.mode_dispatcher = None
        self.legacy_resolver = None

    def configure_transform_coordinator(
        self,
        mode_dispatcher,
        legacy_resolver=None,
    ):
        self.mode_dispatcher = mode_dispatcher
        self.legacy_resolver = legacy_resolver

    def _record(self, event, **data):
        diagnostics = getattr(self.context, "diagnostics", None)
        if diagnostics is not None:
            diagnostics.record(event, data.pop("feature_id", None), **data)

    @staticmethod
    def _normalized_invocation(operation, invocation=None):
        values = dict(invocation or {})
        values["operation"] = str(operation).lower()
        launcher_key = {
            "move": "G",
            "rotate": "R",
            "scale": "S",
        }.get(values["operation"])
        if launcher_key:
            values["launcher_key"] = launcher_key
        domain = str(
            values.get("domain")
            or values.get("ui_context")
            or ""
        ).lower()
        values["domain"] = domain
        values["ui_context"] = domain
        return values

    def _legacy_records(self):
        if not callable(self.legacy_resolver):
            return []
        return list(self.legacy_resolver() or ())

    def _active_transform_records(self):
        records = []
        if self.active is not None and self.active.state != CLOSED:
            records.append(
                {
                    "kind": "native",
                    "operation": self.active.operation,
                    "owner": self.active,
                    "invocation": dict(self.active.invocation),
                }
            )
        records.extend(self._legacy_records())
        return records

    @staticmethod
    def _record_operation(record):
        return str(record.get("operation") or "").lower()

    def _frozen_invocation(self, record, fallback):
        values = dict(fallback or {})
        launch_cursor = values.get("launch_cursor")
        values.update(dict(record.get("invocation") or {}))
        if launch_cursor is not None:
            values["launch_cursor"] = launch_cursor
        operation = self._record_operation(record)
        if operation:
            values["operation"] = operation
        domain = str(
            values.get("domain")
            or values.get("ui_context")
            or ""
        ).lower()
        values["domain"] = domain
        values["ui_context"] = domain
        return values

    @staticmethod
    def _supports(operation, domain):
        operation = str(operation or "").lower()
        domain = str(domain or "").lower()
        if domain == "timeline":
            return operation == "move"
        return domain in ("viewer", "fcurve")

    def _cancel_record(self, record):
        owner = record.get("owner")
        if record.get("kind") == "native":
            return bool(owner.cancel())
        callback = record.get("cancel")
        if callable(callback):
            result = callback()
            if result is False:
                return False
        return bool(getattr(owner, "finished", True))

    def _cancel_pending_evaluation(self):
        evaluation = getattr(self.context, "evaluation", None)
        callback = getattr(evaluation, "cancel_pending", None)
        if callable(callback):
            callback()
        elif evaluation is not None and hasattr(evaluation, "pending"):
            evaluation.pending = False

    def _force_cleanup(self, records):
        for record in records:
            owner = record.get("owner")
            if record.get("kind") == "native":
                if owner is not None and owner.state != CLOSED:
                    try:
                        owner._fail()
                    except Exception:
                        pass
                continue
            callback = record.get("force_cleanup")
            if callable(callback):
                try:
                    callback()
                except Exception:
                    pass
        input_router = getattr(self.context, "input", None)
        if input_router is not None:
            try:
                force_release = getattr(input_router, "force_release", None)
                if callable(force_release):
                    force_release()
                else:
                    owner = getattr(input_router, "owner", None)
                    if owner is not None:
                        input_router.release(owner)
            except Exception:
                pass
        overlays = getattr(self.context, "overlays", None)
        if overlays is not None:
            owner = getattr(overlays, "cursor_owner", None)
            if owner is not None:
                try:
                    overlays.release_cursor(owner)
                except Exception:
                    pass
            owner = getattr(overlays, "owner", None)
            if owner is not None:
                try:
                    overlays.release(owner)
                except Exception:
                    pass
        self._cancel_pending_evaluation()

    def _ownership_released(self, records):
        if self.active is not None and self.active.state != CLOSED:
            return False
        if self._legacy_records():
            return False
        input_router = getattr(self.context, "input", None)
        if input_router is not None:
            if getattr(input_router, "owner", None) is not None:
                return False
            if getattr(input_router, "callback", None) is not None:
                return False
            if getattr(input_router, "cancel_callback", None) is not None:
                return False
            if getattr(input_router, "surface", None) is not None:
                return False
            if getattr(input_router, "_queue", ()):
                return False
            if bool(getattr(input_router, "_drain_scheduled", False)):
                return False
        overlays = getattr(self.context, "overlays", None)
        if overlays is not None and (
            getattr(overlays, "owner", None) is not None
            or getattr(overlays, "cursor_owner", None) is not None
        ):
            return False
        evaluation = getattr(self.context, "evaluation", None)
        if bool(getattr(evaluation, "pending", False)):
            return False
        for record in records:
            if record.get("kind") != "native":
                continue
            transaction = getattr(
                record.get("owner"),
                "undo_transaction",
                None,
            )
            if transaction is not None and not bool(
                getattr(transaction, "closed", True)
            ):
                return False
        return True

    def route_transform_launch(
        self,
        operation,
        invocation=None,
        starter=None,
    ):
        operation = str(operation).lower()
        invocation = self._normalized_invocation(operation, invocation)
        records = self._active_transform_records()
        if len(records) == 1 and self._record_operation(records[0]) == operation:
            self._record(
                "transform_launcher_repeat_ignored",
                operation=operation,
            )
            return records[0].get("owner")

        frozen = invocation
        if records:
            frozen = self._frozen_invocation(records[0], invocation)
            cancelled = True
            for record in records:
                try:
                    if not self._cancel_record(record):
                        cancelled = False
                except Exception:
                    cancelled = False
            self._cancel_pending_evaluation()
            if not cancelled or not self._ownership_released(records):
                self._force_cleanup(records)
                self._record(
                    "transform_handoff_cancel_failed",
                    requested_operation=operation,
                    previous_operations=[
                        self._record_operation(record)
                        for record in records
                    ],
                )
                return None

        frozen = self._normalized_invocation(operation, frozen)
        if not self._supports(operation, frozen.get("domain")):
            self._record(
                "transform_mode_unsupported",
                requested_operation=operation,
                domain=frozen.get("domain"),
            )
            return None
        callback = starter or self.mode_dispatcher
        if not callable(callback):
            self._record(
                "transform_dispatcher_missing",
                requested_operation=operation,
            )
            return None
        result = callback(operation, frozen)
        self._record(
            "transform_mode_dispatched",
            requested_operation=operation,
            domain=frozen.get("domain"),
            started=result is not None,
        )
        return result

    def handle_transform_launcher(self, session, launcher_key, payload=None):
        if session is not self.active:
            return True
        operation = TRANSFORM_KEY_TO_OPERATION.get(
            str(launcher_key).upper()
        )
        if operation is None:
            return False
        invocation = dict(session.invocation)
        launch_cursor = dict(payload or {}).get("cursor")
        if launch_cursor is not None:
            invocation["launch_cursor"] = launch_cursor
        self.route_transform_launch(operation, invocation)
        return True

    def start(self, feature_id, strategy, invocation=None):
        if self.active is not None and self.active.state != CLOSED:
            requested = self._normalized_invocation(
                TRANSFORM_FEATURE_TO_OPERATION.get(
                    str(feature_id),
                    str((invocation or {}).get("operation") or "move"),
                ),
                invocation,
            )
            if self.active.operation == requested.get("operation"):
                return self.active
            previous = self.active
            record = {
                "kind": "native",
                "owner": previous,
                "operation": previous.operation,
            }
            cancelled = previous.cancel()
            self._cancel_pending_evaluation()
            if (
                not cancelled
                or not self._ownership_released([record])
            ):
                self._force_cleanup(
                    [record]
                )
                return None
        legacy = self._legacy_records()
        if legacy:
            cancelled = True
            for record in legacy:
                try:
                    if not self._cancel_record(record):
                        cancelled = False
                except Exception:
                    cancelled = False
            self._cancel_pending_evaluation()
            if not cancelled or not self._ownership_released(legacy):
                self._force_cleanup(legacy)
                return None
        session = InteractionSession(
            self,
            feature_id,
            strategy,
            self.context,
            invocation,
        )
        self.active = session
        try:
            started = session.start()
        except Exception:
            if self.active is session:
                self.active = None
            return None
        if not started:
            self.active = None
            return None
        return session

    def cancel_active(self):
        if self.active is not None:
            self.active.cancel()

    def cancel_owner(self, feature_id):
        if (
            self.active is not None
            and self.active.feature_id == str(feature_id)
        ):
            self.active.cancel()

    def _session_closed(self, session):
        if self.active is session:
            self.active = None

    def stop(self):
        self.cancel_active()
