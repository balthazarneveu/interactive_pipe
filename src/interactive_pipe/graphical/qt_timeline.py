"""Qt timeline of a ``Video`` input: a dark editor-like panel at the bottom of the window.

Top row: transport (first frame, previous frame, play / pause, next frame,
last frame), the timecode, the frame number, and on the right the zoom level
and the loop toggle. Below, over the whole width, the film strip: thumbnails,
a time ruler, the playhead; click / drag seeks, scroll zooms around the
cursor, shift + scroll (or a horizontal scroll) pans, double-click shows the
whole video again. While zoomed the view follows the playhead.

Shown by ``InteractivePipeQT.add_controls`` when the pipeline gets a
``TimelineControl`` (``headless/timeline.py``). Playback ticks at the video
frame rate and moves the control through ``MainWindow.update_parameter``;
refreshes are coalesced, so a pipeline slower than the video drops frames like
a player instead of lagging.
"""

import math
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

import numpy as np

from interactive_pipe.graphical.qt_backend import (
    QColor,
    QFont,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QtWidgetBase,
    QVBoxLayout,
)
from interactive_pipe.graphical.qt_image import numpy_to_pixmap
from interactive_pipe.headless.timeline import TimelineControl, timecode

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow

# ---------------------------------------------------------------- look
PANEL = QColor(28, 29, 32)
TRACK_BACKGROUND = QColor(16, 17, 19)
RULER_BAND = QColor(38, 40, 44)
TEXT = QColor(232, 234, 237)
MUTED = QColor(138, 143, 152)
ACCENT = QColor(255, 176, 32)  # playhead, play button, loop on
ACCENT_HOVER = QColor(255, 196, 84)
ACCENT_PRESSED = QColor(224, 150, 16)
HOVER_FILL = QColor(255, 255, 255, 26)
PRESSED_FILL = QColor(255, 255, 255, 46)
HOVER_LINE = QColor(255, 255, 255, 220)
SHADOW = QColor(0, 0, 0, 140)
OVERVIEW_BACKING = QColor(16, 17, 19, 215)
OVERVIEW_TRACK = QColor(255, 255, 255, 45)
OVERVIEW_VIEW = QColor(255, 255, 255, 190)
PANEL_RADIUS = 8
STRIP_RADIUS = 5

RULER_HEIGHT = 18
THUMB_HEIGHT = 46
STRIP_HEIGHT = RULER_HEIGHT + THUMB_HEIGHT
OVERVIEW_HEIGHT = 4
BUTTON_SIZE = 28
PLAY_SIZE = 34
#: tick spacing candidates in seconds (the first giving >= MIN_TICK_PIXELS between ticks wins)
TICK_STEPS = (1 / 25, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600)
MIN_TICK_PIXELS = 70
#: the most zoomed-in view shows this many frames
MIN_VISIBLE_FRAMES = 8
#: zoom factor per wheel notch (120 units of angleDelta)
ZOOM_PER_NOTCH = 1.25
STRIP_HINT = "click / drag: seek · scroll: zoom · shift + scroll: pan · double-click: whole video"


