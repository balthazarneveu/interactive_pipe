"""Zoomable image viewer widget for the Qt GUI backend.

`ImageView` is a QLabel (so text outputs keep working through setText) that
paints image outputs itself: scaled to fit the widget by default, with wheel
zoom around the cursor, left-drag pan, double-click reset and a "1:1" mode.
All the views of a window share one `ViewSync` so zoom/pan stay identical
across cells (comparing a before/after pair stays aligned).

The view keeps the full-resolution QPixmap plus the original (float) numpy
array, so hovering reports the true pixel value, not the 8-bit display one.

Zoom/pan state is resolution independent: the zoom is a multiplier on top of
either the per-view fit scale ("fit" family) or an absolute 1 screen pixel per
image pixel ("1:1" family), and the view center is stored in normalized image
coordinates (0..1). Cells showing images of different sizes therefore stay
consistently framed.
"""

import math
from typing import Any, Callable, List, Optional, Tuple

import numpy as np

from interactive_pipe.graphical.qt_backend import PYQTVERSION, QLabel, QPixmap, QSize, Qt

# Painting / geometry classes not re-exported by qt_backend: import them from
# the very binding qt_backend picked (never mix two Qt bindings).
_BINDING = QLabel.__module__.split(".")[0]
if _BINDING == "PyQt5":
    from PyQt5.QtCore import QPointF, QRectF  # type: ignore[no-redef]
    from PyQt5.QtGui import QPainter  # type: ignore[no-redef]
    from PyQt5.QtWidgets import QSizePolicy  # type: ignore[no-redef]
elif _BINDING == "PySide6":
    from PySide6.QtCore import QPointF, QRectF  # type: ignore[no-redef]
    from PySide6.QtGui import QPainter  # type: ignore[no-redef]
    from PySide6.QtWidgets import QSizePolicy  # type: ignore[no-redef]
else:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QSizePolicy

__all__ = ["ImageView", "ViewSync", "VIEW_MODES", "pixel_value"]

VIEW_MODES = ("fit", "1:1")
ZOOM_STEP = 1.25
MIN_ZOOM = 1.0 / 64.0
MAX_ZOOM = 256.0
# Bound on the preferred (initial) size of an image cell; the cell can still
# be enlarged by the user and shrunk down to minimumSizeHint.
MAX_HINT = QSize(800, 600)

HoverCallback = Callable[[int, int, Any], None]


def pixel_value(array: Optional[np.ndarray], x: int, y: int) -> Any:
    """Value of `array` at column x / row y: float for grayscale, a tuple of
    floats per channel otherwise, None outside the image or without array."""
    if array is None or array.ndim < 2:
        return None
    h, w = array.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    value = array[y, x]
    if np.ndim(value) == 0:
        return value.item() if hasattr(value, "item") else value
    return tuple(v.item() if hasattr(v, "item") else v for v in np.ravel(value))


class ViewSync:
    """Zoom/pan state shared by all the ImageViews of a window.

    absolute: False -> zoom multiplies each view's fit scale; True -> zoom is
    screen pixels per image pixel. center: normalized image coordinates of the
    point displayed at the middle of each view.
    """

    def __init__(self) -> None:
        self.views: List["ImageView"] = []
        self.absolute = False
        self.zoom = 1.0
        self.center: Tuple[float, float] = (0.5, 0.5)

    @property
    def mode(self) -> str:
        """ "fit" / "1:1" when untouched, "custom" once zoomed or panned."""
        if self.zoom == 1.0 and self.center == (0.5, 0.5):
            return "1:1" if self.absolute else "fit"
        return "custom"

    def register(self, view: "ImageView") -> None:
        if view not in self.views:
            self.views.append(view)

    def unregister(self, view: "ImageView") -> None:
        if view in self.views:
            self.views.remove(view)

    def set_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            raise ValueError(f"view mode must be one of {VIEW_MODES}, got {mode!r}")
        self.absolute = mode == "1:1"
        self.zoom = 1.0
        self.center = (0.5, 0.5)
        self.changed()

    def reset(self) -> None:
        self.set_mode("fit")

    def set_state(self, zoom: float, center: Tuple[float, float]) -> None:
        self.zoom = float(min(max(zoom, MIN_ZOOM), MAX_ZOOM))
        self.center = (float(center[0]), float(center[1]))
        self.changed()

    def changed(self) -> None:
        for view in self.views:
            view.update()


