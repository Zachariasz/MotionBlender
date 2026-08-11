"""Persistent templates for MotionBuilder's native Save Options dialog."""

from __future__ import absolute_import

import hashlib
import json
import os
import shutil
import time
import traceback

try:
    from PySide6 import QtCore, QtGui, QtTest, QtWidgets
    import shiboken6 as shiboken
except ImportError:
    from PySide2 import QtCore, QtGui, QtTest, QtWidgets
    import shiboken2 as shiboken


FEATURE_NAME = "Save Options Templates"
PANEL_OBJECT_NAME = "MobuSaveOptionsTemplatesPanel"
ATTACHED_PROPERTY = "_mobu_save_options_templates_attached"
STORE_FILENAME = "save_options_templates.json"
STORE_VERSION = 1
NO_SELECTION_LABEL = "Save template..."
PATH_SAVE_DIALOG_TITLE = "Save As to Pasted Path..."
PATH_SAVE_MENU_NAME = "Save As to Pasted Path..."
# Main-menu command IDs must be allocated by FBMenuManager. Supplying an
# arbitrary ID to File-menu's FBGenericMenu can index outside MotionBuilder
# 2026.1's native command table and crash tooldesktop.dll.
MAX_MODEL_ROWS = 1000
MAX_MODEL_COLUMNS = 24
MAX_MODEL_DEPTH = 12
# MotionBuilder 2026 exposes these KxSpread tables as painted QWidget canvases,
# not QAbstractItemViews.  Ratios point at the centers of their state columns.
CUSTOM_SPREAD_SPECS = {
    "SpreadScene": {
        "rows": 28,
        "column_ratios": (30.0 / 162.0, 91.0 / 162.0),
    },
    "SpreadSetting": {
        "rows": 5,
        "column_ratios": (60.0 / 162.0,),
    },
    "SpreadTakes": {
        "rows": "takes",
        "column_ratios": (20.0 / 174.0,),
    },
}

_SERVICE = None


def _qt_enum(group_name, value_name):
    group = getattr(QtCore.Qt, group_name, None)
    if group is not None and hasattr(group, value_name):
        return getattr(group, value_name)
    return getattr(QtCore.Qt, value_name)


DISPLAY_ROLE = _qt_enum("ItemDataRole", "DisplayRole")
CHECK_STATE_ROLE = _qt_enum("ItemDataRole", "CheckStateRole")
DECORATION_ROLE = _qt_enum("ItemDataRole", "DecorationRole")
HORIZONTAL = _qt_enum("Orientation", "Horizontal")
LEFT_BUTTON = _qt_enum("MouseButton", "LeftButton")
NO_MODIFIER = _qt_enum("KeyboardModifier", "NoModifier")


def _enum_int(value, default=None):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(value.value)
        except (AttributeError, TypeError, ValueError):
            return default


def _safe(callback, default=None):
    try:
        return callback()
    except (AttributeError, RuntimeError, ReferenceError, TypeError):
        return default


def _is_valid(value):
    if value is None:
        return False
    try:
        return bool(shiboken.isValid(value))
    except Exception:
        try:
            value.metaObject()
            return True
        except (AttributeError, RuntimeError, ReferenceError):
            return False


def _class_name(widget):
    name = _safe(lambda: widget.metaObject().className(), None)
    return str(name or type(widget).__name__)


def _clean_text(value):
    return " ".join(str(value or "").replace("&", "").split())


def _widget_static_text(widget):
    values = [
        _safe(widget.objectName, ""),
        _safe(widget.accessibleName, ""),
        _safe(widget.accessibleDescription, ""),
    ]
    if isinstance(widget, QtWidgets.QAbstractButton):
        values.append(_safe(widget.text, ""))
    elif isinstance(widget, QtWidgets.QGroupBox):
        values.append(_safe(widget.title, ""))
    elif isinstance(widget, QtWidgets.QLabel):
        values.append(_safe(widget.text, ""))
    return "|".join(
        value for value in (_clean_text(item) for item in values) if value
    )


def _direct_widget_children(parent):
    return [
        child
        for child in _safe(parent.children, []) or []
        if isinstance(child, QtWidgets.QWidget)
    ]


def _widget_segment(widget):
    parent = _safe(widget.parentWidget, None)
    class_name = _class_name(widget)
    static_text = _widget_static_text(widget)
    ordinal = 0
    if parent is not None:
        peers = []
        for child in _direct_widget_children(parent):
            if _class_name(child) != class_name:
                continue
            if _widget_static_text(child) != static_text:
                continue
            peers.append(child)
        for index, peer in enumerate(peers):
            if peer is widget:
                ordinal = index
                break
    return "%s[%s]:%s" % (class_name, ordinal, static_text)


def _widget_key(widget, dialog):
    segments = []
    current = widget
    while current is not None and current is not dialog:
        segments.append(_widget_segment(current))
        current = _safe(current.parentWidget, None)
    segments.reverse()
    return "/".join(segments)


def _has_ancestor(widget, widget_type):
    current = _safe(widget.parentWidget, None)
    while current is not None:
        if isinstance(current, widget_type):
            return True
        current = _safe(current.parentWidget, None)
    return False


def _belongs_to_template_panel(widget):
    current = widget
    while current is not None:
        if _safe(current.objectName, "") == PANEL_OBJECT_NAME:
            return True
        current = _safe(current.parentWidget, None)
    return False


def _image_fingerprint(image):
    if image is None or image.isNull():
        return None
    byte_array = QtCore.QByteArray()
    buffer = QtCore.QBuffer(byte_array)
    if not buffer.open(QtCore.QIODevice.WriteOnly):
        return None
    try:
        if not image.save(buffer, "PNG"):
            return None
    finally:
        buffer.close()
    return hashlib.sha1(bytes(byte_array)).hexdigest()


def _icon_fingerprint(value):
    pixmap = None
    if isinstance(value, QtGui.QIcon):
        pixmap = value.pixmap(20, 20)
    elif isinstance(value, QtGui.QPixmap):
        pixmap = value
    elif isinstance(value, QtGui.QImage):
        image = value
    else:
        return None

    if pixmap is not None:
        if pixmap.isNull():
            return None
        image = pixmap.toImage()
    return _image_fingerprint(image)


def _model_data(model, index, role):
    try:
        return model.data(index, role)
    except TypeError:
        if role == DISPLAY_ROLE:
            return model.data(index)
        return None
    except (RuntimeError, ReferenceError):
        return None


def _model_header(model, column):
    try:
        value = model.headerData(column, HORIZONTAL, DISPLAY_ROLE)
    except TypeError:
        value = _safe(lambda: model.headerData(column, HORIZONTAL), "")
    except (RuntimeError, ReferenceError):
        value = ""
    return _clean_text(value)


def _row_label(model, parent, row, column_count):
    for column in range(min(column_count, MAX_MODEL_COLUMNS)):
        index = _safe(lambda c=column: model.index(row, c, parent), None)
        if index is None or not _safe(index.isValid, False):
            continue
        value = _model_data(model, index, DISPLAY_ROLE)
        text = _clean_text(value)
        if text:
            return text
    return ""


