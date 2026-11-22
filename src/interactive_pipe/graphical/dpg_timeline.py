"""Dear PyGui timeline of a ``Video`` input: the same dark panel as on Qt (``qt_timeline.py``).

One drawlist at the bottom of the window, above the status line. Top row:
transport (first frame, previous frame, play / pause, next frame, last frame),
the timecode, the frame number, and on the right the zoom level, a "whole
video" button and the loop toggle. Below, over the whole width, the film strip
(``timeline_view.StripView``): thumbnails, a time ruler, the playhead; click /
drag seeks, scroll zooms around the cursor, shift + scroll pans, double-click
shows the whole video again.

Dear PyGui has no widget events on drawings: ``tick()``, called every frame
by the window, reads the mouse (hover, press, drag, release) and redraws
when something changed. The wheel comes from the window's handler
(``MainWindow.on_mouse_wheel`` -> ``on_wheel``).
"""

import logging
import math
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, cast

import dearpygui.dearpygui as dpg
import numpy as np

from interactive_pipe.graphical import timeline_view as view
from interactive_pipe.graphical.dpg_panels import DpgTimer
from interactive_pipe.graphical.timeline_view import (
    BUFFERED_HEIGHT,
    BUTTON_SIZE,
    OVERVIEW_HEIGHT,
    PANEL_RADIUS,
    PLAY_SIZE,
    RULER_HEIGHT,
    STRIP_HEIGHT,
    STRIP_RADIUS,
    THUMB_HEIGHT,
    StripView,
    ruler_label,
)
from interactive_pipe.headless.timeline import TimelineControl, timecode

if TYPE_CHECKING:
    from interactive_pipe.graphical.dpg_gui import MainWindow

Color = Tuple[int, ...]
Point = Tuple[float, float]

PAD_X = 10
PAD_TOP = 8
ROW_GAP = 6
PAD_BOTTOM = 10
PANEL_HEIGHT = PAD_TOP + PLAY_SIZE + ROW_GAP + STRIP_HEIGHT + PAD_BOTTOM  # one input (one lane)
FOLDED_HEIGHT = PAD_TOP + PLAY_SIZE + PAD_TOP  # collapsed: the transport row only
SMALL_FONT_PX = 12
TIME_FONT_PX = 17
MONO_ADVANCE = 0.602  # DejaVu Sans Mono advance width, in em

HOVER_FILL: Color = (255, 255, 255, 26)
PRESSED_FILL: Color = (255, 255, 255, 46)
HOVER_LINE: Color = (255, 255, 255, 220)
SHADOW: Color = (0, 0, 0, 140)
OVERVIEW_BACKING: Color = (*view.TRACK_BACKGROUND, 215)
OVERVIEW_TRACK: Color = (255, 255, 255, 45)
OVERVIEW_VIEW: Color = (255, 255, 255, 190)
CHECKED_FILL: Color = (*view.ACCENT, 52)
MINOR_TICK: Color = (*view.MUTED, 110)
LABEL_BACKING: Color = (0, 0, 0, 150)  # input name of a lane, over its thumbnails

_FONTS: Dict[str, Any] = {}


def _fonts() -> Dict[str, Any]:
    """DejaVu Sans Mono (regular and bold) from matplotlib, loaded once per Dear PyGui context.

    Empty when they cannot be loaded: the default font is used.
    """
    small = _FONTS.get("small")
    if small is not None and dpg.does_item_exist(small):
        return _FONTS
    _FONTS.clear()
    try:
        from matplotlib import font_manager

        regular = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans Mono"))
        bold = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans Mono", weight="bold"))
        with dpg.font_registry():  # type: ignore[reportGeneralTypeIssues]
            _FONTS["small"] = dpg.add_font(regular, SMALL_FONT_PX)
            _FONTS["time"] = dpg.add_font(bold, TIME_FONT_PX)
            _FONTS["muted"] = dpg.add_font(regular, 13)
    except Exception:  # broad on purpose: a font is a nicety, never a failure
        logging.debug("Dear PyGui: timeline fonts not loaded", exc_info=True)
        _FONTS.clear()
    return _FONTS


def _text_width(text: str, size: float) -> float:
    return len(text) * size * MONO_ADVANCE


