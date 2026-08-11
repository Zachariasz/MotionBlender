"""Shared cursor and viewport overlay presentation."""

from __future__ import absolute_import

import os


AXIS_COLORS = {
    "x": (235, 55, 55, 230),
    "y": (50, 220, 90, 230),
    "z": (75, 135, 255, 230),
}

CURSOR_STYLE_BY_OPERATION = {
    "move": "move",
    "rotate": "rotate",
    "scale": "scale",
}
SCALE_CURSOR_ROTATION_OFFSET = 90.0
SCALE_CURSOR_SIZE_DIVISOR = 1.5
ROTATE_CURSOR_SIZE_DIVISOR = 1.5
ROTATE_TRACKBALL_RELATIVE_SCALE = 0.725


def _qt_modules():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets


def _enum(container, nested_name, name):
    nested = getattr(container, nested_name, container)
    return getattr(nested, name)


def load_move_cursor():
    QtCore, QtGui, _QtWidgets = _qt_modules()
    scripts_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    icon_path = os.path.join(
        scripts_root,
        "custom",
        "icons",
        "4arrow.png",
    )
    if os.path.isfile(icon_path):
        pixmap = QtGui.QPixmap(icon_path)
        if not pixmap.isNull():
            target_width = max(1, int(round(pixmap.width() * 0.5)))
            target_height = max(1, int(round(pixmap.height() * 0.5)))
            transform = _enum(QtCore.Qt, "TransformationMode", "SmoothTransformation")
            pixmap = pixmap.scaled(
                target_width,
                target_height,
                _enum(QtCore.Qt, "AspectRatioMode", "KeepAspectRatio"),
                transform,
            )
            return QtGui.QCursor(
                pixmap,
                pixmap.width() // 2,
                pixmap.height() // 2,
            )
    return QtGui.QCursor(_enum(QtCore.Qt, "CursorShape", "SizeAllCursor"))


def load_blank_cursor():
    QtCore, QtGui, _QtWidgets = _qt_modules()
    return QtGui.QCursor(_enum(QtCore.Qt, "CursorShape", "BlankCursor"))


def _load_icon_pixmap(filename):
    _QtCore, QtGui, _QtWidgets = _qt_modules()
    scripts_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    icon_path = os.path.join(
        scripts_root,
        "custom",
        "icons",
        filename,
    )
    if not os.path.isfile(icon_path):
        return None
    pixmap = QtGui.QPixmap(icon_path)
    return None if pixmap.isNull() else pixmap


def load_scale_cursor_pixmap():
    return _load_icon_pixmap("2arrow.png")


def scale_cursor_draw_geometry(pixmap, radial_angle):
    source_width = float(pixmap.width())
    source_height = float(pixmap.height())
    return (
        float(radial_angle) + SCALE_CURSOR_ROTATION_OFFSET,
        source_width / SCALE_CURSOR_SIZE_DIVISOR,
        source_height / SCALE_CURSOR_SIZE_DIVISOR,
        source_width,
        source_height,
    )


def load_rotate_cursor_pixmaps():
    return {
        "orbit": _load_icon_pixmap("2arrow.png"),
        "trackball": _load_icon_pixmap("4arrow_colored.png"),
    }


def rotate_cursor_draw_angle(radial_angle, variant="orbit"):
    if str(variant or "orbit").lower() != "orbit":
        return 0.0
    # The orbit strategy already publishes the angle required by the vertical
    # two-arrow asset in MotionBuilder overlay coordinates. QPainter applies
    # that screen-space rotation directly; negating it here mirrors the
    # tangent and makes the cursor orbit in the opposite direction.
    return float(radial_angle)


def rotate_cursor_draw_geometry(pixmap, radial_angle, variant="orbit"):
    variant = str(variant or "orbit").lower()
    relative_scale = (
        ROTATE_TRACKBALL_RELATIVE_SCALE
        if variant == "trackball"
        else 1.0
    )
    scale = relative_scale / ROTATE_CURSOR_SIZE_DIVISOR
    return (
        rotate_cursor_draw_angle(radial_angle, variant),
        float(pixmap.width()) * scale,
        float(pixmap.height()) * scale,
        float(pixmap.width()),
        float(pixmap.height()),
    )