def _state_icon_column(headers, column):
    header = _clean_text(headers[column] if column < len(headers) else "").lower()
    hints = (
        "animation",
        "element",
        "export",
        "include",
        "save",
        "setting",
    )
    if any(hint in header for hint in hints):
        return True
    return column > 0 and not header


def _index_from_path(model, row_path, column):
    parent = QtCore.QModelIndex()
    for depth, row in enumerate(row_path):
        target_column = column if depth == len(row_path) - 1 else 0
        index = _safe(
            lambda r=int(row), c=target_column, p=parent: model.index(r, c, p),
            None,
        )
        if index is None or not _safe(index.isValid, False):
            return None
        if depth < len(row_path) - 1:
            parent = _safe(
                lambda r=int(row), p=parent: model.index(r, 0, p),
                None,
            )
            if parent is None or not _safe(parent.isValid, False):
                return None
    return index


def _capture_view(view, dialog):
    model = _safe(view.model, None)
    if model is None:
        return None
    column_count = min(
        int(_safe(lambda: model.columnCount(QtCore.QModelIndex()), 0) or 0),
        MAX_MODEL_COLUMNS,
    )
    headers = [_model_header(model, column) for column in range(column_count)]
    items = []
    visited_rows = [0]

    def walk(parent, row_path, label_path, depth):
        if depth > MAX_MODEL_DEPTH or visited_rows[0] >= MAX_MODEL_ROWS:
            return
        row_count = int(_safe(lambda: model.rowCount(parent), 0) or 0)
        local_columns = min(
            int(_safe(lambda: model.columnCount(parent), column_count) or 0),
            MAX_MODEL_COLUMNS,
        )
        for row in range(row_count):
            if visited_rows[0] >= MAX_MODEL_ROWS:
                return
            visited_rows[0] += 1
            label = _row_label(model, parent, row, local_columns)
            next_row_path = row_path + [row]
            next_label_path = label_path + [label]
            for column in range(local_columns):
                index = _safe(
                    lambda r=row, c=column, p=parent: model.index(r, c, p),
                    None,
                )
                if index is None or not _safe(index.isValid, False):
                    continue
                check_state = _model_data(model, index, CHECK_STATE_ROLE)
                check_value = _enum_int(check_state, None)
                if check_value is not None:
                    items.append(
                        {
                            "mode": "check",
                            "row_path": next_row_path,
                            "label_path": next_label_path,
                            "column": column,
                            "value": check_value,
                        }
                    )
                    continue
                if not _state_icon_column(headers, column):
                    continue
                decoration = _model_data(model, index, DECORATION_ROLE)
                fingerprint = _icon_fingerprint(decoration)
                if fingerprint:
                    items.append(
                        {
                            "mode": "icon",
                            "row_path": next_row_path,
                            "label_path": next_label_path,
                            "column": column,
                            "value": fingerprint,
                        }
                    )
            child_parent = _safe(
                lambda r=row, p=parent: model.index(r, 0, p),
                None,
            )
            if child_parent is not None and _safe(child_parent.isValid, False):
                walk(
                    child_parent,
                    next_row_path,
                    next_label_path,
                    depth + 1,
                )

    walk(QtCore.QModelIndex(), [], [], 0)
    if not items:
        return None
    return {
        "key": _widget_key(view, dialog),
        "class": _class_name(view),
        "headers": headers,
        "items": items,
    }


def _capture_widget(widget, dialog):
    key = _widget_key(widget, dialog)
    if isinstance(widget, QtWidgets.QAbstractButton):
        if _safe(widget.isCheckable, False):
            return {
                "key": key,
                "kind": "button",
                "checked": bool(_safe(widget.isChecked, False)),
            }
        return None
    if isinstance(widget, QtWidgets.QComboBox):
        return {
            "key": key,
            "kind": "combo",
            "index": int(_safe(widget.currentIndex, -1) or 0),
            "text": _clean_text(_safe(widget.currentText, "")),
        }
    if isinstance(widget, QtWidgets.QSpinBox):
        return {
            "key": key,
            "kind": "spin",
            "value": int(_safe(widget.value, 0) or 0),
        }
    if isinstance(widget, QtWidgets.QDoubleSpinBox):
        return {
            "key": key,
            "kind": "double_spin",
            "value": float(_safe(widget.value, 0.0) or 0.0),
        }
    if isinstance(widget, QtWidgets.QSlider):
        return {
            "key": key,
            "kind": "slider",
            "value": int(_safe(widget.value, 0) or 0),
        }
    if isinstance(widget, QtWidgets.QLineEdit):
        if _has_ancestor(widget, QtWidgets.QComboBox):
            return None
        if _has_ancestor(widget, QtWidgets.QAbstractSpinBox):
            return None
        return {
            "key": key,
            "kind": "line_edit",
            "text": str(_safe(widget.text, "") or ""),
        }
    return None


def _accessible_widget(root, name):
    for widget in _safe(
        lambda: root.findChildren(QtWidgets.QWidget), []
    ) or []:
        if str(_safe(widget.accessibleName, "") or "") == name:
            return widget
    return None


def _paint_canvas(widget):
    current = widget
    while current is not None:
        candidates = []
        for child in _direct_widget_children(current):
            if not _safe(child.isVisible, False):
                continue
            if child.width() < max(1, int(current.width() * 0.8)):
                continue
            if child.height() < max(1, int(current.height() * 0.8)):
                continue
            candidates.append(child)
        if not candidates:
            return current
        current = max(
            candidates,
            key=lambda child: child.width() * child.height(),
        )
    return widget


def _current_take_count():
    try:
        from pyfbsdk import FBSystem

        return max(0, len(FBSystem().Scene.Takes))
    except Exception:
        return 0


def _row_centers(canvas, row_count, pitch=None):
    if row_count <= 0:
        return []
    height = float(max(1, canvas.height()))
    if pitch is None or float(pitch) <= 0.0:
        pitch = height / float(row_count)
    pitch = float(pitch)
    return [
        min(height - 1.0, (float(row) + 0.5) * pitch)
        for row in range(row_count)
    ]


def _spread_row_centers(spread, canvas, row_count):
    columns = _accessible_widget(spread, "Columns")
    pitch = None
    if columns is not None:
        header_height = float(max(0, columns.height()))
        if header_height > 2.0:
            pitch = header_height - 1.0
    return _row_centers(canvas, row_count, pitch)


def _grab_canvas_image(canvas):
    pixmap = _safe(canvas.grab, None)
    if pixmap is None or pixmap.isNull():
        return None
    image = pixmap.toImage()
    if image.isNull():
        return None
    return image


