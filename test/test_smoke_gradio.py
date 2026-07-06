"""Gradio GUI smoke tests (no server launch).

Pins the behavior of gradio_gui.py before/while it is split into modules
(tech-debt item 1) and the framework-state refactor (item 2): the dry-run
output-type detection, the global_params save/restore around the dry run,
per-type run_fn conversions, flat slider layouts, panel grouping and audio
mode. Blocks.launch is monkeypatched so no server or browser ever starts;
the double launch (instantiate + refresh) is pinned deliberately.
"""

import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

gr = pytest.importorskip("gradio")

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.data_objects.table import Table  # noqa: E402
from interactive_pipe.graphical import gradio_gui  # noqa: E402
from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio  # noqa: E402
from interactive_pipe.headless.control import Control  # noqa: E402
from interactive_pipe.headless.panel import Panel  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@pytest.fixture(autouse=True)
def launch_recorder(monkeypatch):
    """Record and swallow Blocks.launch so no server ever starts."""
    calls = []

    def fake_launch(self, *args, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(gr.blocks.Blocks, "launch", fake_launch, raising=True)
    return calls


# ---------------------------------------------------------------------------
# Module-level filters & pipelines (the AST parser reads pipeline source)
# ---------------------------------------------------------------------------
@interactive(gr_brightness=(0.5, [0.0, 1.0]), gr_mode=("mean", ["mean", "max"]))
def gr_adjust(img, gr_brightness=0.5, gr_mode="mean"):
    layout.style("gray", title=f"mode={gr_mode}")
    return img * gr_brightness


@interactive()
def gr_curve(img):
    return Curve([SingleCurve(y=img.mean(axis=0))], ylabel="mean")


@interactive()
def gr_table(img):
    return Table(img[:2, :2], columns=["a", "b"])


@interactive()
def gr_text(img):
    return f"mean={img.mean():.2f}"


def gradio_mixed_pipeline(img):
    gray = gr_adjust(img)
    curve = gr_curve(img)
    tab = gr_table(img)
    txt = gr_text(img)
    return [[gray, curve], [tab, txt]]


@interactive(gr_volume=(0.5, [0.0, 1.0]))
def gr_signal(img, gr_volume=0.5):
    return img.flatten() * gr_volume


def gradio_signal_pipeline(img):
    signal = gr_signal(img)
    return signal


@interactive(gr_flat_gain=(0.5, [0.0, 1.0]), gr_flat_offset=(0.1, [0.0, 1.0]))
def gr_flat(img, gr_flat_gain=0.5, gr_flat_offset=0.1):
    return img * gr_flat_gain + gr_flat_offset


def gradio_flat_pipeline(img):
    out = gr_flat(img)
    return out


GR_COLLAPSIBLE_PANEL = Panel("GrExtras", collapsible=True, collapsed=False)
GR_DETACHED_PANEL = Panel("GrDetached", detached=True)


@interactive(
    gr_panel_gain=Control(0.5, [0.0, 1.0], group=GR_COLLAPSIBLE_PANEL),
    gr_detached_gain=Control(0.5, [0.0, 1.0], group=GR_DETACHED_PANEL),
)
def gr_panel_filter(img, gr_panel_gain=0.5, gr_detached_gain=0.5):
    return img * gr_panel_gain * gr_detached_gain


def gradio_panel_pipeline(img):
    out = gr_panel_filter(img)
    return out


def build_and_run(pipeline_function, **gui_kwargs):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = InteractivePipeGradio(pipeline=pipeline, name="gradio smoke", **gui_kwargs)
    results = gui(INPUT_IMAGE.copy())
    return gui, results


def block_types(io):
    return {type(block) for block in io.blocks.values()}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_end_to_end_build_with_mixed_grid(launch_recorder):
    if not gradio_gui.MPL_SUPPORT:
        pytest.skip("matplotlib support not available in gradio backend")
    gui, results = build_and_run(gradio_mixed_pipeline)
    assert isinstance(results, list)
    assert isinstance(gui.window.io, gr.Blocks)
    # instantiate_gradio_interface launches once, refresh() launches again
    assert len(launch_recorder) == 2
    types = block_types(gui.window.io)
    assert gr.Image in types and gr.Plot in types and gr.Dataframe in types and gr.Textbox in types
    canvas = gui.window.image_canvas
    assert canvas[0][0]["type"] == "image"
    assert canvas[0][1]["type"] == "curve"
    assert canvas[1][0]["type"] == "table"
    assert "type" not in canvas[1][1]  # str branch sets no type (pinned)
    # styled title flows into the container labels via the canvas cells
    assert canvas[0][0]["title"] == "mode=mean"


def test_1d_output_becomes_audio_container():
    gui, _ = build_and_run(gradio_signal_pipeline)
    assert gr.Audio in block_types(gui.window.io)
    assert gui.window.image_canvas[0][0]["type"] == "audio"


def test_dry_run_restores_global_params():
    pipeline = HeadlessPipeline.from_function(gradio_flat_pipeline, inputs=["img"])
    pipeline.global_params["user_marker"] = "before"
    gui = InteractivePipeGradio(pipeline=pipeline, name="restore smoke")
    gui(INPUT_IMAGE.copy())
    assert pipeline.global_params["user_marker"] == "before"
    # _reset_global_params must re-link every filter to the restored dict
    assert all(filt.global_params is pipeline.global_params for filt in pipeline.filters)


def test_run_fn_converts_each_output_type():
    if not gradio_gui.MPL_SUPPORT:
        pytest.skip("matplotlib support not available in gradio backend")
    import matplotlib.figure

    gui, _ = build_and_run(gradio_mixed_pipeline)
    window = gui.window
    converted = window.run_fn(*window.default_values)
    assert isinstance(converted, tuple) and len(converted) == 4
    gray, fig, table_data, text = converted
    assert isinstance(gray, np.ndarray) and gray.dtype == np.uint8
    assert isinstance(fig, matplotlib.figure.Figure)
    assert isinstance(table_data, list)
    assert isinstance(text, str) and text.startswith("mean=")


@pytest.mark.parametrize("sliders_layout", ["compact", "vertical", "collapsible", "smart"])
@pytest.mark.parametrize("sliders_per_row_layout", [1, 2])
def test_flat_slider_layouts_build(sliders_layout, sliders_per_row_layout):
    gui, _ = build_and_run(
        gradio_flat_pipeline,
        sliders_layout=sliders_layout,
        sliders_per_row_layout=sliders_per_row_layout,
    )
    assert isinstance(gui.window.io, gr.Blocks)


def test_bogus_sliders_layout_raises():
    with pytest.raises(ValueError, match="sliders_layout must be one of"):
        build_and_run(gradio_flat_pipeline, sliders_layout="bogus")


def test_panels_grouping_and_detached_excluded():
    gui, _ = build_and_run(gradio_panel_pipeline)
    assert gr.Accordion in block_types(gui.window.io)  # collapsible panel
    grouped = gui.window._group_panels_by_position()
    grouped_panels = [panel for panels in grouped.values() for panel in panels]
    assert GR_COLLAPSIBLE_PANEL in grouped_panels
    assert GR_DETACHED_PANEL not in grouped_panels  # detached panels are excluded


def test_audio_mode_adds_html_widget_and_extra_output():
    gui, _ = build_and_run(gradio_signal_pipeline, audio=True)
    window = gui.window
    assert isinstance(window.audio_widget, gr.HTML)
    converted = window.run_fn(*window.default_values)
    assert isinstance(converted, tuple)
    assert isinstance(converted[-1], str)  # trailing audio HTML payload
