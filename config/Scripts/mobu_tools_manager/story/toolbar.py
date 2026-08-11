"""Manager-owned controls for MotionBuilder's native Story UI."""

from __future__ import absolute_import

import ctypes

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import getCppPointer as _get_cpp_pointer
    from shiboken6 import isValid as _is_valid
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import getCppPointer as _get_cpp_pointer
    from shiboken2 import isValid as _is_valid

from .settings import DEFAULTS


CONTROL_OBJECT_NAME = "mobu_tools_manager_story_clip_controls"
ACTION_OBJECT_NAME = "mobu_tools_manager_story_reset_align"
START_ZERO_OBJECT_NAME = "mobu_tools_manager_story_start_zero"
SETTINGS_OBJECT_NAME = "mobu_tools_manager_story_alignment_settings"
INSERT_TAKE_ACTION_OBJECT_NAME = (
    "mobu_tools_manager_story_insert_current_take"
)
FRAME_AFTER_MENU_HIDE_MS = 75
VK_F = 0x46
KEYEVENTF_KEYUP = 0x0002


def _accessible_name(widget):
    try:
        return str(widget.accessibleName() or "").strip()
    except Exception:
        return ""


def _event_value(QtCoreModule, name):
    qevent = QtCoreModule.QEvent
    scoped = getattr(qevent, "Type", qevent)
    value = getattr(qevent, name, None)
    if value is None:
        value = getattr(scoped, name, None)
    return value


def _native_pointer(widget):
    if widget is None:
        return None
    try:
        return int(_get_cpp_pointer(widget)[0])
    except Exception:
        return None


def selected_story_clip_count():
    """Return the current Story clip selection without retaining SDK wrappers."""
    from pyfbsdk import FBStory

    count = [0]

    def visit_track(track):
        try:
            for clip in track.Clips:
                try:
                    if bool(clip.Selected):
                        count[0] += 1
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for child in track.SubTracks:
                visit_track(child)
        except Exception:
            pass

    def visit_folder(folder):
        try:
            for track in folder.Tracks:
                visit_track(track)
        except Exception:
            pass
        try:
            for child in folder.Childs:
                visit_folder(child)
        except Exception:
            pass

    try:
        visit_folder(FBStory().RootFolder)
    except Exception:
        return 0
    return count[0]