def _image_patch_fingerprint(image, canvas_width, canvas_height, x, y):
    if image is None or image.isNull():
        return None
    scale_x = float(image.width()) / float(max(1, canvas_width))
    scale_y = float(image.height()) / float(max(1, canvas_height))
    center_x = int(round(float(x) * scale_x))
    center_y = int(round(float(y) * scale_y))
    half_width = max(7, int(round(10.0 * scale_x)))
    half_height = max(6, int(round(8.0 * scale_y)))
    left = max(0, center_x - half_width)
    top = max(0, center_y - half_height)
    right = min(image.width(), center_x + half_width + 1)
    bottom = min(image.height(), center_y + half_height + 1)
    if right <= left or bottom <= top:
        return None
    patch = image.copy(left, top, right - left, bottom - top)
    return _image_fingerprint(patch)


def _capture_custom_spread(spread, spread_name, spec):
    """Capture one painted save/discard table from a live widget handle."""
    if spread is None or not _is_valid(spread):
        return None
    cells = _accessible_widget(spread, "Cells")
    if cells is None:
        return None
    canvas = _paint_canvas(cells)
    if not _is_valid(canvas) or canvas.width() <= 0 or canvas.height() <= 0:
        return None
    row_spec = spec["rows"]
    row_count = _current_take_count() if row_spec == "takes" else int(row_spec)
    centers = _spread_row_centers(spread, canvas, row_count)
    image = _grab_canvas_image(canvas)
    if image is None:
        return None
    items = []
    for row, y in enumerate(centers):
        for column, ratio in enumerate(spec["column_ratios"]):
            x = float(canvas.width()) * float(ratio)
            fingerprint = _image_patch_fingerprint(
                image,
                canvas.width(),
                canvas.height(),
                x,
                y,
            )
            if fingerprint:
                items.append(
                    {
                        "row": row,
                        "column": column,
                        "value": fingerprint,
                    }
                )
    if not items:
        return None
    return {
        "name": spread_name,
        "row_count": row_count,
        "items": items,
    }


def _visible_accessible_widget(app, name):
    candidates = []
    for widget in _safe(app.allWidgets, []) or []:
        if not _is_valid(widget) or not _safe(widget.isVisible, False):
            continue
        if str(_safe(widget.accessibleName, "") or "") != name:
            continue
        candidates.append(widget)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda widget: max(1, widget.width()) * max(1, widget.height()),
    )


def _capture_custom_spreads(dialog=None, app=None):
    """Capture painted tables even if MotionBuilder invalidated the dialog."""
    records = []
    for spread_name, spec in CUSTOM_SPREAD_SPECS.items():
        spread = _accessible_widget(dialog, spread_name) if dialog else None
        if spread is None and app is not None:
            spread = _visible_accessible_widget(app, spread_name)
        record = _capture_custom_spread(spread, spread_name, spec)
        if record is not None:
            records.append(record)
    return records


def capture_dialog_state(dialog, app=None):
    widgets = []
    views = []
    for widget in _safe(
        lambda: dialog.findChildren(QtWidgets.QWidget), []
    ) or []:
        if not _is_valid(widget) or _belongs_to_template_panel(widget):
            continue
        if isinstance(widget, QtWidgets.QAbstractItemView):
            if _has_ancestor(widget, QtWidgets.QComboBox):
                continue
            record = _capture_view(widget, dialog)
            if record is not None:
                views.append(record)
            continue
        record = _capture_widget(widget, dialog)
        if record is not None:
            widgets.append(record)
    return {
        "schema": STORE_VERSION,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "widgets": widgets,
        "views": views,
        "spreads": _capture_custom_spreads(dialog, app),
    }


def _click_model_index(view, index):
    try:
        view.scrollTo(index)
    except (AttributeError, RuntimeError):
        pass
    rect = _safe(lambda: view.visualRect(index), None)
    if rect is None or not rect.isValid():
        return False
    point = rect.center()
    viewport = _safe(view.viewport, None)
    if viewport is None:
        return False
    try:
        QtTest.QTest.mouseClick(viewport, LEFT_BUTTON, NO_MODIFIER, point)
        return True
    except Exception:
        return False


def _check_state_matches(model, index, target):
    current = _enum_int(_model_data(model, index, CHECK_STATE_ROLE), None)
    return current == int(target)


def _icon_state_matches(model, index, target):
    current = _icon_fingerprint(_model_data(model, index, DECORATION_ROLE))
    return bool(current and current == target)


def _apply_view_record(view, record):
    model = _safe(view.model, None)
    if model is None:
        return 0
    applied = 0
    for item in record.get("items") or ():
        index = _index_from_path(
            model,
            item.get("row_path") or (),
            int(item.get("column", 0)),
        )
        if index is None:
            continue
        mode = item.get("mode")
        target = item.get("value")
        if mode == "check":
            if _check_state_matches(model, index, target):
                applied += 1
                continue
            set_ok = _safe(
                lambda i=index, value=int(target): model.setData(
                    i, value, CHECK_STATE_ROLE
                ),
                False,
            )
            if set_ok and _check_state_matches(model, index, target):
                applied += 1
                continue
            for _attempt in range(4):
                if not _click_model_index(view, index):
                    break
                if _check_state_matches(model, index, target):
                    applied += 1
                    break
        elif mode == "icon":
            if _icon_state_matches(model, index, target):
                applied += 1
                continue
            for _attempt in range(4):
                if not _click_model_index(view, index):
                    break
                if _icon_state_matches(model, index, target):
                    applied += 1
                    break
    return applied


def _apply_widget_record(widget, record):
    kind = record.get("kind")
    if kind == "button" and isinstance(widget, QtWidgets.QAbstractButton):
        target = bool(record.get("checked"))
        if bool(_safe(widget.isChecked, False)) != target:
            _safe(widget.click, None)
        if bool(_safe(widget.isChecked, False)) != target:
            _safe(lambda: widget.setChecked(target), None)
        return 1
    if kind == "combo" and isinstance(widget, QtWidgets.QComboBox):
        text = str(record.get("text") or "")
        index = widget.findText(text) if text else -1
        if index < 0:
            index = int(record.get("index", -1))
        if 0 <= index < widget.count():
            widget.setCurrentIndex(index)
            return 1
        return 0
    if kind == "spin" and isinstance(widget, QtWidgets.QSpinBox):
        widget.setValue(int(record.get("value", 0)))
        return 1
    if kind == "double_spin" and isinstance(widget, QtWidgets.QDoubleSpinBox):
        widget.setValue(float(record.get("value", 0.0)))
        return 1
    if kind == "slider" and isinstance(widget, QtWidgets.QSlider):
        widget.setValue(int(record.get("value", 0)))
        return 1
    if kind == "line_edit" and isinstance(widget, QtWidgets.QLineEdit):
        widget.setText(str(record.get("text") or ""))
        _safe(widget.editingFinished.emit, None)
        return 1
    return 0


def _click_custom_cell(canvas, x, y):
    point = QtCore.QPoint(
        max(0, min(canvas.width() - 1, int(round(x)))),
        max(0, min(canvas.height() - 1, int(round(y)))),
    )
    try:
        QtTest.QTest.mouseClick(
            canvas,
            LEFT_BUTTON,
            NO_MODIFIER,
            point,
        )
        return True
    except Exception:
        return False