def _points(points: Sequence[Point]) -> List[List[float]]:
    return [[float(x), float(y)] for x, y in points]


def _rgba(color: Sequence[int]) -> Color:
    return tuple(color) if len(color) == 4 else (*color, 255)


class _Button:
    def __init__(self, kind: str, size: int, action: Callable[[], None], primary: bool = False) -> None:
        self.kind = kind
        self.size = size
        self.action = action
        self.primary = primary
        self.checked = False
        self.visible = True
        self.box = (0.0, 0.0, 0.0, 0.0)  # x0, y0, x1, y1 in drawlist coordinates

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.box
        return self.visible and x0 <= x <= x1 and y0 <= y <= y1


def draw_icon(parent: Any, kind: str, center: Point, size: float, color: Color) -> None:
    """Icon ``kind`` (play, pause, first, previous, next, last, loop, fit, collapse, expand) of ``size`` px."""
    cx, cy = center
    s = size / 2

    def at(x: float, y: float) -> Point:  # unit coordinates in [-1, 1]
        return cx + x * s, cy + y * s

    stroke = max(size / 9, 1.6)
    if kind == "play":
        dpg.draw_triangle(at(-0.55, -0.8), at(0.85, 0.0), at(-0.55, 0.8), color=color, fill=color, parent=parent)
    elif kind == "pause":
        for left in (-0.62, 0.18):
            x0, y0 = at(left, -0.75)
            dpg.draw_rectangle(
                (x0, y0), (x0 + 0.44 * s, y0 + 1.5 * s), color=color, fill=color, rounding=0.12 * s, parent=parent
            )
    elif kind in ("first", "last"):
        sign = -1 if kind == "first" else 1
        dpg.draw_triangle(
            at(-0.6 * sign, -0.7), at(0.45 * sign, 0.0), at(-0.6 * sign, 0.7), color=color, fill=color, parent=parent
        )
        x0, y0 = at(0.5 if sign > 0 else -0.72, -0.7)
        dpg.draw_rectangle(
            (x0, y0), (x0 + 0.22 * s, y0 + 1.4 * s), color=color, fill=color, rounding=0.08 * s, parent=parent
        )
    elif kind in ("previous", "next"):
        sign = -1 if kind == "previous" else 1
        points = [at(-0.25 * sign, -0.6), at(0.3 * sign, 0.0), at(-0.25 * sign, 0.6)]
        dpg.draw_polyline(_points(points), color=color, thickness=stroke, parent=parent)
    elif kind in ("collapse", "expand"):  # chevron down: fold the panel; up: unfold it
        sign = 1 if kind == "collapse" else -1
        points = [at(-0.55, -0.25 * sign), at(0.0, 0.3 * sign), at(0.55, -0.25 * sign)]
        dpg.draw_polyline(_points(points), color=color, thickness=stroke, parent=parent)
    elif kind == "loop":
        radius = 0.68 * s
        arc = [
            (cx + radius * math.cos(math.radians(a)), cy - radius * math.sin(math.radians(a)))
            for a in range(70, 361, 10)
        ]
        dpg.draw_polyline(_points(arc), color=color, thickness=stroke, parent=parent)
        tip_x, tip_y = arc[0]
        head = 0.42 * s
        dpg.draw_triangle(
            (tip_x + head, tip_y),
            (tip_x - 0.2 * head, tip_y - 0.75 * head),
            (tip_x - 0.2 * head, tip_y + 0.75 * head),
            color=color,
            fill=color,
            parent=parent,
        )
    elif kind == "fit":
        for sign in (-1, 1):
            dpg.draw_line(at(0.85 * sign, -0.6), at(0.85 * sign, 0.6), color=color, thickness=stroke, parent=parent)
            dpg.draw_line(at(0.1 * sign, 0.0), at(0.6 * sign, 0.0), color=color, thickness=stroke, parent=parent)
            points = [at(0.35 * sign, -0.3), at(0.6 * sign, 0.0), at(0.35 * sign, 0.3)]
            dpg.draw_polyline(_points(points), color=color, thickness=stroke, parent=parent)


