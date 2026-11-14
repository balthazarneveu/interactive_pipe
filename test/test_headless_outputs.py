"""Raw outputs of a GUI-decorated pipeline without opening a window: `.headless`."""

import numpy as np
import pytest

from interactive_pipe import interactive, interactive_pipeline
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def ho_amplify(img, gain=1.0):
    return img * gain


def ho_body(img):
    amplified = ho_amplify(img)
    return amplified


@pytest.fixture
def no_snapshot_env(monkeypatch):
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


def test_gui_decorated_pipeline_gives_its_outputs(no_snapshot_env):
    pytest.importorskip("matplotlib")
    demo = interactive_pipeline(gui="mpl")(ho_body)  # building the GUI object opens nothing
    assert isinstance(demo.headless, HeadlessPipeline)
    (out,) = demo.headless(np.ones(3), gain=2.0)
    np.testing.assert_array_equal(out, 2 * np.ones(3))
    # its own pipeline: the window's controls are untouched
    assert demo.pipeline.pipeline.controls[0].value == 1.0


def test_headless_pipeline_has_it_too(no_snapshot_env):
    pipe = interactive_pipeline(gui=None)(ho_body)
    assert pipe.headless is pipe
    (out,) = pipe.headless(np.ones(3), gain=3.0)
    assert out[0] == 3.0


def test_snapshot_launcher_has_it(monkeypatch, tmp_path, no_snapshot_env):
    monkeypatch.setenv("INTERACTIVE_PIPE_SNAPSHOT", str(tmp_path / "x.png"))
    demo = interactive_pipeline(gui="qt")(ho_body)
    (out,) = demo.headless(np.ones(2), gain=0.5)
    assert out[0] == 0.5


@pytest.mark.parametrize("guess", ["run", "outputs", "results", "compute"])
def test_wrong_guesses_point_to_headless(guess, no_snapshot_env):
    demo = interactive_pipeline(gui="mpl")(ho_body)
    with pytest.raises(AttributeError, match=rf"ho_body\.{guess}\(\.\.\.\) does not exist.*ho_body\.headless\(img"):
        getattr(demo, guess)(np.ones(3))
