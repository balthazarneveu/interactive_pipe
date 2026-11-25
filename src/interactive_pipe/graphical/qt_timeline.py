"""Qt timeline of a ``Video`` input: an editor-like panel at the bottom of the window.

Top row: transport (first frame, previous frame, play / pause, next frame,
last frame), the timecode, the frame number, and on the right the zoom level
and the loop toggle. Below, over the whole width, the film strip: thumbnails,
a time ruler, the playhead; click / drag seeks, scroll zooms around the
cursor, shift + scroll (or a horizontal scroll) pans, double-click shows the
whole video again. While zoomed the view follows the playhead.

The panel is dark on a dark window and light on a light one
(``timeline_view.theme_for`` of the window palette, checked again when the
palette changes).

Shown by ``InteractivePipeQT.add_controls`` when the pipeline gets a
``TimelineControl`` (``headless/timeline.py``). Playback ticks at the video
frame rate and moves the control through ``MainWindow.update_parameter``;
refreshes are coalesced, so a pipeline slower than the video drops frames like
a player instead of lagging.
"""

import functools
import math
import sys
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence, Tuple

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
from interactive_pipe.graphical.timeline_view import (
    BUFFERED_HEIGHT,
    BUTTON_SIZE,
    OVERVIEW_HEIGHT,
    PANEL_RADIUS,
    PLAY_SIZE,
    RULER_HEIGHT,
    STRIP_HINT,
    STRIP_RADIUS,
    THUMB_HEIGHT,
    StripView,
    Theme,
    ruler_label,
    theme_for,
)
from interactive_pipe.headless.timeline import TimelineControl, timecode

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow

# ---------------------------------------------------------------- look (themes: timeline_view.py)
HOVER_LINE = QColor(255, 255, 255, 220)  # over the thumbnails, whatever the theme
SHADOW = QColor(0, 0, 0, 140)
LABEL_BACKING = QColor(0, 0, 0, 150)  # input name of a lane, over its thumbnails
#: how often the panel checks for thumbnails / frames ready in the background
BACKGROUND_POLL_MS = 100


class QtColors:
    """The ``QColor`` s of a ``Theme``."""

    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        light = theme.overlay != (255, 255, 255)
        self.panel = QColor(*theme.panel)
        self.track_background = QColor(*theme.track_background)
        self.ruler_band = QColor(*theme.ruler_band)
        self.text = QColor(*theme.text)
        self.muted = QColor(*theme.muted)
        self.accent = QColor(*theme.accent)
        self.accent_hover = QColor(*theme.accent_hover)
        self.accent_pressed = QColor(*theme.accent_pressed)
        self.on_accent = QColor(*theme.on_accent)
        self.border = QColor(*theme.border) if theme.border is not None else None
        self.hover_fill = QColor(*theme.overlay, 16 if light else 26)
        self.pressed_fill = QColor(*theme.overlay, 30 if light else 46)
        self.checked_fill = QColor(*theme.accent, 40 if light else 52)
        self.minor_tick = QColor(*theme.muted, 110)
        self.overview_backing = QColor(*theme.track_background, 215)
        self.overview_track = QColor(*theme.overlay, 40 if light else 45)
        self.overview_view = QColor(*theme.overlay, 150 if light else 190)
        self.buffered = QColor(*theme.buffered)


def _window_theme(widget: Any) -> Theme:
    color = widget.palette().window().color()
    return theme_for((color.red(), color.green(), color.blue()))


def _event_x(event: Any) -> float:
    position = event.position() if hasattr(event, "position") else event.pos()
    return float(position.x())


@functools.lru_cache(maxsize=1)
def monospace_family() -> str:
    """The system fixed-width family (Menlo on macOS, DejaVu Sans Mono on most Linux).

    Asking for ``"monospace"`` by name makes Qt scan every font family alias on
    macOS, where no family has that name (a ``qt.qpa.fonts`` warning and ~50 ms).
    """
    database = sys.modules[QFont.__module__].QFontDatabase  # same binding as QFont
    fixed = getattr(getattr(database, "SystemFont", database), "FixedFont")
    return database.systemFont(fixed).family()


def monospace_css() -> str:
    """``font-family`` value for style sheets and rich text."""
    return f'"{monospace_family()}", monospace'


def _monospace(size: float) -> Any:
    font = QFont(monospace_family())
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(size)
    return font