class InteractionOverlay(object):
    def __init__(self):
        QtCore, QtGui, QtWidgets = _qt_modules()
        self.QtCore = QtCore
        self.QtGui = QtGui
        self.QtWidgets = QtWidgets
        # This transient window owns active transform presentation and must
        # remain above MotionBuilder's native viewport until the interaction
        # commits or cancels.
        flags = (
            _enum(QtCore.Qt, "WindowType", "Tool")
            | _enum(QtCore.Qt, "WindowType", "FramelessWindowHint")
            | _enum(QtCore.Qt, "WindowType", "WindowStaysOnTopHint")
        )
        try:
            flags |= _enum(
                QtCore.Qt,
                "WindowType",
                "WindowDoesNotAcceptFocus",
            )
        except AttributeError:
            pass
        try:
            flags |= _enum(
                QtCore.Qt,
                "WindowType",
                "WindowTransparentForInput",
            )
        except AttributeError:
            pass

        outer = self

        class OverlayWidget(QtWidgets.QWidget):
            def paintEvent(self, event):
                outer._paint(self)

        self.widget = OverlayWidget()
        self.widget.setWindowFlags(flags)
        self.widget.setAttribute(
            _enum(QtCore.Qt, "WidgetAttribute", "WA_TranslucentBackground"),
            True,
        )
        self.widget.setAttribute(
            _enum(
                QtCore.Qt,
                "WidgetAttribute",
                "WA_TransparentForMouseEvents",
            ),
            True,
        )
        try:
            self.widget.setAttribute(
                _enum(
                    QtCore.Qt,
                    "WidgetAttribute",
                    "WA_ShowWithoutActivating",
                ),
                True,
            )
        except AttributeError:
            pass
        try:
            self.widget.setFocusPolicy(
                _enum(QtCore.Qt, "FocusPolicy", "NoFocus")
            )
        except AttributeError:
            pass
        self.status = {}
        self.cursor_style = None
        self.scale_cursor_pixmap = load_scale_cursor_pixmap()
        self.rotate_cursor_pixmaps = load_rotate_cursor_pixmaps()

    def set_cursor_style(self, style):
        value = str(style or "").strip().lower()
        self.cursor_style = value if value else None
        self.widget.update()

    def clear_status(self):
        self.status = {}
        try:
            visible = bool(self.widget.isVisible())
        except Exception:
            visible = False
        if visible:
            # Erase the translucent widget's backing store before it is hidden.
            # A queued update is too late: Qt can reuse the previous frame when
            # the next transform shows this shared widget.
            self.widget.repaint()
        else:
            self.widget.update()

    def set_rect(self, rect):
        self.widget.setGeometry(*[int(value) for value in rect])

    def show(self):
        self.widget.show()

    def repaint(self):
        self.widget.repaint()

    def hide(self):
        if self.status:
            self.clear_status()
        try:
            if self.QtWidgets.QWidget.mouseGrabber() is self.widget:
                self.widget.releaseMouse()
        except Exception:
            pass
        try:
            if self.QtWidgets.QWidget.keyboardGrabber() is self.widget:
                self.widget.releaseKeyboard()
        except Exception:
            pass
        try:
            self.widget.clearFocus()
        except Exception:
            pass
        self.widget.hide()

    def deleteLater(self):
        self.widget.deleteLater()

    def update(self, status):
        self.status = dict(status or {})
        self.widget.update()

    def _paint(self, widget):
        painter = self.QtGui.QPainter(widget)
        try:
            composition = getattr(
                self.QtGui.QPainter,
                "CompositionMode",
                self.QtGui.QPainter,
            )
            painter.setCompositionMode(
                getattr(composition, "CompositionMode_Source")
            )
            painter.fillRect(
                widget.rect(),
                self.QtGui.QColor(0, 0, 0, 0),
            )
            painter.setCompositionMode(
                getattr(composition, "CompositionMode_SourceOver")
            )
        except Exception:
            pass
        painter.setRenderHint(
            self.QtGui.QPainter.RenderHint.Antialiasing
            if hasattr(self.QtGui.QPainter, "RenderHint")
            else self.QtGui.QPainter.Antialiasing,
            True,
        )

        radial_line = self.status.get("radial_line")
        if radial_line:
            radial_pen = self.QtGui.QPen(
                self.QtGui.QColor(255, 255, 255, 230),
                2.0,
            )
            radial_pen.setStyle(
                _enum(self.QtCore.Qt, "PenStyle", "DashLine")
            )
            painter.setPen(radial_pen)
            painter.drawLine(
                self.QtCore.QPointF(*radial_line[0]),
                self.QtCore.QPointF(*radial_line[1]),
            )

        axis = str(self.status.get("axis") or "").lower()
        line = self.status.get("axis_line")
        if axis in AXIS_COLORS and line:
            color = self.QtGui.QColor(*AXIS_COLORS[axis])
            painter.setPen(self.QtGui.QPen(color, 2.0))
            painter.drawLine(
                self.QtCore.QPointF(*line[0]),
                self.QtCore.QPointF(*line[1]),
            )

        cursor_point = self.status.get("cursor_point")
        if (
            self.cursor_style == "scale"
            and cursor_point
            and self.scale_cursor_pixmap is not None
        ):
            pixmap = self.scale_cursor_pixmap
            (
                angle,
                target_width,
                target_height,
                source_width,
                source_height,
            ) = scale_cursor_draw_geometry(
                pixmap,
                self.status.get("cursor_angle") or 0.0,
            )
            painter.save()
            painter.translate(self.QtCore.QPointF(*cursor_point))
            painter.rotate(angle)
            painter.drawPixmap(
                self.QtCore.QRectF(
                    -target_width * 0.5,
                    -target_height * 0.5,
                    target_width,
                    target_height,
                ),
                pixmap,
                self.QtCore.QRectF(
                    0.0,
                    0.0,
                    source_width,
                    source_height,
                ),
            )
            painter.restore()

        rotate_cursor = str(
            self.status.get("cursor_variant") or "orbit"
        ).lower()
        rotate_pixmap = self.rotate_cursor_pixmaps.get(rotate_cursor)
        if (
            self.cursor_style == "rotate"
            and cursor_point
            and rotate_pixmap is not None
        ):
            (
                angle,
                target_width,
                target_height,
                source_width,
                source_height,
            ) = rotate_cursor_draw_geometry(
                rotate_pixmap,
                self.status.get("cursor_angle") or 0.0,
                rotate_cursor,
            )
            painter.save()
            painter.translate(self.QtCore.QPointF(*cursor_point))
            painter.rotate(angle)
            painter.drawPixmap(
                self.QtCore.QRectF(
                    -target_width * 0.5,
                    -target_height * 0.5,
                    target_width,
                    target_height,
                ),
                rotate_pixmap,
                self.QtCore.QRectF(
                    0.0,
                    0.0,
                    source_width,
                    source_height,
                ),
            )
            painter.restore()

        text = str(self.status.get("text") or "")
        if text:
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            metrics = self.QtGui.QFontMetrics(font)
            width = metrics.horizontalAdvance(text) + 20
            height = metrics.height() + 10
            x = max(8, int((widget.width() - width) * 0.5))
            y = max(8, widget.height() - height - 18)
            background = self.QtGui.QColor(25, 25, 25, 215)
            painter.setPen(self.QtGui.QPen(self.QtGui.QColor(85, 85, 85, 230)))
            painter.setBrush(background)
            painter.drawRect(x, y, width, height)
            painter.setPen(self.QtGui.QColor(235, 235, 235))
            painter.drawText(
                self.QtCore.QRect(x + 10, y + 5, width - 20, height - 10),
                _enum(
                    self.QtCore.Qt,
                    "AlignmentFlag",
                    "AlignCenter",
                ),
                text,
            )
        painter.end()


