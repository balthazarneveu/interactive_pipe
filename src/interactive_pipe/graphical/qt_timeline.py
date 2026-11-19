"""Qt timeline of a ``Video`` input: transport buttons, film strip with a playhead, timecode.

Shown full width between the images and the controls by
``InteractivePipeQT.add_controls`` when the pipeline gets a ``TimelineControl``
(``headless/timeline.py``). Playback ticks at the video frame rate and moves the
control through ``MainWindow.update_parameter``; refreshes are coalesced, so a
pipeline slower than the video drops frames like a player instead of lagging.
"""

import math
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import numpy as np

from interactive_pipe.graphical.qt_backend import (
    QColor,
    QFont,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPen,
    QPushButton,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QtWidgetBase,
    QWidget,
)
from interactive_pipe.graphical.qt_image import numpy_to_pixmap
from interactive_pipe.headless.timeline import TimelineControl

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow

STRIP_HEIGHT = 58
RULER_HEIGHT = 14
TRACK_BACKGROUND = QColor(32, 33, 36)
RULER_TEXT = QColor(170, 174, 181)
PLAYED_SHADE = QColor(79, 142, 247, 60)
PLAYHEAD = QColor(255, 176, 32)
HOVER_LINE = QColor(255, 255, 255, 110)
#: tick spacing candidates in seconds (the first giving >= MIN_TICK_PIXELS between ticks wins)
TICK_STEPS = (1 / 25, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600)
MIN_TICK_PIXELS = 70


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


def _standard_icon(widget: QWidget, name: str) -> Any:
    style = widget.style()
    enum = getattr(type(style), "StandardPixmap", type(style))
    return style.standardIcon(getattr(enum, name))  # type: ignore[union-attr]


