"""Metric readouts: ``layout.style("out", title=f"PSNR {psnr:.2f} dB")`` (and
``subtitle=``) follows each frame on every backend, in snapshots and in each
sweep cell; ``str`` outputs are written larger and wrapped to their cell."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, layout  # noqa: E402
from interactive_pipe.graphical.display import TEXT_FONT_PT, wrap_text  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

IMG = np.full((16, 16, 3), 0.25)


@interactive(gain=(1.0, [0.5, 3.0]))
def amplify(img, gain=1.0):
    layout.style("out", title=f"PSNR {10 * gain:.2f} dB", subtitle=f"gain {gain:.1f}")
    return np.clip(img * gain, 0.0, 1.0)


def readout_pipeline(img):
    out = amplify(img)
    return out


LONG = "precision 0.93 · recall 0.87 · F1 0.90 · " * 4


@interactive()
def metrics(img):
    return LONG


def text_pipeline(img):
    out = amplify(img)
    txt = metrics(img)
    return [out, txt]


def expected_title(gain):
    return f"PSNR {10 * gain:.2f} dB · gain {gain:.1f}"


def test_snapshot_titles_follow_the_parameters():
    from interactive_pipe.headless.snapshot import result_grid

    pipe = HeadlessPipeline.from_function(readout_pipeline)
    for gain in (0.5, 2.0):
        result = pipe(IMG, gain=gain)
        assert result_grid(pipe, result)[0][0].title == expected_title(gain)


def test_each_sweep_cell_shows_its_own_title(monkeypatch):
    from interactive_pipe.headless import explore

    seen = []
    original = explore.render_sweep

    def spy(panels, **kwargs):
        seen.extend(cell.title for row in panels for panel in row for cells in panel for cell in cells if cell)
        return original(panels, **kwargs)

    monkeypatch.setattr(explore, "render_sweep", spy)
    HeadlessPipeline.from_function(readout_pipeline).sweep(None, IMG, gain=[0.5, 1.0, 2.0])
    assert seen == [expected_title(g) for g in (0.5, 1.0, 2.0)]


def test_wrap_text():
    assert wrap_text("short", 1000, 12) == "short"
    wrapped = wrap_text(LONG, 300, 12)  # ~41 characters per line
    assert all(len(line) <= 41 for line in wrapped.splitlines())
    assert " ".join(wrapped.split()) == " ".join(LONG.split())
    assert wrap_text("a\nb", 1000, 12) == "a\nb"  # line breaks kept
    assert max(len(line) for line in wrap_text("x" * 200, 120, 12).splitlines()) <= 16  # no endless line


def test_snapshot_text_cell_is_wrapped_and_larger():
    from matplotlib.figure import Figure

    from interactive_pipe.headless.snapshot import SnapshotCell, draw_cell

    ax = Figure(figsize=(4.4, 2)).subplots()
    draw_cell(ax, SnapshotCell(name="txt", content=LONG, title=None), 4.4, 100, 2.0)
    (text,) = ax.texts
    assert text.get_fontsize() == TEXT_FONT_PT
    assert len(text.get_text().splitlines()) > 2


# ---------------------------------------------------------------------------
# GUI backends: the title follows each frame
# ---------------------------------------------------------------------------


def test_qt_title_and_text_cell():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(text_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="readouts")
    try:
        gui.pipeline.inputs = [IMG]
        for gain in (0.5, 2.0):
            gui.window.update_parameter("gain", gain)
            gui.window.refresh()
            assert gui.window.image_canvas[0][0]["title"].text() == expected_title(gain)
        text_view = gui.window.image_canvas[0][1]["image"]
        assert text_view.text() == LONG
        assert text_view.wordWrap()
        assert text_view.font().pointSizeF() == TEXT_FONT_PT
    finally:
        gui.close()


def test_mpl_title_and_text_cell():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(text_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="readouts mpl")
    try:
        gui.pipeline.inputs = [IMG]
        for gain in (0.5, 2.0):
            gui.window.update_parameter("gain", gain)
            assert gui.window.image_canvas[0][0]["ax"].get_title() == expected_title(gain)
        text = gui.window.image_canvas[0][1]["data"]
        assert text.get_fontsize() == TEXT_FONT_PT
        lines = text.get_text().splitlines()
        assert len(lines) > 2 and " ".join(" ".join(lines).split()) == " ".join(LONG.split())
    finally:
        gui.close()


def test_dpg_title_follows_the_frame():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(readout_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="readouts dpg")
        gui.pipeline.inputs = [IMG]
        for gain in (0.5, 2.0):
            gui.window.update_parameter("gain", gain)
            gui.window.refresh()
            assert gui.window.image_canvas[0][0]["full_title"] == expected_title(gain)
    finally:
        dpg_backend.destroy_context()


def test_gradio_label_follows_the_frame(monkeypatch):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(readout_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="readouts gradio")
    gui(IMG)
    window = gui.window
    gain_index = [ctrl.name for ctrl in window.ctrl.values()].index("gain")
    values = list(window.default_values)
    values[gain_index] = 0.5
    shown = window.run_fn(*values)
    assert isinstance(shown, dict) and shown["label"] == expected_title(0.5)
    assert isinstance(shown["value"], np.ndarray)
    shown = window.run_fn(*values)
    assert isinstance(shown, np.ndarray)  # unchanged title: a plain value
    values[gain_index] = 2.0
    shown = window.run_fn(*values)  # the label follows
    assert isinstance(shown, dict) and shown["label"] == expected_title(2.0)


def test_dpg_text_cell_uses_the_larger_font():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    import dearpygui.dearpygui as dpg

    from interactive_pipe.graphical import dpg_backend

    try:
        pipe = HeadlessPipeline.from_function(text_pipeline, inputs=["img"])
        gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="readouts dpg text")
        gui.pipeline.inputs = [IMG]
        gui.window.refresh()
        item = gui.window.image_canvas[0][1]["content"]
        assert dpg.get_value(item) == LONG
        assert dpg.get_item_configuration(item)["wrap"] > 0
        assert dpg.get_item_font(item) not in (None, 0)
    finally:
        dpg_backend.destroy_context()
