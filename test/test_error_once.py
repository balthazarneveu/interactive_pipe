"""A failing filter is reported once: raised only by headless calls, snapshot,
sweep and the command line; printed once by the excepthook of a script that
does not catch it; printed once by a GUI window, which keeps running, shows
the error and recovers on the next valid value."""

import os
import subprocess
import sys
import textwrap

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.core.engine import FilterError  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

MESSAGE = "the sensor overheated"
IMG = np.full((4, 6, 3), 0.5)


@interactive(overheat=(False,))
def fragile(img, overheat=False):
    if overheat:
        raise ValueError(MESSAGE)
    return img


def fragile_pipeline(img):
    out = fragile(img)
    return out


@pytest.fixture(autouse=True)
def _reset_control():
    yield
    HeadlessPipeline.from_function(fragile_pipeline)(IMG, overheat=False)  # controls are shared


def _count(text):
    return text.count(MESSAGE)


@pytest.mark.parametrize("call", ["call", "snapshot", "sweep"])
def test_headless_calls_raise_only(call, capsys, tmp_path):
    pipe = HeadlessPipeline.from_function(fragile_pipeline)
    with pytest.raises(FilterError) as info:
        if call == "call":
            pipe(IMG, overheat=True)
        elif call == "snapshot":
            pipe.snapshot(tmp_path / "s.png", IMG, overheat=True)
        else:
            pipe.sweep(tmp_path / "s.png", IMG, overheat=[False, True])
    assert MESSAGE in str(info.value)
    printed = capsys.readouterr()
    assert _count(printed.out + printed.err) == 0
    assert "PIPELINE ERROR" not in printed.out + printed.err


SCRIPT = textwrap.dedent(
    f"""
    import numpy as np
    from interactive_pipe import interactive
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    REASON = {MESSAGE!r}

    @interactive()
    def fragile(img):
        raise ValueError(REASON)

    def fragile_pipeline(img):
        out = fragile(img)
        return out

    HeadlessPipeline.from_function(fragile_pipeline)(np.zeros((2, 2)))
    """
)


def _run_script(tmp_path, env_extra=None):
    path = tmp_path / "uncaught.py"
    path.write_text(SCRIPT)
    env = {**os.environ, **(env_extra or {})}
    if not env_extra:
        env.pop("INTERACTIVE_PIPE_DEBUG", None)
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env, timeout=120)


def test_uncaught_in_a_script_prints_once(tmp_path):
    done = _run_script(tmp_path)
    assert done.returncode == 1
    assert _count(done.stdout + done.stderr) == 1, done.stderr
    assert "PIPELINE ERROR" in done.stderr
    assert "INTERACTIVE_PIPE_DEBUG=1" in done.stderr
    assert "Traceback (most recent call last)" not in done.stderr


def test_uncaught_with_debug_prints_the_full_traceback_once(tmp_path):
    done = _run_script(tmp_path, {"INTERACTIVE_PIPE_DEBUG": "1"})
    assert "Traceback (most recent call last)" in done.stderr
    assert _count(done.stdout + done.stderr) == 1, done.stderr


def test_command_line_reports_once(tmp_path, capsys, monkeypatch):
    from interactive_pipe.agent.command_line import main

    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)
    path = tmp_path / "uncaught.py"
    path.write_text(SCRIPT)
    main(["snapshot", str(path), "-o", f"{tmp_path}/shots/"])
    printed = capsys.readouterr()
    assert _count(printed.out + printed.err) == 1, printed.err


# --- GUI windows: the window survives, shows the error, prints it once, recovers ---------------


def _qt_window():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(fragile_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="error once qt")
    gui.pipeline.inputs = [IMG]
    return gui, gui.close


def _dpg_window():
    dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")
    from interactive_pipe.graphical import dpg_backend

    pipe = HeadlessPipeline.from_function(fragile_pipeline, inputs=["img"])
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipe, name="error once dpg")
    gui.pipeline.inputs = [IMG]
    return gui, dpg_backend.destroy_context


def _mpl_window():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(fragile_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="error once mpl")
    gui.pipeline.inputs = [IMG]
    return gui, gui.close


@pytest.mark.parametrize("make", [_qt_window, _dpg_window, _mpl_window], ids=["qt", "dpg", "mpl"])
def test_gui_window_survives_shows_and_prints_once(make, capsys):
    gui, close = make()
    window = gui.window
    try:
        window.refresh()
        assert window.last_error is None
        window.ctrl["overheat"].update(True)
        for _ in range(3):  # three slider moves on a failing value
            window.refresh()  # must not raise
        assert isinstance(window.last_error, FilterError)
        printed = capsys.readouterr()
        assert _count(printed.out + printed.err) == 1
        window.ctrl["overheat"].update(False)
        window.refresh()
        assert window.last_error is None  # recovered
        window.ctrl["overheat"].update(True)
        window.refresh()
        printed = capsys.readouterr()
        assert _count(printed.out + printed.err) == 1  # failing again after a success: printed again
    finally:
        window.ctrl["overheat"].update(False)
        close()


def test_gradio_shows_the_error_in_the_page_and_recovers(monkeypatch, capsys):
    gr = pytest.importorskip("gradio")
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio

    monkeypatch.setattr(gr.blocks.Blocks, "launch", lambda self, *a, **k: None, raising=True)
    pipe = HeadlessPipeline.from_function(fragile_pipeline)
    gui = InteractivePipeGradio(pipeline=pipe, name="error once gradio")
    gui(IMG)
    window = gui.window
    index = window.ctrl_keys_with_widgets.index("overheat")
    values = list(window.default_values)
    capsys.readouterr()
    values[index] = True
    for _ in range(2):
        with pytest.raises(gr.Error) as info:
            window.run_fn(*values)
        assert MESSAGE in str(info.value)
    printed = capsys.readouterr()
    assert _count(printed.out + printed.err) == 1
    values[index] = False
    converted = window.run_fn(*values)
    assert np.asarray(converted).dtype == np.uint8
