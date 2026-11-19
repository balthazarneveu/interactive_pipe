"""Video inputs in the GUIs: the Qt timeline widget, the Dear PyGui transport, a frame slider elsewhere."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from test_video import one_video, ramp  # noqa: E402

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