def ruler_label(seconds: float, step: float) -> str:
    """``"0:05"`` for whole-second ticks, ``"1.5s"`` / ``"0.04s"`` below."""
    if step >= 1:
        minutes, secs = divmod(int(round(seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
    decimals = 1 if step >= 0.1 else 2
    return f"{seconds:.{decimals}f}s"


def _event_x(event: Any) -> float:
    position = event.position() if hasattr(event, "position") else event.pos()
    return float(position.x())


def _monospace(size: float) -> Any:
    font = QFont("monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(size)
    return font


def _hex(color: Any) -> str:
    return color.name()


# ---------------------------------------------------------------- icons
def _polygon(points: List[Tuple[float, float]]) -> Any:
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    path.closeSubpath()
    return path


def _polyline(points: List[Tuple[float, float]]) -> Any:
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    return path


def paint_icon(painter: Any, kind: str, center: Tuple[float, float], size: float, color: Any) -> None:
    """Draw transport icon ``kind`` (play, pause, first, previous, next, last, loop, fit) of ``size`` px."""
    cx, cy = center
    s = size / 2

    def at(x: float, y: float) -> Tuple[float, float]:  # unit coordinates in [-1, 1]
        return cx + x * s, cy + y * s

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    if kind == "play":
        painter.drawPath(_polygon([at(-0.55, -0.8), at(0.85, 0.0), at(-0.55, 0.8)]))
        return
    if kind == "pause":
        for left in (-0.62, 0.18):
            painter.drawRoundedRect(QRectF(*at(left, -0.75), 0.44 * s, 1.5 * s), 0.12 * s, 0.12 * s)
        return
    if kind in ("first", "last"):
        sign = -1 if kind == "first" else 1
        painter.drawPath(_polygon([at(-0.6 * sign, -0.7), at(0.45 * sign, 0.0), at(-0.6 * sign, 0.7)]))
        bar_left = 0.5 if sign > 0 else -0.72
        painter.drawRoundedRect(QRectF(*at(bar_left, -0.7), 0.22 * s, 1.4 * s), 0.08 * s, 0.08 * s)
        return
    pen = QPen(color, max(size / 9, 1.6))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind in ("previous", "next"):
        sign = -1 if kind == "previous" else 1
        painter.drawPath(_polyline([at(-0.25 * sign, -0.6), at(0.3 * sign, 0.0), at(-0.25 * sign, 0.6)]))
    elif kind == "loop":
        radius = 0.68 * s
        box = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        path = QPainterPath()
        path.arcMoveTo(box, 70)
        path.arcTo(box, 70, 290)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        tip_x = cx + radius * math.cos(math.radians(70))
        tip_y = cy - radius * math.sin(math.radians(70))
        head = 0.42 * s
        painter.drawPath(
            _polygon(
                [
                    (tip_x + head, tip_y),
                    (tip_x - 0.2 * head, tip_y - 0.75 * head),
                    (tip_x - 0.2 * head, tip_y + 0.75 * head),
                ]
            )
        )
    elif kind == "fit":
        for sign in (-1, 1):
            painter.drawPath(_polyline([at(0.85 * sign, -0.6), at(0.85 * sign, 0.6)]))
            painter.drawPath(_polyline([at(0.1 * sign, 0.0), at(0.6 * sign, 0.0)]))
            painter.drawPath(_polyline([at(0.35 * sign, -0.3), at(0.6 * sign, 0.0), at(0.35 * sign, 0.3)]))


class IconButton(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Flat round button with a painted icon; ``primary``: the filled accent play / pause button."""

    def __init__(
        self,
        kind: str,
        tooltip: str,
        on_click: Callable[[], None],
        parent=None,
        primary: bool = False,
        checkable: bool = False,
        checked: bool = False,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.on_click = on_click
        self.primary = primary
        self.checkable = checkable
        self.checked = checked
        self.hovered = False
        self.pressed = False
        side = PLAY_SIZE if primary else BUTTON_SIZE
        self.setFixedSize(side, side)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the window (space, arrows)

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def click(self) -> None:
        if self.checkable:
            self.checked = not self.checked
        self.on_click()
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            box = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
            painter.setPen(Qt.PenStyle.NoPen)
            if self.primary:
                painter.setBrush(ACCENT_PRESSED if self.pressed else ACCENT_HOVER if self.hovered else ACCENT)
                painter.drawEllipse(box)
                icon_color = PANEL
            else:
                if self.checked:
                    painter.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 52))
                    painter.drawEllipse(box)
                if self.pressed or self.hovered:
                    painter.setBrush(PRESSED_FILL if self.pressed else HOVER_FILL)
                    painter.drawEllipse(box)
                icon_color = ACCENT if self.checked else TEXT if self.hovered else MUTED
            icon = self.width() * (0.4 if self.primary else 0.46)
            offset = icon * 0.08 if self.kind == "play" else 0.0  # optical centre of the triangle
            paint_icon(painter, self.kind, (self.width() / 2 + offset, self.height() / 2), icon, icon_color)
        finally:
            painter.end()

    def enterEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.hovered = True
        self.update()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.hovered = self.pressed = False
        self.update()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed = True
            self.update()

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        was_pressed, self.pressed = self.pressed, False
        position = event.position() if hasattr(event, "position") else event.pos()
        if was_pressed and 0 <= position.x() <= self.width() and 0 <= position.y() <= self.height():
            self.click()
        self.update()


# ---------------------------------------------------------------- film strip
class FilmStrip(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Thumbnails of the video along the time axis, a time ruler and the playhead; click / drag seeks."""

    def __init__(
        self,
        timeline: TimelineControl,
        on_seek: Callable[[int], None],
        parent=None,
        on_view_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.timeline = timeline
        self.on_seek = on_seek
        self.on_view_change = on_view_change
        self.hover_frame: Optional[int] = None
        self._view: Optional[Tuple[float, float]] = None  # (first, last) visible frame; None: the whole video
        self._strip_cache: Optional[tuple] = None  # (width, view, n_frames, ids of videos) -> pixmap
        self.setMinimumHeight(STRIP_HEIGHT)
        self.setMaximumHeight(STRIP_HEIGHT)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(STRIP_HINT)

    def sizeHint(self) -> QSize:
        return QSize(600, STRIP_HEIGHT)

    # ---------------------------------------------------------------- view (zoom / pan)
    def _full(self) -> Tuple[float, float]:
        return 0.0, float(max(self.timeline.n_frames - 1, 1))

    @property
    def view(self) -> Tuple[float, float]:
        """``(first, last)`` frame shown at the left and right edges (fractional when zoomed)."""
        if self._view is None:
            return self._full()
        return self._view

    @property
    def zoomed(self) -> bool:
        return self._view is not None

    @property
    def zoom_factor(self) -> float:
        first, last = self.view
        low, high = self._full()
        return (high - low) / max(last - first, 1e-9)

    def set_view(self, first: float, last: float) -> None:
        """Show frames ``first`` to ``last``: clamped to the video, at least ``MIN_VISIBLE_FRAMES`` wide."""
        low, high = self._full()
        span = min(max(last - first, min(MIN_VISIBLE_FRAMES, high - low)), high - low)
        first = min(max(first, low), high - span)
        view = None if span >= high - low else (first, first + span)
        changed = view != self._view
        self._view = view
        self.update()
        if changed and self.on_view_change is not None:
            self.on_view_change()

    def reset_view(self) -> None:
        low, high = self._full()
        self.set_view(low, high)

    def zoom(self, factor: float, around: Optional[float] = None) -> None:
        """Zoom in (``factor`` > 1) or out keeping frame ``around`` (default: the centre) in place."""
        first, last = self.view
        if around is None:
            around = (first + last) / 2
        self.set_view(around - (around - first) / factor, around + (last - around) / factor)

    def pan(self, fraction: float) -> None:
        """Move the view by ``fraction`` of its width (positive: later in the video)."""
        first, last = self.view
        offset = fraction * (last - first)
        self.set_view(first + offset, last + offset)

    def follow(self, frame: int) -> None:
        """Page the zoomed view so that ``frame`` is visible (playback, keys, buttons)."""
        if self._view is None:
            return
        first, last = self._view
        if first <= frame <= last:
            return
        span = last - first
        start = frame - 0.1 * span if frame > last else frame - 0.9 * span
        self.set_view(start, start + span)

    # ---------------------------------------------------------------- geometry
    def _x_of(self, frame: float) -> float:
        first, last = self.view
        return 1.0 + (self.width() - 2.0) * (frame - first) / max(last - first, 1e-9)

    def _frame_of(self, x: float) -> float:
        first, last = self.view
        return first + (x - 1.0) / max(self.width() - 2.0, 1.0) * (last - first)

    def frame_at(self, x: float) -> int:
        frame = round(self._frame_of(x))
        return int(min(max(frame, 0), self.timeline.n_frames - 1))

    # ---------------------------------------------------------------- painting
    def _strip_pixmap(self) -> Any:
        """Film strip of the first video, cached per width and view.

        Thumbnails sit on a grid of frames (a power of two apart, chosen from
        the zoom), so panning and zooming reuse the ones already decoded.
        """
        width = max(self.width(), 1)
        videos = self.timeline.videos
        key = (width, self.view, self.timeline.n_frames, tuple(id(video) for video in videos))
        if self._strip_cache is not None and self._strip_cache[0] == key:
            return self._strip_cache[1]
        background = (TRACK_BACKGROUND.red(), TRACK_BACKGROUND.green(), TRACK_BACKGROUND.blue())
        strip = np.zeros((THUMB_HEIGHT, width, 3), dtype=np.uint8)
        strip[...] = background
        if videos:
            video = videos[0]
            try:
                tile = max(video.thumbnail(0, THUMB_HEIGHT).shape[1], 8)
                first, last = self.view
                pixels_per_frame = (width - 2.0) / max(last - first, 1e-9)
                step = 1
                while step * pixels_per_frame < 0.75 * tile:
                    step *= 2
                n_frames = self.timeline.n_frames
                half = 0.5 if step == 1 else 0.0  # one frame per tile: the tile is centred on its frame
                for anchor in range(int(first // step) * step, int(last) + 1, step):
                    if anchor >= n_frames:
                        break
                    left = int(round(self._x_of(anchor - half)))
                    right = min(int(round(self._x_of(anchor + step - half))), width)
                    thumb = video.thumbnail(video.index_at(anchor / self.timeline.fps), THUMB_HEIGHT)
                    crop = max(-left, 0)
                    left = max(left, 0)
                    shown = thumb[:, crop : crop + max(min(right - left, thumb.shape[1] - crop), 0)]
                    strip[:, left : left + shown.shape[1]] = shown
                    if 0 < left < width:
                        strip[:, left - 1 : left + 1] = background  # gap between the frames of the film
            except Exception:  # noqa: BLE001 - a frame that cannot be previewed leaves a plain track
                pass
        pixmap = numpy_to_pixmap(np.ascontiguousarray(strip))
        self._strip_cache = (key, pixmap)
        return pixmap

    def _pixels_per_second(self) -> float:
        first, last = self.view
        return (self.width() - 2.0) / max((last - first) / self.timeline.fps, 1e-9)

    def _tick_step(self) -> float:
        fps = self.timeline.fps
        pixels_per_second = self._pixels_per_second()
        frame_steps = tuple(k / fps for k in (1, 2, 5, 10))
        for step in sorted(set(frame_steps + tuple(t for t in TICK_STEPS if t > 1 / fps))):
            if step * pixels_per_second >= MIN_TICK_PIXELS:
                return step
        return TICK_STEPS[-1]

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _ticks(self, step: float) -> List[float]:
        """Times (s) of the multiples of ``step`` inside the view."""
        fps = self.timeline.fps
        first, last = self.view
        start = int(math.ceil(first / fps / step - 1e-9))
        stop = int(math.floor(last / fps / step + 1e-9))
        return [k * step for k in range(start, stop + 1)]

    def _paint(self, painter: Any) -> None:
        width, height = self.width(), self.height()
        fps = self.timeline.fps
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, width, height), STRIP_RADIUS, STRIP_RADIUS)
        painter.setClipPath(clip)
        painter.fillRect(0, 0, width, height, TRACK_BACKGROUND)
        painter.fillRect(0, 0, width, RULER_HEIGHT, RULER_BAND)
        painter.drawPixmap(0, RULER_HEIGHT, self._strip_pixmap())

        # ruler: labelled ticks every "nice" number of seconds, minor ticks in between
        painter.setFont(_monospace(7.5))
        step = self._tick_step()
        minor = step / 5 if step * self._pixels_per_second() >= 60 else step / 2
        painter.setPen(QPen(QColor(MUTED.red(), MUTED.green(), MUTED.blue(), 110), 1))
        for seconds in self._ticks(minor):
            x = int(self._x_of(seconds * fps)) + 0.5
            painter.drawLine(QPointF(x, RULER_HEIGHT - 3), QPointF(x, RULER_HEIGHT))
        painter.setPen(QPen(MUTED, 1))
        for seconds in self._ticks(step):
            x = int(self._x_of(seconds * fps)) + 0.5
            painter.drawLine(QPointF(x, RULER_HEIGHT - 7), QPointF(x, RULER_HEIGHT))
            if x < width - 36:
                painter.drawText(QPointF(x + 4, RULER_HEIGHT - 6), ruler_label(seconds, step))

        x_head = self._x_of(int(self.timeline.value))
        # played part: a thin accent line along the top of the thumbnails
        played = min(max(x_head, 0.0), float(width))
        painter.fillRect(QRectF(0, RULER_HEIGHT, played, 2), ACCENT)

        # hover: a line and the time under the cursor, in a bubble on the ruler
        if self.hover_frame is not None:
            x_hover = int(self._x_of(self.hover_frame)) + 0.5
            painter.setPen(QPen(SHADOW, 3))
            painter.drawLine(QPointF(x_hover, RULER_HEIGHT), QPointF(x_hover, height))
            painter.setPen(QPen(HOVER_LINE, 1))
            painter.drawLine(QPointF(x_hover, RULER_HEIGHT), QPointF(x_hover, height))
            text = f"{timecode(self.hover_frame / fps)} · {self.hover_frame}"
            text_width = painter.fontMetrics().horizontalAdvance(text) + 12
            left = min(max(x_hover - text_width / 2, 1.0), width - text_width - 1.0)
            bubble = QRectF(left, 1, text_width, RULER_HEIGHT - 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(TEXT)
            painter.drawRoundedRect(bubble, 4, 4)
            painter.setPen(QPen(PANEL))
            painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)

        # overview when zoomed: the whole video, the visible part, the playhead
        if self.zoomed:
            first, last = self.view
            low, high = self._full()
            top = height - OVERVIEW_HEIGHT - 4
            inner = width - 16.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(OVERVIEW_BACKING)
            painter.drawRoundedRect(QRectF(5, top - 3, inner + 6, OVERVIEW_HEIGHT + 6), 5, 5)
            painter.setBrush(OVERVIEW_TRACK)
            painter.drawRoundedRect(QRectF(8, top, inner, OVERVIEW_HEIGHT), 2, 2)
            painter.setBrush(OVERVIEW_VIEW)
            left = 8 + inner * (first - low) / (high - low)
            span = max(inner * (last - first) / (high - low), 4.0)
            painter.drawRoundedRect(QRectF(left, top, span, OVERVIEW_HEIGHT), 2, 2)
            painter.setBrush(ACCENT)
            head = 8 + inner * int(self.timeline.value) / (high - low)
            painter.drawRect(QRectF(head - 1, top - 1, 2, OVERVIEW_HEIGHT + 2))

        # playhead: a handle on the ruler and a line over the thumbnails (shadowed for bright frames)
        if -6 <= x_head <= width + 6:
            painter.setPen(QPen(SHADOW, 4))
            painter.drawLine(QPointF(x_head, RULER_HEIGHT), QPointF(x_head, height))
            painter.setPen(QPen(ACCENT, 2))
            painter.drawLine(QPointF(x_head, RULER_HEIGHT - 2), QPointF(x_head, height))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ACCENT)
            half = 5.5
            handle = [
                (x_head - half, 1),
                (x_head + half, 1),
                (x_head + half, RULER_HEIGHT - 8),
                (x_head, RULER_HEIGHT - 2),
                (x_head - half, RULER_HEIGHT - 8),
            ]
            painter.drawPath(_polygon(handle))

    # ---------------------------------------------------------------- mouse
    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.on_seek(self.frame_at(_event_x(event)))

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        frame = self.frame_at(_event_x(event))
        self.hover_frame = frame
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.on_seek(frame)
        self.update()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.hover_frame = None
        self.update()

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.reset_view()

    def wheelEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        """Scroll: zoom around the cursor; shift + scroll or horizontal scroll: pan."""
        delta = event.angleDelta()
        horizontal = abs(delta.x()) > abs(delta.y())
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        notches = (delta.x() if horizontal else delta.y()) / 120.0
        if horizontal or shift:
            self.pan(-0.15 * notches)
        elif notches:
            self.zoom(ZOOM_PER_NOTCH**notches, around=self._frame_of(_event_x(event)))
        if self.hover_frame is not None:
            self.hover_frame = self.frame_at(_event_x(event))
        event.accept()  # the window behind does not scroll


# ---------------------------------------------------------------- panel
class TimelineWidget(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Timeline panel of a ``TimelineControl``: transport and timecode on top, the film strip below."""

    def __init__(self, window: "MainWindow", timeline: TimelineControl) -> None:
        super().__init__(window)
        self.main_window = window  # not `window`: QWidget.window() is a method
        self.timeline = timeline
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(2)
        self.buttons: List[IconButton] = []

        def button(kind: str, tooltip: str, slot: Callable[[], None], **options: Any) -> IconButton:
            widget = IconButton(kind, tooltip, slot, self, **options)
            top.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            self.buttons.append(widget)
            return widget

        def label(style: str) -> Any:
            widget = QLabel("", self)
            widget.setStyleSheet(f"QLabel {{ {style} }}")
            top.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            return widget

        button("first", "first frame", lambda: self.seek(0))
        button("previous", "previous frame [←]", lambda: self.step(-1))
        self.play_button = button("play", "play / pause [Space]", self.play_pause, primary=True)
        button("next", "next frame [→]", lambda: self.step(1))
        button("last", "last frame", lambda: self.seek(self.timeline.n_frames - 1))
        top.addSpacing(14)
        self.time_label = label("background: transparent;")
        self.time_label.setTextFormat(Qt.TextFormat.RichText)
        top.addSpacing(10)
        self.frame_label = label(
            f"background: {_hex(RULER_BAND)}; color: {_hex(TEXT)}; border-radius: 10px;"
            " padding: 0px 10px; font-family: monospace; font-size: 11px;"
        )
        self.frame_label.setFixedHeight(22)  # Qt drops a radius larger than half the height
        top.addSpacing(6)
        self.fps_label = label(f"color: {_hex(MUTED)}; font-size: 11px; background: transparent;")
        top.addStretch(1)
        self.zoom_label = label(
            f"color: {_hex(MUTED)}; font-family: monospace; font-size: 11px; background: transparent;"
        )
        self.zoom_label.setToolTip("scroll on the film strip to zoom, shift + scroll to pan")
        top.addSpacing(2)
        self.fit_button = button("fit", "show the whole video (double-click on the strip)", self.strip_fit)
        self.loop_button = button(
            "loop", "loop playback", self._loop_clicked, checkable=True, checked=bool(timeline.loop)
        )

        self.strip = FilmStrip(timeline, self.seek, self, on_view_change=self._view_changed)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addWidget(self.strip)
        self.setLayout(layout)
        # never squeezed by the images: the panel keeps its height
        self.setFixedHeight(6 + PLAY_SIZE + 6 + STRIP_HEIGHT + 10)
        self._view_changed()
        self.reset()
        if timeline.playing:
            self.play()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(PANEL)
            painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), PANEL_RADIUS, PANEL_RADIUS)
        finally:
            painter.end()

    # ---------------------------------------------------------------- state
    def reset(self) -> None:
        """Sync with the control value (reset, tuning import, session restore, key step)."""
        position = self.timeline.position
        self.time_label.setText(
            f"<span style='font-family: monospace; font-size: 15px; font-weight: 600; color: {_hex(TEXT)}'>"
            f"{timecode(position.time)}</span>"
            f"<span style='font-family: monospace; font-size: 12px; color: {_hex(MUTED)}'>"
            f"&nbsp;/&nbsp;{timecode(position.duration)}</span>"
        )
        self.frame_label.setText(f"frame {position.frame} / {position.n_frames - 1}")
        self.fps_label.setText(f"{self.timeline.fps:g} fps")
        self.strip.follow(position.frame)
        self.strip.update()

    def _view_changed(self) -> None:
        zoomed = self.strip.zoomed
        self.zoom_label.setText(f"zoom ×{self.strip.zoom_factor:.1f}" if zoomed else "")
        self.zoom_label.setVisible(zoomed)
        self.fit_button.setVisible(zoomed)

    def strip_fit(self) -> None:
        """Show the whole video on the film strip."""
        self.strip.reset_view()

    def seek(self, frame: int) -> None:
        frame = int(min(max(frame, 0), self.timeline.n_frames - 1))
        if frame != int(self.timeline.value):
            self.main_window.update_parameter(self.timeline.name, frame)
        self.reset()

    def step(self, offset: int) -> None:
        self.pause()
        target = self.timeline.next_frame(offset)
        if target is not None:
            self.seek(target)

    def _loop_clicked(self) -> None:
        self.timeline.loop = self.loop_button.checked

    # ---------------------------------------------------------------- playback
    def play(self) -> None:
        if self.timeline.next_frame() is None:
            self.seek(0)  # at the end without loop: start over
        self.timeline.playing = True
        self.timer.start(max(int(round(1000.0 / self.timeline.fps)), 1))
        self.play_button.set_kind("pause")

    def pause(self) -> None:
        self.timeline.playing = False
        self.timer.stop()
        self.play_button.set_kind("play")

    def play_pause(self) -> None:
        if self.timeline.playing:
            self.pause()
        else:
            self.play()

    def _tick(self) -> None:
        target = self.timeline.next_frame()
        if target is None:
            self.pause()
            return
        self.seek(target)