def _hex(color: Any) -> str:
    return color.name()


# ---------------------------------------------------------------- icons
def _polygon(points: Sequence[Tuple[float, float]]) -> Any:
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    path.closeSubpath()
    return path


def _polyline(points: Sequence[Tuple[float, float]]) -> Any:
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    return path


def paint_icon(painter: Any, kind: str, center: Tuple[float, float], size: float, color: Any) -> None:
    """Draw icon ``kind`` (play, pause, first, previous, next, last, loop, fit, collapse, expand) of ``size`` px."""
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
    elif kind in ("collapse", "expand"):  # chevron down: fold the panel; up: unfold it
        sign = 1 if kind == "collapse" else -1
        painter.drawPath(_polyline([at(-0.55, -0.25 * sign), at(0.0, 0.3 * sign), at(0.55, -0.25 * sign)]))
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
        self.colors = QtColors(theme_for((0, 0, 0)))  # set by the panel
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
            colors = self.colors
            if self.primary:
                painter.setBrush(
                    colors.accent_pressed if self.pressed else colors.accent_hover if self.hovered else colors.accent
                )
                painter.drawEllipse(box)
                icon_color = colors.on_accent
            else:
                if self.checked:
                    painter.setBrush(colors.checked_fill)
                    painter.drawEllipse(box)
                if self.pressed or self.hovered:
                    painter.setBrush(colors.pressed_fill if self.pressed else colors.hover_fill)
                    painter.drawEllipse(box)
                icon_color = colors.accent if self.checked else colors.text if self.hovered else colors.muted
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
class FilmStrip(QtWidgetBase, StripView):  # type: ignore[reportGeneralTypeIssues]
    """Thumbnails of the video along the time axis, a time ruler and the playhead; click / drag seeks."""

    def __init__(
        self,
        timeline: TimelineControl,
        on_seek: Callable[[int], None],
        parent=None,
        on_view_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.init_strip_view(timeline)
        self.colors = QtColors(self.theme)
        self.on_seek = on_seek
        self._on_view_change = on_view_change
        self._pixmap_cache: Optional[tuple] = None  # (strip image id) -> pixmap
        self.apply_height()
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(STRIP_HINT)

    def sizeHint(self) -> QSize:
        return QSize(600, self.strip_height())

    def apply_height(self) -> None:
        """Ruler and one lane per input: called again when the inputs change."""
        self.setFixedHeight(self.strip_height())

    def set_colors(self, colors: QtColors) -> None:
        self.colors = colors
        self.theme = colors.theme  # thumbnails background (strip_image)
        self.update()

    def strip_width(self) -> int:
        return self.width()

    def on_view_change(self) -> None:
        self.update()
        if self._on_view_change is not None:
            self._on_view_change()

    def _strip_pixmap(self) -> Any:
        image = self.strip_image(THUMB_HEIGHT)
        if self._pixmap_cache is None or self._pixmap_cache[0] is not image:
            self._pixmap_cache = (image, numpy_to_pixmap(image))
        return self._pixmap_cache[1]

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: Any) -> None:
        width, height = self.width(), self.height()
        fps = self.timeline.fps
        colors = self.colors
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, width, height), STRIP_RADIUS, STRIP_RADIUS)
        painter.setClipPath(clip)
        painter.fillRect(0, 0, width, height, colors.track_background)
        painter.fillRect(0, 0, width, RULER_HEIGHT, colors.ruler_band)
        painter.drawPixmap(0, RULER_HEIGHT, self._strip_pixmap())
        if self.n_lanes > 1:
            self._paint_lane_labels(painter)
        # frames decoded ahead: a band along the bottom of the ruler, above the played line
        for left, right in self.buffered_spans():
            painter.fillRect(
                QRectF(left, RULER_HEIGHT - BUFFERED_HEIGHT, right - left, BUFFERED_HEIGHT), colors.buffered
            )

        # ruler: labelled ticks every "nice" number of seconds, minor ticks in between
        painter.setFont(_monospace(7.5))
        step = self.tick_step()
        minor = self.minor_step(step)
        painter.setPen(QPen(colors.minor_tick, 1))
        for seconds in self.ticks(minor):
            x = int(self.x_of(seconds * fps)) + 0.5
            painter.drawLine(QPointF(x, RULER_HEIGHT - 3), QPointF(x, RULER_HEIGHT))
        painter.setPen(QPen(colors.muted, 1))
        for seconds in self.ticks(step):
            x = int(self.x_of(seconds * fps)) + 0.5
            painter.drawLine(QPointF(x, RULER_HEIGHT - 7), QPointF(x, RULER_HEIGHT))
            if x < width - 36:
                painter.drawText(QPointF(x + 4, RULER_HEIGHT - 6), ruler_label(seconds, step))

        x_head = self.x_of(int(self.timeline.value))
        # played part: a thin accent line along the top of the thumbnails
        played = min(max(x_head, 0.0), float(width))
        painter.fillRect(QRectF(0, RULER_HEIGHT, played, 2), colors.accent)

        # hover: a line and the time under the cursor, in a bubble on the ruler
        if self.hover_frame is not None:
            x_hover = int(self.x_of(self.hover_frame)) + 0.5
            painter.setPen(QPen(SHADOW, 3))
            painter.drawLine(QPointF(x_hover, RULER_HEIGHT), QPointF(x_hover, height))
            painter.setPen(QPen(HOVER_LINE, 1))
            painter.drawLine(QPointF(x_hover, RULER_HEIGHT), QPointF(x_hover, height))
            text = f"{timecode(self.hover_frame / fps)} · {self.hover_frame}"
            text_width = painter.fontMetrics().horizontalAdvance(text) + 12
            left = min(max(x_hover - text_width / 2, 1.0), width - text_width - 1.0)
            bubble = QRectF(left, 1, text_width, RULER_HEIGHT - 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors.text)
            painter.drawRoundedRect(bubble, 4, 4)
            painter.setPen(QPen(colors.panel))
            painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)

        # overview when zoomed: the whole video, the visible part, the playhead
        if self.zoomed:
            top = height - OVERVIEW_HEIGHT - 4
            inner = width - 16.0
            start, span, head = self.overview(inner)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors.overview_backing)
            painter.drawRoundedRect(QRectF(5, top - 3, inner + 6, OVERVIEW_HEIGHT + 6), 5, 5)
            painter.setBrush(colors.overview_track)
            painter.drawRoundedRect(QRectF(8, top, inner, OVERVIEW_HEIGHT), 2, 2)
            painter.setBrush(colors.overview_view)
            painter.drawRoundedRect(QRectF(8 + start, top, span, OVERVIEW_HEIGHT), 2, 2)
            painter.setBrush(colors.accent)
            painter.drawRect(QRectF(8 + head - 1, top - 1, 2, OVERVIEW_HEIGHT + 2))

        # playhead: a handle on the ruler and a line over the thumbnails (shadowed for bright frames)
        if -6 <= x_head <= width + 6:
            painter.setPen(QPen(SHADOW, 4))
            painter.drawLine(QPointF(x_head, RULER_HEIGHT), QPointF(x_head, height))
            painter.setPen(QPen(colors.accent, 2))
            painter.drawLine(QPointF(x_head, RULER_HEIGHT - 2), QPointF(x_head, height))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors.accent)
            half = 5.5
            handle = [
                (x_head - half, 1),
                (x_head + half, 1),
                (x_head + half, RULER_HEIGHT - 8),
                (x_head, RULER_HEIGHT - 2),
                (x_head - half, RULER_HEIGHT - 8),
            ]
            painter.drawPath(_polygon(handle))

    def _paint_lane_labels(self, painter: Any) -> None:
        """The input name of each lane, in a small tag at its top left."""
        painter.setFont(_monospace(7.5))
        metrics = painter.fontMetrics()
        for name, top in self.lane_tops(THUMB_HEIGHT):
            text = str(name)
            box = QRectF(4, RULER_HEIGHT + top + 4, metrics.horizontalAdvance(text) + 10, metrics.height() + 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(LABEL_BACKING)
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QPen(HOVER_LINE))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

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
        self.wheel(notches, _event_x(event), pan=horizontal or shift)
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
        # thumbnails and read-ahead come from a background thread: redraw the strip when they change
        self._background_version: tuple = ()
        self.background_timer = QTimer(self)
        self.background_timer.timeout.connect(self._background_changed)
        self.background_timer.start(BACKGROUND_POLL_MS)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(2)
        self.buttons: List[IconButton] = []

        def button(kind: str, tooltip: str, slot: Callable[[], None], **options: Any) -> IconButton:
            widget = IconButton(kind, tooltip, slot, self, **options)
            top.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            self.buttons.append(widget)
            return widget

        def label() -> Any:
            widget = QLabel("", self)
            top.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            return widget

        button("first", "first frame", lambda: self.seek(0))
        button("previous", "previous frame [←]", lambda: self.step(-1))
        self.play_button = button("play", "play / pause [Space]", self.play_pause, primary=True)
        button("next", "next frame [→]", lambda: self.step(1))
        button("last", "last frame", lambda: self.seek(self.timeline.n_frames - 1))
        top.addSpacing(14)
        self.time_label = label()
        self.time_label.setTextFormat(Qt.TextFormat.RichText)
        top.addSpacing(10)
        self.frame_label = label()
        self.frame_label.setFixedHeight(22)  # Qt drops a radius larger than half the height
        top.addSpacing(6)
        self.fps_label = label()
        top.addStretch(1)
        self.zoom_label = label()
        self.zoom_label.setToolTip("scroll on the film strip to zoom, shift + scroll to pan")
        top.addSpacing(2)
        self.fit_button = button("fit", "show the whole video (double-click on the strip)", self.strip_fit)
        self.loop_button = button(
            "loop", "loop playback", self._loop_clicked, checkable=True, checked=bool(timeline.loop)
        )
        self.collapse_button = button("collapse", "hide the film strip", self.toggle_collapsed)

        self.strip = FilmStrip(timeline, self.seek, self, on_view_change=self._view_changed)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addWidget(self.strip)
        self.setLayout(layout)
        self.colors = QtColors(_window_theme(self))
        self._apply_colors()
        self._view_changed()
        self.apply_display()
        self.reset()
        if timeline.playing:
            self.play()

    # ---------------------------------------------------------------- display (Video(..., timeline=...))
    def apply_display(self) -> None:
        """Show, fold or hide the panel after ``timeline.display`` / ``timeline.collapsed``."""
        timeline = self.timeline
        self._applied_display = (timeline.display, timeline.collapsed, self.strip.n_lanes)
        folded = timeline.collapsible and timeline.collapsed
        self.collapse_button.setVisible(timeline.collapsible)
        self.collapse_button.set_kind("expand" if folded else "collapse")
        self.collapse_button.setToolTip("show the film strip" if folded else "hide the film strip")
        self.strip.setVisible(not folded)
        self.strip.apply_height()
        # never squeezed by the images: the panel keeps its height
        self.setFixedHeight(6 + PLAY_SIZE + (8 if folded else 6 + self.strip.strip_height() + 10))
        self.setVisible(timeline.display != "hidden")

    def toggle_collapsed(self) -> None:
        """Fold the panel to its transport row, or unfold it (collapsible displays)."""
        self.timeline.collapsed = not self.timeline.collapsed
        self.apply_display()

    def _apply_colors(self) -> None:
        colors = self.colors
        self.frame_label.setStyleSheet(
            f"QLabel {{ background: {_hex(colors.ruler_band)}; color: {_hex(colors.text)}; border-radius: 10px;"
            f" padding: 0px 10px; font-family: {monospace_css()}; font-size: 11px; }}"
        )
        muted = f"color: {_hex(colors.muted)}; font-size: 11px; background: transparent;"
        self.fps_label.setStyleSheet(f"QLabel {{ {muted} }}")
        self.zoom_label.setStyleSheet(f"QLabel {{ {muted} font-family: {monospace_css()}; }}")
        self.time_label.setStyleSheet("QLabel { background: transparent; }")
        for widget in self.buttons:
            widget.colors = colors
            widget.update()
        self.strip.set_colors(colors)

    def set_theme(self, theme: Theme) -> None:
        """Repaint the panel with ``theme`` (``timeline_view.DARK`` / ``LIGHT``)."""
        self.colors = QtColors(theme)
        self._apply_colors()
        self.reset()
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        theme = _window_theme(self)
        if theme != self.colors.theme:  # the window switched between light and dark
            self.set_theme(theme)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            box = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
            border = self.colors.border
            painter.setPen(QPen(border, 1) if border is not None else Qt.PenStyle.NoPen)
            painter.setBrush(self.colors.panel)
            painter.drawRoundedRect(box, PANEL_RADIUS, PANEL_RADIUS)
        finally:
            painter.end()

    # ---------------------------------------------------------------- state
    def sync_length(self) -> None:
        """After a run: a ``Video`` a filter returned changed length or frame rate, show it."""
        length = (self.timeline.n_frames, self.timeline.fps)
        if length != getattr(self, "_synced_length", length):
            self.reset()
        self._synced_length = length

    def reset(self) -> None:
        """Sync with the control value (reset, tuning import, session restore, key step)."""
        if (self.timeline.display, self.timeline.collapsed, self.strip.n_lanes) != self._applied_display:
            self.apply_display()  # new Video inputs: another timeline=..., another number of lanes
        position = self.timeline.position
        mono = monospace_css()
        self.time_label.setText(
            f"<span style='font-family: {mono}; font-size: 15px; font-weight: 600; color: {_hex(self.colors.text)}'>"
            f"{timecode(position.time)}</span>"
            f"<span style='font-family: {mono}; font-size: 12px; color: {_hex(self.colors.muted)}'>"
            f"&nbsp;/&nbsp;{timecode(position.duration)}</span>"
        )
        self.frame_label.setText(f"frame {position.frame} / {position.n_frames - 1}")
        self.frame_label.setVisible(self.timeline.has_video)  # sounds only: the timecode says it all
        if self.timeline.has_video:
            self.fps_label.setText(f"{self.timeline.fps:g} fps")
        else:
            self.fps_label.setText(f"{self.timeline.audio_clips[0].sample_rate / 1000:g} kHz")
        self.strip.follow(position.frame)
        self.strip.update()
        self.timeline.preload(position.frame)  # decode the next frames before playback reaches them

    def _background_changed(self) -> None:
        self._follow_audio_state()
        version = self.timeline.background_version
        if version != self._background_version:
            self._background_version = version
            if self.strip.isVisible():
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
        """Move the playhead to ``frame`` (and the sound of ``AudioClip`` inputs with it)."""
        frame = self._advance(frame)
        audio = self._audio()
        if audio is not None:
            audio.seek(frame / self.timeline.fps)
            if self.timeline.playing and frame / self.timeline.fps < self._audio_duration():
                audio.play()  # back inside the sound (loop of a longer video)

    def _advance(self, frame: int) -> int:
        """Move the playhead without touching the sound (playback follows it)."""
        frame = int(min(max(frame, 0), self.timeline.n_frames - 1))
        if frame != int(self.timeline.value):
            self.main_window.update_parameter(self.timeline.name, frame)
        self.reset()
        return frame

    # ---------------------------------------------------------------- sound (AudioClip inputs)
    def _audio(self) -> Any:
        """The ``audio`` bindings of the pipeline when an ``AudioClip`` is on the timeline, else None."""
        if not self.timeline.audio_clips:
            return None
        pipeline = getattr(self.main_window, "pipeline", None)
        state = getattr(pipeline, "framework_state", None)
        return getattr(state, "audio", None)

    def _audio_duration(self) -> float:
        return max((clip.duration for clip in self.timeline.audio_clips), default=0.0)

    def _audio_clock(self) -> Optional[float]:
        """Seconds played by the sound when it is playing (the playhead follows it), else None."""
        audio = self._audio()
        if audio is None or not audio.playing():
            return None
        position = audio.position()
        return None if position is None else float(position)

    def _follow_audio_state(self) -> None:
        """A filter started the sound (``audio.play()``): the playhead follows it."""
        if not self.timeline.playing and self._audio_clock() is not None:
            self.timeline.playing = True
            self.timer.start(max(int(round(1000.0 / self.timeline.fps)), 1))
            self.play_button.set_kind("pause")

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
        audio = self._audio()
        time = int(self.timeline.value) / self.timeline.fps
        if audio is not None and time < self._audio_duration():
            audio.seek(time)
            audio.play()

    def pause(self) -> None:
        self.timeline.playing = False
        self.timer.stop()
        self.play_button.set_kind("play")
        audio = self._audio()
        if audio is not None:
            audio.pause()

    def play_pause(self) -> None:
        if self.timeline.playing:
            self.pause()
        else:
            self.play()

    def _tick(self) -> None:
        clock = self._audio_clock()
        if clock is not None:  # the sound plays: the playhead follows it, never the other way round
            self._advance(int(clock * self.timeline.fps))
            return
        target = self.timeline.next_frame()
        if target is None:
            self.pause()
            return
        if target < int(self.timeline.value):
            self.seek(target)  # looped: the sound starts over too
        else:
            self._advance(target)  # past the end of a shorter sound: the timer goes on
