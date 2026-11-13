"""INTERACTIVE_PIPE_SNAPSHOT: GUI-decorated pipelines render a PNG instead of a window."""

import matplotlib

matplotlib.use("Agg")

from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import interactive, interactive_pipeline  # noqa: E402
from interactive_pipe.cli import SNAPSHOT_ENV_VAR, snapshot_path_from_env, snapshot_requested  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

SIZE = 12


@interactive(gain=(0.5, [0.0, 1.0]))
def env_amplify(img, gain=0.5):
    return img * gain


def env_pipeline(img):
    amplified = env_amplify(img)
    return [amplified]


def white():
    return np.ones((SIZE, SIZE, 3))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)


def test_path_parsing(monkeypatch, tmp_path):
    assert snapshot_path_from_env("pipe") is None and not snapshot_requested()
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, "  ")
    assert snapshot_path_from_env("pipe") is None
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, "out/{name}_shot")
    assert snapshot_requested()
    assert snapshot_path_from_env("my pipe") == Path("out/my_pipe_shot.png")
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, "shots/")
    assert snapshot_path_from_env("pipe") == Path("shots/pipe.png")
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, str(tmp_path))
    assert snapshot_path_from_env("pipe") == tmp_path / "pipe.png"
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, "a.png")
    assert snapshot_path_from_env("pipe") == Path("a.png")


@pytest.mark.parametrize("gui", ["qt", "auto", "nb"])
def test_gui_call_writes_a_snapshot_and_returns_results(monkeypatch, tmp_path, capsys, gui):
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, str(tmp_path / "{name}.png"))
    launcher = interactive_pipeline(gui=gui)(env_pipeline)
    assert isinstance(launcher.pipeline, HeadlessPipeline)  # no GUI object was built
    with pytest.warns(UserWarning, match="not_a_parameter"):
        results = launcher(white(), gain=1.0, not_a_parameter=3)
    assert (tmp_path / "env_pipeline.png").is_file()
    assert isinstance(results, list) and len(results) == 1
    np.testing.assert_allclose(results[0], white())
    assert "env_pipeline.png" in capsys.readouterr().out
    # stateless like snapshot(): the default is back
    assert launcher.pipeline.parameters["env_amplify"]["gain"] == 0.5
    assert launcher.describe()["controls"][0]["name"] == "gain"


def test_headless_pipelines_are_unaffected(monkeypatch, tmp_path):
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, str(tmp_path / "x.png"))
    pipe = interactive_pipeline(gui=None)(env_pipeline)
    assert isinstance(pipe, HeadlessPipeline)
    pipe(white())
    assert not (tmp_path / "x.png").exists()


def test_filter_interact_writes_a_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv(SNAPSHOT_ENV_VAR, str(tmp_path) + "/")
    results = env_amplify.interact(white(), gui="qt")
    assert (tmp_path / "env_amplify.png").is_file()
    np.testing.assert_allclose(results[0], white() * 0.5)