def _apply_custom_spread(dialog, record, app=None):
    """Cycle painted cells until their visual state matches the template."""
    name = record.get("name")
    spec = CUSTOM_SPREAD_SPECS.get(name)
    if spec is None:
        return 0
    spread = _accessible_widget(dialog, name) if dialog else None
    if spread is None and app is not None:
        spread = _visible_accessible_widget(app, name)
    if spread is None:
        return 0
    cells = _accessible_widget(spread, "Cells")
    if cells is None:
        return 0
    canvas = _paint_canvas(cells)
    if not _is_valid(canvas) or canvas.width() <= 0 or canvas.height() <= 0:
        return 0

    row_spec = spec["rows"]
    available_rows = (
        _current_take_count() if row_spec == "takes" else int(row_spec)
    )
    target_rows = int(record.get("row_count", 0) or 0)
    row_count = min(available_rows, target_rows)
    centers = _spread_row_centers(
        spread,
        canvas,
        max(1, available_rows),
    )
    image = _grab_canvas_image(canvas)
    if image is None:
        return 0
    applied = 0
    for item in record.get("items") or ():
        row = int(item.get("row", -1))
        column = int(item.get("column", -1))
        if row < 0 or row >= row_count:
            continue
        ratios = spec["column_ratios"]
        if column < 0 or column >= len(ratios):
            continue
        x = float(canvas.width()) * float(ratios[column])
        y = centers[row]
        target = item.get("value")
        current = _image_patch_fingerprint(
            image,
            canvas.width(),
            canvas.height(),
            x,
            y,
        )
        if current == target:
            applied += 1
            continue
        for _attempt in range(3):
            if not _click_custom_cell(canvas, x, y):
                break
            image = _grab_canvas_image(canvas)
            current = _image_patch_fingerprint(
                image,
                canvas.width(),
                canvas.height(),
                x,
                y,
            )
            if current == target:
                applied += 1
                break
    return applied


def apply_dialog_state(dialog, state, app=None):
    current_widgets = {}
    current_views = {}
    views_by_headers = {}
    for widget in _safe(
        lambda: dialog.findChildren(QtWidgets.QWidget), []
    ) or []:
        if not _is_valid(widget) or _belongs_to_template_panel(widget):
            continue
        if isinstance(widget, QtWidgets.QAbstractItemView):
            if _has_ancestor(widget, QtWidgets.QComboBox):
                continue
            key = _widget_key(widget, dialog)
            current_views[key] = widget
            model = _safe(widget.model, None)
            if model is not None:
                count = min(
                    int(
                        _safe(
                            lambda: model.columnCount(QtCore.QModelIndex()),
                            0,
                        )
                        or 0
                    ),
                    MAX_MODEL_COLUMNS,
                )
                headers = tuple(
                    _model_header(model, column) for column in range(count)
                )
                views_by_headers.setdefault(headers, []).append(widget)
            continue
        record = _capture_widget(widget, dialog)
        if record is not None:
            current_widgets[record["key"]] = widget

    applied = 0
    for record in state.get("spreads") or ():
        applied += _apply_custom_spread(dialog, record, app)

    for record in state.get("views") or ():
        view = current_views.get(record.get("key"))
        if view is None:
            candidates = views_by_headers.get(tuple(record.get("headers") or ()))
            if candidates and len(candidates) == 1:
                view = candidates[0]
        if view is not None:
            applied += _apply_view_record(view, record)

    for record in state.get("widgets") or ():
        widget = current_widgets.get(record.get("key"))
        if widget is not None:
            applied += _apply_widget_record(widget, record)
    return applied


class TemplateStore(object):
    def __init__(self, directory):
        self.directory = os.path.abspath(directory)
        self.path = os.path.join(self.directory, STORE_FILENAME)
        self.templates = {}
        self.last_error = None

    def load(self):
        self.templates = {}
        self.last_error = None
        if not os.path.isfile(self.path):
            return self.templates
        try:
            with open(self.path, "r", encoding="utf-8-sig") as stream:
                payload = json.load(stream)
            templates = payload.get("templates") if isinstance(payload, dict) else None
            if not isinstance(templates, dict):
                raise ValueError("templates must be a JSON object")
            self.templates = dict(
                (str(name), value)
                for name, value in templates.items()
                if str(name).strip() and isinstance(value, dict)
            )
        except Exception:
            self.last_error = traceback.format_exc()
            stamp = time.strftime("%Y%m%d-%H%M%S")
            invalid_path = self.path + ".invalid-" + stamp
            try:
                shutil.copy2(self.path, invalid_path)
            except Exception:
                pass
            self.templates = {}
        return self.templates

    def save(self):
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
        payload = {
            "version": STORE_VERSION,
            "templates": self.templates,
        }
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        try:
            os.replace(temporary, self.path)
        except AttributeError:
            if os.path.exists(self.path):
                os.remove(self.path)
            os.rename(temporary, self.path)

    def names(self):
        return sorted(self.templates, key=lambda value: value.casefold())


