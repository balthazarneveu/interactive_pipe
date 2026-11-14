"""Mouse input on the matplotlib backend (Agg): simulated clicks and shift-drags."""

import logging

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from matplotlib.backend_bases import MouseEvent  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from interactive_pipe import PointControl, RegionControl, interactive, layout, to_pixels  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

IMAGE = np.random.default_rng(0).random((100, 200, 3)) * 0.5
HEATMAP = np.linspace(0.0, 1.0, 20 * 30).reshape(20, 30)


@interactive(
    mp_seed=PointControl((0.5, 0.5), name="mp_seed"),
    mp_roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="mp_roi"),
)
def mp_probe(img, mp_seed=(0.5, 0.5), mp_roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(mp_seed, img)
    x0, y0, x1, y1 = to_pixels(mp_roi, img)
    profile = img[row, :, 0]
    return img[y0:y1, x0:x1], profile


def mp_pipeline(img):
    crop, profile = mp_probe(img)
    return [img, crop, profile]


@interactive(hm_seed=PointControl((0.5, 0.5), on="heat", name="hm_seed"))
def hm_probe(heat, hm_seed=(0.5, 0.5)):
    layout.style("heat", colorbar=True)
    col, row = to_pixels(hm_seed, heat)
    return np.array([heat[row, col]])


def hm_pipeline(heat):
    value = hm_probe(heat)
    return [heat, value]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


# MouseEvent truncates screen positions to ints: fractions are compared to about one screen pixel
SCREEN = 0.01


def _gui(pipe_func, inputs):
    pipeline = HeadlessPipeline.from_function(pipe_func, inputs=["img" if pipe_func is mp_pipeline else "heat"])
    for ctrl in pipeline.controls:
        ctrl.update(ctrl.value_default)
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="pointer mpl")
    gui.pipeline.inputs = inputs
    gui.window.refresh()
    return gui


def _event(window, name, xdata, ydata, key=None, cell=(0, 0), button=1):
    ax = window.image_canvas[cell[0]][cell[1]]["ax"]
    x, y = ax.transData.transform((xdata, ydata))
    canvas = window.fig.canvas
    canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, button=button, key=key))


def _click(window, xdata, ydata, **kwargs):
    _event(window, "button_press_event", xdata, ydata, **kwargs)
    _event(window, "button_release_event", xdata, ydata, **kwargs)


def _results(gui):
    return gui.pipeline.results[0]


def test_point_and_region_have_no_slider():
    gui = _gui(mp_pipeline, [IMAGE])
    assert gui.window.sliders_list == {}
    assert set(gui.window.ctrl) == {"mp_seed", "mp_roi"}
    gui.close()


def test_click_sets_the_point_and_reruns():
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    _click(window, 49.0, 19.0)  # pixel (col 49, row 19): its centre
    seed = window.ctrl["mp_seed"].value
    assert seed == pytest.approx((49.5 / 200, 19.5 / 100), abs=SCREEN)
    assert gui.pipeline.parameters["mp_probe"]["mp_seed"] == seed
    col, row = to_pixels(seed, IMAGE)
    np.testing.assert_array_equal(_results(gui)[2], IMAGE[row, :, 0])  # the pipeline ran again
    gui.close()


def test_shift_drag_draws_the_region():
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    _event(window, "button_press_event", 9.5, 9.5, key="shift")
    _event(window, "motion_notify_event", 59.5, 49.5, key="shift")
    roi = window.ctrl["mp_roi"].value
    assert roi == pytest.approx((0.05, 0.1, 0.3, 0.5), abs=SCREEN)  # live while dragging
    x0, y0, x1, y1 = to_pixels(roi, IMAGE)
    assert _results(gui)[1].shape == (y1 - y0, x1 - x0, 3)
    _event(window, "button_release_event", 99.5, 79.5, key="shift")
    x0, y0, x1, y1 = window.ctrl["mp_roi"].value
    assert (x0, y0) == pytest.approx((0.05, 0.1), abs=SCREEN)
    assert (x1, y1) == pytest.approx((0.5, 0.8), abs=0.02)  # the axes move a little as the crop changes
    assert window.ctrl["mp_seed"].value == (0.5, 0.5)  # a region gesture leaves the point alone
    gui.close()


