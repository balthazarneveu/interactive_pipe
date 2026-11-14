"""What numpy users actually return is displayed the same way by every backend
(Qt, Dear PyGui, matplotlib, Gradio) and by the snapshot: ``prepare_display``
is the single conversion point. Arrays whose layout cannot be guessed give one
error naming the output and the filter, with the fix: raised by the snapshot,
shown in the cell by the GUI windows (which keep running and recover)."""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical.display import (  # noqa: E402
    CHECKER_DARK,
    CHECKER_LIGHT,
    DisplayError,
    checkerboard,
    prepare_display,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

H, W = 12, 16
GRADIENT = np.linspace(0.0, 1.0, H * W).reshape(H, W)
RGB = np.dstack([GRADIENT, 1.0 - GRADIENT, np.full((H, W), 0.25)])

# name -> (array, expected (H, W, 3) float image in [0, 1])
GOOD = {
    "float2d": (GRADIENT, np.dstack([GRADIENT] * 3)),
    "float_rgb": (RGB, RGB),
    "hw1": (GRADIENT[..., None], np.dstack([GRADIENT] * 3)),
    "bool": (GRADIENT > 0.5, np.dstack([(GRADIENT > 0.5).astype(float)] * 3)),
    "uint8": ((RGB * 255).round().astype(np.uint8), (RGB * 255).round() / 255),
    "uint16": ((GRADIENT * 65535).round().astype(np.uint16), np.dstack([(GRADIENT * 65535).round() / 65535] * 3)),
    "int_mask": ((GRADIENT > 0.5).astype(np.int64), np.dstack([(GRADIENT > 0.5).astype(float)] * 3)),
    "float32": (RGB.astype(np.float32), RGB),
    "rgba_opaque": (np.dstack([RGB, np.ones((H, W))]), RGB),
    "rgba_transparent": (np.dstack([RGB, np.zeros((H, W))]), np.dstack([checkerboard(H, W)] * 3)),
    "uint8_rgba": (
        np.dstack([(RGB * 255).round(), np.full((H, W), 255)]).astype(np.uint8),
        (RGB * 255).round() / 255,
    ),
}

# name -> (array, words of the message)
BAD = {
    "chw3": (np.stack([GRADIENT] * 3), ("channel-first", "np.moveaxis(img, 0, -1)")),
    "chw1": (GRADIENT[None], ("channel-first", "img[0]")),
    "batch": (np.stack([RGB, RGB]), ("4D array", "batch[0]")),
    "empty": (np.zeros((0, 4)), ("empty array", "None for an empty cell")),
    "object": (np.array([[1, "a"]], dtype=object), ("not numbers", "astype")),
    "complex": (GRADIENT * 1j, ("complex array", "np.abs")),
    "two_channels": (np.dstack([GRADIENT, GRADIENT]), ("2-channel", "(H, W, 4) RGBA")),
}

CURRENT = {"value": GRADIENT}


@interactive()
def produce(img):
    return CURRENT["value"]


def zoo_pipeline(img):
    out = produce(img)
    return out


def _expected(name):
    return np.clip(GOOD[name][1], 0.0, 1.0)


# ---------------------------------------------------------------------------
# what each backend shows, as an (H, W, 3) float array, or the cell's text
# ---------------------------------------------------------------------------


def _qt_shown(value):
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    CURRENT["value"] = value
    pipe = HeadlessPipeline.from_function(zoo_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="zoo")
    try:
        gui.pipeline.inputs = [GRADIENT]
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        if cell["kind"] == "text":
            return cell["image"].text()
        image = cell["image"].pixmap().toImage()
        return (
            np.array(
                [
                    [[image.pixelColor(x, y).red(), image.pixelColor(x, y).green(), image.pixelColor(x, y).blue()]]
                    for y in range(image.height())
                    for x in range(image.width())
                ],
                dtype=float,
            ).reshape(image.height(), image.width(), 3)
            / 255.0
        )
    finally:
        gui.close()


def _dpg_shown(value):
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    import dearpygui.dearpygui as dpg

    from interactive_pipe.graphical import dpg_backend

    CURRENT["value"] = value
    try:
        pipe = HeadlessPipeline.from_function(zoo_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="zoo")
        gui.pipeline.inputs = [GRADIENT]
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        if cell["kind"] == "text":
            return dpg.get_value(cell["content"])
        return np.asarray(cell["buffer"])[..., :3].astype(float)
    finally:
        dpg_backend.destroy_context()


def _mpl_shown(value):
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    CURRENT["value"] = value
    pipe = HeadlessPipeline.from_function(zoo_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name=f"zoo {id(value)}")
    try:
        gui.pipeline.inputs = [GRADIENT]
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        data = cell["data"]
        if cell["kind"] == "text":
            return data.get_text()
        # gray is drawn as gray: an RGB array (imshow applies no colormap to it)
        array = np.asarray(data.get_array(), dtype=float)
        assert array.ndim == 3, "a 2D array would be drawn with the default colormap (viridis)"
        return array
    finally:
        gui.close()


def _gradio_shown(value, monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    CURRENT["value"] = value
    pipe = HeadlessPipeline.from_function(zoo_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="zoo")
    gui(GRADIENT)
    converted = gui.window.run_fn(*gui.window.default_values)
    first = converted[0] if isinstance(converted, tuple) else converted
    if isinstance(first, str):
        return first
    if isinstance(first, dict):  # gradio update dict
        return first.get("value")
    return np.asarray(first, dtype=float) / 255.0


def _snapshot_shown(value):
    from interactive_pipe.headless.snapshot import result_grid

    CURRENT["value"] = value
    pipe = HeadlessPipeline.from_function(zoo_pipeline)
    result = pipe(GRADIENT)
    return np.clip(result_grid(pipe, result)[0][0].content, 0.0, 1.0)


BACKENDS = ["qt", "dpg", "mpl", "gradio", "snapshot"]


def _shown(backend, value, monkeypatch):
    if backend == "qt":
        return _qt_shown(value)
    if backend == "dpg":
        return _dpg_shown(value)
    if backend == "mpl":
        return _mpl_shown(value)
    if backend == "gradio":
        return _gradio_shown(value, monkeypatch)
    return _snapshot_shown(value)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("case", sorted(GOOD))
def test_every_backend_shows_the_same_image(backend, case, monkeypatch):
    shown = _shown(backend, GOOD[case][0], monkeypatch)
    assert isinstance(shown, np.ndarray), shown
    # uint8 backends (Qt, Gradio) quantise: within one level
    np.testing.assert_allclose(shown, _expected(case), atol=1.01 / 255)


@pytest.mark.parametrize("backend", ["qt", "dpg", "mpl", "gradio"])
@pytest.mark.parametrize("case", sorted(BAD))
def test_gui_shows_the_error_in_the_cell(backend, case, monkeypatch, caplog):
    value, words = BAD[case]
    with caplog.at_level(logging.ERROR):
        shown = _shown(backend, value, monkeypatch)
    assert isinstance(shown, str), type(shown)
    assert all(len(line) <= 60 for line in shown.splitlines())  # wrapped to fit a cell
    shown = " ".join(shown.split())
    assert "output 'out' (returned by filter 'produce') cannot be displayed" in shown
    for word in words:
        assert word in shown
    assert caplog.text.count("cannot be displayed") == 1


@pytest.mark.parametrize("case", sorted(BAD))
def test_snapshot_raises_the_same_error(case, tmp_path):
    value, words = BAD[case]
    CURRENT["value"] = value
    pipe = HeadlessPipeline.from_function(zoo_pipeline)
    with pytest.raises(DisplayError) as info:
        pipe.snapshot(tmp_path / "zoo.png", GRADIENT)
    message = str(info.value)
    assert "output 'out' (returned by filter 'produce') cannot be displayed" in message
    for word in words:
        assert word in message
    assert isinstance(info.value, ValueError)


def test_gui_window_recovers_on_the_next_valid_output():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    CURRENT["value"] = BAD["chw3"][0]
    pipe = HeadlessPipeline.from_function(zoo_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="zoo recovers")
    try:
        gui.pipeline.inputs = [GRADIENT]
        gui.window.refresh()
        assert gui.window.image_canvas[0][0]["kind"] == "text"
        CURRENT["value"] = RGB
        gui.window.refresh()
        cell = gui.window.image_canvas[0][0]
        assert cell["kind"] == "image"
        assert cell["image"].pixmap().width() == W
    finally:
        gui.close()


def test_rgba_is_composited_on_a_checkerboard():
    half = np.dstack([np.ones((64, 64, 3)), np.full((64, 64), 0.5)])
    shown = prepare_display(half)
    board = checkerboard(64, 64)
    assert set(np.unique(board)) == {np.float32(CHECKER_LIGHT), np.float32(CHECKER_DARK)}
    np.testing.assert_allclose(shown[..., 0], 0.5 + 0.5 * board, atol=1e-6)


def test_conversion_leaves_the_output_untouched():
    value = (RGB * 255).astype(np.uint8)
    value.setflags(write=False)
    shown = prepare_display(value)
    assert shown.dtype.kind == "f" and value.dtype == np.uint8
    float_rgb = RGB.copy()
    assert prepare_display(float_rgb) is float_rgb  # no copy for what backends draw natively


def test_one_dimensional_arrays_stay_signals():
    signal = np.linspace(0, 1, 10)
    assert prepare_display(signal) is signal
    assert prepare_display(np.arange(10)).dtype == np.arange(10).dtype