class FilmStrip(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Thumbnails of the video along the time axis, a time ruler and the playhead; click / drag seeks."""

    def __init__(self, timeline: TimelineControl, on_seek: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self.timeline = timeline
        self.on_seek = on_seek
        self.hover_frame: Optional[int] = None
        self._strip_cache: Optional[tuple] = None  # (width, n_frames, ids of videos) -> pixmap
        self.setMinimumHeight(STRIP_HEIGHT)
        self.setMaximumHeight(STRIP_HEIGHT)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(600, STRIP_HEIGHT)

    # ---------------------------------------------------------------- geometry
    def _x_of(self, frame: float) -> float:
        span = max(self.timeline.n_frames - 1, 1)
        return 1.0 + (self.width() - 2.0) * frame / span

    def frame_at(self, x: float) -> int:
        span = max(self.timeline.n_frames - 1, 1)
        fraction = (x - 1.0) / max(self.width() - 2.0, 1.0)
        return int(min(max(round(fraction * span), 0), self.timeline.n_frames - 1))

    # ---------------------------------------------------------------- painting
    def _strip_pixmap(self) -> Any:
        """Film strip of the first video, cached per width (thumbnails decoded once)."""
        width = max(self.width(), 1)
        videos = self.timeline.videos
        key = (width, self.timeline.n_frames, tuple(id(video) for video in videos))
        if self._strip_cache is not None and self._strip_cache[0] == key:
            return self._strip_cache[1]
        height = STRIP_HEIGHT - RULER_HEIGHT
        strip = np.zeros((height, width, 3), dtype=np.uint8)
        strip[...] = (TRACK_BACKGROUND.red(), TRACK_BACKGROUND.green(), TRACK_BACKGROUND.blue())
        if videos:
            video = videos[0]
            try:
                sample = video.thumbnail(0, height)
                tile = max(sample.shape[1], 8)
                for left in range(0, width, tile):
                    frame = self.frame_at(left + tile / 2)
                    seconds = frame / self.timeline.fps
                    thumb = video.thumbnail(video.index_at(seconds), height)
                    right = min(left + thumb.shape[1], width)
                    strip[:, left:right] = thumb[:, : right - left]
                    strip[:, left : left + 1] = 0  # sprocket-like separation between tiles
            except Exception:  # noqa: BLE001 - a frame that cannot be previewed leaves a plain track
                pass
        pixmap = numpy_to_pixmap(np.ascontiguousarray(strip))
        self._strip_cache = (key, pixmap)
        return pixmap

    def _tick_step(self) -> float:
        duration = self.timeline.n_frames / self.timeline.fps
        pixels_per_second = (self.width() - 2.0) / max(duration, 1e-9)
        for step in TICK_STEPS:
            if step * pixels_per_second >= MIN_TICK_PIXELS:
                return step
        return TICK_STEPS[-1]

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: Any) -> None:
        width, height = self.width(), self.height()
        painter.fillRect(0, 0, width, height, TRACK_BACKGROUND)
        painter.drawPixmap(0, RULER_HEIGHT, self._strip_pixmap())
        # ruler: ticks every "nice" number of seconds, labelled with their timecode
        font = QFont(painter.font())
        font.setPointSizeF(max(font.pointSizeF() * 0.75, 6.0))
        painter.setFont(font)
        painter.setPen(QPen(RULER_TEXT))
        step = self._tick_step()
        duration = self.timeline.n_frames / self.timeline.fps
        for k in range(int(math.floor(duration / step)) + 1):
            seconds = k * step
            x = self._x_of(seconds * self.timeline.fps)
            painter.drawLine(int(x), RULER_HEIGHT - 4, int(x), RULER_HEIGHT)
            if x < width - 40:
                painter.drawText(int(x) + 3, RULER_HEIGHT - 3, ruler_label(seconds, step))
        # played part, hover position, playhead
        x_head = self._x_of(int(self.timeline.value))
        painter.fillRect(QRectF(0, RULER_HEIGHT, x_head, height - RULER_HEIGHT), PLAYED_SHADE)
        if self.hover_frame is not None:
            x_hover = self._x_of(self.hover_frame)
            painter.setPen(QPen(HOVER_LINE, 1))
            painter.drawLine(int(x_hover), RULER_HEIGHT, int(x_hover), height)
        pen = QPen(PLAYHEAD, 2)
        painter.setPen(pen)
        painter.drawLine(int(x_head), 0, int(x_head), height)
        painter.fillRect(QRectF(x_head - 4, 0, 8, 6), PLAYHEAD)

    # ---------------------------------------------------------------- mouse
    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.on_seek(self.frame_at(_event_x(event)))

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        frame = self.frame_at(_event_x(event))
        self.hover_frame = frame
        self.setToolTip(self.timeline.label(frame))
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.on_seek(frame)
        self.update()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        self.hover_frame = None
        self.update()


class TimelineWidget(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Transport bar of a ``TimelineControl``: ⏮ ◀ ▶/⏸ ▶ ⏭, film strip, timecode, loop toggle."""

    def __init__(self, window: "MainWindow", timeline: TimelineControl) -> None:
        super().__init__(window)
        self.main_window = window  # not `window`: QWidget.window() is a method
        self.timeline = timeline
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.buttons: List[QPushButton] = []

        def button(icon: str, tooltip: str, slot: Callable[[], None]) -> QPushButton:
            widget = QPushButton(self)
            widget.setIcon(_standard_icon(self, icon))
            widget.setToolTip(tooltip)
            widget.setFixedSize(30, 26)
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys stay with the window (space, arrows)
            widget.clicked.connect(lambda _checked=False: slot())
            layout.addWidget(widget)
            self.buttons.append(widget)
            return widget

        button("SP_MediaSkipBackward", "first frame", lambda: self.seek(0))
        button("SP_MediaSeekBackward", "previous frame [←]", lambda: self.step(-1))
        self.play_button = button("SP_MediaPlay", "play / pause [SPACE]", self.play_pause)
        button("SP_MediaSeekForward", "next frame [→]", lambda: self.step(1))
        button("SP_MediaSkipForward", "last frame", lambda: self.seek(self.timeline.n_frames - 1))
        self.strip = FilmStrip(timeline, self.seek, self)
        layout.addWidget(self.strip, 1)
        self.time_label = QLabel("", self)
        self.time_label.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.time_label)
        self.loop_button = QPushButton("⟳", self)
        self.loop_button.setCheckable(True)
        self.loop_button.setChecked(timeline.loop)
        self.loop_button.setToolTip("loop playback")
        self.loop_button.setFixedSize(30, 26)
        self.loop_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.loop_button.toggled.connect(self._set_loop)
        layout.addWidget(self.loop_button)
        self.setLayout(layout)
        # never squeezed by the images: the strip keeps its height
        self.setFixedHeight(max(self.sizeHint().height(), STRIP_HEIGHT + 4))
        self.reset()
        if timeline.playing:
            self.play()

    # ---------------------------------------------------------------- state
    def reset(self) -> None:
        """Sync with the control value (reset, tuning import, session restore, key step)."""
        self.time_label.setText(self.timeline.label())
        self.strip.update()

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

    def _set_loop(self, checked: bool) -> None:
        self.timeline.loop = bool(checked)

    # ---------------------------------------------------------------- playback
    def play(self) -> None:
        if self.timeline.next_frame() is None:
            self.seek(0)  # at the end without loop: start over
        self.timeline.playing = True
        self.timer.start(max(int(round(1000.0 / self.timeline.fps)), 1))
        self.play_button.setIcon(_standard_icon(self, "SP_MediaPause"))

    def pause(self) -> None:
        self.timeline.playing = False
        self.timer.stop()
        self.play_button.setIcon(_standard_icon(self, "SP_MediaPlay"))

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
