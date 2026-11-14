"""Outputs that cannot be displayed, or are displayed misleadingly, are named
by snapshot / sweep with the fix and the list of displayable types."""

import logging

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.data_objects.table import Table
from interactive_pipe.headless.output_check import SUPPORTED_OUTPUTS, output_problem, output_problems
from interactive_pipe.headless.pipeline import HeadlessPipeline


@pytest.mark.parametrize(
    "value",
    [
        None,
        "text",
        np.zeros((4, 4)),
        np.zeros((4, 4, 3)),
        np.linspace(0, 1, 5),
        np.eye(3, dtype=bool),
        np.full((4, 4), 1.3),  # mild saturation is the expected display
        Curve([np.linspace(0, 1, 4)]),
        Table({"a": [1, 2]}),
    ],
)
def test_displayable_values(value):
    assert output_problem(value) is None


@pytest.mark.parametrize(
    "value, severity, what, fix",
    [
        ({"a": 1}, "unsupported", "dict is not a displayable type", "separate outputs"),
        ([1, 2], "unsupported", "list is not a displayable type", "separate outputs"),
        (3, "unsupported", "int is not a displayable type", "as text"),
        (np.zeros((0, 0)), "unsupported", "empty array", "non-empty"),
        (np.zeros((2, 4, 4, 3)), "unsupported", "4D array", "batch[0]"),
        (np.zeros((3, 8, 8)), "unsupported", "channel-first", "np.moveaxis"),
        (np.zeros((1, 8, 8)), "unsupported", "channel-first", "np.moveaxis"),
        (np.zeros((8, 8, 1)), "gui", "single-channel", "img[..., 0]"),
        (np.zeros((8, 8, 4)), "gui", "RGBA", "img[..., :3]"),
        (np.zeros((8, 8, 2)), "unsupported", "2-channel", "(H, W, 3)"),
        (np.zeros((4, 4), dtype=complex), "unsupported", "complex128", "np.abs"),
        (np.zeros((4, 4), dtype=np.uint8), "gui", "uint8 image", "img / 255.0"),
        (np.zeros((4, 4), dtype=np.uint16), "gui", "uint16 image", "65535"),
        (np.array([[np.nan, 0.5]]), "misleading", "NaN/inf", "np.nan_to_num"),
        (np.full((4, 4), 200.0), "misleading", "is clipped to [0, 1]", "normalize"),
    ],
)
def test_problems(value, severity, what, fix):
    problem = output_problem(value)
    assert problem is not None
    assert problem[0] == severity
    assert what in problem[1]
    assert fix in problem[2]


def test_third_party_objects():
    pil = pytest.importorskip("PIL.Image")
    problem = output_problem(pil.new("RGB", (4, 4)))
    assert problem is not None and "PIL.Image" in problem[1] and "np.asarray" in problem[2]
    import matplotlib.figure

    problem = output_problem(matplotlib.figure.Figure().add_subplot())
    assert problem is not None and "matplotlib" in problem[1]


def test_messages_name_the_output():
    messages = output_problems([("ok", np.zeros((4, 4))), ("mask", np.zeros((8, 8, 1)))])
    assert messages == [
        "output 'mask' is drawn by snapshot but not by every GUI backend: single-channel array (8, 8, 1) "
        "(the Qt and Dear PyGui backends raise on it). Fix: drop the channel axis: img[..., 0]."
    ]


@interactive()
def checked_source(img):
    return (img * 255).astype(np.uint8), {"meta": 1}


def checked_pipeline(img):
    raw, meta = checked_source(img)
    return raw, meta


def test_snapshot_logs_display_problems(tmp_path, caplog):
    pipe = HeadlessPipeline.from_function(checked_pipeline)
    with caplog.at_level(logging.WARNING):
        pipe.snapshot(tmp_path / "out.png", np.ones((4, 4)) * 0.5)
    text = caplog.text
    assert "snapshot(): output 'raw' is drawn by snapshot but not by every GUI backend: uint8 image" in text
    assert "output 'meta' cannot be displayed: dict is not a displayable type" in text
    assert SUPPORTED_OUTPUTS in text
    assert (tmp_path / "out.png").exists()


def test_snapshot_of_good_outputs_is_quiet(tmp_path, caplog):
    @interactive()
    def fine(img):
        return img

    def fine_pipeline(img):
        out = fine(img)
        return out

    with caplog.at_level(logging.WARNING):
        HeadlessPipeline.from_function(fine_pipeline).snapshot(tmp_path / "ok.png", np.ones((4, 4)) * 0.5)
    assert "cannot be displayed" not in caplog.text and "misleadingly" not in caplog.text


@interactive(gain=(1.0, [0.0, 3.0]))
def checked_gain(img, gain=1.0):
    return np.repeat((img * gain)[..., None], 4, axis=-1)


def checked_gain_pipeline(img):
    out = checked_gain(img)
    return out


def test_sweep_logs_each_problem_once(tmp_path, caplog):
    pipe = HeadlessPipeline.from_function(checked_gain_pipeline)
    with caplog.at_level(logging.WARNING):
        pipe.sweep(tmp_path / "sweep.png", np.ones((4, 4)) * 0.2, gain=[0.5, 1.0, 2.0])
    assert caplog.text.count("output 'out' is drawn by snapshot but not by every GUI backend: RGBA array") == 1


def test_heatmap_style_silences_range_warnings():
    assert output_problem(np.full((4, 4), 500.0), {"colormap": "viridis", "vmin": 0, "vmax": 1000}) is None
    assert output_problem(np.full((4, 4), 500.0), {"title": "t"}) is not None


@interactive(scale=(1.0, [0.5, 2.0]))
def styled_heatmap(img, scale=1.0):
    from interactive_pipe import layout

    layout.style("heat", colormap="viridis", vmin=0, vmax=1000)
    return img * 1000 * scale


def heatmap_pipeline(img):
    heat = styled_heatmap(img)
    return heat


def test_snapshot_and_sweep_respect_layout_style(tmp_path, caplog):
    pipe = HeadlessPipeline.from_function(heatmap_pipeline)
    with caplog.at_level(logging.WARNING):
        pipe.snapshot(tmp_path / "heat.png", np.ones((4, 4)) * 0.5)
        pipe.sweep(tmp_path / "heat_sweep.png", np.ones((4, 4)) * 0.5, scale=[1.0, 2.0])
    assert "clipped" not in caplog.text
