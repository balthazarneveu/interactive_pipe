"""A filter written with pyplot (``plt.subplots()`` ... ``return fig``) works and leaks no figure."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, interactive_pipeline  # noqa: E402


@interactive(gain=(1.0, [0.0, 2.0]))
def pyplot_curve(x, gain=1.0):
    plt.figure(figsize=(3, 2))
    plt.plot(x * gain)
    return plt.gcf()


@interactive()
def pyplot_axes(x):
    _, axes = plt.subplots(1, 2)
    axes[0].plot(x)
    return axes[1], x.mean()  # an Axes and a value


@pytest.fixture(autouse=True)
def no_open_figure():
    plt.close("all")
    yield
    plt.close("all")


def test_headless_runs_leak_no_pyplot_figure():
    @interactive_pipeline(gui=None)
    def plots(x):
        fig = pyplot_curve(x)
        ax, mean = pyplot_axes(x)
        return fig, ax

    for gain in (0.5, 1.0, 1.5):
        fig, ax = plots(np.arange(5.0), gain=gain)
    assert plt.get_fignums() == []
    assert fig.axes[0].lines[0].get_ydata()[-1] == pytest.approx(6.0)  # the last run's figure, still usable
    fig.savefig(__import__("io").BytesIO(), format="png")


def test_gui_pipeline_snapshot_and_headless_leak_nothing():
    @interactive_pipeline(gui="qt")
    def plots(x):
        fig = pyplot_curve(x)
        return fig

    image = plots.snapshot(None, np.arange(5.0), gain=2.0)
    assert image.std() > 0
    plots.headless(np.arange(5.0))
    assert plt.get_fignums() == []


def test_direct_call_keeps_the_pyplot_figure():
    """A plain call is plain Python: the caller owns the figure (plt.show() shows it)."""
    pyplot_curve(np.arange(3.0))
    assert len(plt.get_fignums()) == 1