class StoryToolbarController(QtCore.QObject):
    """Own the native-Story toolbar additions and context-menu action."""

    REFRESH_EVENTS = tuple(
        value
        for value in (
            _event_value(QtCore, "MouseButtonRelease"),
            _event_value(QtCore, "KeyRelease"),
            _event_value(QtCore, "FocusIn"),
            _event_value(QtCore, "WindowActivate"),
            _event_value(QtCore, "Show"),
            _event_value(QtCore, "Hide"),
            _event_value(QtCore, "Resize"),
            _event_value(QtCore, "ChildAdded"),
            _event_value(QtCore, "ChildRemoved"),
            _event_value(QtCore, "LayoutRequest"),
        )
        if value is not None
    )

    def __init__(self, manager, ui_context):
        QtCore.QObject.__init__(self)
        self.manager = manager
        self.ui_context = ui_context
        self.container = None
        self.action_button = None
        self.start_zero_button = None
        self.settings_button = None
        self.settings_menu = None
        self.threshold_input = None
        self.story_host = None
        self.context_menu = None
        self.context_action = None
        self.context_separator = None
        self.context_menu_pending = False
        self.frame_pending = False
        self.refresh_pending = False
        self.started = False
        self.context_expiry_timer = QtCore.QTimer(self)
        self.context_expiry_timer.setSingleShot(True)
        self.context_expiry_timer.timeout.connect(
            self._expire_context_menu_request
        )
        self.frame_timer = QtCore.QTimer(self)
        self.frame_timer.setSingleShot(True)
        self.frame_timer.timeout.connect(self._press_story_frame_key)

    def start(self):
        if self.started:
            return self
        self.started = True
        self.ui_context.add_event_observer(self._on_ui_event)
        self._schedule_refresh()
        return self

    def stop(self):
        if not self.started:
            return
        self.started = False
        self.refresh_pending = False
        self.context_menu_pending = False
        self.frame_pending = False
        self.context_expiry_timer.stop()
        self.frame_timer.stop()
        self._release_context_menu(remove_actions=True)
        self.ui_context.remove_event_observer(self._on_ui_event)
        self._detach_controls()
        self.story_host = None

    def _on_ui_event(self, watched, event):
        try:
            event_type = event.type()
        except Exception:
            return
        context_menu_event = _event_value(QtCore, "ContextMenu")
        mouse_release_event = _event_value(QtCore, "MouseButtonRelease")
        show_event = _event_value(QtCore, "Show")
        right_release = False
        if event_type == mouse_release_event:
            try:
                right_button = getattr(
                    getattr(QtCore.Qt, "MouseButton", QtCore.Qt),
                    "RightButton",
                )
                right_release = event.button() == right_button
            except Exception:
                right_release = False
        if (
            (event_type == context_menu_event or right_release)
            and self._is_story_widget(watched)
        ):
            self.context_menu_pending = True
            self.context_expiry_timer.start(500)
        elif (
            event_type == show_event
            and self.context_menu_pending
            and isinstance(watched, QtWidgets.QMenu)
        ):
            self._extend_story_context_menu(watched)
        if event_type in self.REFRESH_EVENTS:
            self._schedule_refresh()

    def _schedule_refresh(self):
        if not self.started or self.refresh_pending:
            return
        self.refresh_pending = True
        QtCore.QTimer.singleShot(0, self._refresh)

    def _schedule_retry(self):
        if not self.started:
            return
        QtCore.QTimer.singleShot(50, self._schedule_refresh)

    @staticmethod
    def _valid(widget):
        if widget is None:
            return False
        try:
            return bool(_is_valid(widget))
        except Exception:
            try:
                widget.objectName()
                return True
            except Exception:
                return False

    def _find_story_toolbar(self):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return None
        try:
            top_levels = list(app.topLevelWidgets())
        except Exception:
            return None
        for top_level in top_levels:
            try:
                candidates = top_level.findChildren(QtWidgets.QWidget)
            except Exception:
                continue
            for candidate in candidates:
                if _accessible_name(candidate).lower() != "toolbar":
                    continue
                try:
                    direct_children = [
                        child
                        for child in candidate.children()
                        if isinstance(child, QtWidgets.QWidget)
                    ]
                except Exception:
                    continue
                names = set(
                    _accessible_name(child).lower()
                    for child in direct_children
                )
                if {
                    "story",
                    "razor",
                    "summary clips",
                    "selection",
                }.issubset(names):
                    # MotionBuilder rebuilds the native toolbar itself and
                    # can leave readable zombie wrappers behind. Its parent
                    # Story pane is stable, so own our child there and place
                    # it over this toolbar row.
                    try:
                        host = candidate.parentWidget()
                        if host is None:
                            continue
                        geometry = candidate.geometry()
                        native_right = 0
                        for child in direct_children:
                            if not child.isVisible():
                                continue
                            child_geometry = child.geometry()
                            if child_geometry.height() > geometry.height() + 4:
                                continue
                            native_right = max(
                                native_right,
                                int(child_geometry.right()) + 1,
                            )
                        toolbar_snapshot = {
                            "x": int(geometry.x()),
                            "y": int(geometry.y()),
                            "width": int(geometry.width()),
                            "height": int(geometry.height()),
                            "native_right": native_right,
                            "host_width": int(host.width()),
                        }
                        if not self._valid(self.container):
                            self._attach_controls(host)
                        self.story_host = host
                    except RuntimeError:
                        self._detach_controls()
                        continue
                    return toolbar_snapshot
        return None

    def _current_story_host(self):
        # MotionBuilder can invalidate the wrapper cached while scanning its
        # native toolbar even though our child remains attached to the live
        # Story pane. Reacquire that pane from the owned child first.
        if self._valid(self.container):
            try:
                host = self.container.parentWidget()
            except Exception:
                host = None
            if self._valid(host):
                self.story_host = host
                return host

        host = self.story_host
        if self._valid(host):
            return host

        self.story_host = None
        self._find_story_toolbar()
        if self._valid(self.container):
            try:
                host = self.container.parentWidget()
            except Exception:
                host = None
            if self._valid(host):
                self.story_host = host
                return host
        return self.story_host if self._valid(self.story_host) else None

    def _is_story_widget(self, widget):
        host = self._current_story_host()
        if not self._valid(host) or widget is None:
            return False
        story_anchor = host
        current = host
        while current is not None:
            if isinstance(current, QtWidgets.QDockWidget):
                story_anchor = current
                break
            try:
                current = current.parentWidget()
            except Exception:
                break

        anchor_pointer = _native_pointer(story_anchor)
        current = widget
        while current is not None:
            if (
                current is story_anchor
                or (
                    anchor_pointer is not None
                    and _native_pointer(current) == anchor_pointer
                )
            ):
                return True
            try:
                current = current.parentWidget()
            except Exception:
                return False
        return False

    def _expire_context_menu_request(self):
        self.context_menu_pending = False

    def _release_context_menu(self, remove_actions=False):
        menu = self.context_menu
        action = self.context_action
        separator = self.context_separator
        self.context_menu = None
        self.context_action = None
        self.context_separator = None
        if not self._valid(menu):
            return
        try:
            menu.aboutToHide.disconnect(self._on_context_menu_hidden)
        except Exception:
            pass
        if not remove_actions:
            return
        for owned_action in (action, separator):
            if not self._valid(owned_action):
                continue
            try:
                menu.removeAction(owned_action)
            except Exception:
                pass
            try:
                owned_action.deleteLater()
            except Exception:
                pass

    def _extend_story_context_menu(self, menu):
        self.context_menu_pending = False
        self.context_expiry_timer.stop()
        stale_actions = []
        try:
            for existing in menu.actions():
                if existing.objectName() == INSERT_TAKE_ACTION_OBJECT_NAME:
                    stale_actions.append(existing)
        except Exception:
            return

        self._release_context_menu(remove_actions=True)
        try:
            for stale_action in stale_actions:
                menu.removeAction(stale_action)
                stale_action.deleteLater()

            native_actions = list(menu.actions())
            first_native_action = (
                native_actions[0] if native_actions else None
            )
            action = menu.addAction("Insert Current Take to Story")
            action.setObjectName(INSERT_TAKE_ACTION_OBJECT_NAME)
            action.setStatusTip(
                "Create a Character Animation track for the active "
                "Character Controls character and insert the current take."
            )
            action.setEnabled(
                self.manager.is_enabled("story.insert_current_take")
            )
            action.triggered.connect(self._insert_current_take)
            separator = menu.addSeparator()
            if first_native_action is not None:
                menu.insertAction(first_native_action, action)
                menu.insertAction(first_native_action, separator)
            menu.aboutToHide.connect(self._on_context_menu_hidden)
            self.context_menu = menu
            self.context_action = action
            self.context_separator = separator
        except Exception:
            self._release_context_menu(remove_actions=True)

    def _insert_current_take(self, checked=False):
        del checked
        if not self.started:
            return
        try:
            clip = self.manager.dispatch("story.insert_current_take")
        except Exception:
            return
        if clip is None:
            return
        self.frame_pending = True
        # Normally aboutToHide follows QAction.triggered and restarts this
        # countdown from the actual menu-close boundary. This fallback also
        # covers a native menu destroyed while the command changes Story.
        self.frame_timer.start(FRAME_AFTER_MENU_HIDE_MS)

    def _on_context_menu_hidden(self):
        self._release_context_menu(remove_actions=True)
        if self.started and self.frame_pending:
            self.frame_timer.start(FRAME_AFTER_MENU_HIDE_MS)

    def _press_story_frame_key(self):
        if not self.started or not self.frame_pending:
            return
        self.frame_pending = False

        # F is contextual in MotionBuilder. Never send it if the pointer has
        # left Story while the menu was closing; that would frame the Viewer.
        try:
            widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        except Exception:
            widget = None
        if not self._is_story_widget(widget):
            return

        user32 = ctypes.windll.user32
        scan_code = user32.MapVirtualKeyW(VK_F, 0)
        try:
            user32.keybd_event(VK_F, scan_code, 0, 0)
        finally:
            user32.keybd_event(
                VK_F,
                scan_code,
                KEYEVENTF_KEYUP,
                0,
            )

    def _detach_controls(self):
        container = self.container
        self.container = None
        self.action_button = None
        self.start_zero_button = None
        self.settings_button = None
        self.settings_menu = None
        self.threshold_input = None
        if not self._valid(container):
            return
        try:
            container.hide()
            container.setParent(None)
            container.deleteLater()
        except Exception:
            pass

    def _attach_controls(self, host):
        self._detach_controls()
        container = QtWidgets.QWidget(host)
        container.setObjectName(CONTROL_OBJECT_NAME)
        container.setAccessibleName("Managed Story clip commands")
        container.setFixedSize(218, 20)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        action_button = QtWidgets.QToolButton(container)
        action_button.setObjectName(ACTION_OBJECT_NAME)
        action_button.setAccessibleName("Reset and Align Selected Story Clips")
        action_button.setText("Reset / Align +Z")
        action_button.setAutoRaise(True)
        action_button.setFixedSize(130, 20)
        action_button.setToolTip(
            "Reset selected Story clips to 0,0,0 and align their root path "
            "or characterized facing direction to global +Z."
        )
        action_button.clicked.connect(self._run_command)
        layout.addWidget(action_button)

        start_zero_button = QtWidgets.QToolButton(container)
        start_zero_button.setObjectName(START_ZERO_OBJECT_NAME)
        start_zero_button.setAccessibleName(
            "Move Selected Story Clips to Frame 0"
        )
        start_zero_button.setText("Start 0f")
        start_zero_button.setAutoRaise(True)
        start_zero_button.setFixedSize(66, 20)
        start_zero_button.setToolTip(
            "Move selected Story clips so their timeline start is frame 0 "
            "without changing clip duration."
        )
        start_zero_button.clicked.connect(self._move_clips_to_zero)
        layout.addWidget(start_zero_button)

        settings_button = QtWidgets.QToolButton(container)
        settings_button.setObjectName(SETTINGS_OBJECT_NAME)
        settings_button.setAccessibleName("Story alignment settings")
        settings_button.setAutoRaise(True)
        settings_button.setFixedSize(20, 20)
        arrow_type = getattr(
            getattr(QtCore.Qt, "ArrowType", QtCore.Qt),
            "DownArrow",
        )
        settings_button.setArrowType(arrow_type)
        settings_button.setToolTip("Story alignment settings")

        menu = QtWidgets.QMenu(settings_button)
        editor = QtWidgets.QWidget(menu)
        editor.setMinimumWidth(270)
        editor_layout = QtWidgets.QVBoxLayout(editor)
        editor_layout.setContentsMargins(10, 8, 10, 8)
        editor_layout.setSpacing(5)
        title = QtWidgets.QLabel("Path movement threshold", editor)
        editor_layout.addWidget(title)
        threshold_input = QtWidgets.QDoubleSpinBox(editor)
        threshold_input.setDecimals(3)
        threshold_input.setRange(0.0, 1000000.0)
        threshold_input.setSingleStep(1.0)
        threshold_input.setSuffix(" units")
        threshold_input.setKeyboardTracking(False)
        threshold_input.setToolTip(
            "Motion below this distance is treated as in-place and uses "
            "the character's characterized rest-pose facing direction."
        )
        editor_layout.addWidget(threshold_input)
        explanation = QtWidgets.QLabel(
            "Shorter motion uses rest-pose facing. Motion at or above this "
            "distance aligns the travelling path to +Z.",
            editor,
        )
        explanation.setWordWrap(True)
        editor_layout.addWidget(explanation)
        widget_action = QtWidgets.QWidgetAction(menu)
        widget_action.setDefaultWidget(editor)
        menu.addAction(widget_action)
        menu.aboutToShow.connect(self._refresh_threshold_input)
        threshold_input.editingFinished.connect(self._commit_threshold)
        settings_button.setMenu(menu)
        popup_mode = getattr(
            getattr(
                QtWidgets.QToolButton,
                "ToolButtonPopupMode",
                QtWidgets.QToolButton,
            ),
            "InstantPopup",
        )
        settings_button.setPopupMode(popup_mode)
        layout.addWidget(settings_button)

        self.container = container
        self.action_button = action_button
        self.start_zero_button = start_zero_button
        self.settings_button = settings_button
        self.settings_menu = menu
        self.threshold_input = threshold_input
        self._refresh_threshold_input()

    def _position_controls(self, toolbar_snapshot):
        container = self.container
        if not self._valid(container):
            return
        try:
            x_position = (
                int(toolbar_snapshot["x"])
                + int(toolbar_snapshot["native_right"])
                + 6
            )
            maximum_x = max(
                0,
                int(toolbar_snapshot["host_width"])
                - int(container.width())
                - 2,
            )
            x_position = min(x_position, maximum_x)
            container.move(x_position, int(toolbar_snapshot["y"]))
            container.raise_()
        except Exception:
            pass

    def _refresh(self):
        self.refresh_pending = False
        if not self.started:
            return
        toolbar_snapshot = self._find_story_toolbar()
        if toolbar_snapshot is None:
            self.story_host = None
            self._detach_controls()
            return
        self._position_controls(toolbar_snapshot)
        selected_count = selected_story_clip_count()
        enabled = self.manager.is_enabled("story.reset_selected_clips")
        visible = bool(selected_count and enabled)
        try:
            self.action_button.setToolTip(
                "Reset %d selected Story clip(s) to 0,0,0 and align the "
                "root path or characterized facing direction to global +Z."
                % selected_count
            )
            self.start_zero_button.setToolTip(
                "Move %d selected Story clip(s) to frame 0 without changing "
                "clip duration." % selected_count
            )
            self.container.setVisible(visible)
            if visible:
                self.container.raise_()
        except Exception:
            self._detach_controls()

    def _run_command(self):
        self.manager.dispatch("story.reset_selected_clips")
        self._schedule_refresh()

    def _move_clips_to_zero(self):
        self.manager.dispatch("story.move_selected_clips_to_zero")
        self._schedule_refresh()

    def _refresh_threshold_input(self):
        if not self._valid(self.threshold_input):
            return
        values = self.manager.story_settings()
        value = float(
            values.get(
                "clip_path_min_distance",
                DEFAULTS["clip_path_min_distance"],
            )
        )
        self.threshold_input.setValue(value)

    def _commit_threshold(self):
        if not self._valid(self.threshold_input):
            return
        try:
            validated = self.manager.update_story_settings(
                {
                    "clip_path_min_distance": (
                        self.threshold_input.value()
                    ),
                }
            )
            self.threshold_input.setValue(
                float(validated["clip_path_min_distance"])
            )
        except Exception as error:
            QtWidgets.QMessageBox.warning(
                self.settings_menu,
                "Story Alignment Settings",
                str(error),
            )
            self._refresh_threshold_input()