def test_plain_drag_does_not_move_the_point():
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    _event(window, "button_press_event", 10.0, 10.0)
    _event(window, "motion_notify_event", 80.0, 60.0)
    _event(window, "button_release_event", 80.0, 60.0)
    assert window.ctrl["mp_seed"].value == (0.5, 0.5)
    gui.close()


def test_other_buttons_and_other_cells_are_ignored():
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    _click(window, 10.0, 10.0, button=3)
    _click(window, 5.0, 5.0, cell=(0, 1))  # the crop is not the target (first image only)
    assert window.ctrl["mp_seed"].value == (0.5, 0.5)
    gui.close()


def test_toolbar_pan_mode_keeps_the_mouse(monkeypatch):
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    monkeypatch.setattr(window, "_toolbar_busy", lambda: True)
    _click(window, 10.0, 10.0)
    assert window.ctrl["mp_seed"].value == (0.5, 0.5)
    gui.close()


def test_overlay_marks_follow_the_values():
    gui = _gui(mp_pipeline, [IMAGE])
    window = gui.window
    artists = window.image_canvas[0][0]["pointer_artists"]
    lines = [artist for artist in artists if hasattr(artist, "get_xdata")]
    rects = [artist for artist in artists if isinstance(artist, Rectangle)]
    assert len(lines) == 1 and len(rects) == 1
    assert (lines[0].get_xdata()[0], lines[0].get_ydata()[0]) == pytest.approx((99.5, 49.5))
    assert rects[0].get_xy() == pytest.approx((49.5, 24.5))
    assert (rects[0].get_width(), rects[0].get_height()) == pytest.approx((100, 50))
    _click(window, 9.0, 9.0)
    lines = [a for a in window.image_canvas[0][0]["pointer_artists"] if hasattr(a, "get_xdata")]
    assert (lines[0].get_xdata()[0], lines[0].get_ydata()[0]) == pytest.approx((9.0, 9.0), abs=2)
    assert "pointer_artists" not in window.image_canvas[0][1] or not window.image_canvas[0][1]["pointer_artists"]
    # the image extent is not changed by the overlay
    ax = window.image_canvas[0][0]["ax"]
    assert ax.get_xlim() == pytest.approx((-0.5, 199.5))
    gui.close()


def test_heatmap_with_colorbar_maps_to_data_pixels():
    gui = _gui(hm_pipeline, [HEATMAP])
    window = gui.window
    shown = window._shown_shape(0, 0)
    upscale = window.cell_data_size(0, 0)[0] / 30
    assert upscale > 1 and shown[1] > 30 * upscale  # enlarged, colorbar on the right
    _click(window, 6.5 * upscale - 0.5, 4.5 * upscale - 0.5)  # centre of data pixel (col 6, row 4)
    seed = window.ctrl["hm_seed"].value
    assert to_pixels(seed, HEATMAP) == (6, 4)
    assert _results(gui)[1][0] == HEATMAP[4, 6]
    _click(window, shown[1] - 5, 10)  # on the colorbar: ignored
    assert window.ctrl["hm_seed"].value == seed
    gui.close()


def test_target_on_a_figure_output_warns_and_is_ignored(caplog):
    import matplotlib.pyplot as plt

    @interactive(fig_seed=PointControl((0.5, 0.5), on="plot", name="fig_seed"))
    def fig_probe(img, fig_seed=(0.5, 0.5)):
        fig, ax = plt.subplots()
        ax.plot(img[0, :, 0])
        return fig

    def fig_pipeline(img):
        plot = fig_probe(img)
        return [plot]

    pipeline = HeadlessPipeline.from_function(fig_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name="pointer fig")
    gui.pipeline.inputs = [IMAGE]
    with caplog.at_level(logging.WARNING):
        gui.window.refresh()
    assert "Clicks on figures are not supported" in caplog.text
    _click(gui.window, 10.0, 10.0)
    assert gui.window.ctrl["fig_seed"].value == (0.5, 0.5)
    gui.close()
