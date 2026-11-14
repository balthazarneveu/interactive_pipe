"""layout.style: successive calls on one output during one run add up."""

import os

import numpy as np
import pytest

from interactive_pipe import interactive, layout
from interactive_pipe.headless.output_check import output_problems
from interactive_pipe.headless.pipeline import HeadlessPipeline

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HEAT = np.linspace(0, 10, 64).reshape(8, 8)


@interactive()
def heat_twice():
    layout.style("h", colormap="viridis", vmin=0, vmax=10)
    layout.style("h", title="readout")
    return HEAT.copy()


def twice_pipeline():
    h = heat_twice()
    return h


@interactive()
def heat_once():
    layout.style("h", colormap="viridis", vmin=0, vmax=10, title="readout")
    return HEAT.copy()


def once_pipeline():
    h = heat_once()
    return h


def _styles(pipe):
    return pipe.framework_state.output_styles


def test_second_call_keeps_the_first_calls_keys():
    pipe = HeadlessPipeline.from_function(twice_pipeline)
    pipe()
    assert _styles(pipe)["h"] == {"colormap": "viridis", "vmin": 0, "vmax": 10, "title": "readout"}


def test_reproducer_no_longer_warns_clipped():
    pipe = HeadlessPipeline.from_function(twice_pipeline)
    pipe()
    assert output_problems([("h", HEAT)], {}) != []  # without the style: clipped
    assert output_problems([("h", HEAT)], _styles(pipe)) == []


def test_later_call_wins_and_none_removes_a_key():
    @interactive()
    def f():
        layout.style("h", colormap="viridis", vmin=0, title="a")
        layout.style("h", vmin=2, title=None)
        return HEAT.copy()

    def p():
        h = f()
        return h

    pipe = HeadlessPipeline.from_function(p)
    pipe()
    assert _styles(pipe)["h"] == {"colormap": "viridis", "vmin": 2}


def test_subtitle_added_later_goes_after_the_earlier_title():
    @interactive()
    def f():
        layout.style("h", title="map")
        layout.style("h", subtitle="max 3")
        return HEAT.copy()

    def p():
        h = f()
        return h

    pipe = HeadlessPipeline.from_function(p)
    pipe()
    assert _styles(pipe)["h"]["title"] == "map · max 3"


def test_two_filters_styling_one_output_add_up():
    @interactive()
    def make():
        layout.style("h", colormap="magma")
        return HEAT.copy()

    @interactive()
    def annotate(h):
        layout.style("h", title=f"max {h.max():.0f}")

    def p():
        h = make()
        annotate(h)
        return h

    pipe = HeadlessPipeline.from_function(p)
    pipe()
    assert _styles(pipe)["h"] == {"colormap": "magma", "title": "max 10"}


def test_next_run_starts_afresh():
    @interactive()
    def f(viridis=True):
        if viridis:
            layout.style("h", colormap="viridis")
        else:
            layout.style("h", title="plain")
        return HEAT.copy()

    def p():
        h = f()
        return h

    pipe = HeadlessPipeline.from_function(p, cache=False)
    pipe()
    pipe.parameters = {"f": {"viridis": False}}
    pipe()
    assert _styles(pipe)["h"] == {"title": "plain"}


def test_snapshot_equals_a_single_call():
    twice = HeadlessPipeline.from_function(twice_pipeline).snapshot(None)
    once = HeadlessPipeline.from_function(once_pipeline).snapshot(None)
    np.testing.assert_array_equal(twice, once)


def _cell_rgb_qt(pipeline_function):
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(pipeline_function, inputs=[])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="merge")
    try:
        gui.pipeline.inputs = []
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        image = cell["image"].pixmap().toImage()
        color = image.pixelColor(image.width() - 1, image.height() - 1)
        return (color.red(), color.green(), color.blue()), dict(_styles(pipe)["h"])
    finally:
        gui.close()


def test_qt_shows_the_colormap_and_the_title():
    rgb, style = _cell_rgb_qt(twice_pipeline)
    assert style["title"] == "readout"
    assert rgb[0] != rgb[1] or rgb[1] != rgb[2], "a colormapped cell is not gray"
    assert rgb == _cell_rgb_qt(once_pipeline)[0]


def test_mpl_shows_the_colormap():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(twice_pipeline, inputs=[])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="merge mpl")
    try:
        gui.pipeline.inputs = []
        gui.window.refresh()
        array = np.asarray(gui.window.image_canvas[0][0]["data"].get_array(), dtype=float)
        assert array.ndim == 3 and not np.allclose(array[..., 0], array[..., 1])
    finally:
        gui.close()


def test_clipped_hint_does_not_suggest_a_style_already_given():
    rgb = np.full((4, 4, 3), 200.0)
    problems = output_problems([("img", rgb)], {"img": {"vmin": 0, "vmax": 255}})
    assert len(problems) == 1
    assert "use layout.style" not in problems[0]
    assert "2D (H, W) arrays only" in problems[0]
    plain = output_problems([("img", rgb)], {})
    assert "layout.style(name, vmin=..., vmax=...)" in plain[0]
