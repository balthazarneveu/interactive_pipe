"""Mouse input on the Gradio backend: gr.Image.select sets a PointControl (no server launch)."""

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

gr = pytest.importorskip("gradio")

from interactive_pipe import PointControl, RegionControl, interactive, layout, to_pixels  # noqa: E402
from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

IMAGE = np.zeros((100, 200, 3))
HEATMAP = np.linspace(0.0, 1.0, 20 * 30).reshape(20, 30)


@pytest.fixture(autouse=True)
def no_launch(monkeypatch):
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, *args, **kwargs: None)


@interactive(
    gp_seed=PointControl((0.5, 0.5), name="gp_seed"),
    gp_roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="gp_roi"),
)
def gp_probe(img, gp_seed=(0.5, 0.5), gp_roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(gp_seed, img)
    x0, y0, x1, y1 = to_pixels(gp_roi, img)
    return img[y0:y1, x0:x1], f"{col}, {row}"


def gp_pipeline(img):
    crop, where = gp_probe(img)
    return [img, crop, where]


@interactive(gh_seed=PointControl((0.5, 0.5), on="heat", name="gh_seed"))
def gh_probe(heat, gh_seed=(0.5, 0.5)):
    layout.style("heat", colorbar=True)
    col, row = to_pixels(gh_seed, heat)
    return f"{heat[row, col]:.4f}"


def gh_pipeline(heat):
    value = gh_probe(heat)
    return [heat, value]


class Select:
    """Stands for gr.SelectData: ``index = [x, y]`` in pixels of the displayed image."""

    def __init__(self, x, y):
        self.index = [x, y]


def _gui(pipe_func, image):
    pipeline = HeadlessPipeline.from_function(pipe_func, inputs=["img" if pipe_func is gp_pipeline else "heat"])
    for ctrl in pipeline.controls:
        ctrl.update(ctrl.value_default)
    gui = InteractivePipeGradio(pipeline=pipeline, name="pointer gradio")
    gui(image)
    return gui, gui.window


def test_point_has_no_widget_region_keeps_sliders():
    gui, window = _gui(gp_pipeline, IMAGE)
    assert [widget.label for widget in window.widget_list] == ["gp_roi x0", "gp_roi y0", "gp_roi x1", "gp_roi y1"]
    gui.print_message = lambda lines: None
    lines = gui.show_help()
    assert "[click] on the first image : set gp_seed" in lines
    assert not any("shift+drag" in line for line in lines)


def test_select_event_is_bound_on_the_image_output():
    _, window = _gui(gp_pipeline, IMAGE)
    triggers = [(trigger[1], getattr(fn, "fn", None)) for fn in window.io.fns.values() for trigger in fn.targets]
    assert any(name == "select" for name, _ in triggers)


def test_click_sets_point_and_reruns():
    _, window = _gui(gp_pipeline, IMAGE)
    handler = window.select_handler(0, 0)
    outputs = handler(Select(40, 30), *window.default_values)
    assert to_pixels(window.ctrl["gp_seed"].value, IMAGE) == (40, 30)
    assert window.pipeline.parameters["gp_probe"]["gp_seed"] == window.ctrl["gp_seed"].value
    assert outputs[2] == "40, 30"


def test_click_on_another_cell_changes_nothing():
    _, window = _gui(gp_pipeline, IMAGE)
    outputs = window.select_handler(0, 1)(Select(3, 3), *window.default_values)
    assert window.ctrl["gp_seed"].value == (0.5, 0.5)
    assert outputs[2] == "100, 50"


def test_marks_drawn_on_the_displayed_copy_only():
    _, window = _gui(gp_pipeline, IMAGE)
    outputs = window.run_fn(*window.default_values)
    shown = outputs[0]
    assert shown.dtype == np.uint8 and shown.shape == (100, 200, 3)
    assert shown[50, 100].any()  # the point marker
    assert shown[25, 120].any()  # the top edge of the region
    assert not shown[90, 10].any()
    assert not np.asarray(window.pipeline.results[0][0]).any()  # the output itself is untouched
    assert not outputs[1].any()  # the crop is not a target


def test_heatmap_with_colorbar_maps_to_data_pixels():
    _, window = _gui(gh_pipeline, HEATMAP)
    shown = window.run_fn(*window.default_values)[0]
    upscale = shown.shape[0] // 20
    assert upscale > 1 and shown.shape[1] > 30 * upscale
    outputs = window.select_handler(0, 0)(Select(6 * upscale + 1, 4 * upscale + 1), *window.default_values)
    seed = window.ctrl["gh_seed"].value
    assert to_pixels(seed, HEATMAP) == (6, 4)
    assert outputs[1] == f"{HEATMAP[4, 6]:.4f}"
    window.select_handler(0, 0)(Select(shown.shape[1] - 3, 5), *window.default_values)  # colorbar
    assert window.ctrl["gh_seed"].value == seed
