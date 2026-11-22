"""Video inputs in the GUIs: the Qt timeline widget, the Dear PyGui transport, a frame slider elsewhere."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from test_video import one_video, ramp, two_videos  # noqa: E402

from interactive_pipe import KeyboardControl, Video, interactive  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402


def test_qt_timeline_widget():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(10), fps=20), frame=3)
    widget = gui.window.timeline_widget
    assert gui.window.ctrl["frame"] is pipeline.timeline
    assert widget.frame_label.text() == "frame 3 / 9" and "00:00.15" in widget.time_label.text()
    gui.on_press("right")
    assert pipeline.timeline.value == 4
    widget.seek(9)
    widget.play()
    widget._tick()  # loops to the start
    assert pipeline.timeline.value == 0 and pipeline.timeline.playing
    assert widget.play_button.kind == "pause"
    gui.on_press(" ")
    assert not pipeline.timeline.playing and widget.play_button.kind == "play"
    widget.play_button.click()  # the painted button plays / pauses too
    assert pipeline.timeline.playing
    widget.play_button.click()
    widget.loop_button.click()
    assert not pipeline.timeline.loop and not widget.loop_button.checked
    assert not widget.grab().isNull()  # paints the panel and its buttons
    widget.strip.resize(300, 58)
    assert widget.strip.frame_at(299) == 9 and widget.strip.frame_at(0) == 0
    pixmap = widget.strip.grab()  # paints the film strip and the ruler
    assert not pixmap.isNull()
    pipeline.timeline.value = 5
    gui.window.reset_sliders()
    assert widget.frame_label.text() == "frame 5 / 9"
    layout = gui.window.layout()
    assert layout.indexOf(widget) == layout.indexOf(gui.window.status_label) - 1  # at the bottom


def test_timeline_theme_follows_the_window():
    from interactive_pipe.graphical.timeline_view import DARK, LIGHT, theme_for

    assert theme_for((239, 239, 239)) is LIGHT and theme_for((45, 45, 48)) is DARK
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video theme")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(10), fps=20))
    widget = gui.window.timeline_widget
    for theme in (LIGHT, DARK):
        widget.set_theme(theme)
        assert widget.strip.theme is theme and widget.play_button.colors.theme is theme
        widget.strip.strip_image()
        assert widget.strip._strip_cache[0][2] == theme.name  # thumbnails redrawn on the theme background
        assert widget.colors.text.red() == theme.text[0] and not widget.grab().isNull()


def test_qt_timeline_zoom():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    from interactive_pipe.graphical.timeline_view import MIN_VISIBLE_FRAMES

    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video zoom")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(200), fps=20))
    widget = gui.window.timeline_widget
    strip = widget.strip
    strip.resize(400, 58)
    assert strip.view == (0.0, 199.0) and not strip.zoomed
    strip.zoom(4.0, around=100.0)  # the frame under the cursor stays in place
    first, last = strip.view
    assert last - first == pytest.approx(199.0 / 4) and first < 100.0 < last
    assert (100.0 - first) / (last - first) == pytest.approx(100.0 / 199.0)
    assert strip.frame_at(1.0) == round(first) and strip.frame_at(399.0) == round(last)
    assert not strip.grab().isNull()  # thumbnails of the zoomed part, overview bar
    strip.zoom(1000.0)
    first, last = strip.view
    assert last - first == pytest.approx(MIN_VISIBLE_FRAMES)
    strip.pan(-100.0)  # clamped to the start
    assert strip.view[0] == 0.0
    assert not strip.grab().isNull()  # one thumbnail per frame
    widget.seek(150)  # the view pages to the playhead
    first, last = strip.view
    assert first <= 150 <= last
    strip.zoom(0.001)  # zoomed out past the whole video: back to the full view
    assert not strip.zoomed
    strip.zoom(2.0)
    assert widget.zoom_label.text() == "zoom ×2.0" and not widget.fit_button.isHidden()
    strip.mouseDoubleClickEvent(None)
    assert not strip.zoomed and widget.fit_button.isHidden()
    strip.zoom(2.0)
    widget.fit_button.click()
    assert not strip.zoomed
    strip.hover_frame = 12
    assert not strip.grab().isNull()  # hover line and time bubble


def test_qt_user_key_binding_wins():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

    @interactive(level=KeyboardControl(0, [0, 3], keydown="left", keyup="right"))
    def keyed(img, level=0):
        return img + level

    def keyed_pipeline(clip):
        out = keyed(clip)
        return out

    pipeline = HeadlessPipeline.from_function(keyed_pipeline)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video keys")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(4)))
    assert getattr(gui.key_bindings["right"], "_timeline_key", False) is False
    assert getattr(gui.key_bindings[" "], "_timeline_key", False) is True


def test_dpg_timeline_panel():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="video dpg")
    gui.run = lambda: None  # no viewport in tests
    gui(Video(ramp(100), fps=20))
    window = gui.window
    panel = window.timeline_panel
    assert panel is not None and window.widget_list["frame"] is panel
    assert "frame" not in window.name_label  # not a slider row: the panel at the bottom
    gui.on_press("right")
    assert pipeline.timeline.value == 1
    gui.on_press(" ")
    assert pipeline.timeline.playing and panel.play_button.kind == "pause"
    panel.timer.tick(0.0)
    panel.timer.tick(1.0)
    assert pipeline.timeline.value == 2

    def click(button):
        x0, y0, x1, y1 = button.box
        panel.press((x0 + x1) / 2, (y0 + y1) / 2)
        panel.release((x0 + x1) / 2, (y0 + y1) / 2)

    click(panel.play_button)
    assert not pipeline.timeline.playing and panel.play_button.kind == "play"
    click(panel.buttons[4])  # last frame
    assert pipeline.timeline.value == 99
    click(panel.loop_button)
    assert not pipeline.timeline.loop
    sx, sy = panel.strip_origin
    panel.press(sx + 1, sy + 30)  # on the film strip: seeks to the start
    panel.release(sx + 1, sy + 30)
    assert pipeline.timeline.value == 0
    panel.wheel(3.0, panel.strip_width() / 2)
    assert panel.zoomed
    panel.hover_frame = 10
    panel.draw()  # zoomed strip, overview, hover bubble, fit button
    assert panel.fit_button.visible
    click(panel.fit_button)
    assert not panel.zoomed
    gui.close()


def test_qt_timeline_collapsible_and_hidden():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video folds")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(10), fps=20, timeline="collapsible"))
    widget = gui.window.timeline_widget
    full = widget.height()
    assert not widget.collapse_button.isHidden() and not widget.strip.isHidden()
    widget.collapse_button.click()
    assert pipeline.timeline.collapsed and widget.strip.isHidden() and widget.height() < full
    assert widget.collapse_button.kind == "expand"
    widget.collapse_button.click()
    assert widget.height() == full and not widget.strip.isHidden()

    pipeline = HeadlessPipeline.from_function(one_video)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="video hidden")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(10), fps=20, timeline="hidden"))
    widget = gui.window.timeline_widget
    assert widget.isHidden()
    gui.on_press("right")  # the keys still drive the timeline
    assert pipeline.timeline.value == 1
    gui.on_press(" ")
    assert pipeline.timeline.playing
    widget._tick()
    assert pipeline.timeline.value == 2


def test_dpg_timeline_collapsible_and_hidden():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="video dpg folds")
    gui.run = lambda: None  # no viewport in tests
    gui(Video(ramp(100), fps=20, timeline="collapsed"))
    window = gui.window
    panel = window.timeline_panel
    assert panel.folded and panel.collapse_button.kind == "expand"
    folded = window._timeline_height()
    sx, sy = panel.strip_origin
    assert not panel._in_strip(sx + 5, sy + 30)  # no strip while folded
    panel.draw()
    x0, y0, x1, y1 = panel.collapse_button.box
    panel.press((x0 + x1) / 2, (y0 + y1) / 2)
    panel.release((x0 + x1) / 2, (y0 + y1) / 2)
    assert not panel.folded and window._timeline_height() > folded
    pipeline.timeline.set_display("hidden")
    panel.tick()
    assert panel.height == 0 and window._timeline_height() == 0
    gui.on_press("right")
    assert pipeline.timeline.value == 1
    gui.close()


@pytest.mark.parametrize("backend", ["mpl", "gradio"])
def test_other_backends_show_a_frame_slider(backend):
    from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

    try:
        gui_class = get_interactive_pipeline_class(backend)
    except Exception as exc:  # noqa: BLE001 - backend not installed
        pytest.skip(f"{backend}: {exc}")
    pipeline = HeadlessPipeline.from_function(one_video)
    gui = gui_class(pipeline=pipeline, name="video")
    gui.run = lambda: None
    before = gui.window
    gui(Video(ramp(4)))
    assert any(ctrl is pipeline.timeline for ctrl in gui.controls)
    assert gui.window is not before  # built again (not shown yet) with the frame slider
    if backend == "mpl":
        import matplotlib.pyplot as plt

        open_figures = [plt.figure(number) for number in plt.get_fignums()]
        assert all(figure is not before.fig for figure in open_figures)  # the first figure is closed


def test_film_strip_has_one_lane_per_video():
    from interactive_pipe.graphical.timeline_view import DARK, LANE_GAP, StripView, lanes_height

    class Strip(StripView):
        def strip_width(self):
            return 200

    pipeline = HeadlessPipeline.from_function(two_videos)
    pipeline.inputs = [Video(ramp(20), fps=20), Video(ramp(5), fps=10)]  # b lasts 0.5 s of the 1 s timeline
    timeline = pipeline.timeline
    assert [name for name, _ in timeline.tracks] == ["a", "b"]
    strip = Strip()
    strip.init_strip_view(timeline)
    assert strip.n_lanes == 2 and strip.lane_tops(20) == [("a", 0), ("b", 20 + LANE_GAP)]
    image = strip.strip_image(20, wait=True)
    assert image.shape == (lanes_height(2, 20), 200, 3) == (40 + LANE_GAP, 200, 3)
    assert (image[20 : 20 + LANE_GAP] == DARK.panel).all()  # the gap between the lanes
    lane_b = image[20 + LANE_GAP :]
    assert not (lane_b[:, 20] == DARK.track_background).all()  # thumbnails while b lasts
    assert (lane_b[:, 150:] == DARK.track_background).all()  # b has ended: its lane is empty
    assert not (image[:20, 150:] == DARK.track_background).all()  # a goes on


def test_qt_timeline_grows_with_the_videos():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    from interactive_pipe.graphical.timeline_view import STRIP_HEIGHT, strip_height

    pipeline = HeadlessPipeline.from_function(two_videos)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="two videos")
    qt_gui.QTimer.singleShot(0, gui.close)
    gui(Video(ramp(10), fps=20), Video(ramp(10), fps=20))
    widget = gui.window.timeline_widget
    assert widget.strip.height() == strip_height(2) > STRIP_HEIGHT
    assert widget.height() > widget.strip.height()
    widget.strip.resize(300, strip_height(2))
    assert not widget.strip.grab().isNull()  # paints both lanes and their labels


def test_dpg_timeline_grows_with_the_videos():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical.dpg_timeline import PANEL_HEIGHT
    from interactive_pipe.graphical.timeline_view import STRIP_HEIGHT, lanes_height, strip_height

    pipeline = HeadlessPipeline.from_function(two_videos)
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="two videos dpg")
    gui.run = lambda: None  # no viewport in tests
    gui(Video(ramp(10), fps=20), Video(ramp(10), fps=20))
    panel = gui.window.timeline_panel
    assert panel.height == PANEL_HEIGHT - STRIP_HEIGHT + strip_height(2)
    sx, sy = panel.strip_origin
    assert panel._in_strip(sx + 5, sy + strip_height(2) - 2)  # the second lane seeks too
    panel.draw()  # both lanes and their labels
    assert panel._texture_size[1] == lanes_height(2)  # one texture holds both lanes
    gui.close()
