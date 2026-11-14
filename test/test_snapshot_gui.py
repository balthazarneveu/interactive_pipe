"""snapshot / sweep / describe reachable from GUI-decorated pipelines, without a window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, interactive_pipeline, layout  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

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
    assert callable(gui_pipe) and not isinstance(gui_pipe, HeadlessPipeline)  # still the launcher function
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


QT_SCRIPT = """
import numpy as np
from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(0.5, [0.0, 1.0]))
def amp(img, gain=0.5):
    return img * gain


@interactive_pipeline(gui="qt")
def demo(img):
    out = amp(img)
    return img, out


demo(np.ones((8, 8, 3)) * 0.5)
from interactive_pipe.graphical.qt_backend import PYQTVERSION
if PYQTVERSION == 6:
    from PyQt6.QtCore import qWarning
    qWarning("another qt message")
"""


def test_offscreen_qt_snapshot_prints_no_plugin_notice(tmp_path):
    import subprocess
    import sys

    pytest.importorskip("PyQt6")
    script = tmp_path / "qt_script.py"
    script.write_text(QT_SCRIPT)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "INTERACTIVE_PIPE_SNAPSHOT": str(tmp_path / "shot.png")}
    done = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "shot.png").exists()
    assert "propagateSizeHints" not in done.stderr
    assert "another qt message" in done.stderr  # other Qt messages still reach stderr
