"""snapshot / sweep / describe reachable from GUI-decorated pipelines, without a window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, interactive_pipeline, layout  # noqa: E402

SIZE = 16


@interactive(gain=(0.5, [0.0, 1.0]))
def gui_amplify(img, gain=0.5):
    layout.style("amplified", title=f"x{gain:.1f}")
    return img * gain


def gui_pipeline(img):
    amplified = gui_amplify(img)
    return img, amplified


def white():
    return np.ones((SIZE, SIZE, 3))


@pytest.fixture(params=["mpl", "qt"])
def gui_pipe(request, monkeypatch):
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)
    if request.param == "qt":
        pytest.importorskip("PyQt6")
    yield interactive_pipeline(gui=request.param)(gui_pipeline)
    if request.param == "mpl":
        import matplotlib.pyplot as plt

        plt.close("gui_pipeline")  # the mpl GUI creates its (never shown) figure at construction


def test_decorated_gui_function_exposes_the_loop(gui_pipe, tmp_path):
    assert callable(gui_pipe) and not hasattr(gui_pipe, "run")  # still the launcher function
    path = gui_pipe.snapshot(tmp_path / "gui.png", white(), gain=1.0)
    assert path.is_file()
    rgb = gui_pipe.sweep(None, gain=[0.0, 1.0], output="amplified", caption=False)
    left, right = rgb[:, : rgb.shape[1] // 2], rgb[:, rgb.shape[1] // 2 :]
    assert left.mean() < right.mean()
    data = gui_pipe.describe()
    assert [entry["name"] for entry in data["controls"]] == ["gain"]
    assert "gui_amplify(img) -> amplified" in gui_pipe.summary()


def test_gui_object_delegates_to_its_pipeline(gui_pipe):
    gui = gui_pipe.pipeline
    rgb = gui.snapshot(None, white())
    assert rgb.ndim == 3
    assert gui.describe() == gui_pipe.describe()
    assert gui.summary() == gui_pipe.summary()
    assert gui.sweep(None, gain=[0.2, 0.4]).ndim == 3
    # the GUI state is untouched: defaults are still in place
    assert gui.pipeline.parameters["gui_amplify"]["gain"] == 0.5