class SaveOptionsTemplatePanel(QtWidgets.QFrame):
    def __init__(self, service, dialog):
        QtWidgets.QFrame.__init__(self, dialog)
        self.service = service
        self.dialog = dialog
        self._add_pending = False
        self._pending_state = None
        self._cached_state = None
        self.setObjectName(PANEL_OBJECT_NAME)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setAutoFillBackground(True)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(3)

        self.combo = QtWidgets.QComboBox(self)
        self.combo.setMinimumWidth(220)
        self.combo.setToolTip("Apply a saved Save Options template")
        self.add_button = QtWidgets.QPushButton("+", self)
        self.remove_button = QtWidgets.QPushButton("-", self)
        for button in (self.add_button, self.remove_button):
            button.setFixedSize(25, 24)
        self.add_button.setToolTip("Save the current options as a template")
        self.remove_button.setToolTip("Remove the selected template")

        self.name_label = QtWidgets.QLabel("Template name:", self)
        self.name_edit = QtWidgets.QLineEdit(self)
        self.name_edit.setMinimumWidth(180)
        self.name_edit.setPlaceholderText("Enter a template name")
        self.name_save_button = QtWidgets.QPushButton("Save", self)
        self.name_cancel_button = QtWidgets.QPushButton("Cancel", self)
        for widget in (
            self.name_label,
            self.name_edit,
            self.name_save_button,
            self.name_cancel_button,
        ):
            widget.hide()

        layout.addWidget(self.combo)
        layout.addWidget(self.add_button)
        layout.addWidget(self.remove_button)
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.name_save_button)
        layout.addWidget(self.name_cancel_button)
        self.reload_names()

        self.combo.currentIndexChanged.connect(self._on_selection_changed)
        # Use pressed so the inline prompt appears immediately even when the
        # native modal dialog consumes the corresponding mouse-release event.
        self.add_button.pressed.connect(self._on_add)
        self.remove_button.clicked.connect(self._on_remove)
        self.name_edit.returnPressed.connect(self._save_inline_name)
        self.name_save_button.clicked.connect(self._save_inline_name)
        self.name_cancel_button.clicked.connect(self._cancel_inline_name)

    def reload_names(self, selected_name=None):
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            self.combo.addItem(NO_SELECTION_LABEL, None)
            selected_index = 0
            for name in self.service.store.names():
                self.combo.addItem(name, name)
                if name == selected_name:
                    selected_index = self.combo.count() - 1
            self.combo.setCurrentIndex(selected_index)
        finally:
            self.combo.blockSignals(False)

    def selected_name(self):
        value = self.combo.currentData()
        return str(value) if value else None

    def _on_selection_changed(self, _index):
        name = self.selected_name()
        if name:
            self.service.apply_template(self._host_dialog(), name)

    def _host_dialog(self):
        dialog = self.service._save_options_dialog_for(self)
        if dialog is not None:
            return dialog
        for callback in (self.parentWidget, self.window):
            candidate = _safe(callback, None)
            if candidate is not None and candidate is not self and _is_valid(candidate):
                return candidate
        return self.dialog if _is_valid(self.dialog) else None

    def _on_add(self):
        if self._add_pending:
            return
        self.service.add_click_count += 1
        self.service.prompt_show_count += 1
        self.service.last_add_stage = "capturing-options"
        dialog = self._host_dialog()
        try:
            state = capture_dialog_state(dialog, self.service.app)
            if (
                not state["widgets"]
                and not state["views"]
                and not state["spreads"]
            ):
                state = self._cached_state
            if not state or (
                not state.get("widgets")
                and not state.get("views")
                and not state.get("spreads")
            ):
                raise RuntimeError("No supported Save Options controls were found")
            self._pending_state = state
            self._cached_state = state
            self.service.last_error = None
        except Exception:
            self._pending_state = None
            self.service.last_error = traceback.format_exc()
            self.service.last_add_stage = "capture-error"
        self._add_pending = True
        for widget in (self.combo, self.add_button, self.remove_button):
            widget.hide()
        for widget in (
            self.name_label,
            self.name_edit,
            self.name_save_button,
            self.name_cancel_button,
        ):
            widget.show()
        self.name_edit.clear()
        if self._pending_state is None:
            self.name_label.setText("Could not capture options")
            self.name_edit.setPlaceholderText("Press Cancel and try again")
            self.name_edit.setEnabled(False)
            self.name_save_button.setEnabled(False)
        else:
            self.name_label.setText("Template name:")
            self.name_edit.setPlaceholderText("Enter a template name")
            self.name_edit.setEnabled(True)
            self.name_save_button.setEnabled(True)
            self.service.last_add_stage = "inline-prompt-visible"
            self.name_edit.setFocus()
        self._refresh_size()

    def _save_inline_name(self, _checked=False):
        name = _clean_text(self.name_edit.text())
        if not name:
            self.service.last_add_stage = "empty-name"
            self.name_edit.setPlaceholderText("A name is required")
            self.name_edit.setFocus()
            return
        self.name_save_button.setEnabled(False)
        if self._pending_state is None:
            self.service.last_add_stage = "capture-missing"
            return
        self.service.last_add_stage = "saving"
        try:
            saved = self.service.add_template(
                self._host_dialog(),
                self,
                name,
                state=self._pending_state,
            )
        finally:
            if _is_valid(self.name_save_button):
                self.name_save_button.setEnabled(True)
        if saved:
            self.finish_add()

    def _cancel_inline_name(self, _checked=False):
        self.service.last_add_stage = "cancelled"
        self.finish_add()

    def _refresh_size(self):
        if not _is_valid(self):
            return
        self.layout().invalidate()
        self.adjustSize()
        self.resize(self.sizeHint())
        self.service._position_panel(id(self.dialog))
        self.raise_()

    def finish_add(self):
        if _is_valid(self):
            self._add_pending = False
            self._pending_state = None
            for widget in (
                self.name_label,
                self.name_edit,
                self.name_save_button,
                self.name_cancel_button,
            ):
                widget.hide()
            for widget in (self.combo, self.add_button, self.remove_button):
                widget.show()
            self.name_edit.setEnabled(True)
            self.name_save_button.setEnabled(True)
            self.add_button.setEnabled(True)
            self._refresh_size()

    def _on_remove(self):
        name = self.selected_name()
        if name:
            self.service.remove_template(name)
            self.reload_names()


class PastePathSaveDialog(QtWidgets.QDialog):
    """Paste-friendly replacement for MotionBuilder's first Save As screen."""

    def __init__(self, service, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.service = service
        self.setObjectName("MobuPastePathSaveDialog")
        self.setWindowTitle(PATH_SAVE_DIALOG_TITLE.rstrip("."))
        self.setModal(True)
        self.setMinimumWidth(620)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        explanation = QtWidgets.QLabel(
            "Paste a destination folder, or paste a complete .fbx path "
            "into the folder field.",
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        folder_row = QtWidgets.QWidget(self)
        folder_layout = QtWidgets.QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(5)
        self.folder_edit = QtWidgets.QLineEdit(folder_row)
        self.folder_edit.setPlaceholderText(
            r"C:\project\scenes  or  C:\project\scenes\shot.fbx"
        )
        self.browse_button = QtWidgets.QPushButton("Browse...", folder_row)
        folder_layout.addWidget(self.folder_edit, 1)
        folder_layout.addWidget(self.browse_button)
        form.addRow("Folder / full path:", folder_row)

        self.filename_edit = QtWidgets.QLineEdit(self)
        self.filename_edit.setPlaceholderText("scene.fbx")
        form.addRow("File name:", self.filename_edit)
        layout.addLayout(form)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel", self)
        self.continue_button = QtWidgets.QPushButton(
            "Continue to Save Options",
            self,
        )
        self.continue_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.continue_button)
        layout.addLayout(button_row)

        self.browse_button.clicked.connect(self._browse)
        self.cancel_button.clicked.connect(self.reject)
        self.continue_button.clicked.connect(self._continue)
        self.folder_edit.returnPressed.connect(self._continue)
        self.filename_edit.returnPressed.connect(self._continue)

    def set_defaults(self, folder, filename):
        self.folder_edit.setText(str(folder or ""))
        self.filename_edit.setText(str(filename or ""))
        self.folder_edit.selectAll()
        self.folder_edit.setFocus()

    def _browse(self, _checked=False):
        initial = self.folder_edit.text().strip().strip('"')
        if not os.path.isdir(initial):
            initial = os.path.dirname(initial)
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose Save Folder",
            initial,
        )
        if path:
            self.folder_edit.setText(str(path))

    def _continue(self, _checked=False):
        if self.service.prepare_path_save(
            self,
            self.folder_edit.text(),
            self.filename_edit.text(),
        ):
            self.accept()


