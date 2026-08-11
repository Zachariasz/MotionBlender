"""Shared, event-driven MotionBuilder runtime services.

The services are intentionally conservative in this compatibility release:
legacy scripts do not use them yet, but migrated features receive the same
``CommandContext`` and avoid rebuilding scene/UI state independently.
"""

from __future__ import absolute_import

import builtins
import time
from contextlib import contextmanager


def _qt_modules():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    return QtCore, QtWidgets


class SelectionCache(object):
    def __init__(self, sdk):
        self.sdk = sdk
        self.generation = 0
        self._built_generation = -1
        self._models = ()

    def invalidate(self):
        self.generation += 1

    def snapshot(self):
        if self._built_generation != self.generation:
            try:
                models = self.sdk.FBModelList()
                self.sdk.FBGetSelectedModels(models)
                self._models = tuple(models)
                self._built_generation = self.generation
            except Exception:
                self.invalidate()
                self._models = ()
                raise
        return self._models


class SceneIndex(object):
    def __init__(self, scene):
        self.scene = scene
        self.generation = 0
        self._components = ()
        self._by_name = {}
        self._dirty = True

    def invalidate(self):
        self.generation += 1
        self._dirty = True

    def reset(self, scene):
        self.scene = scene
        self._components = ()
        self._by_name = {}
        self.invalidate()

    def add(self, component):
        self.generation += 1
        if self._dirty or component is None:
            return
        if component not in self._components:
            self._components = self._components + (component,)
            for attribute in ("LongName", "Name"):
                try:
                    name = getattr(component, attribute)
                except Exception:
                    continue
                if name:
                    bucket = self._by_name.setdefault(str(name), [])
                    if all(existing is not component for existing in bucket):
                        bucket.append(component)

    def remove(self, component):
        self.generation += 1
        if self._dirty or component is None:
            return
        self._components = tuple(
            candidate
            for candidate in self._components
            if candidate is not component
        )
        for name, candidates in list(self._by_name.items()):
            retained = [
                candidate
                for candidate in candidates
                if candidate is not component
            ]
            if retained:
                self._by_name[name] = retained
            else:
                self._by_name.pop(name, None)

    def _rebuild(self):
        components = tuple(self.scene.Components)
        by_name = {}
        for component in components:
            for attribute in ("LongName", "Name"):
                try:
                    name = getattr(component, attribute)
                except Exception:
                    continue
                if name:
                    bucket = by_name.setdefault(str(name), [])
                    if all(existing is not component for existing in bucket):
                        bucket.append(component)
        self._components = components
        self._by_name = by_name
        self._dirty = False

    def components(self):
        if self._dirty:
            self._rebuild()
        return self._components

    def named(self, name):
        if self._dirty:
            self._rebuild()
        return tuple(self._by_name.get(str(name), ()))


class FCurveService(object):
    def __init__(self, sdk, scene_index):
        self.sdk = sdk
        self.scene_index = scene_index
        self._utility = None
        self._properties_generation = -1
        self._displayed_properties = ()

    def invalidate(self):
        self._properties_generation = -1
        self._displayed_properties = ()
        self._utility = None

    def _editor_utility(self):
        if self._utility is None:
            self._utility = self.sdk.FBFCurveEditorUtility()
        return self._utility

    def displayed_properties(self, refresh=False):
        generation = self.scene_index.generation
        if refresh or self._properties_generation != generation:
            properties = []
            error = None
            for arguments in (
                (properties, False, None),
                (properties, False),
                (properties,),
            ):
                try:
                    self._editor_utility().GetProperties(*arguments)
                    error = None
                    break
                except TypeError as exception:
                    error = exception
            if error is not None:
                raise error
            self._displayed_properties = tuple(properties)
            self._properties_generation = generation
        return self._displayed_properties

    def displayed_fcurves(self, take=None, layer=None):
        """Resolve curves for displayed properties without caching key state."""
        if take is None:
            try:
                take = self.sdk.FBSystem().CurrentTake
            except Exception:
                take = None
        if layer is None and take is not None:
            try:
                layer = take.GetCurrentLayer()
            except Exception:
                layer = None
        curves = []
        seen = set()
        for prop in self.displayed_properties():
            node = None
            try:
                node = prop.GetAnimationNode()
            except Exception:
                pass
            if node is None:
                continue
            for candidate in self._walk_animation_nodes(node):
                fcurve = None
                if layer is not None:
                    try:
                        fcurve = candidate.GetFCurve(layer)
                    except Exception:
                        pass
                if fcurve is None:
                    fcurve = getattr(candidate, "FCurve", None)
                if fcurve is not None and id(fcurve) not in seen:
                    seen.add(id(fcurve))
                    curves.append(fcurve)
        return tuple(curves)

    def _walk_animation_nodes(self, node):
        yield node
        try:
            children = tuple(node.Nodes)
        except Exception:
            children = ()
        for child in children:
            for descendant in self._walk_animation_nodes(child):
                yield descendant

    @staticmethod
    def selected_keys(fcurve):
        """Key selection and values are deliberately read fresh every call."""
        selected = []
        for index in range(len(fcurve.Keys)):
            try:
                if fcurve.Keys[index].Selected:
                    selected.append((index, fcurve.Keys[index]))
            except Exception:
                continue
        return tuple(selected)

    def whole_scene_fcurve_records(self):
        """Explicit lazy fallback retaining owners for undo registration."""
        records = []
        seen = set()
        try:
            take = self.sdk.FBSystem().CurrentTake
            layer = take.GetCurrentLayer() if take is not None else None
        except Exception:
            layer = None

        def add_curve(prop, node, curve):
            if curve is not None and id(curve) not in seen:
                seen.add(id(curve))
                records.append((prop, node, curve))

        for component in self.scene_index.components():
            try:
                if isinstance(component, self.sdk.FBFCurve):
                    add_curve(None, None, component)
            except Exception:
                pass
            try:
                properties = tuple(component.PropertyList)
            except Exception:
                properties = ()
            for prop in properties:
                try:
                    if not prop.IsAnimatable():
                        continue
                    root = prop.GetAnimationNode()
                except Exception:
                    continue
                for node in self._walk_animation_nodes(root):
                    curve = None
                    if layer is not None:
                        try:
                            curve = node.GetFCurve(layer)
                        except Exception:
                            pass
                    try:
                        if curve is None:
                            curve = node.FCurve
                    except Exception:
                        pass
                    add_curve(prop, node, curve)
            try:
                nodes = component.AnimationNode
            except Exception:
                nodes = None
            if nodes is None:
                continue
            for node in self._walk_animation_nodes(nodes):
                curve = None
                if layer is not None:
                    try:
                        curve = node.GetFCurve(layer)
                    except Exception:
                        pass
                if curve is None:
                    curve = getattr(node, "FCurve", None)
                add_curve(None, node, curve)
        return tuple(records)

    def whole_scene_fcurves(self):
        return tuple(
            record[2] for record in self.whole_scene_fcurve_records()
        )

    def displayed_time_span(self, editor=None):
        try:
            return self._editor_utility().GetTimeSpan(editor)
        except Exception:
            return self._editor_utility().GetTimeSpan()


