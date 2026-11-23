"""The notebook backend shows its figure once, inside the widget."""

import pytest


def test_the_notebook_window_keeps_its_figure_out_of_pyplot(capsys):
    """A figure left open in pyplot is shown again by the inline backend at the end of the
    cell (a stale copy under the sliders), and plt.draw() creates an empty one when none is open."""
    pytest.importorskip("ipywidgets")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    from interactive_pipe import interactive, interactive_pipeline

    @interactive(gain=(1.0, [0.0, 2.0]))
    def amplify(img, gain=1.0):
        return img * gain

    @interactive_pipeline(gui="nb")
    def app(img):
        return amplify(img)

    plt.close("all")
    app(np.zeros((8, 8, 3)))
    window = app.pipeline.window
    window.need_redraw = True
    window._interact_fn(gain=0.5)  # a slider move
    assert plt.get_fignums() == []