class DpgTimeline(StripView):
    """Timeline panel of a ``TimelineControl`` in the Dear PyGui window (see the module docstring)."""

    def __init__(self, window: "MainWindow", timeline: TimelineControl, parent: Any, before: Any = 0) -> None:
        self.init_strip_view(timeline)
        self._background_version: tuple = ()
        self.window = window
        self.width = 800  # panel width, followed every frame
        self.timer = DpgTimer(max(int(round(1000.0 / timeline.fps)), 1), self._tick_playback)
        self.panel = dpg.add_child_window(
            parent=parent,
            before=before,
            height=PANEL_HEIGHT,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        )
        with dpg.theme() as theme:  # type: ignore[reportGeneralTypeIssues]
            with dpg.theme_component(dpg.mvAll):  # type: ignore[reportGeneralTypeIssues]
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, _rgba(view.PANEL), category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, PANEL_RADIUS, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0, category=dpg.mvThemeCat_Core)
        dpg.bind_item_theme(self.panel, theme)
        self.drawlist = dpg.add_drawlist(width=self.width, height=PANEL_HEIGHT, parent=self.panel)
        self.fonts = _fonts()
        if "small" in self.fonts:
            dpg.bind_item_font(self.drawlist, self.fonts["small"])
        self.texture: Optional[Any] = None
        self._texture_size = (0, 0)
        self._texture_image: Optional[np.ndarray] = None
        self.buttons: List[_Button] = [
            _Button("first", BUTTON_SIZE, lambda: self.seek(0)),
            _Button("previous", BUTTON_SIZE, lambda: self.step(-1)),
            _Button("play", PLAY_SIZE, self.play_pause, primary=True),
            _Button("next", BUTTON_SIZE, lambda: self.step(1)),
            _Button("last", BUTTON_SIZE, lambda: self.seek(self.timeline.n_frames - 1)),
        ]
        self.play_button = self.buttons[2]
        self.fit_button = _Button("fit", BUTTON_SIZE, self.reset_view)
        self.loop_button = _Button("loop", BUTTON_SIZE, self._toggle_loop)
        self.loop_button.checked = bool(timeline.loop)
        self.collapse_button = _Button("collapse", BUTTON_SIZE, self.toggle_collapsed)
        self.buttons += [self.fit_button, self.loop_button, self.collapse_button]
        self._applied_display = (timeline.display, timeline.collapsed, self.n_lanes)
        self.hover_button: Optional[_Button] = None
        self.pressed_button: Optional[_Button] = None
        self.dragging = False
        self._mouse_was_down = False
        self.dirty = True
        if timeline.playing:
            timeline.playing = False
            self.play()
        self.apply_display()
        self.draw()

    # ---------------------------------------------------------------- display (Video(..., timeline=...))
    @property
    def folded(self) -> bool:
        return self.timeline.collapsible and self.timeline.collapsed

    @property
    def height(self) -> int:
        """Panel height: 0 when hidden, the transport row only when folded."""
        if self.timeline.display == "hidden":
            return 0
        return FOLDED_HEIGHT if self.folded else PANEL_HEIGHT - STRIP_HEIGHT + self.strip_height()

    def apply_display(self) -> None:
        """Show, fold or hide the panel after ``timeline.display`` / ``timeline.collapsed``."""
        self._applied_display = (self.timeline.display, self.timeline.collapsed, self.n_lanes)
        self.collapse_button.visible = self.timeline.collapsible
        self.collapse_button.kind = "expand" if self.folded else "collapse"
        height = self.height
        dpg.configure_item(self.panel, height=max(height, 1), show=height > 0)
        dpg.configure_item(self.drawlist, height=max(height, 1))
        self.dirty = True
        self.window.layout_timeline()

    def toggle_collapsed(self) -> None:
        """Fold the panel to its transport row, or unfold it (collapsible displays)."""
        self.timeline.collapsed = not self.timeline.collapsed
        self.apply_display()

    # ---------------------------------------------------------------- StripView hooks
    def strip_width(self) -> int:
        return max(int(self.width) - 2 * PAD_X, 10)

    def on_view_change(self) -> None:
        self.dirty = True

    @property
    def strip_origin(self) -> Point:
        return float(PAD_X), float(PAD_TOP + PLAY_SIZE + ROW_GAP)

    # ---------------------------------------------------------------- transport
    def reset(self) -> None:
        """Sync with the control value (reset, tuning import, session restore, key step)."""
        self.follow(int(self.timeline.value))
        self.dirty = True
        self.timeline.preload()  # decode the next frames before playback reaches them

    def seek(self, frame: int) -> None:
        frame = int(min(max(frame, 0), self.timeline.n_frames - 1))
        if frame != int(self.timeline.value):
            self.window.update_parameter(self.timeline.name, frame)
        self.reset()

    def step(self, offset: int) -> None:
        self.pause()
        target = self.timeline.next_frame(offset)
        if target is not None:
            self.seek(target)

    def play(self) -> None:
        if self.timeline.next_frame() is None:
            self.seek(0)  # at the end without loop: start over
        self.timeline.playing = True
        self.timer.start()
        self.play_button.kind = "pause"
        self.dirty = True

    def pause(self) -> None:
        self.timeline.playing = False
        self.timer.stop()
        self.play_button.kind = "play"
        self.dirty = True

    def play_pause(self) -> None:
        if self.timeline.playing:
            self.pause()
        else:
            self.play()

    def _tick_playback(self) -> None:
        target = self.timeline.next_frame()
        if target is None:
            self.pause()
        else:
            self.seek(target)

    def _toggle_loop(self) -> None:
        self.timeline.loop = not self.timeline.loop
        self.loop_button.checked = self.timeline.loop

    # ---------------------------------------------------------------- mouse
    def _mouse(self) -> Optional[Point]:
        """Mouse position in drawlist coordinates, None when it is not over the panel."""
        if not dpg.is_item_hovered(self.drawlist) or self.window.modal_shown():
            return None
        x0, y0 = dpg.get_item_rect_min(self.drawlist)
        x, y = dpg.get_mouse_pos(local=False)[:2]
        return float(x - x0), float(y - y0)

    def _in_strip(self, x: float, y: float) -> bool:
        if self.folded:
            return False
        sx, sy = self.strip_origin
        return sx <= x <= sx + self.strip_width() and sy <= y <= sy + self.strip_height()

    def on_wheel(self, delta: float, shift: bool) -> bool:
        """Wheel over the film strip: zoom (pan with shift); False when the mouse is elsewhere."""
        mouse = self._mouse()
        if mouse is None or not self._in_strip(*mouse):
            return False
        x = mouse[0] - self.strip_origin[0]
        self.wheel(float(delta), x, pan=shift)
        self.hover_frame = self.frame_at(x)
        self.dirty = True
        return True

    def press(self, x: float, y: float) -> None:
        for button in self.buttons:
            if button.contains(x, y):
                self.pressed_button = button
                self.dirty = True
                return
        if self._in_strip(x, y):
            self.dragging = True
            self.seek(self.frame_at(x - self.strip_origin[0]))

    def release(self, x: float, y: float) -> None:
        button, self.pressed_button = self.pressed_button, None
        self.dragging = False
        if button is not None and button.contains(x, y):
            button.action()
        self.dirty = True

    def hover(self, mouse: Optional[Point]) -> None:
        hover_button = None
        hover_frame = None
        if mouse is not None:
            hover_button = next((b for b in self.buttons if b.contains(*mouse)), None)
            if self._in_strip(*mouse):
                hover_frame = self.frame_at(mouse[0] - self.strip_origin[0])
        if hover_button is not self.hover_button or hover_frame != self.hover_frame:
            self.hover_button, self.hover_frame = hover_button, hover_frame
            self.dirty = True

    def tick(self) -> None:
        """Every frame: follow the panel width, read the mouse, redraw when something changed."""
        if not dpg.does_item_exist(self.drawlist):
            return
        if (self.timeline.display, self.timeline.collapsed, self.n_lanes) != self._applied_display:
            self.apply_display()  # new Video inputs: another timeline=..., another number of lanes
        if self.timeline.display == "hidden":
            return
        version = self.timeline.background_version  # thumbnails / frames ready in the background
        if version != self._background_version:
            self._background_version = version
            self.dirty = True
        width = int(dpg.get_item_rect_size(self.panel)[0]) if self.window.viewport_ready else 0
        if width > 0 and width != self.width:
            self.width = width
            dpg.configure_item(self.drawlist, width=width)
            self.dirty = True
        if self.window.viewport_ready:
            mouse = self._mouse()
            down = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
            if down and not self._mouse_was_down and mouse is not None:
                self.press(*mouse)
            elif down and self.dragging:
                local = dpg.get_mouse_pos(local=False)[0] - dpg.get_item_rect_min(self.drawlist)[0]
                self.seek(self.frame_at(local - self.strip_origin[0]))
            elif not down and self._mouse_was_down:
                self.release(*(mouse if mouse is not None else (-1.0, -1.0)))
            if (
                mouse is not None
                and dpg.is_mouse_button_double_clicked(dpg.mvMouseButton_Left)
                and self._in_strip(*mouse)
            ):
                self.reset_view()
            self._mouse_was_down = down
            self.hover(mouse)
        if self.dirty:
            self.draw()

    # ---------------------------------------------------------------- drawing
    def _update_texture(self) -> Any:
        image = self.strip_image(THUMB_HEIGHT)
        height, width = image.shape[:2]
        if self._texture_image is image and self.texture is not None:
            return self.texture
        rgba = np.ones((height, width, 4), dtype=np.float32)
        rgba[..., :3] = image.astype(np.float32) / 255.0
        if self.texture is None or (width, height) != self._texture_size:
            if self.texture is not None and dpg.does_item_exist(self.texture):
                dpg.delete_item(self.texture)
            self.texture = dpg.add_raw_texture(
                width,
                height,
                cast(Any, rgba.ravel()),
                format=dpg.mvFormat_Float_rgba,
                parent=self.window.texture_registry,
            )
            self._texture_size = (width, height)
        else:
            dpg.set_value(self.texture, rgba.ravel())
        self._texture_image = image
        return self.texture

    def _text(
        self, pos: Point, text: str, color: Sequence[int], font: str = "small", size: float = SMALL_FONT_PX
    ) -> None:
        item = dpg.draw_text(pos, text, color=_rgba(color), size=size, parent=self.drawlist)
        if font in self.fonts:
            dpg.bind_item_font(item, self.fonts[font])

    def draw(self) -> None:
        self.dirty = False
        dl = self.drawlist
        dpg.delete_item(dl, children_only=True)
        self._draw_top_row(dl)
        if not self.folded:
            self._draw_strip(dl)

    def _draw_button(self, dl: Any, button: _Button, x: float, cy: float) -> float:
        size = button.size
        button.box = (x, cy - size / 2, x + size, cy + size / 2)
        center = (x + size / 2, cy)
        hovered = button is self.hover_button
        pressed = button is self.pressed_button and hovered
        if button.primary:
            fill = view.ACCENT_PRESSED if pressed else view.ACCENT_HOVER if hovered else view.ACCENT
            dpg.draw_circle(center, size / 2, color=_rgba(fill), fill=_rgba(fill), segments=48, parent=dl)
            icon_color = _rgba(view.PANEL)
        else:
            if button.checked:
                dpg.draw_circle(center, size / 2, color=CHECKED_FILL, fill=CHECKED_FILL, segments=40, parent=dl)
            if hovered:
                fill = PRESSED_FILL if pressed else HOVER_FILL
                dpg.draw_circle(center, size / 2, color=fill, fill=fill, segments=40, parent=dl)
            icon_color = _rgba(view.ACCENT if button.checked else view.TEXT if hovered else view.MUTED)
        icon = size * (0.4 if button.primary else 0.46)
        offset = icon * 0.08 if button.kind == "play" else 0.0  # optical centre of the triangle
        draw_icon(dl, button.kind, (center[0] + offset, cy), icon, icon_color)
        return x + size

    def _draw_top_row(self, dl: Any) -> None:
        width = self.width
        dpg.draw_rectangle(
            (0, 0),
            (width, self.height),
            color=_rgba(view.PANEL),
            fill=_rgba(view.PANEL),
            rounding=PANEL_RADIUS,
            parent=dl,
        )
        cy = PAD_TOP + PLAY_SIZE / 2
        x = float(PAD_X)
        for button in self.buttons[:5]:
            x = self._draw_button(dl, button, x, cy) + 2
        x += 14
        position = self.timeline.position
        now = timecode(position.time)
        self._text((x, cy - TIME_FONT_PX * 0.62), now, view.TEXT, "time", TIME_FONT_PX)
        x += _text_width(now, TIME_FONT_PX) + 4
        total = f"/ {timecode(position.duration)}"
        self._text((x, cy - 13 * 0.55), total, view.MUTED, "muted", 13)
        x += _text_width(total, 13) + 12
        chip = f"frame {position.frame} / {position.n_frames - 1}"
        chip_w = _text_width(chip, SMALL_FONT_PX) + 20
        dpg.draw_rectangle(
            (x, cy - 11),
            (x + chip_w, cy + 11),
            color=_rgba(view.RULER_BAND),
            fill=_rgba(view.RULER_BAND),
            rounding=11,
            parent=dl,
        )
        self._text((x + 10, cy - SMALL_FONT_PX * 0.62), chip, view.TEXT)
        x += chip_w + 8
        self._text((x, cy - SMALL_FONT_PX * 0.62), f"{self.timeline.fps:g} fps", view.MUTED)
        # right side: zoom level, whole-video button (zoomed only), loop toggle, fold button (collapsible)
        right = width - PAD_X
        if self.collapse_button.visible:
            right -= self.collapse_button.size
            self._draw_button(dl, self.collapse_button, right, cy)
            right -= 2
        right -= self.loop_button.size
        self._draw_button(dl, self.loop_button, right, cy)
        self.fit_button.visible = self.zoomed and not self.folded
        if self.fit_button.visible:
            right -= 2 + self.fit_button.size
            self._draw_button(dl, self.fit_button, right, cy)
            label = f"zoom ×{self.zoom_factor:.1f}"
            self._text((right - 6 - _text_width(label, SMALL_FONT_PX), cy - SMALL_FONT_PX * 0.62), label, view.MUTED)

    def _draw_strip(self, dl: Any) -> None:
        sx, sy = self.strip_origin
        width = self.strip_width()
        bottom = sy + self.strip_height()
        fps = self.timeline.fps
        dpg.draw_rectangle(
            (sx, sy),
            (sx + width, bottom),
            color=_rgba(view.TRACK_BACKGROUND),
            fill=_rgba(view.TRACK_BACKGROUND),
            rounding=STRIP_RADIUS,
            parent=dl,
        )
        dpg.draw_rectangle(
            (sx, sy),
            (sx + width, sy + RULER_HEIGHT),
            color=_rgba(view.RULER_BAND),
            fill=_rgba(view.RULER_BAND),
            rounding=STRIP_RADIUS,
            parent=dl,
        )
        dpg.draw_rectangle(
            (sx, sy + RULER_HEIGHT / 2),
            (sx + width, sy + RULER_HEIGHT),
            color=_rgba(view.RULER_BAND),
            fill=_rgba(view.RULER_BAND),
            parent=dl,
        )
        dpg.draw_image(self._update_texture(), (sx, sy + RULER_HEIGHT), (sx + width, bottom), parent=dl)
        # rounded bottom corners: a stroke of the panel colour around the strip
        dpg.draw_rectangle(
            (sx - 2, sy - 2),
            (sx + width + 2, bottom + 2),
            color=_rgba(view.PANEL),
            thickness=4,
            rounding=STRIP_RADIUS + 2,
            parent=dl,
        )

        if self.n_lanes > 1:  # the input name of each lane, at its top left
            for name, top in self.lane_tops(THUMB_HEIGHT):
                text = str(name)
                y = sy + RULER_HEIGHT + top + 4
                dpg.draw_rectangle(
                    (sx + 4, y),
                    (sx + 14 + _text_width(text, 11), y + 14),
                    color=LABEL_BACKING,
                    fill=LABEL_BACKING,
                    rounding=3,
                    parent=dl,
                )
                self._text((sx + 9, y + 1), text, view.TEXT, "small", 11)

        # frames decoded ahead: a band along the bottom of the ruler, above the played line
        for left, right in self.buffered_spans():
            dpg.draw_rectangle(
                (sx + left, sy + RULER_HEIGHT - BUFFERED_HEIGHT),
                (sx + right, sy + RULER_HEIGHT),
                color=_rgba(view.DARK.buffered),
                fill=_rgba(view.DARK.buffered),
                parent=dl,
            )

        # ruler
        step = self.tick_step()
        for seconds in self.ticks(self.minor_step(step)):
            x = sx + int(self.x_of(seconds * fps)) + 0.5
            dpg.draw_line((x, sy + RULER_HEIGHT - 3), (x, sy + RULER_HEIGHT), color=MINOR_TICK, thickness=1, parent=dl)
        for seconds in self.ticks(step):
            x = sx + int(self.x_of(seconds * fps)) + 0.5
            dpg.draw_line(
                (x, sy + RULER_HEIGHT - 7), (x, sy + RULER_HEIGHT), color=_rgba(view.MUTED), thickness=1, parent=dl
            )
            if x < sx + width - 36:
                self._text((x + 4, sy + 2), ruler_label(seconds, step), view.MUTED, "small", 11)

        x_head = sx + self.x_of(int(self.timeline.value))
        played = min(max(x_head, sx), sx + width)
        if played > sx:
            dpg.draw_rectangle(
                (sx, sy + RULER_HEIGHT),
                (played, sy + RULER_HEIGHT + 2),
                color=_rgba(view.ACCENT),
                fill=_rgba(view.ACCENT),
                parent=dl,
            )

        if self.hover_frame is not None:
            x_hover = sx + int(self.x_of(self.hover_frame)) + 0.5
            dpg.draw_line((x_hover, sy + RULER_HEIGHT), (x_hover, bottom), color=SHADOW, thickness=3, parent=dl)
            dpg.draw_line((x_hover, sy + RULER_HEIGHT), (x_hover, bottom), color=HOVER_LINE, thickness=1, parent=dl)
            text = f"{timecode(self.hover_frame / fps)} · {self.hover_frame}"
            text_w = _text_width(text, 11) + 12
            left = min(max(x_hover - text_w / 2, sx + 1), sx + width - text_w - 1)
            dpg.draw_rectangle(
                (left, sy + 1),
                (left + text_w, sy + RULER_HEIGHT - 2),
                color=_rgba(view.TEXT),
                fill=_rgba(view.TEXT),
                rounding=4,
                parent=dl,
            )
            self._text((left + 6, sy + 2), text, view.PANEL, "small", 11)

        if self.zoomed:
            top = bottom - OVERVIEW_HEIGHT - 4
            inner = width - 16.0
            start, span, head = self.overview(inner)
            left = sx + 8
            dpg.draw_rectangle(
                (left - 3, top - 3),
                (left + inner + 3, top + OVERVIEW_HEIGHT + 3),
                color=OVERVIEW_BACKING,
                fill=OVERVIEW_BACKING,
                rounding=5,
                parent=dl,
            )
            dpg.draw_rectangle(
                (left, top),
                (left + inner, top + OVERVIEW_HEIGHT),
                color=OVERVIEW_TRACK,
                fill=OVERVIEW_TRACK,
                rounding=2,
                parent=dl,
            )
            dpg.draw_rectangle(
                (left + start, top),
                (left + start + span, top + OVERVIEW_HEIGHT),
                color=OVERVIEW_VIEW,
                fill=OVERVIEW_VIEW,
                rounding=2,
                parent=dl,
            )
            dpg.draw_rectangle(
                (left + head - 1, top - 1),
                (left + head + 1, top + OVERVIEW_HEIGHT + 1),
                color=_rgba(view.ACCENT),
                fill=_rgba(view.ACCENT),
                parent=dl,
            )

        if sx - 6 <= x_head <= sx + width + 6:
            dpg.draw_line((x_head, sy + RULER_HEIGHT), (x_head, bottom), color=SHADOW, thickness=4, parent=dl)
            dpg.draw_line(
                (x_head, sy + RULER_HEIGHT - 2), (x_head, bottom), color=_rgba(view.ACCENT), thickness=2, parent=dl
            )
            half = 5.5
            top, tip = sy + 1, sy + RULER_HEIGHT - 2
            accent = _rgba(view.ACCENT)
            dpg.draw_rectangle((x_head - half, top), (x_head + half, tip - 6), color=accent, fill=accent, parent=dl)
            dpg.draw_triangle(
                (x_head - half, tip - 6), (x_head + half, tip - 6), (x_head, tip), color=accent, fill=accent, parent=dl
            )