class UIContextService(object):
    WINDOW_CLASSES = (
        ("fcurve", ("fcurve", "curve editor")),
        ("timeline", ("timeline", "transport")),
        ("navigator", ("navigator",)),
        ("story", ("story",)),
        ("character_controls", ("character controls", "charactercontrols")),
        ("viewer", ("viewer", "render window", "viewport")),
    )
    SURFACE_NAMES = {
        "fcurve": ("fcurve",),
        "timeline": ("timecursor",),
        "viewer": ("viewerwithrightbar",),
    }

    def __init__(self, input_router=None):
        QtCore, QtWidgets = _qt_modules()
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.input_router = input_router
        self.app = QtWidgets.QApplication.instance()
        self.active_widget = None
        self.active_surface = None
        self.hovered_widget = None
        self.hovered_surface = None
        self.active_classification = "other"
        self.hovered_classification = "other"
        self._surface_cache = {}
        self._surface_generations = {}
        self._mouse_tracking = {}
        self._event_observers = []
        self.invalidation_callback = None
        self.activation_callback = None
        self.surface_enter_callback = None
        self.installed = False
        outer = self

        class EventFilter(QtCore.QObject):
            def eventFilter(self, watched, event):
                consumed = False
                try:
                    consumed = bool(outer._observe(watched, event))
                except Exception:
                    pass
                if consumed:
                    return True
                if outer.input_router is not None:
                    try:
                        return bool(
                            outer.input_router.handle_qt_event(
                                watched,
                                event,
                            )
                        )
                    except Exception:
                        pass
                return False

        self.filter = EventFilter()

    @staticmethod
    def _description(widget):
        parts = []
        for name in ("objectName", "windowTitle", "accessibleName"):
            try:
                value = getattr(widget, name)()
            except Exception:
                value = ""
            if value:
                parts.append(str(value))
        try:
            parts.append(widget.metaObject().className())
        except Exception:
            parts.append(type(widget).__name__)
        return " ".join(parts).lower()

    def classify(self, widget):
        current = widget
        while current is not None:
            text = self._description(current)
            for classification, needles in self.WINDOW_CLASSES:
                if any(needle in text for needle in needles):
                    return classification
            try:
                current = current.parentWidget()
            except Exception:
                current = None
        return "other"

    @staticmethod
    def _accessible_name(widget):
        try:
            return str(widget.accessibleName() or "").strip().lower()
        except Exception:
            return ""

    @staticmethod
    def _valid_widget(widget):
        """Reject stale PySide wrappers left by MotionBuilder UI rebuilds."""
        if widget is None:
            return False
        try:
            try:
                import shiboken6 as shiboken
            except ImportError:
                import shiboken2 as shiboken
            return bool(shiboken.isValid(widget))
        except Exception:
            try:
                widget.metaObject()
                return True
            except (AttributeError, RuntimeError, ReferenceError):
                return False

    @staticmethod
    def _root_widget(widget):
        current = widget
        root = widget
        while current is not None:
            root = current
            try:
                current = current.parentWidget()
            except Exception:
                current = None
        return root

    @staticmethod
    def _contains_global(widget, cursor):
        try:
            top_left = widget.mapToGlobal(widget.rect().topLeft())
            x = float(top_left.x())
            y = float(top_left.y())
            width = float(widget.width())
            height = float(widget.height())
            return (
                widget.isVisible()
                and width > 20.0
                and height > 10.0
                and x <= cursor[0] <= x + width
                and y <= cursor[1] <= y + height
            )
        except Exception:
            return False

    def _cursor_position(self):
        try:
            from PySide6 import QtGui
        except ImportError:
            from PySide2 import QtGui
        point = QtGui.QCursor.pos()
        return float(point.x()), float(point.y())

    def _enable_mouse_tracking(self, widget):
        if widget is None or id(widget) in self._mouse_tracking:
            return
        try:
            original = bool(widget.hasMouseTracking())
            self._mouse_tracking[id(widget)] = (widget, original)
            if not original:
                widget.setMouseTracking(True)
        except Exception:
            pass

    def _canonical_surface(self, widget, classification, cursor=None):
        exact_names = self.SURFACE_NAMES.get(classification, ())
        if widget is None or not exact_names:
            return None
        cursor = cursor or self._cursor_position()
        current = widget
        while current is not None:
            if (
                self._accessible_name(current) in exact_names
                and self._contains_global(current, cursor)
            ):
                self._enable_mouse_tracking(current)
                self._enable_mouse_tracking(widget)
                return current
            try:
                current = current.parentWidget()
            except Exception:
                current = None

        root = self._root_widget(widget)
        cache_key = (classification, id(root))
        cached = self._surface_cache.get(cache_key)
        if (
            cached is not None
            and self._accessible_name(cached) in exact_names
            and self._contains_global(cached, cursor)
        ):
            self._enable_mouse_tracking(cached)
            self._enable_mouse_tracking(widget)
            return cached

        try:
            candidates = root.findChildren(self.QtWidgets.QWidget)
        except Exception:
            candidates = ()
        matches = []
        for candidate in candidates:
            if self._accessible_name(candidate) not in exact_names:
                continue
            if not self._contains_global(candidate, cursor):
                continue
            try:
                area = int(candidate.width()) * int(candidate.height())
            except Exception:
                area = 0
            matches.append((area, candidate))
        if not matches:
            self._surface_cache.pop(cache_key, None)
            return None
        matches.sort(key=lambda item: item[0])
        surface = matches[0][1]
        self._surface_cache[cache_key] = surface
        self._enable_mouse_tracking(surface)
        self._enable_mouse_tracking(widget)
        return surface

    def surface_generation(self, surface):
        return int(self._surface_generations.get(id(surface), 0))

    def find_surface_geometry(self, classification):
        """Return immutable global geometry without leaking a native Qt wrapper.

        MotionBuilder rebuilds QOpenGL-backed editor surfaces during operations
        such as naming a Timeline marker.  A resident service must therefore not
        retain the borrowed PySide wrapper returned by ``allWidgets()``.
        """
        classification = str(classification or "").strip().lower()
        exact_names = self.SURFACE_NAMES.get(classification, ())
        if self.app is None or not exact_names:
            return None
        try:
            widgets = tuple(self.app.allWidgets())
        except Exception:
            return None

        matches = []
        for candidate in widgets:
            if not self._valid_widget(candidate):
                continue
            if self._accessible_name(candidate) not in exact_names:
                continue
            if self.classify(candidate) != classification:
                continue
            try:
                if not candidate.isVisible():
                    continue
                width = int(candidate.width())
                height = int(candidate.height())
                if width <= 20 or height <= 10:
                    continue
                top_left = candidate.mapToGlobal(candidate.rect().topLeft())
                geometry = (
                    int(top_left.x()),
                    int(top_left.y()),
                    width,
                    height,
                )
            except Exception:
                continue
            matches.append((width * height, geometry))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def find_surface_attachment(self, classification):
        """Return a stable parent pane and pane-local surface geometry.

        The native editor surface remains a borrowed, volatile wrapper. The
        returned parent is only for immediately parenting a manager-owned
        child. The child then owns the durable link to its stable pane.
        """
        classification = str(classification or "").strip().lower()
        exact_names = self.SURFACE_NAMES.get(classification, ())
        if self.app is None or not exact_names:
            return None
        try:
            widgets = tuple(self.app.allWidgets())
        except Exception:
            return None

        matches = []
        for candidate in widgets:
            if not self._valid_widget(candidate):
                continue
            if self._accessible_name(candidate) not in exact_names:
                continue
            if self.classify(candidate) != classification:
                continue
            try:
                if not candidate.isVisible():
                    continue
                host = candidate.parentWidget()
                if not self._valid_widget(host):
                    continue
                surface_geometry = candidate.geometry()
                geometry = (
                    int(surface_geometry.x()),
                    int(surface_geometry.y()),
                    int(surface_geometry.width()),
                    int(surface_geometry.height()),
                )
                if geometry[2] <= 20 or geometry[3] <= 10:
                    continue
            except RuntimeError:
                continue
            matches.append((geometry[2] * geometry[3], host, geometry))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        _area, host, geometry = matches[0]
        return host, geometry

    def _bump_surface_generation(self, surface):
        if surface is None:
            return
        key = id(surface)
        self._surface_generations[key] = (
            self._surface_generations.get(key, 0) + 1
        )

    def invalidate(self):
        for widget, original in tuple(self._mouse_tracking.values()):
            try:
                widget.setMouseTracking(original)
            except Exception:
                pass
        self._mouse_tracking = {}
        self._surface_cache = {}
        self._surface_generations = {}
        self.active_surface = None
        self.hovered_surface = None

    def _observe(self, watched, event):
        event_type = event.type()
        qevent = self.QtCore.QEvent
        qevent_type = getattr(qevent, "Type", qevent)

        def event_value(name):
            value = getattr(qevent, name, None)
            if value is None:
                value = getattr(qevent_type, name, None)
            return value

        focus_types = set(
            value
            for value in (
                event_value("FocusIn"),
                event_value("WindowActivate"),
            )
            if value is not None
        )
        hover_types = set(
            value
            for value in (
                event_value("Enter"),
                event_value("MouseMove"),
            )
            if value is not None
        )
        if event_type in focus_types:
            self.active_widget = watched
            self.active_classification = self.classify(watched)
            self.active_surface = self._canonical_surface(
                watched,
                self.active_classification,
            )
            if (
                event_type == event_value("WindowActivate")
                and callable(self.activation_callback)
            ):
                callback = self.activation_callback
                callback(self.active_surface)

                def post_activation_cleanup():
                    if self.activation_callback is callback:
                        callback(None)

                try:
                    self.QtCore.QTimer.singleShot(
                        0,
                        post_activation_cleanup,
                    )
                except Exception:
                    pass
        if event_type in hover_types:
            self.hovered_widget = watched
            self.hovered_classification = self.classify(watched)
            self.hovered_surface = self._canonical_surface(
                watched,
                self.hovered_classification,
            )
            if (
                event_type == event_value("Enter")
                and self.hovered_surface is not None
                and callable(self.surface_enter_callback)
            ):
                self.surface_enter_callback(self.hovered_surface)

        generation_types = set(
            value
            for value in (
                event_value("Wheel"),
                event_value("Resize"),
                event_value("DevicePixelRatioChange"),
            )
            if value is not None
        )
        mouse_move = event_value("MouseMove")
        destroy_type = event_value("Destroy")
        needs_surface = (
            event_type in generation_types
            or event_type == mouse_move
            or event_type == destroy_type
        )
        surface = None
        if needs_surface:
            surface = self._canonical_surface(
                watched,
                self.classify(watched),
            )
        if event_type in generation_types:
            self._bump_surface_generation(surface)
        if event_type == mouse_move and surface is not None:
            try:
                middle = getattr(
                    getattr(
                        self.QtCore.Qt,
                        "MouseButton",
                        self.QtCore.Qt,
                    ),
                    "MiddleButton",
                )
                if event.buttons() & middle:
                    self._bump_surface_generation(surface)
            except Exception:
                pass
        if event_type == destroy_type:
            self._bump_surface_generation(surface)
            if callable(self.invalidation_callback):
                self.invalidation_callback(surface or watched)
            self._surface_cache = dict(
                (key, value)
                for key, value in self._surface_cache.items()
                if value is not watched and value is not surface
            )
            self._mouse_tracking = dict(
                (key, value)
                for key, value in self._mouse_tracking.items()
                if value[0] is not watched and value[0] is not surface
            )
        consumed = False
        for callback in tuple(self._event_observers):
            try:
                consumed = bool(callback(watched, event)) or consumed
            except Exception:
                pass
        return consumed

    def add_event_observer(self, callback):
        if callback not in self._event_observers:
            self._event_observers.append(callback)

    def remove_event_observer(self, callback):
        try:
            self._event_observers.remove(callback)
        except ValueError:
            pass

    def start(self):
        if not self.installed and self.app is not None:
            self.app.installEventFilter(self.filter)
            self.installed = True

    def stop(self):
        if self.installed and self.app is not None:
            try:
                self.app.removeEventFilter(self.filter)
            except Exception:
                pass
        self.installed = False
        self.invalidate()

    def snapshot(self):
        hovered_widget = self.hovered_widget
        hovered_classification = self.hovered_classification
        hovered_surface = self.hovered_surface
        if self.app is not None:
            try:
                from PySide6 import QtGui
            except ImportError:
                try:
                    from PySide2 import QtGui
                except ImportError:
                    QtGui = None
            if QtGui is not None:
                try:
                    candidate = self.app.widgetAt(QtGui.QCursor.pos())
                    if candidate is not None:
                        point = QtGui.QCursor.pos()
                        hovered_widget = candidate
                        hovered_classification = self.classify(candidate)
                        hovered_surface = self._canonical_surface(
                            candidate,
                            hovered_classification,
                            (float(point.x()), float(point.y())),
                        )
                        self.hovered_widget = candidate
                        self.hovered_classification = hovered_classification
                        self.hovered_surface = hovered_surface
                except Exception:
                    pass
        return {
            "active_widget": self.active_widget,
            "active": self.active_classification,
            "active_surface": self.active_surface,
            "hovered_widget": hovered_widget,
            "hovered": hovered_classification,
            "surface": hovered_surface,
            "surface_generation": (
                self.surface_generation(hovered_surface)
                if hovered_surface is not None
                else 0
            ),
        }

    @staticmethod
    def _is_within_surface(widget, surface):
        if widget is None or surface is None:
            return False
        current = widget
        while current is not None:
            if current is surface:
                return True
            try:
                current = current.parentWidget()
            except Exception:
                return False
        return False

    def restore_focus(self, surface, preferred_widget=None):
        if self.app is None or surface is None:
            return False
        target = (
            preferred_widget
            if self._is_within_surface(preferred_widget, surface)
            else surface
        )

        def apply_focus():
            try:
                if self.app.activeModalWidget() is not None:
                    return
            except Exception:
                pass
            try:
                state_container = getattr(
                    self.QtCore.Qt,
                    "ApplicationState",
                    self.QtCore.Qt,
                )
                active_state = getattr(
                    state_container,
                    "ApplicationActive",
                )
                if self.app.applicationState() != active_state:
                    return
            except Exception:
                pass
            try:
                window = target.window()
                if window is not None:
                    window.activateWindow()
            except Exception:
                pass
            try:
                reason_container = getattr(
                    self.QtCore.Qt,
                    "FocusReason",
                    self.QtCore.Qt,
                )
                target.setFocus(
                    getattr(reason_container, "OtherFocusReason")
                )
            except Exception:
                try:
                    target.setFocus()
                except Exception:
                    pass

        apply_focus()
        return True