class ImageView(QLabel):  # type: ignore[reportGeneralTypeIssues]
    """QLabel that displays images fitted/zoomed/panned, text as usual."""

    def __init__(self, parent=None, sync: Optional[ViewSync] = None) -> None:
        super().__init__(parent)
        self.sync = sync if sync is not None else ViewSync()
        self.sync.register(self)
        self._pixmap: Optional[QPixmap] = None
        self.array: Optional[np.ndarray] = None
        self.hover_callback: Optional[HoverCallback] = None
        self._drag_origin = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # --- content -----------------------------------------------------------
    def set_image(self, pixmap: QPixmap, array: Optional[np.ndarray] = None) -> None:
        """Show `pixmap` (full resolution); `array` is the value source for hovering."""
        if self._pixmap is None:
            super().clear()  # drop a previous text
        self._pixmap = pixmap
        self.array = array
        self.updateGeometry()
        self.update()

    def setPixmap(self, pixmap: QPixmap) -> None:  # noqa: N802 - Qt API
        self.set_image(pixmap)

    def pixmap(self):  # type: ignore[override]
        """Full-resolution pixmap of an image cell (QLabel's otherwise)."""
        if self._pixmap is not None:
            return self._pixmap
        return super().pixmap()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        if self._pixmap is not None:
            self._pixmap = None
            self.array = None
            self.updateGeometry()
        super().setText(text)

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    # --- geometry ----------------------------------------------------------
    def image_size(self) -> Tuple[int, int]:
        if not self.has_image():
            return (0, 0)
        return (self._pixmap.width(), self._pixmap.height())  # type: ignore[union-attr]

    def fit_scale(self) -> float:
        w, h = self.image_size()
        if w == 0 or h == 0:
            return 1.0
        return max(min(self.width() / w, self.height() / h), 1e-6)

    def scale(self) -> float:
        """Screen pixels per image pixel currently used to paint."""
        base = 1.0 if self.sync.absolute else self.fit_scale()
        return base * self.sync.zoom

    def image_rect(self) -> Tuple[float, float, float, float]:
        """(x, y, width, height) of the painted image in widget coordinates."""
        w, h = self.image_size()
        s = self.scale()
        cu, cv = self.sync.center
        return (self.width() / 2.0 - cu * w * s, self.height() / 2.0 - cv * h * s, w * s, h * s)

    def map_to_image(self, px: float, py: float) -> Tuple[float, float]:
        """Widget coordinates -> (continuous) image pixel coordinates."""
        x0, y0, _, _ = self.image_rect()
        s = self.scale()
        return ((px - x0) / s, (py - y0) / s)

    def pixel_at(self, px: float, py: float) -> Tuple[int, int, Any]:
        """(x, y, value) of the image pixel under widget point (px, py)."""
        fx, fy = self.map_to_image(px, py)
        x, y = int(math.floor(fx)), int(math.floor(fy))
        source = self.array
        if source is None or source.shape[:2] != (self.image_size()[1], self.image_size()[0]):
            source = None
        value = pixel_value(source, x, y)
        if value is None and source is None and self.has_image():
            w, h = self.image_size()
            if 0 <= x < w and 0 <= y < h:
                color = self._pixmap.toImage().pixelColor(x, y)  # type: ignore[union-attr]
                value = (color.red(), color.green(), color.blue())
        return x, y, value

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        if not self.has_image():
            return super().sizeHint()
        w, h = self.image_size()
        ratio = min(1.0, MAX_HINT.width() / w, MAX_HINT.height() / h)
        return QSize(max(1, int(w * ratio)), max(1, int(h * ratio)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        if not self.has_image():
            return super().minimumSizeHint()
        return QSize(32, 32)

    # --- view control (synced) ---------------------------------------------
    def set_mode(self, mode: str) -> None:
        self.sync.set_mode(mode)

    def reset_view(self) -> None:
        self.sync.reset()

    def zoom_in(self) -> None:
        self.zoom_by(ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom_by(1.0 / ZOOM_STEP)

    def zoom_by(self, factor: float, anchor: Optional[Tuple[float, float]] = None) -> None:
        """Zoom by `factor` keeping the image point under `anchor` (widget
        coordinates, default: widget center) in place."""
        w, h = self.image_size()
        if w == 0 or h == 0:
            self.sync.set_state(self.sync.zoom * factor, self.sync.center)
            return
        if anchor is None:
            anchor = (self.width() / 2.0, self.height() / 2.0)
        fx, fy = self.map_to_image(*anchor)
        new_zoom = min(max(self.sync.zoom * factor, MIN_ZOOM), MAX_ZOOM)
        base = 1.0 if self.sync.absolute else self.fit_scale()
        new_scale = base * new_zoom
        cu = (fx - (anchor[0] - self.width() / 2.0) / new_scale) / w
        cv = (fy - (anchor[1] - self.height() / 2.0) / new_scale) / h
        self.sync.set_state(new_zoom, (cu, cv))

    def pan_by(self, dx: float, dy: float) -> None:
        """Move the image by (dx, dy) widget pixels."""
        w, h = self.image_size()
        if w == 0 or h == 0:
            return
        s = self.scale()
        cu, cv = self.sync.center
        self.sync.set_state(self.sync.zoom, (cu - dx / (s * w), cv - dy / (s * h)))

    # --- Qt events -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self.has_image():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        if self.scale() < 1.0:
            # downscaling: smooth; upscaling keeps crisp pixels for inspection
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        x, y, w, h = self.image_rect()
        painter.drawPixmap(QRectF(x, y, w, h), self._pixmap, QRectF(self._pixmap.rect()))  # type: ignore[arg-type]
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.update()  # the fit scale depends on the widget size

    @staticmethod
    def _event_pos(event) -> Tuple[float, float]:
        if PYQTVERSION == 6 and hasattr(event, "position"):
            pos = event.position()
        else:
            pos = QPointF(event.pos())
        return (pos.x(), pos.y())

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self.has_image():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self.zoom_by(ZOOM_STEP ** (delta / 120.0), self._event_pos(event))
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.has_image() and event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = self._event_pos(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self.has_image():
            super().mouseMoveEvent(event)
            return
        pos = self._event_pos(event)
        if self._drag_origin is not None:
            self.pan_by(pos[0] - self._drag_origin[0], pos[1] - self._drag_origin[1])
            self._drag_origin = pos
        if self.hover_callback is not None:
            self.hover_callback(*self.pixel_at(*pos))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.has_image():
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def detach(self) -> None:
        """Leave the shared sync (call when the view is removed from the grid)."""
        self.sync.unregister(self)
