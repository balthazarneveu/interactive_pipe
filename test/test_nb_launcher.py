"""`python script.py -b nb` from a terminal offers to write a notebook and open it in Jupyter."""

import json
import sys
from pathlib import Path

import pytest

from interactive_pipe.graphical import nb_launcher
from interactive_pipe.graphical.nb_launcher import (
    NOTEBOOK_MARKER,
    build_notebook,
    notebook_path_for,
    offer_notebook,
    script_path,
    write_notebook,
)


@pytest.fixture
def script(tmp_path, monkeypatch):
    path = tmp_path / "my demo.py"
    path.write_text("print('hello')\n")
    monkeypatch.setattr(sys, "argv", [str(path), "-b", "nb", "--image", "a b.png"])
    monkeypatch.chdir(tmp_path)
    return path


def test_script_path_ignores_non_scripts(tmp_path):
    assert script_path("-c") is None
    assert script_path("") is None
    assert script_path(str(tmp_path / "missing.py")) is None


def test_notebook_runs_the_script_with_the_same_arguments(script, tmp_path):
    notebook = build_notebook(script, ["-b", "nb", "--image", "a b.png"], tmp_path)
    code = notebook["cells"][1]["source"]
    assert f"sys.argv = {[str(script), '-b', 'nb', '--image', 'a b.png']!r}" in code
    assert f"os.chdir({str(tmp_path)!r})" in code
    assert "%run" not in code  # %run adds an empty figure after the script
    import interactive_pipe

    source_tree = str(Path(interactive_pipe.__file__).resolve().parent.parent)
    assert f"sys.path.insert(0, {source_tree!r})" in code  # tests run on a source tree, not site-packages
    assert code.splitlines()[-1].startswith("script_globals = runpy.run_path(")  # not printed
    assert notebook["metadata"][NOTEBOOK_MARKER] is True
    assert notebook["nbformat"] == 4


def test_a_foreign_notebook_is_never_overwritten(script):
    assert notebook_path_for(script) == script.with_suffix(".ipynb")
    script.with_suffix(".ipynb").write_text(json.dumps({"metadata": {}}))
    assert notebook_path_for(script).name == "my demo_interactive_pipe.ipynb"


def test_a_generated_notebook_is_regenerated_in_place(script):
    first = write_notebook(script, [])
    assert write_notebook(script, ["-b", "nb"]) == first
    assert "'-b', 'nb'" in json.loads(first.read_text())["cells"][1]["source"]


def test_no_offer_when_not_interactive(script):
    def ask(_):
        raise AssertionError("must not ask")

    assert offer_notebook(ask=ask, interactive=False) is False


def test_declining_keeps_going(script):
    assert offer_notebook(ask=lambda _: "n", interactive=True) is False
    assert not script.with_suffix(".ipynb").exists()


def test_accepting_writes_and_launches_jupyter(script, monkeypatch):
    launched = []
    monkeypatch.setattr(nb_launcher, "jupyter_command", lambda path: ["jupyter", "lab", str(path)])
    with pytest.raises(SystemExit) as exit_info:
        offer_notebook(ask=lambda _: "", launch=lambda command: launched.append(command) or 0, interactive=True)
    assert exit_info.value.code == 0
    assert launched == [["jupyter", "lab", str(script.with_suffix(".ipynb"))]]
    assert script.with_suffix(".ipynb").exists()


def test_accepting_without_jupyter_prints_how_to_open_it(script, monkeypatch, capsys):
    monkeypatch.setattr(nb_launcher, "jupyter_command", lambda path: None)
    with pytest.raises(SystemExit) as exit_info:
        offer_notebook(ask=lambda _: "y", interactive=True)
    assert exit_info.value.code == 1
    assert "-m jupyterlab" in capsys.readouterr().out
    assert script.with_suffix(".ipynb").exists()


def test_no_offer_inside_ipython(script, monkeypatch):
    monkeypatch.setattr(nb_launcher, "running_in_ipython", lambda: True)
    assert offer_notebook(ask=lambda _: "y", interactive=True) is False
