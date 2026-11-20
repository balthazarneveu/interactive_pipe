"""Film strip of a video timeline, independent of the GUI toolkit (pure Python + numpy).

``StripView`` holds what the Qt and Dear PyGui timelines share: the visible
range of frames (zoom / pan / follow the playhead), the frame <-> pixel
mapping, the ruler ticks, and the thumbnails composed into one RGB strip.
A backend subclasses it and provides ``strip_width()`` and, optionally,
``on_view_change()``; it draws the result its own way (``qt_timeline.py``,
``dpg_timeline.py``). Colours and sizes of both timelines live here too.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from interactive_pipe.headless.timeline import TimelineControl

RGB = Tuple[int, int, int]


# ---------------------------------------------------------------- look (shared by the backends)
@dataclass(frozen=True)
class Theme:
    """Colours of the timeline panel; ``overlay`` tints hover / pressed fills (white on dark, black on light)."""

    name: str
    panel: RGB
    track_background: RGB
    ruler_band: RGB
    text: RGB
    muted: RGB
    accent: RGB  # playhead, play button, loop on
    accent_hover: RGB
    accent_pressed: RGB
    on_accent: RGB  # icon on the play button
    overlay: RGB
    buffered: RGB  # frames decoded ahead (thin band under the thumbnails)
    pending: RGB  # a thumbnail still being built
    border: Optional[RGB] = None  # outline of the panel (light theme: it sits on a light window)


DARK = Theme(
    name="dark",
    panel=(28, 29, 32),
    track_background=(16, 17, 19),
    ruler_band=(38, 40, 44),
    text=(232, 234, 237),
    muted=(138, 143, 152),
    accent=(255, 176, 32),
    accent_hover=(255, 196, 84),
    accent_pressed=(224, 150, 16),
    on_accent=(28, 29, 32),
    overlay=(255, 255, 255),
    buffered=(150, 156, 166),
    pending=(30, 32, 36),
)
LIGHT = Theme(
    name="light",
    panel=(252, 252, 253),
    track_background=(218, 221, 226),
    ruler_band=(236, 238, 242),
    text=(32, 34, 38),
    muted=(108, 114, 124),
    accent=(242, 140, 0),
    accent_hover=(255, 160, 30),
    accent_pressed=(214, 120, 0),
    on_accent=(255, 255, 255),
    overlay=(0, 0, 0),
    buffered=(120, 126, 136),
    pending=(204, 208, 214),
    border=(210, 213, 219),
)


def theme_for(background: Sequence[int]) -> Theme:
    """``LIGHT`` on a light window background (an RGB triple), else ``DARK``."""
    red, green, blue = (float(c) for c in background[:3])
    return LIGHT if 0.299 * red + 0.587 * green + 0.114 * blue > 128 else DARK


# the dark theme's colours, by name (Dear PyGui draws on its own dark theme)
PANEL: RGB = DARK.panel
TRACK_BACKGROUND: RGB = DARK.track_background
RULER_BAND: RGB = DARK.ruler_band
TEXT: RGB = DARK.text
MUTED: RGB = DARK.muted
ACCENT: RGB = DARK.accent
ACCENT_HOVER: RGB = DARK.accent_hover
ACCENT_PRESSED: RGB = DARK.accent_pressed

RULER_HEIGHT = 18
THUMB_HEIGHT = 46
STRIP_HEIGHT = RULER_HEIGHT + THUMB_HEIGHT
OVERVIEW_HEIGHT = 4
BUFFERED_HEIGHT = 2  # band of the frames decoded ahead, along the bottom of the thumbnails
BUTTON_SIZE = 28
PLAY_SIZE = 34
PANEL_RADIUS = 8
STRIP_RADIUS = 5

#: tick spacing candidates in seconds (the first giving >= MIN_TICK_PIXELS between ticks wins)
TICK_STEPS = (1 / 25, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600)
MIN_TICK_PIXELS = 70
#: the most zoomed-in view shows this many frames
MIN_VISIBLE_FRAMES = 8
#: zoom factor per wheel notch
ZOOM_PER_NOTCH = 1.25
#: fraction of the view a wheel notch pans
PAN_PER_NOTCH = 0.15
STRIP_HINT = "click / drag: seek · scroll: zoom · shift + scroll: pan · double-click: whole video"


def ruler_label(seconds: float, step: float) -> str:
    """``"0:05"`` for whole-second ticks, ``"1.5s"`` / ``"0.04s"`` below."""
    if step >= 1:
        minutes, secs = divmod(int(round(seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
    decimals = 1 if step >= 0.1 else 2
    return f"{seconds:.{decimals}f}s"


def _fill_width(thumb: np.ndarray, width: int) -> np.ndarray:
    """``thumb`` enlarged to cover ``width`` columns, cropped to its height around the centre (no gap)."""
    height, thumb_width = thumb.shape[:2]
    if width <= thumb_width:
        return thumb
    scale = width / thumb_width
    rows = ((np.arange(height) + (height * scale - height) / 2) / scale).astype(int).clip(0, height - 1)
    columns = (np.arange(width) / scale).astype(int).clip(0, thumb_width - 1)
    return thumb[rows[:, None], columns[None, :]]


class StripView:
    """Visible range, geometry, ticks and thumbnails of a timeline film strip.

    The strip spans ``strip_width()`` pixels with a 1 px margin on each side;
    ``x_of`` / ``frame_at`` are in that strip's coordinates.
    """

    timeline: TimelineControl

    def init_strip_view(self, timeline: TimelineControl) -> None:
        self.timeline = timeline
        self.theme: Theme = DARK
        self.hover_frame: Optional[int] = None
        self._view: Optional[Tuple[float, float]] = None  # (first, last) visible frame; None: the whole video
        self._strip_cache: Optional[tuple] = None  # (width, view, n_frames, ids of videos) -> image

    # ---------------------------------------------------------------- backend hooks
    def strip_width(self) -> int:
        raise NotImplementedError

    def on_view_change(self) -> None:
        """Called when the visible range changed (zoom, pan, follow)."""

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
        if changed:
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

    def wheel(self, notches: float, x: float, pan: bool = False) -> None:
        """A wheel turn of ``notches`` (positive: away from the user) at strip position ``x``."""
        if pan:
            self.pan(-PAN_PER_NOTCH * notches)
        elif notches:
            self.zoom(ZOOM_PER_NOTCH**notches, around=self.frame_of(x))

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
    def x_of(self, frame: float) -> float:
        first, last = self.view
        return 1.0 + (self.strip_width() - 2.0) * (frame - first) / max(last - first, 1e-9)

    def frame_of(self, x: float) -> float:
        first, last = self.view
        return first + (x - 1.0) / max(self.strip_width() - 2.0, 1.0) * (last - first)

    def frame_at(self, x: float) -> int:
        frame = round(self.frame_of(x))
        return int(min(max(frame, 0), self.timeline.n_frames - 1))

    def overview(self, length: float) -> Tuple[float, float, float]:
        """``(start, span, playhead)`` of the visible part and the playhead on a bar ``length`` px long."""
        first, last = self.view
        low, high = self._full()
        scale = length / (high - low)
        return (first - low) * scale, max((last - first) * scale, 4.0), int(self.timeline.value) * scale

    # ---------------------------------------------------------------- ruler
    def pixels_per_second(self) -> float:
        first, last = self.view
        return (self.strip_width() - 2.0) / max((last - first) / self.timeline.fps, 1e-9)

    def tick_step(self) -> float:
        """Seconds between labelled ticks: frame multiples when zoomed in, "nice" durations otherwise."""
        fps = self.timeline.fps
        pixels_per_second = self.pixels_per_second()
        frame_steps = tuple(k / fps for k in (1, 2, 5, 10))
        for step in sorted(set(frame_steps + tuple(t for t in TICK_STEPS if t > 1 / fps))):
            if step * pixels_per_second >= MIN_TICK_PIXELS:
                return step
        return TICK_STEPS[-1]

    def minor_step(self, step: float) -> float:
        return step / 5 if step * self.pixels_per_second() >= 60 else step / 2

    def ticks(self, step: float) -> List[float]:
        """Times (s) of the multiples of ``step`` inside the view."""
        fps = self.timeline.fps
        first, last = self.view
        start = int(math.ceil(first / fps / step - 1e-9))
        stop = int(math.floor(last / fps / step + 1e-9))
        return [k * step for k in range(start, stop + 1)]

    # ---------------------------------------------------------------- buffered frames
    def buffered_spans(self) -> List[Tuple[float, float]]:
        """``(x_start, x_end)`` strip spans of the frames decoded and in memory (runs of consecutive frames)."""
        spans: List[Tuple[float, float]] = []
        first, last = self.view
        run_start = previous = None
        for frame in self.timeline.buffered():
            if frame < first - 1 or frame > last + 1:
                continue
            if previous is not None and frame == previous + 1:
                previous = frame
                continue
            if run_start is not None and previous is not None:
                spans.append((self.x_of(run_start - 0.5), self.x_of(previous + 0.5)))
            run_start = previous = frame
        if run_start is not None and previous is not None:
            spans.append((self.x_of(run_start - 0.5), self.x_of(previous + 0.5)))
        width = float(self.strip_width())
        return [(max(a, 0.0), min(b, width)) for a, b in spans if b > 0 and a < width]

    # ---------------------------------------------------------------- thumbnails
    def strip_image(self, height: int = THUMB_HEIGHT, wait: bool = False) -> np.ndarray:
        """``(height, strip_width(), 3)`` uint8 film strip of the first video, cached per width and view.

        Thumbnails sit on a grid of frames (a power of two apart, chosen from
        the zoom), so panning and zooming reuse the ones already decoded. The
        missing ones are built in the background (a plain tile meanwhile; the
        strip is composed again when ``timeline.background_version`` changes);
        ``wait=True`` builds them first (tests, screenshots).
        """
        width = max(self.strip_width(), 1)
        videos = self.timeline.videos
        key = (
            width,
            height,
            self.theme.name,
            self.view,
            self.timeline.n_frames,
            tuple(id(video) for video in videos),
            videos[0].background_version[1] if videos else 0,
        )
        if self._strip_cache is not None and self._strip_cache[0] == key:
            return self._strip_cache[1]
        strip = np.zeros((height, width, 3), dtype=np.uint8)
        strip[...] = self.theme.track_background
        if videos:
            video = videos[0]
            try:
                anchors = self._thumbnail_anchors(video, width, height, wait)
                if wait:
                    for anchor, _, _ in anchors:
                        video.thumbnail(anchor, height)
                missing = []
                for anchor, left, right in anchors:
                    thumb = video.cached_thumbnail(anchor, height)
                    if thumb is None:
                        if not video.thumbnail_failed(anchor, height):
                            missing.append(anchor)
                            strip[2:-2, max(left + 1, 0) : max(right - 1, 0)] = self.theme.pending
                        continue
                    thumb = _fill_width(thumb, right - left)
                    crop = max(-left, 0)
                    left = max(left, 0)
                    shown = thumb[:, crop : crop + max(min(right - left, thumb.shape[1] - crop), 0)]
                    strip[:, left : left + shown.shape[1]] = shown
                    if 0 < left < width:
                        strip[:, left - 1 : left + 1] = self.theme.track_background  # gap between the frames
                # nearest the playhead first
                head = int(self.timeline.value)
                if video.cached_thumbnail(0, height) is None and not video.thumbnail_failed(0, height):
                    missing.insert(0, 0)  # the grid of the next composition
                video.request_thumbnails(sorted(missing, key=lambda anchor: (anchor != 0, abs(anchor - head))), height)
            except Exception:  # noqa: BLE001 - a frame that cannot be previewed leaves a plain track
                pass
        strip = np.ascontiguousarray(strip)
        self._strip_cache = (key, strip)
        return strip

    def _thumbnail_anchors(self, video, width: int, height: int, wait: bool = False) -> List[Tuple[int, int, int]]:
        """``(video frame, left x, right x)`` of the thumbnails of the view."""
        thumb = video.cached_thumbnail(0, height)
        if thumb is None and wait:
            thumb = video.thumbnail(0, height)
        # the first thumbnail's width sets the grid; until it is built, a 4:3 guess
        tile = max(thumb.shape[1] if thumb is not None else round(height * 4 / 3), 8)
        first, last = self.view
        pixels_per_frame = (width - 2.0) / max(last - first, 1e-9)
        step = 1
        while step * pixels_per_frame < 0.75 * tile:
            step *= 2
        n_frames = self.timeline.n_frames
        half = 0.5 if step == 1 else 0.0  # one frame per tile: the tile is centred on its frame
        anchors = []
        for anchor in range(int(first // step) * step, int(last) + 1, step):
            if anchor >= n_frames:
                break
            left = int(round(self.x_of(anchor - half)))
            right = min(int(round(self.x_of(anchor + step - half))), width)
            anchors.append((video.index_at(anchor / self.timeline.fps), left, right))
        return anchors
