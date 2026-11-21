"""Regression tests for defects found by the November 2026 code audit (headless, command line)."""

import os
import textwrap
import threading

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.agent.command_line import main
from interactive_pipe.agent.run_script import run_script
from interactive_pipe.cli import SNAPSHOT_ENV_VAR, get_snapshot_hook
from interactive_pipe.headless.pipeline import HeadlessPipeline

ONE_CALL = """
import numpy as np
from interactive_pipe import interactive, interactive_pipeline
{extra_import}

@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui="mpl")
def process(img):
    out = amplify(img)
    return img, out

{body}
"""

CALLED = 'res = process(np.full((8, 8), 0.4), gain=2.0)\nprint("AFTER", float(res[0][1].max()))\n'


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)


def _script(folder, body=CALLED, extra_import=""):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "script.py"
    path.write_text(ONE_CALL.format(body=body, extra_import=extra_import))
    return path


def test_sweep_gives_the_script_its_results(tmp_path, capsys):
    script = _script(tmp_path)
    code = main(["sweep", str(script), "--param", "gain=0.5,1", "-o", f"{tmp_path}/shots/"])
    out = capsys.readouterr().out
    assert code == 0
    assert "AFTER 0.8" in out  # the script indexes the results of its call: its own gain=2.0


def test_max_calls_lets_a_script_with_that_many_calls_finish(tmp_path, capsys):
    script = _script(tmp_path)
    run = run_script(str(script), output=f"{tmp_path}/shots/", max_calls=1)
    assert not run.stopped_early
    assert "AFTER" in capsys.readouterr().out  # the code after the call ran


def test_check_set_applies_to_an_uncalled_pipeline(tmp_path, capsys, monkeypatch):
    body = textwrap.dedent(
        """
        @interactive(level=(0.5, [0.0, 1.0]))
        def generate(level=0.5):
            return np.full((4, 4), level)


        @interactive_pipeline(gui="mpl")
        def uncalled():
            out = generate()
            return out
        """
    )
    monkeypatch.chdir(tmp_path)
    _script(tmp_path, body=body)
    assert main(["check", "script.py", "--set", "level=1"]) == 0
    assert "[1, 1]" in capsys.readouterr().out
    assert main(["check", "script.py", "--set", "nonsense=3"]) == 2


def test_packages_next_to_the_script_are_forgotten_between_runs(tmp_path, capsys):
    for name in ("a", "b"):
        package = tmp_path / name / "helpers"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "mod.py").write_text(f"NAME = {name!r}\n")
        script = _script(tmp_path / name, body='print("PACKAGE", NAME)\n', extra_import="from helpers.mod import NAME")
        run_script(str(script), output=f"{tmp_path}/shots/")
        assert f"PACKAGE {name}" in capsys.readouterr().out


def test_run_script_restores_everything_off_the_main_thread(tmp_path):
    script = _script(tmp_path)
    environment = {name: os.environ.get(name) for name in (SNAPSHOT_ENV_VAR, "QT_QPA_PLATFORM")}
    hook = get_snapshot_hook()
    errors = []

    def target():
        try:
            run_script(str(script), output=f"{tmp_path}/shots/")
        except Exception as exc:  # reported in the main thread
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    assert not errors  # signal handlers cannot be set there: skipped, not raised
    assert get_snapshot_hook() is hook
    assert {name: os.environ.get(name) for name in environment} == environment


def test_save_uses_the_control_values(tmp_path):
    @interactive(gain=(1.0, [0.0, 2.0]))
    def amplify_saved(img, gain=1.0):
        return img * gain

    def pipe(img):
        out = amplify_saved(img)
        return out

    pipeline = HeadlessPipeline.from_function(pipe)
    pipeline(np.full((4, 4, 3), 0.4))
    pipeline.controls[0].value = 0.5
    pipeline.save(tmp_path / "res.npy", data_wrapper_fn=_Saver)
    np.testing.assert_allclose(_Saver.last, 0.2)
    with pytest.raises(ValueError, match="path"):
        pipeline.save(None)


class _Saver:
    last = None

    def __init__(self, value):
        self.value = value

    def save(self, path):
        _Saver.last = self.value