class EvaluationScheduler(object):
    def __init__(self, scene):
        self.scene = scene
        self.pending = False
        self.fcurve_refresh_pending = False
        self.error_callback = None

    def request(self):
        if self.pending:
            return
        self.pending = True
        try:
            QtCore, _QtWidgets = _qt_modules()
            QtCore.QTimer.singleShot(0, self.flush)
        except Exception:
            self.flush()

    def request_fcurve(self):
        self.fcurve_refresh_pending = True
        self.request()

    @staticmethod
    def _refresh_fcurve_animation():
        from pyfbsdk import FBPlayerControl, FBSystem, FBTime

        system = FBSystem()
        player = FBPlayerControl()
        current_time = FBTime(system.LocalTime.Get())
        current_ticks = int(current_time.Get())
        try:
            mode = player.GetTransportFps()
            frame_ticks = abs(
                int(FBTime(0, 0, 0, 1, 0, mode).Get())
            )
        except Exception:
            frame_ticks = abs(int(FBTime(0, 0, 0, 1).Get()))
        frame_ticks = max(1, frame_ticks)
        refresh_ticks = current_ticks + frame_ticks
        try:
            take = system.CurrentTake
            time_span = take.LocalTimeSpan if take is not None else None
            start_ticks = int(time_span.GetStart().Get())
            stop_ticks = int(time_span.GetStop().Get())
            if (
                refresh_ticks > stop_ticks
                and current_ticks - frame_ticks >= start_ticks
            ):
                refresh_ticks = current_ticks - frame_ticks
        except Exception:
            pass
        refresh_succeeded = bool(player.Goto(FBTime(refresh_ticks)))
        restore_succeeded = bool(player.Goto(current_time))
        return refresh_succeeded and restore_succeeded

    def _evaluate(self, fcurve_refresh):
        if fcurve_refresh:
            try:
                if self._refresh_fcurve_animation():
                    return True
            except Exception:
                pass
        return self.scene.Evaluate()

    def flush(self):
        if not self.pending:
            return
        self.pending = False
        fcurve_refresh = self.fcurve_refresh_pending
        self.fcurve_refresh_pending = False
        try:
            self._evaluate(fcurve_refresh)
        except Exception:
            callback = self.error_callback
            if callable(callback):
                callback()

    def flush_now(self):
        self.pending = False
        fcurve_refresh = self.fcurve_refresh_pending
        self.fcurve_refresh_pending = False
        try:
            return self._evaluate(fcurve_refresh)
        except Exception:
            callback = self.error_callback
            if callable(callback):
                callback()
            return None

    def cancel_pending(self):
        self.pending = False
        self.fcurve_refresh_pending = False

    def stop(self):
        self.pending = False
        self.fcurve_refresh_pending = False