class SessionPresentation(object):
    def __init__(self, context, owner, rect):
        self.context = context
        self.owner = owner
        self.rect = rect
        self.surface = dict(
            getattr(owner, "invocation", {}) or {}
        ).get("surface")
        self.overlay = None
        self.cursor_claimed = False
        self.overlay_visible = False
        operation = str(
            dict(getattr(owner, "invocation", {}) or {}).get(
                "operation"
            )
            or ""
        ).lower()
        self.cursor_style = CURSOR_STYLE_BY_OPERATION.get(operation)

    def start(self):
        self.overlay = self.context.overlays.claim(self.owner, self.rect)
        try:
            claimed = self.context.overlays.claim_cursor(
                self.owner,
                self.surface,
                self.cursor_style,
            )
        except TypeError:
            claimed = self.context.overlays.claim_cursor(
                self.owner,
                self.surface,
            )
        self.cursor_claimed = bool(claimed)

    def update(self, status):
        if self.cursor_claimed:
            self.context.overlays.ensure_cursor(
                self.owner,
                self.surface,
            )
        self.overlay.update(status)
        if not self.overlay_visible:
            # Install the new owner's complete first frame before mapping the
            # shared overlay, then paint it synchronously.  This prevents Qt
            # from presenting the previous tool's backing-store image.
            self.overlay.show()
            repaint = getattr(self.overlay, "repaint", None)
            if callable(repaint):
                repaint()
            self.overlay_visible = True

    def close(self):
        # Hide and clear the shared overlay before cursor restoration flushes
        # Qt events.  Otherwise the previous scale radial line can repaint for
        # one frame while the next transform takes ownership.
        self.context.overlays.release(self.owner)
        self.overlay = None
        self.overlay_visible = False
        if self.cursor_claimed:
            self.context.overlays.release_cursor(self.owner)
            self.cursor_claimed = False