class SaveOptionsTemplateService(QtCore.QObject):
    def __init__(self, context):
        app = context.qt_application
        QtCore.QObject.__init__(self, app)
        self.app = app
        self.context = context
        user_config_path = str(context.system.UserConfigPath)
        settings_directory = os.path.join(
            user_config_path,
            "MotionBuilderToolsManager",
        )
        self.store = TemplateStore(settings_directory)
        self.store.load()
        self.running = False
        self.dialogs = {}
        self.last_error = None
        self.last_apply_count = 0
        self.last_detected_widget_count = 0
        self.last_detected_view_count = 0
        self.last_detected_spread_count = 0
        self.last_detected_classes = {}
        self.add_click_count = 0
        self.prompt_show_count = 0
        self.last_add_stage = None
        self.name_prompts = {}
        self.path_save_dialog = None
        self.pending_save_path = None
        self.last_explicit_save_path = None
        self.last_explicit_save_result = None
        self.last_explicit_save_error = None
        self.file_menu = None
        self.file_menu_item = None
        self.file_menu_item_id = None
        self.file_menu_placement = None
        self.file_menu_callback = self._on_file_menu_activate
        self.file_menu_activation_count = 0
        self.last_file_menu_stage = None
        self.file_menu_error = None
        self._focus_window_connected = False

    def start(self):
        if self.running:
            return self
        if self.app is None:
            raise RuntimeError("MotionBuilder QApplication is unavailable")
        self.app.focusChanged.connect(self._on_focus_changed)
        focus_window_signal = getattr(self.app, "focusWindowChanged", None)
        if focus_window_signal is not None:
            try:
                focus_window_signal.connect(self._on_focus_window_changed)
                self._focus_window_connected = True
            except Exception:
                self._focus_window_connected = False
        self.running = True
        try:
            self._install_file_menu_item()
        except Exception:
            # Keep the template overlay available even if a customized install
            # does not expose MotionBuilder's standard File menu.
            self.file_menu_error = traceback.format_exc()
        QtCore.QTimer.singleShot(0, self.scan_visible_dialogs)
        return self

    def stop(self):
        if (
            not self.running
            and not self.dialogs
            and self.file_menu_item is None
        ):
            return
        self.running = False
        self._remove_file_menu_item()
        try:
            self.app.focusChanged.disconnect(self._on_focus_changed)
        except Exception:
            pass
        if self._focus_window_connected:
            try:
                self.app.focusWindowChanged.disconnect(
                    self._on_focus_window_changed
                )
            except Exception:
                pass
        self._focus_window_connected = False
        if _is_valid(self.path_save_dialog):
            try:
                self.path_save_dialog.close()
                self.path_save_dialog.deleteLater()
            except Exception:
                pass
        self.path_save_dialog = None
        self.pending_save_path = None
        for key in list(self.name_prompts):
            self._close_name_prompt(key)
        for key in list(self.dialogs):
            self._detach_dialog(key)

    def _install_file_menu_item(self):
        """Register the command using MotionBuilder's own ID allocator."""
        if self.file_menu_item is not None:
            return self.file_menu_item
        from pyfbsdk import FBMenuManager

        menu_manager = FBMenuManager()
        file_menu = menu_manager.GetMenu("File")
        if file_menu is None:
            raise RuntimeError("MotionBuilder's File menu is unavailable")

        save_as_caption = self._find_save_as_menu_caption(file_menu)
        item = None
        placed_after_save_as = False
        if save_as_caption:
            try:
                item = menu_manager.InsertAfter(
                    "File",
                    save_as_caption,
                    PATH_SAVE_MENU_NAME,
                )
                placed_after_save_as = item is not None
            except Exception:
                item = None
        if item is None:
            item = menu_manager.InsertLast("File", PATH_SAVE_MENU_NAME)
        if item is None:
            raise RuntimeError("MotionBuilder did not create the File-menu item")
        item_id = int(item.Id)

        try:
            file_menu.OnMenuActivate.Add(self.file_menu_callback)
        except Exception:
            try:
                file_menu.DeleteItem(item)
            except Exception:
                pass
            raise

        self.file_menu = file_menu
        self.file_menu_item = item
        self.file_menu_item_id = item_id
        self.file_menu_placement = (
            "after-save-as" if placed_after_save_as else "end-of-file-menu"
        )
        self.file_menu_error = None
        self.last_file_menu_stage = "installed"
        return item

    @staticmethod
    def _find_save_as_menu_caption(file_menu):
        """Return the exact native caption used by the existing Save As item."""
        item = file_menu.GetFirstItem()
        for _index in range(512):
            if item is None:
                break
            caption = str(getattr(item, "Caption", "") or "")
            visible_caption = caption.split("\t", 1)[0]
            label = _clean_text(visible_caption).rstrip(".\u2026").strip().casefold()
            if label == "save as":
                return caption
            item = file_menu.GetNextItem(item)
        return None

    def _remove_file_menu_item(self):
        file_menu = self.file_menu
        item = self.file_menu_item
        callback = self.file_menu_callback
        self.file_menu = None
        self.file_menu_item = None
        self.file_menu_item_id = None
        self.file_menu_placement = None
        if file_menu is None:
            return
        try:
            file_menu.OnMenuActivate.Remove(callback)
        except Exception:
            pass
        if item is not None:
            try:
                file_menu.DeleteItem(item)
            except Exception:
                pass

    def _on_file_menu_activate(self, _control, event):
        # Never let an exception escape an FBEvent callback: MotionBuilder
        # unregisters Python callbacks that raise during native dispatch.
        try:
            event_id = _enum_int(getattr(event, "Id", None), None)
            if event_id is None or event_id != self.file_menu_item_id:
                return
            self.file_menu_activation_count += 1
            self.last_file_menu_stage = "clicked"
            # Let the native menu close before creating a modal Qt dialog.
            QtCore.QTimer.singleShot(
                100,
                self._show_path_dialog_from_file_menu,
            )
        except Exception:
            self.file_menu_error = traceback.format_exc()
            self.last_file_menu_stage = "callback-error"

    def _show_path_dialog_from_file_menu(self):
        if not self.running:
            return
        try:
            self.last_file_menu_stage = "opening-dialog"
            self.show_path_save_dialog()
            self.last_file_menu_stage = "dialog-open"
        except Exception:
            self.file_menu_error = traceback.format_exc()
            self.last_file_menu_stage = "dialog-error"
            self._show_error(
                _safe(self.app.activeWindow, None),
                "Could not open the pasted-path Save As window.",
            )

    def _on_focus_changed(self, _old, current):
        if not self.running:
            return
        dialog = self._save_options_dialog_for(current)
        if dialog is not None:
            self._attach_dialog(dialog)

    def _default_save_destination(self):
        current = str(getattr(self.context.application, "FBXFileName", "") or "")
        current = os.path.normpath(current) if current else ""
        folder = os.path.dirname(current) if current else ""
        filename = os.path.basename(current) if current else ""
        if not folder or not os.path.isdir(folder):
            try:
                from pyfbsdk import FBFilePopup

                folder = str(FBFilePopup().Path or "")
            except Exception:
                folder = ""
        if not filename or not filename.lower().endswith(".fbx"):
            filename = "Untitled.fbx"
        return folder, filename

    def show_path_save_dialog(self):
        if not self.running:
            return None
        if _is_valid(self.path_save_dialog):
            self.path_save_dialog.show()
            self.path_save_dialog.raise_()
            self.path_save_dialog.activateWindow()
            return self.path_save_dialog
        parent = _safe(self.app.activeWindow, None)
        dialog = PastePathSaveDialog(self, parent)
        folder, filename = self._default_save_destination()
        dialog.set_defaults(folder, filename)
        dialog.finished.connect(self._path_save_dialog_finished)
        self.path_save_dialog = dialog
        dialog.open()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _path_save_dialog_finished(self, result):
        dialog = self.path_save_dialog
        self.path_save_dialog = None
        accepted_group = getattr(QtWidgets.QDialog, "DialogCode", None)
        accepted_value = (
            getattr(accepted_group, "Accepted", None)
            if accepted_group is not None
            else None
        )
        if accepted_value is None:
            accepted_value = getattr(QtWidgets.QDialog, "Accepted", 1)
        accepted = _enum_int(result, -1) == _enum_int(accepted_value, 1)
        if _is_valid(dialog):
            dialog.deleteLater()
        if accepted and self.pending_save_path:
            QtCore.QTimer.singleShot(0, self._execute_pending_path_save)
        else:
            self.pending_save_path = None

    def _clean_pasted_path(self, value):
        value = str(value or "").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1].strip()
        return os.path.expandvars(os.path.expanduser(value))

    def prepare_path_save(self, dialog, folder_value, filename_value):
        folder = self._clean_pasted_path(folder_value)
        filename = self._clean_pasted_path(filename_value)
        if folder.lower().endswith(".fbx") and not os.path.isdir(folder):
            filename = os.path.basename(folder)
            folder = os.path.dirname(folder)
        elif os.path.dirname(filename):
            folder = os.path.dirname(filename)
            filename = os.path.basename(filename)
        folder = os.path.normpath(folder) if folder else ""
        filename = os.path.basename(filename.strip())
        if not folder or not os.path.isabs(folder):
            QtWidgets.QMessageBox.warning(
                dialog,
                PATH_SAVE_DIALOG_TITLE,
                "Paste an absolute destination folder or a complete .fbx path.",
            )
            return False
        if not filename:
            QtWidgets.QMessageBox.warning(
                dialog,
                PATH_SAVE_DIALOG_TITLE,
                "Enter a file name.",
            )
            return False
        if not filename.lower().endswith(".fbx"):
            filename += ".fbx"
        if not os.path.isdir(folder):
            answer = QtWidgets.QMessageBox.question(
                dialog,
                PATH_SAVE_DIALOG_TITLE,
                "The folder does not exist. Create it?\n\n" + folder,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return False
            try:
                os.makedirs(folder)
            except Exception:
                self.last_explicit_save_error = traceback.format_exc()
                QtWidgets.QMessageBox.critical(
                    dialog,
                    PATH_SAVE_DIALOG_TITLE,
                    "Could not create the destination folder.\n\n"
                    + self.last_explicit_save_error[-1200:],
                )
                return False
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            answer = QtWidgets.QMessageBox.question(
                dialog,
                PATH_SAVE_DIALOG_TITLE,
                "Replace the existing file?\n\n" + path,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return False
        self.pending_save_path = path
        return True

    def _execute_pending_path_save(self):
        path = self.pending_save_path
        self.pending_save_path = None
        if not path or not self.running:
            return False
        self.last_explicit_save_path = path
        self.last_explicit_save_result = None
        self.last_explicit_save_error = None
        try:
            from pyfbsdk import FBFbxOptions

            options = FBFbxOptions(False)
            options.ShowFileDialog = False
            options.ShowOptionsDialog = True
            options.UpdateRecentFiles = True
            self.last_explicit_save_result = bool(
                self.context.application.FileSave(path, options)
            )
            return self.last_explicit_save_result
        except Exception:
            self.last_explicit_save_error = traceback.format_exc()
            QtWidgets.QMessageBox.critical(
                _safe(self.app.activeWindow, None),
                PATH_SAVE_DIALOG_TITLE,
                "Could not start Save As.\n\n"
                + self.last_explicit_save_error[-1200:],
            )
            return False

    def _on_focus_window_changed(self, _window):
        if self.running:
            self.scan_visible_dialogs()

    def scan_visible_dialogs(self):
        if not self.running or self.app is None:
            return
        for widget in list(self.app.topLevelWidgets()):
            if not _is_valid(widget) or not _safe(widget.isVisible, False):
                continue
            if self._is_save_options_dialog(widget):
                self._attach_dialog(widget)

    def _save_options_dialog_for(self, widget):
        if widget is None or not _is_valid(widget):
            return None
        window = _safe(widget.window, None)
        if window is not None and self._is_save_options_dialog(window):
            return window
        return None

    def _is_save_options_dialog(self, widget):
        if widget is None or _belongs_to_template_panel(widget):
            return False
        title = _clean_text(_safe(widget.windowTitle, "")).lower()
        if not title or "save" not in title or not title.endswith("options"):
            return False
        if "template" in title or title.startswith("open "):
            return False
        return True

    def _attach_dialog(self, dialog):
        key = id(dialog)
        if key in self.dialogs or not _is_valid(dialog):
            return
        if bool(_safe(lambda: dialog.property(ATTACHED_PROPERTY), False)):
            return
        try:
            panel = SaveOptionsTemplatePanel(self, dialog)
            destroyed_callback = (
                lambda _object=None, dialog_key=key: self._dialog_destroyed(
                    dialog_key
                )
            )
            dialog.destroyed.connect(destroyed_callback)
            dialog.installEventFilter(self)
            dialog.setProperty(ATTACHED_PROPERTY, True)
            self.dialogs[key] = {
                "dialog": dialog,
                "panel": panel,
                "destroyed_callback": destroyed_callback,
            }
            detected_state = capture_dialog_state(dialog, self.app)
            panel._cached_state = detected_state
            self.last_detected_widget_count = len(
                detected_state.get("widgets") or ()
            )
            self.last_detected_view_count = len(
                detected_state.get("views") or ()
            )
            self.last_detected_spread_count = len(
                detected_state.get("spreads") or ()
            )
            classes = {}
            for child in _safe(
                lambda: dialog.findChildren(QtWidgets.QWidget), []
            ) or []:
                name = _class_name(child)
                classes[name] = classes.get(name, 0) + 1
            self.last_detected_classes = classes
            self._position_panel(key)
            panel.show()
            panel.raise_()
        except Exception:
            self.last_error = traceback.format_exc()
            self._detach_dialog(key)

    def _detach_dialog(self, key):
        record = self.dialogs.pop(key, None)
        if not record:
            return
        dialog = record.get("dialog")
        panel = record.get("panel")
        callback = record.get("destroyed_callback")
        if panel is not None:
            self._close_name_prompt(id(panel))
        if _is_valid(dialog):
            try:
                dialog.removeEventFilter(self)
            except Exception:
                pass
            if callback is not None:
                try:
                    dialog.destroyed.disconnect(callback)
                except Exception:
                    pass
            try:
                dialog.setProperty(ATTACHED_PROPERTY, False)
            except Exception:
                pass
        if _is_valid(panel):
            try:
                panel.hide()
                panel.setParent(None)
                panel.deleteLater()
            except Exception:
                pass

    def _dialog_destroyed(self, key):
        self.dialogs.pop(key, None)

    def _position_panel(self, key):
        record = self.dialogs.get(key)
        if not record:
            return
        dialog = record["dialog"]
        panel = record["panel"]
        if not _is_valid(dialog) or not _is_valid(panel):
            return
        panel.adjustSize()
        margin = 10
        x = max(margin, dialog.width() - panel.width() - margin)
        panel.move(x, margin)
        panel.raise_()

    def eventFilter(self, watched, event):
        key = id(watched)
        if key in self.dialogs:
            event_type = _safe(event.type, None)
            names = ("Resize", "Show", "LayoutRequest")
            tracked = set()
            event_group = getattr(QtCore.QEvent, "Type", None)
            for name in names:
                value = (
                    getattr(event_group, name, None)
                    if event_group is not None
                    else None
                )
                if value is None:
                    value = getattr(QtCore.QEvent, name, None)
                if value is not None:
                    tracked.add(value)
            if event_type in tracked:
                self._position_panel(key)
        return False

    def begin_add_template(self, dialog, panel):
        """Ask for a name using MotionBuilder's native modal input box."""
        from pyfbsdk import FBMessageBoxGetUserValue, FBPopupInputType

        self.last_add_stage = "prompt-opening"
        self.prompt_show_count += 1
        button, name = FBMessageBoxGetUserValue(
            FEATURE_NAME,
            "Template name:",
            "",
            FBPopupInputType.kFBPopupString,
            "Save",
            "Cancel",
            None,
            1,
            True,
        )
        if int(button) != 1:
            self.last_add_stage = "cancelled"
            panel.finish_add()
            return False
        self.last_add_stage = "name-accepted"
        QtCore.QTimer.singleShot(
            0,
            lambda d=dialog, p=panel, n=str(name or ""): (
                self._complete_add_template(d, p, n)
            ),
        )
        return True

    def _close_name_prompt(self, key):
        record = self.name_prompts.pop(key, None)
        if record is None:
            return
        prompt = record.get("prompt")
        callback = record.get("finished_callback")
        if _is_valid(prompt):
            if callback is not None:
                try:
                    prompt.finished.disconnect(callback)
                except Exception:
                    pass
            try:
                prompt.close()
                prompt.deleteLater()
            except Exception:
                pass
        panel = record.get("panel")
        if _is_valid(panel):
            panel.finish_add()

    def _complete_add_template(self, dialog, panel, name):
        try:
            self.add_template(dialog, panel, name)
        finally:
            if _is_valid(panel):
                panel.finish_add()

    def add_template(self, dialog, panel, name, state=None):
        try:
            name = _clean_text(name)
            if not name:
                self.last_add_stage = "empty-name"
                return False
            if state is None:
                if dialog is None or not _is_valid(dialog):
                    raise RuntimeError("The Save Options window is unavailable")
                state = capture_dialog_state(dialog)
            if (
                not state["widgets"]
                and not state["views"]
                and not state["spreads"]
            ):
                raise RuntimeError("No supported Save Options controls were found")

            previous = self.store.templates.get(name)
            self.store.templates[name] = state
            try:
                self.store.save()
            except Exception:
                if previous is None:
                    self.store.templates.pop(name, None)
                else:
                    self.store.templates[name] = previous
                raise
            if _is_valid(panel):
                panel.reload_names(name)
            self.last_error = None
            self.last_add_stage = "saved"
            return True
        except Exception:
            self.last_error = traceback.format_exc()
            self.last_add_stage = "save-error"
            self._show_error(dialog, "Could not save the template.")
            return False

    def _show_error(self, dialog, summary):
        details = (self.last_error or "Unknown error")[-1200:]
        try:
            QtWidgets.QMessageBox.critical(
                dialog,
                FEATURE_NAME,
                summary + "\n\n" + details,
            )
        except Exception:
            print("%s: %s\n%s" % (FEATURE_NAME, summary, details))

    def remove_template(self, name):
        if name not in self.store.templates:
            return False
        original = self.store.templates.pop(name)
        try:
            self.store.save()
            return True
        except Exception:
            self.store.templates[name] = original
            self.last_error = traceback.format_exc()
            return False

    def apply_template(self, dialog, name):
        state = self.store.templates.get(name)
        if not isinstance(state, dict):
            return 0
        try:
            self.last_apply_count = apply_dialog_state(dialog, state, self.app)
            self.last_error = None
            return self.last_apply_count
        except Exception:
            self.last_error = traceback.format_exc()
            QtWidgets.QMessageBox.critical(
                dialog,
                FEATURE_NAME,
                "Could not apply the template.\n\n" + self.last_error[-1200:],
            )
            return 0

    def status(self):
        return {
            "running": self.running,
            "attached_dialogs": len(self.dialogs),
            "template_count": len(self.store.templates),
            "store_path": self.store.path,
            "last_apply_count": self.last_apply_count,
            "last_detected_widget_count": self.last_detected_widget_count,
            "last_detected_view_count": self.last_detected_view_count,
            "last_detected_spread_count": self.last_detected_spread_count,
            "last_detected_classes": dict(self.last_detected_classes),
            "add_click_count": self.add_click_count,
            "prompt_show_count": self.prompt_show_count,
            "active_name_prompts": len(self.name_prompts),
            "last_add_stage": self.last_add_stage,
            "path_save_dialog_open": _is_valid(self.path_save_dialog),
            "last_explicit_save_path": self.last_explicit_save_path,
            "last_explicit_save_result": self.last_explicit_save_result,
            "last_explicit_save_error": self.last_explicit_save_error,
            "file_menu_installed": self.file_menu_item is not None,
            "file_menu_item_id": self.file_menu_item_id,
            "file_menu_placement": self.file_menu_placement,
            "file_menu_activation_count": self.file_menu_activation_count,
            "last_file_menu_stage": self.last_file_menu_stage,
            "file_menu_error": self.file_menu_error,
            "last_error": self.last_error or self.store.last_error,
        }


def start(context):
    global _SERVICE
    if _SERVICE is not None and _SERVICE.running:
        return _SERVICE
    if _SERVICE is not None:
        try:
            _SERVICE.stop()
        except Exception:
            pass
    _SERVICE = SaveOptionsTemplateService(context)
    return _SERVICE.start()


def stop():
    global _SERVICE
    service = _SERVICE
    _SERVICE = None
    if service is not None:
        service.stop()


def status():
    if _SERVICE is None:
        return {"running": False}
    return _SERVICE.status()