class InputRouter(object):
    """Single Qt input boundary for all manager-owned interactions."""

    KEY_NAMES = {
        0x01000000: "ESCAPE",
        0x01000003: "BACKSPACE",
        0x01000004: "RETURN",
        0x01000005: "ENTER",
        0x01000020: "SHIFT",
        0x01000021: "CONTROL",
        0x01000022: "ALT",
    }
    VIRTUAL_KEYS = {
        "G": 0x47,
        "R": 0x52,
        "S": 0x53,
        "SHIFT": 0x10,
        "CONTROL": 0x11,
        "LEFT": 0x01,
        "RIGHT": 0x02,
    }

    def __init__(self, native_capture_releaser=None):
        QtCore, QtWidgets = _qt_modules()
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        try:
            from PySide6 import QtGui
        except ImportError:
            from PySide2 import QtGui
        self.QtGui = QtGui
        self.owner = None
        self.callback = None
        self.cancel_callback = None
        self.transform_launcher = None
        self.character_keying_launcher = None
        self.surface = None
        self._queue = []
        self._drain_scheduled = False
        self._guard_context_menu_until = 0.0
        self._last_mouse_cursor = None
        self._native_capture_releaser = native_capture_releaser

    def configure_transform_launcher(self, callback):
        self.transform_launcher = callback

    def configure_character_keying_launcher(self, callback):
        self.character_keying_launcher = callback

    def clear_character_keying_launcher(self, callback=None):
        current = getattr(self, "character_keying_launcher", None)
        if callback is None or current is callback:
            self.character_keying_launcher = None

    def claim(self, owner, callback, cancel_callback, surface=None):
        if self.owner is not None and self.owner is not owner:
            previous_cancel = self.cancel_callback
            if callable(previous_cancel):
                previous_cancel()
        self.owner = owner
        self.callback = callback
        self.cancel_callback = cancel_callback
        self.surface = surface

    def release(self, owner):
        if self.owner is not owner:
            return
        surface = self.surface
        self.owner = None
        self.callback = None
        self.cancel_callback = None
        self.surface = None
        self._queue = []
        self._drain_scheduled = False
        self.release_captures(surface)

    @staticmethod
    def _release_widget_grab(widget, method_name):
        if widget is None:
            return False
        method = getattr(widget, method_name, None)
        if not callable(method):
            return False
        try:
            method()
            return True
        except Exception:
            return False

    def _grabber(self, method_name):
        application = getattr(self.QtWidgets, "QApplication", None)
        method = getattr(application, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                pass
        try:
            instance = application.instance()
        except Exception:
            instance = None
        method = getattr(instance, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                pass
        widget_class = getattr(self.QtWidgets, "QWidget", None)
        method = getattr(widget_class, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                pass
        return None

    def _release_native_capture(self):
        callback = getattr(self, "_native_capture_releaser", None)
        if callable(callback):
            try:
                callback()
                return True
            except Exception:
                return False
        try:
            import ctypes

            ctypes.windll.user32.ReleaseCapture()
            return True
        except Exception:
            return False

    def release_captures(self, surface=None):
        mouse_grabber = self._grabber("mouseGrabber")
        keyboard_grabber = self._grabber("keyboardGrabber")
        self._release_widget_grab(mouse_grabber, "releaseMouse")
        self._release_widget_grab(keyboard_grabber, "releaseKeyboard")

        # Qt can lose track of a native Win32 capture owned by MotionBuilder's
        # viewport. Releasing it is what makes the next camera gesture native.
        self._release_native_capture()

    def force_release(self):
        surface = self.surface
        self.owner = None
        self.callback = None
        self.cancel_callback = None
        self.surface = None
        self._queue = []
        self._drain_scheduled = False
        self.release_captures(surface)

    def arm_terminal_guard(self, button):
        if str(button).lower() != "right":
            return
        self._guard_context_menu_until = time.perf_counter() + 0.25
        expected = self._guard_context_menu_until

        def clear():
            if self._guard_context_menu_until == expected:
                self._guard_context_menu_until = 0.0

        self.QtCore.QTimer.singleShot(250, clear)

    def cursor_position(self):
        position = self.QtGui.QCursor.pos()
        return float(position.x()), float(position.y())

    @staticmethod
    def _enum(container, nested_name, name):
        nested = getattr(container, nested_name, container)
        return getattr(nested, name, None)

    def _modifier_down(self, modifiers, name):
        value = self._enum(
            self.QtCore.Qt,
            "KeyboardModifier",
            name,
        )
        return bool(value is not None and modifiers & value)

    def _button_name(self, button):
        left = self._enum(self.QtCore.Qt, "MouseButton", "LeftButton")
        right = self._enum(self.QtCore.Qt, "MouseButton", "RightButton")
        if button == left:
            return "left"
        if button == right:
            return "right"
        return "other"

    def _key_name(self, event):
        try:
            key_value = int(event.key())
        except Exception:
            key_value = 0
        if key_value in self.KEY_NAMES:
            return self.KEY_NAMES[key_value]
        try:
            text = str(event.text() or "")
        except Exception:
            text = ""
        if len(text) == 1:
            if text == ".":
                return "PERIOD"
            if text == "-":
                return "MINUS"
            return text.upper()
        return str(key_value)

    def _payload(self, event_type, event):
        modifiers = self.QtWidgets.QApplication.keyboardModifiers()
        payload = {
            "type": event_type,
            "cursor": self.cursor_position(),
            "shift": self._modifier_down(modifiers, "ShiftModifier"),
            "control": self._modifier_down(
                modifiers,
                "ControlModifier",
            ),
            "alt": self._modifier_down(modifiers, "AltModifier"),
            "meta": self._modifier_down(modifiers, "MetaModifier"),
            "keypad": self._modifier_down(modifiers, "KeypadModifier"),
            "key": None,
            "text": "",
            "button": None,
            "auto_repeat": False,
        }
        if event_type.startswith("key_"):
            payload["key"] = self._key_name(event)
            try:
                payload["text"] = str(event.text() or "")
            except Exception:
                pass
            try:
                payload["auto_repeat"] = bool(event.isAutoRepeat())
            except Exception:
                pass
        elif event_type.startswith("mouse_"):
            try:
                payload["button"] = self._button_name(event.button())
            except Exception:
                payload["button"] = "other"
        return payload

    def _shortcut_focus_is_blocked(self):
        application = getattr(self.QtWidgets, "QApplication", None)
        instance = None
        try:
            instance = application.instance()
        except Exception:
            pass

        for owner in (application, instance):
            if owner is None:
                continue
            for method_name in ("activeModalWidget", "activePopupWidget"):
                method = getattr(owner, method_name, None)
                if not callable(method):
                    continue
                try:
                    if method() is not None:
                        return True
                except Exception:
                    pass

        focus_widget = None
        for owner in (application, instance):
            method = getattr(owner, "focusWidget", None)
            if not callable(method):
                continue
            try:
                focus_widget = method()
            except Exception:
                focus_widget = None
            if focus_widget is not None:
                break
        if focus_widget is None:
            return False

        for class_name in (
            "QLineEdit",
            "QTextEdit",
            "QPlainTextEdit",
            "QAbstractSpinBox",
            "QComboBox",
            "QKeySequenceEdit",
        ):
            widget_class = getattr(self.QtWidgets, class_name, None)
            if widget_class is None:
                continue
            try:
                if isinstance(focus_widget, widget_class):
                    return True
            except Exception:
                pass
        return False

    def _try_character_keying_launcher(self, event):
        callback = getattr(self, "character_keying_launcher", None)
        if not callable(callback):
            return False
        payload = self._payload("key_press", event)
        if (
            payload.get("auto_repeat")
            or payload.get("shift")
            or payload.get("control")
            or payload.get("alt")
            or payload.get("meta")
            or payload.get("keypad")
            or payload.get("key") not in ("1", "2", "3")
            or self._shortcut_focus_is_blocked()
        ):
            return False
        try:
            result = callback(payload["key"], payload)
        except Exception:
            return False
        return result is not None and result is not False

    @staticmethod
    def _event_global_cursor(event):
        for method_name in ("globalPosition", "globalPos"):
            method = getattr(event, method_name, None)
            if not callable(method):
                continue
            try:
                point = method()
                return float(point.x()), float(point.y())
            except Exception:
                pass
        return None

    def _remember_mouse_cursor(self, event):
        cursor = self._event_global_cursor(event)
        if cursor is not None:
            self._last_mouse_cursor = cursor

    def _try_transform_launcher(self, event):
        callback = getattr(self, "transform_launcher", None)
        if not callable(callback):
            return False
        payload = self._payload("key_press", event)
        launch_cursor = getattr(self, "_last_mouse_cursor", None)
        if launch_cursor is not None:
            payload["cursor"] = launch_cursor
        if (
            payload.get("auto_repeat")
            or payload.get("shift")
            or payload.get("control")
            or payload.get("alt")
            or payload.get("key") not in ("G", "R", "S")
        ):
            return False
        try:
            result = callback(payload["key"], payload)
        except Exception:
            return False
        return result is not None and result is not False

    def handle_qt_event(self, watched, event):
        qevent = self.QtCore.QEvent
        qevent_type = getattr(qevent, "Type", qevent)

        def event_value(name):
            return getattr(qevent_type, name, getattr(qevent, name, None))

        mapping = {
            event_value("MouseMove"): "mouse_move",
            event_value("MouseButtonPress"): "mouse_press",
            event_value("MouseButtonDblClick"): "mouse_press",
            event_value("MouseButtonRelease"): "mouse_release",
            event_value("KeyPress"): "key_press",
            event_value("KeyRelease"): "key_release",
            event_value("ContextMenu"): "context_menu",
        }
        event_type = mapping.get(event.type())
        if event_type is None:
            return False
        if (
            event_type == "context_menu"
            and time.perf_counter() < self._guard_context_menu_until
        ):
            return True
        if event_type.startswith("mouse_"):
            self._remember_mouse_cursor(event)
        if self.callback is None:
            if (
                event_type == "key_press"
                and self._try_character_keying_launcher(event)
            ):
                return True
            if (
                event_type == "key_press"
                and self._try_transform_launcher(event)
            ):
                return True
            return False
        payload = self._payload(event_type, event)
        if event_type == "mouse_move" and self._queue:
            if self._queue[-1].get("type") == "mouse_move":
                self._queue[-1] = payload
            else:
                self._queue.append(payload)
        else:
            self._queue.append(payload)
        self._schedule_drain()
        if event_type == "key_release":
            invocation = dict(
                getattr(self.owner, "invocation", {}) or {}
            )
            launcher_key = str(
                invocation.get("launcher_key") or ""
            ).upper()
            if launcher_key and payload.get("key") == launcher_key:
                return False
        return True

    def _schedule_drain(self):
        if self._drain_scheduled:
            return
        self._drain_scheduled = True
        self.QtCore.QTimer.singleShot(0, self.drain)

    def drain(self):
        self._drain_scheduled = False
        queue, self._queue = self._queue, []
        callback = self.callback
        for payload in queue:
            if callback is None or callback is not self.callback:
                break
            try:
                callback(payload)
            except Exception:
                cancel = self.cancel_callback
                if callable(cancel):
                    try:
                        cancel()
                    except Exception:
                        pass
                break

    def is_key_down(self, key_name):
        virtual_key = self.VIRTUAL_KEYS.get(str(key_name).upper())
        if virtual_key is None:
            return False
        try:
            import ctypes

            return bool(
                ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000
            )
        except Exception:
            return False

    @staticmethod
    def pressed_virtual_keys():
        """Return physical keyboard keys currently down, excluding mice."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            mouse_keys = {0x01, 0x02, 0x04, 0x05, 0x06}
            return tuple(
                virtual_key
                for virtual_key in range(0x08, 0xFF)
                if virtual_key not in mouse_keys
                and user32.GetAsyncKeyState(virtual_key) & 0x8000
            )
        except Exception:
            return ()

    @staticmethod
    def virtual_keys_are_down(virtual_keys):
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return any(
                user32.GetAsyncKeyState(int(virtual_key)) & 0x8000
                for virtual_key in virtual_keys
            )
        except Exception:
            return False

    def mouse_button_down(self, button):
        return self.is_key_down(str(button).upper())

    def stop(self):
        if callable(self.cancel_callback):
            try:
                self.cancel_callback()
            except Exception:
                pass
        self.force_release()
        self._guard_context_menu_until = 0.0
        self.character_keying_launcher = None


class OverlayCoordinator(object):
    CURSOR_OVERRIDE_SCAN_LIMIT = 64

    def __init__(
        self,
        diagnostics=None,
        overlay=None,
        cursor=None,
        qt_core=None,
        qt_widgets=None,
        blank_cursor=None,
    ):
        from .interactions.cursor_overlay import (
            InteractionOverlay,
            load_blank_cursor,
            load_move_cursor,
        )

        if qt_core is None or qt_widgets is None:
            default_core, default_widgets = _qt_modules()
            qt_core = qt_core or default_core
            qt_widgets = qt_widgets or default_widgets
        self.QtCore = qt_core
        self.QtWidgets = qt_widgets
        self.diagnostics = diagnostics
        self.owner = None
        self.overlay = overlay if overlay is not None else InteractionOverlay()
        self.default_cursor = (
            cursor if cursor is not None else load_move_cursor()
        )
        self.cursor = self.default_cursor
        self.cursor_style = None
        self._blank_cursor = (
            blank_cursor
            if blank_cursor is not None
            else load_blank_cursor()
        )
        self.cursor_owner = None
        self.cursor_surface = None
        self.surface_previous_cursor = None
        self.surface_had_explicit_cursor = None
        self.override_active = False
        self.override_baseline = ()
        self.override_baseline_captured = False
        self.cursor_cleanup_generation = 0

    def _cursor_for_style(self, style):
        if str(style or "").lower() not in ("rotate", "scale"):
            return self.default_cursor
        return self._blank_cursor

    def _set_overlay_cursor_style(self, style):
        callback = getattr(self.overlay, "set_cursor_style", None)
        if callable(callback):
            callback(style)

    def _record(self, event, owner=None, **data):
        if self.diagnostics is None:
            return
        self.diagnostics.record(
            event,
            getattr(owner, "feature_id", None),
            **data
        )

    @staticmethod
    def _cursor_signature(cursor):
        if cursor is None:
            return None
        try:
            pixmap = cursor.pixmap()
            if pixmap is not None and not pixmap.isNull():
                hotspot = cursor.hotSpot()
                return (
                    "pixmap",
                    int(pixmap.cacheKey()),
                    int(pixmap.width()),
                    int(pixmap.height()),
                    int(hotspot.x()),
                    int(hotspot.y()),
                )
        except Exception:
            pass
        try:
            shape = cursor.shape()
            try:
                value = int(shape)
            except (TypeError, ValueError):
                value = int(shape.value)
            return ("shape", value)
        except Exception:
            return ("object", id(cursor))

    def _cursor_matches(self, actual):
        return self._cursors_equivalent(actual, self.cursor)

    def _cursors_equivalent(self, actual, expected):
        actual_signature = self._cursor_signature(actual)
        expected_signature = self._cursor_signature(expected)
        if actual_signature == expected_signature:
            return actual_signature is not None
        if actual is None or expected is None:
            return False
        try:
            actual_pixmap = actual.pixmap()
            expected_pixmap = expected.pixmap()
            if (
                actual_pixmap is None
                or expected_pixmap is None
                or actual_pixmap.isNull()
                or expected_pixmap.isNull()
                or actual_pixmap.width() != expected_pixmap.width()
                or actual_pixmap.height() != expected_pixmap.height()
                or actual.hotSpot() != expected.hotSpot()
            ):
                return False
            return actual_pixmap.toImage() == expected_pixmap.toImage()
        except Exception:
            return False

    def _is_manager_cursor(self, cursor):
        return any(
            self._cursors_equivalent(cursor, candidate)
            for candidate in (self.default_cursor, self._blank_cursor)
            if candidate is not None
        )

    def _surface_cursor_matches(self, surface):
        if surface is None:
            return False
        try:
            return self._cursor_matches(surface.cursor())
        except Exception:
            return False

    def _application(self):
        return self.QtWidgets.QApplication.instance()

    def _active_override_cursor(self):
        try:
            return self.QtWidgets.QApplication.overrideCursor()
        except Exception:
            return None

    def _surface_has_explicit_cursor(self, surface):
        if surface is None:
            return None
        try:
            attributes = getattr(
                self.QtCore.Qt,
                "WidgetAttribute",
                self.QtCore.Qt,
            )
            attribute = getattr(attributes, "WA_SetCursor")
            return bool(surface.testAttribute(attribute))
        except Exception:
            return None

    def _restore_surface_cursor(self):
        surface = self.cursor_surface
        if surface is None:
            return
        try:
            if self.surface_had_explicit_cursor is False:
                surface.unsetCursor()
            elif self.surface_previous_cursor is not None:
                surface.setCursor(self.surface_previous_cursor)
            else:
                surface.unsetCursor()
        except Exception:
            pass
        self.cursor_surface = None
        self.surface_previous_cursor = None
        self.surface_had_explicit_cursor = None

    def _set_surface_cursor(self, surface):
        if surface is None:
            return False
        if surface is not self.cursor_surface:
            self._restore_surface_cursor()
            try:
                self.surface_previous_cursor = surface.cursor()
            except Exception:
                self.surface_previous_cursor = None
            self.surface_had_explicit_cursor = (
                self._surface_has_explicit_cursor(surface)
            )
            if (
                self.surface_had_explicit_cursor is True
                and self._is_manager_cursor(self.surface_previous_cursor)
            ):
                # A cursor left by an older manager instance has a different
                # Qt cache key even though it contains the same pixels.  Never
                # retain that stale cursor as MotionBuilder's baseline.
                try:
                    surface.unsetCursor()
                    self.surface_previous_cursor = surface.cursor()
                    self.surface_had_explicit_cursor = False
                    self._record(
                        "transform_stale_surface_cursor_cleared",
                        None,
                    )
                except Exception:
                    pass
            self.cursor_surface = surface
        try:
            surface.setCursor(self.cursor)
            return self._cursor_matches(surface.cursor())
        except Exception:
            return False

    def _flush_cursor_change(self):
        app = self._application()
        if app is None:
            return
        try:
            process_flags = getattr(
                self.QtCore.QEventLoop,
                "ProcessEventsFlag",
                self.QtCore.QEventLoop,
            )
            exclude_input = getattr(
                process_flags,
                "ExcludeUserInputEvents",
            )
            app.processEvents(exclude_input)
        except Exception:
            pass

    def _set_application_cursor(self):
        app = self._application()
        if app is None:
            return False
        try:
            active = self._active_override_cursor()
            if not self._cursor_matches(active):
                # MotionBuilder can push its own override above ours while an
                # interaction is active.  Never replace that entry: doing so
                # leaves the manager's older cursor buried in Qt's stack.
                self.QtWidgets.QApplication.setOverrideCursor(self.cursor)
            self.override_active = True
            active = self._active_override_cursor()
            return self._cursor_matches(active)
        except Exception:
            return False

    @staticmethod
    def _copy_override_cursor(cursor):
        try:
            try:
                from PySide6 import QtGui
            except ImportError:
                from PySide2 import QtGui
            return QtGui.QCursor(cursor)
        except Exception:
            return cursor

    def _is_transient_busy_cursor(self, cursor):
        try:
            shape_value = cursor.shape()
            try:
                shape = int(shape_value)
            except (TypeError, ValueError):
                shape = int(shape_value.value)
        except Exception:
            return False
        shapes = getattr(
            self.QtCore.Qt,
            "CursorShape",
            self.QtCore.Qt,
        )
        values = []
        for name in ("WaitCursor", "BusyCursor"):
            try:
                value = getattr(shapes, name)
                try:
                    values.append(int(value))
                except (TypeError, ValueError):
                    values.append(int(value.value))
            except Exception:
                pass
        return shape in values

    def _take_application_override_stack(self):
        """Return the Qt override stack in bottom-to-top order."""
        popped = []
        scanned = 0
        for _index in range(self.CURSOR_OVERRIDE_SCAN_LIMIT):
            active = self._active_override_cursor()
            if active is None:
                break
            scanned += 1
            saved_cursor = self._copy_override_cursor(active)
            try:
                self.QtWidgets.QApplication.restoreOverrideCursor()
            except Exception:
                break
            popped.append(saved_cursor)
        return tuple(reversed(popped)), scanned

    def _restore_application_override_stack(self, cursors):
        restored = 0
        for cursor in cursors:
            try:
                self.QtWidgets.QApplication.setOverrideCursor(cursor)
                restored += 1
            except Exception:
                break
        return restored

    def _capture_application_cursor_baseline(self):
        stack, scanned = self._take_application_override_stack()
        # A matching cursor can only be a stale manager layer from an earlier
        # failed/reloaded interaction.  It is never part of the host baseline.
        baseline = tuple(
            cursor
            for cursor in stack
            if (
                not self._cursor_matches(cursor)
                and not self._is_transient_busy_cursor(cursor)
            )
        )
        restored = self._restore_application_override_stack(baseline)
        self.override_baseline = baseline
        self.override_baseline_captured = True
        return len(stack) - len(baseline), restored, scanned

    def _remove_application_cursors(self):
        """Clear all overrides, matching the proven legacy Rotate cleanup."""
        stack, scanned = self._take_application_override_stack()
        removed = sum(
            1 for cursor in stack if self._cursor_matches(cursor)
        )
        discarded = max(0, len(stack) - removed)
        self.override_active = False
        self.override_baseline = ()
        self.override_baseline_captured = False
        return removed, 0, scanned, discarded

    def _restore_native_arrow_cursor(self):
        if self._active_override_cursor() is not None:
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.LoadCursorW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            user32.LoadCursorW.restype = ctypes.c_void_p
            user32.SetCursor.argtypes = [ctypes.c_void_p]
            user32.SetCursor.restype = ctypes.c_void_p
            arrow = user32.LoadCursorW(None, ctypes.c_void_p(32512))
            if arrow:
                user32.SetCursor(arrow)
                return True
        except Exception:
            pass
        return False

    def _clear_transient_cursor_overrides(self):
        if self.cursor_owner is not None:
            return 0
        removed = 0
        for _index in range(self.CURSOR_OVERRIDE_SCAN_LIMIT):
            active = self._active_override_cursor()
            if active is None or not self._is_transient_busy_cursor(active):
                break
            try:
                self.QtWidgets.QApplication.restoreOverrideCursor()
            except Exception:
                break
            removed += 1
        if removed:
            self._flush_cursor_change()
            self._restore_native_arrow_cursor()
            self._record(
                "transform_transient_cursor_cleared",
                None,
                removed_overrides=removed,
            )
        return removed

    def finish_cursor_release(self, surface=None):
        """Clear cursor state posted after the interaction's direct cleanup."""
        if self.cursor_owner is not None:
            return False
        self.cursor_cleanup_generation += 1
        generation = self.cursor_cleanup_generation
        self._clear_transient_cursor_overrides()
        self.clear_unowned_cursors(surface)

        def cleanup():
            if (
                generation != self.cursor_cleanup_generation
                or self.cursor_owner is not None
            ):
                return
            self._clear_transient_cursor_overrides()
            self.clear_unowned_cursors(surface)

        try:
            self.QtCore.QTimer.singleShot(0, cleanup)
            self.QtCore.QTimer.singleShot(50, cleanup)
        except Exception:
            pass
        return True

    def clear_unowned_cursors(self, surface=None):
        """Remove manager cursors that survived reload or app activation."""
        if self.owner is not None or self.cursor_owner is not None:
            return False

        surfaces = []
        if surface is not None:
            surfaces.append(surface)
        else:
            try:
                surfaces.extend(self.QtWidgets.QApplication.allWidgets())
            except Exception:
                pass

        cleared_surfaces = 0
        seen = set()
        for candidate in surfaces:
            identity = id(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            try:
                if (
                    self._surface_has_explicit_cursor(candidate) is True
                    and self._is_manager_cursor(candidate.cursor())
                ):
                    candidate.unsetCursor()
                    cleared_surfaces += 1
            except Exception:
                pass

        cleared_overrides = 0
        for _index in range(self.CURSOR_OVERRIDE_SCAN_LIMIT):
            active = self._active_override_cursor()
            if active is None or not self._is_manager_cursor(active):
                break
            try:
                self.QtWidgets.QApplication.restoreOverrideCursor()
            except Exception:
                break
            cleared_overrides += 1

        if cleared_surfaces or cleared_overrides:
            self._flush_cursor_change()
            self._restore_native_arrow_cursor()
            self._record(
                "transform_unowned_cursor_cleared",
                None,
                cleared_surfaces=cleared_surfaces,
                cleared_overrides=cleared_overrides,
            )
            return True
        return False

    def claim(self, owner, rect):
        if self.owner is not None and self.owner is not owner:
            try:
                self.overlay.hide()
            except Exception:
                pass
        clear_status = getattr(self.overlay, "clear_status", None)
        if callable(clear_status):
            clear_status()
        self.owner = owner
        self.overlay.set_rect(rect)
        return self.overlay

    def release(self, owner):
        if self.owner is owner:
            try:
                clear_status = getattr(self.overlay, "clear_status", None)
                if callable(clear_status):
                    clear_status()
                self.overlay.hide()
            finally:
                self.owner = None

    def claim_cursor(self, owner, surface=None, style=None):
        if self.cursor_owner is not None and self.cursor_owner is not owner:
            self.release_cursor(self.cursor_owner)
        if self.cursor_owner is owner:
            return self.ensure_cursor(owner, surface)

        self.cursor_style = str(style or "").strip().lower() or None
        self.cursor = self._cursor_for_style(self.cursor_style)
        self._set_overlay_cursor_style(self.cursor_style)
        self.cursor_cleanup_generation += 1
        surface_ok = self._set_surface_cursor(surface)
        application_ok = self._set_application_cursor()
        # Cursor setters update Qt state synchronously. Pumping every pending
        # paint here blocks transform startup and can discard early mouse travel.
        application_ok = (
            self._cursor_matches(self._active_override_cursor())
            or application_ok
        )
        surface_ok = self._surface_cursor_matches(surface) or surface_ok
        if not application_ok and not surface_ok:
            self._restore_surface_cursor()
            self._remove_application_cursors()
            self.cursor = self.default_cursor
            self.cursor_style = None
            self._set_overlay_cursor_style(None)
            self._record("transform_cursor_claim_failed", owner)
            return False
        self.cursor_owner = owner
        self._record(
            "transform_cursor_claimed",
            owner,
            application_override=application_ok,
            surface_cursor=surface_ok,
        )
        return True

    def ensure_cursor(self, owner, surface=None):
        if self.cursor_owner is not owner:
            return False
        repaired = False
        if surface is None:
            surface = self.cursor_surface
        if surface is not None and not self._surface_cursor_matches(surface):
            repaired = self._set_surface_cursor(surface) or repaired
        if not self._cursor_matches(self._active_override_cursor()):
            repaired = self._set_application_cursor() or repaired
        if repaired:
            self._flush_cursor_change()
            self._record("transform_cursor_reasserted", owner)
        return (
            self._cursor_matches(self._active_override_cursor())
            or (
                surface is not None
                and self._surface_cursor_matches(surface)
            )
        )

    def release_cursor(self, owner):
        if self.cursor_owner is not owner:
            return False
        surface = self.cursor_surface
        self._restore_surface_cursor()
        removed, restored, scanned, discarded = (
            self._remove_application_cursors()
        )
        self.cursor_owner = None
        self._flush_cursor_change()
        native_arrow = self._restore_native_arrow_cursor()
        self.cursor = self.default_cursor
        self.cursor_style = None
        self._set_overlay_cursor_style(None)
        self._record(
            "transform_cursor_released",
            owner,
            removed_overrides=removed,
            restored_overrides=restored,
            scanned_overrides=scanned,
            discarded_interaction_overrides=discarded,
            native_arrow=native_arrow,
        )
        self.finish_cursor_release(surface)
        return True

    def stop(self):
        if self.owner is not None:
            self.release(self.owner)
        if self.cursor_owner is not None:
            self.release_cursor(self.cursor_owner)
        try:
            self.overlay.deleteLater()
        except Exception:
            pass
        self.overlay = None
        self.cursor = None


class UndoTransaction(object):
    def __init__(self, sdk, label):
        self.sdk = sdk
        self.label = str(label)
        self.manager = None
        self.opened = False
        self.owned = False
        self.closed = False
        self._registered_properties = set()
        self._registered_models = set()
        try:
            self.manager = sdk.FBUndoManager()
            if not self.manager.TransactionIsOpen():
                result = self.manager.TransactionBegin(self.label)
                try:
                    self.opened = bool(self.manager.TransactionIsOpen())
                except Exception:
                    self.opened = bool(result)
                self.owned = self.opened
        except Exception:
            self.manager = None

    def add_property(self, prop):
        if prop is None or id(prop) in self._registered_properties:
            return
        self._registered_properties.add(id(prop))
        if self.manager is not None and self.opened:
            try:
                self.manager.TransactionAddProperty(prop)
            except Exception:
                pass

    def add_model_trs(self, model):
        if model is None or id(model) in self._registered_models:
            return
        self._registered_models.add(id(model))
        if self.manager is not None and self.opened:
            for method_name in (
                "TransactionAddModelTRS",
                "TransactionAddModel",
            ):
                method = getattr(self.manager, method_name, None)
                if callable(method):
                    try:
                        method(model)
                        break
                    except Exception:
                        pass

    def _end(self):
        if self.closed:
            return
        self.closed = True
        if self.manager is not None and self.opened:
            try:
                self.manager.TransactionEnd()
            except Exception:
                pass

    def commit(self):
        self._end()

    def cancel(self):
        self._end()
        if self.manager is not None and self.owned:
            try:
                self.manager.Undo(True)
            except Exception:
                pass


class UndoHelper(object):
    def __init__(self, sdk):
        self.sdk = sdk

    def begin(self, label):
        return UndoTransaction(self.sdk, label)

    @contextmanager
    def scope(self, label):
        manager = None
        opened = False
        try:
            manager = self.sdk.FBUndoManager()
            if not manager.TransactionIsOpen():
                result = manager.TransactionBegin(label)
                try:
                    opened = bool(manager.TransactionIsOpen())
                except Exception:
                    opened = bool(result)
        except Exception:
            manager = None
        try:
            yield
        except Exception:
            if manager is not None and opened:
                try:
                    manager.TransactionEnd()
                    manager.Undo(True)
                except Exception:
                    pass
            raise
        else:
            if manager is not None and opened:
                try:
                    manager.TransactionEnd()
                except Exception:
                    pass


class CommandContext(object):
    """Lazy public context passed to future native feature modules."""

    def __init__(self, runtime):
        self._runtime = runtime

    @property
    def system(self):
        return self._runtime.system

    @property
    def application(self):
        return self._runtime.application

    @property
    def player_control(self):
        return self._runtime.player_control

    @property
    def action_manager(self):
        return self._runtime.action_manager

    @property
    def scene(self):
        return self._runtime.scene

    @property
    def qt_application(self):
        return self._runtime.ui.app

    @property
    def take(self):
        return self._runtime.current_take()

    @property
    def animation_layer(self):
        take = self.take
        try:
            return take.GetCurrentLayer()
        except Exception:
            return None

    @property
    def selection(self):
        return self._runtime.selection.snapshot()

    @property
    def ui_context(self):
        return self._runtime.ui.snapshot()

    @property
    def fcurves(self):
        return self._runtime.fcurves

    @property
    def scene_index(self):
        return self._runtime.scene_index

    @property
    def evaluation(self):
        return self._runtime.evaluation

    @property
    def input(self):
        return self._runtime.input

    @property
    def overlays(self):
        return self._runtime.overlays

    @property
    def undo(self):
        return self._runtime.undo

    @property
    def policy(self):
        return self._runtime.policy

    @property
    def story_settings(self):
        return dict(self._runtime.story_settings)

    @property
    def interactions(self):
        return self._runtime.interactions

    @property
    def graph_transforms(self):
        return self._runtime.graph_transforms

    @property
    def hik(self):
        return self._runtime.hik

    @property
    def character_keying_state(self):
        return self._runtime.hik.current_keying_state(
            self,
            self.selection,
        )

    def begin_character_manipulation(self, operation, snapshots):
        return self._runtime.hik.begin_manipulation(
            self,
            operation,
            snapshots,
        )

    @property
    def diagnostics(self):
        return self._runtime.diagnostics

    def surface_generation(self, surface):
        return self._runtime.ui.surface_generation(surface)

    def find_ui_surface_geometry(self, classification):
        """Find immutable editor geometry through the shared UI service."""
        return self._runtime.ui.find_surface_geometry(classification)

    def find_ui_surface_attachment(self, classification):
        """Find a stable editor pane and pane-local surface geometry."""
        return self._runtime.ui.find_surface_attachment(classification)

    def retire_legacy_precision_services(self):
        return self._runtime.retire_legacy_precision_services()

    def restore_editor_focus(self, surface, preferred_widget=None):
        return self._runtime.ui.restore_focus(surface, preferred_widget)

    def add_ui_event_observer(self, callback):
        """Observe events through the manager's single application filter."""
        return self._runtime.ui.add_event_observer(callback)

    def remove_ui_event_observer(self, callback):
        return self._runtime.ui.remove_event_observer(callback)


class RuntimeServices(object):
    LEGACY_PRECISION_SERVICE_ATTRS = (
        "_codex_precision_transform_shift_rmb_service",
        "_codex_precision_transform_hold_shift_service",
    )

    def __init__(
        self,
        diagnostics=None,
        interaction_settings=None,
        story_settings=None,
    ):
        import pyfbsdk as sdk
        from .fcurves.view_transform import FCurveViewTransformCache
        from .interactions.policy import InteractionPolicy
        from .interactions.session import InteractionManager
        from .object_transforms.hik import HIKIndex
        from .story.settings import validate_story_settings

        self.sdk = sdk
        self.diagnostics = diagnostics
        self.policy = InteractionPolicy(interaction_settings)
        self.story_settings = validate_story_settings(story_settings)
        self.system = sdk.FBSystem()
        self.application = sdk.FBApplication()
        self.player_control = sdk.FBPlayerControl()
        self.action_manager = sdk.FBActionManager()
        self.scene = self.system.Scene
        self.selection = SelectionCache(sdk)
        self.scene_index = SceneIndex(self.scene)
        self.fcurves = FCurveService(sdk, self.scene_index)
        self.input = InputRouter()
        self.ui = UIContextService(self.input)
        self.evaluation = EvaluationScheduler(self.scene)
        self.overlays = OverlayCoordinator(diagnostics=diagnostics)
        self.graph_transforms = FCurveViewTransformCache()
        self.hik = HIKIndex()
        self.undo = UndoHelper(sdk)
        self.context = CommandContext(self)
        self.interactions = InteractionManager(self.context)
        self.evaluation.error_callback = self.interactions.cancel_active
        self.ui.invalidation_callback = self._on_surface_invalidated
        self.ui.activation_callback = self.overlays.clear_unowned_cursors
        self.ui.surface_enter_callback = self.overlays.clear_unowned_cursors
        self.started = False
        self._scene_callback = self._on_scene_change
        self._take_callback = self._on_take_change
        self._file_open_callback = self._on_file_reset
        self._file_new_callback = self._on_file_reset
        self._take_identity = None

    def _record(self, event, **data):
        if self.diagnostics:
            self.diagnostics.record(event, **data)

    def retire_legacy_precision_services(self):
        stopped = []
        for attr in self.LEGACY_PRECISION_SERVICE_ATTRS:
            service = getattr(builtins, attr, None)
            if service is None:
                continue
            stop = getattr(service, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    self._record(
                        "legacy_precision_stop_error",
                        resource_attr=attr,
                    )
            try:
                setattr(builtins, attr, None)
            except Exception:
                pass
            stopped.append(attr)
        if stopped:
            self._record(
                "legacy_precision_services_retired",
                resource_attrs=stopped,
            )
        return tuple(stopped)

    def start(self):
        if self.started:
            return
        self.retire_legacy_precision_services()
        try:
            self.scene.OnChange.Add(self._scene_callback)
        except Exception:
            pass
        try:
            self.scene.OnTakeChange.Add(self._take_callback)
        except Exception:
            pass
        try:
            self.application.OnFileOpenCompleted.Add(self._file_open_callback)
        except Exception:
            pass
        try:
            self.application.OnFileNewCompleted.Add(self._file_new_callback)
        except Exception:
            pass
        self.ui.start()
        self.overlays.clear_unowned_cursors()
        self._take_identity = self._safe_take_identity()
        self.started = True
        self._record("runtime_started")

    def _change_name(self, event):
        for attr in ("Type", "ChangeType"):
            try:
                return str(getattr(event, attr))
            except Exception:
                pass
        return ""

    def _on_scene_change(self, control, event):
        name = self._change_name(event).lower()
        if any(token in name for token in ("destroy", "removechild", "detach")):
            self.interactions.cancel_active()
        if "select" in name:
            self.selection.invalidate()
        component = None
        for attribute in ("ChildComponent", "Component"):
            try:
                component = getattr(event, attribute)
            except Exception:
                component = None
            if component is not None:
                break
        if any(token in name for token in ("addchild", "attach")):
            self.scene_index.add(component)
            self.fcurves.invalidate()
            self.hik.invalidate()
        elif any(token in name for token in ("destroy", "removechild", "detach")):
            self.scene_index.remove(component)
            self.fcurves.invalidate()
            self.hik.invalidate()
            self.graph_transforms.clear()
        elif any(token in name for token in ("rename", "changedname", "changename")):
            self.scene_index.invalidate()
            self.fcurves.invalidate()
            self.hik.invalidate()
        elif any(token in name for token in ("load", "clear")):
            self.invalidate_all("scene_" + name)
        if not name:
            self.selection.invalidate()
            self.scene_index.invalidate()
            self.fcurves.invalidate()
            self.hik.invalidate()
            self.graph_transforms.clear()

    def _on_surface_invalidated(self, surface):
        self.graph_transforms.invalidate_surface(surface)

    def _on_take_change(self, control, event):
        self._take_identity = self._safe_take_identity()
        self.invalidate_wrappers("take_event")

    def _on_file_reset(self, control, event):
        self._rebind_scene()
        self.invalidate_all("file")

    def _rebind_scene(self):
        previous = self.scene
        current = self.system.Scene
        if current is previous:
            return
        try:
            previous.OnChange.Remove(self._scene_callback)
        except Exception:
            pass
        try:
            previous.OnTakeChange.Remove(self._take_callback)
        except Exception:
            pass
        self.scene = current
        self.scene_index.reset(current)
        self.evaluation.scene = current
        try:
            current.OnChange.Add(self._scene_callback)
        except Exception:
            pass
        try:
            current.OnTakeChange.Add(self._take_callback)
        except Exception:
            pass

    def _safe_take_identity(self):
        try:
            take = self.system.CurrentTake
            return (id(take), str(take.Name))
        except Exception:
            return None

    def current_take(self):
        identity = self._safe_take_identity()
        if identity != self._take_identity:
            self._take_identity = identity
            self.invalidate_wrappers("take")
        try:
            return self.system.CurrentTake
        except Exception:
            self.invalidate_wrappers("take_access_error")
            return None

    def invalidate_wrappers(self, reason):
        self.interactions.cancel_active()
        self.selection.invalidate()
        self.fcurves.invalidate()
        self.graph_transforms.clear()
        self.hik.invalidate()
        self.ui.invalidate()
        self._record("runtime_wrappers_invalidated", reason=reason)

    def invalidate_all(self, reason):
        self.interactions.cancel_active()
        self.selection.invalidate()
        self.scene_index.invalidate()
        self.fcurves.invalidate()
        self.graph_transforms.clear()
        self.hik.invalidate()
        self.ui.invalidate()
        self._take_identity = self._safe_take_identity()
        self._record("runtime_invalidated", reason=reason)

    def stop(self):
        if not self.started:
            return
        try:
            self.scene.OnChange.Remove(self._scene_callback)
        except Exception:
            pass
        try:
            self.scene.OnTakeChange.Remove(self._take_callback)
        except Exception:
            pass
        try:
            self.application.OnFileOpenCompleted.Remove(self._file_open_callback)
        except Exception:
            pass
        try:
            self.application.OnFileNewCompleted.Remove(self._file_new_callback)
        except Exception:
            pass
        self.ui.stop()
        self.interactions.stop()
        self.evaluation.stop()
        self.input.stop()
        self.overlays.stop()
        self.graph_transforms.clear()
        self.hik.invalidate()
        self.started = False
        self._record("runtime_stopped")
