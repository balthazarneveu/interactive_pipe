"""`interactive-pipe check SCRIPT.py`: one short, stable report for coding agents."""

import json
import textwrap

import pytest

from interactive_pipe.agent.check import describe_value
from interactive_pipe.agent.command_line import main
from interactive_pipe.cli import SNAPSHOT_ENV_VAR

HEADER = """
import numpy as np
from interactive_pipe import interactive, interactive_pipeline
"""

GOOD = (
    HEADER
    + """

@interactive(gain=(1.0, [0.0, 2.0]), mode=("dark", ["dark", "light"]))
def amplify(img, gain=1.0, mode="dark"):
    return np.clip(img * gain, 0, 1)


@interactive_pipeline(gui="mpl")
def process(img):
    out = amplify(img)
    return img, out


if __name__ == "__main__":
    process(np.full((8, 12, 3), 0.25), gain=2.0)
"""
)

SYNTAX_ERROR = (
    HEADER
    + """

@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive_pipeline(gui="mpl")
def process(img):
    out = amplify(img)
    if out is None:
        return img
    return out


if __name__ == "__main__":
    process(np.zeros((8, 8)))
"""
)

FILTER_RAISES = (
    HEADER
    + """

@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * undefined_name


@interactive_pipeline(gui="mpl")
def process(img):
    out = amplify(img)
    return out


if __name__ == "__main__":
    process(np.zeros((8, 8)))
"""
)

MISLEADING = (
    HEADER
    + """

@interactive()
def to_counts(img):
    return (img * 255).astype(np.int64)


@interactive_pipeline(gui="mpl")
def process(img):
    counts = to_counts(img)
    return img, counts


if __name__ == "__main__":
    process(np.full((8, 8, 3), 0.5))
"""
)

ONLY_DEFINED = (
    HEADER
    + """

@interactive(size=(8, [2, 16]))
def make(size=8):
    return np.ones((size, size))


@interactive()
def blur(img):
    return img


@interactive_pipeline(gui=None)
def generator():
    img = make()
    return img


@interactive_pipeline(gui="mpl")
def needs_input(img):
    out = blur(img)
    return out
"""
)


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)


def _check(tmp_path, monkeypatch, capsys, source, *extra):
    monkeypatch.chdir(tmp_path)  # paths in the report are relative to the working directory
    (tmp_path / "script.py").write_text(source)
    code = main(["check", "script.py", *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_good_script(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, GOOD)
    assert code == 0
    assert out.splitlines() == [
        "check script.py: OK - 1 pipeline, 0 errors, 0 warnings",
        "pipeline 'process' (inputs: img)",
        "  controls: gain = 1 slider(float) in [0, 2]",
        "            mode = dark dropdown in {dark, light}",
        "  outputs : img  (8, 12, 3) float64 [0.25, 0.25]",
        "            out  (8, 12, 3) float64 [0.5, 0.5]",  # run with the script's gain=2.0
    ]


def test_output_is_stable(tmp_path, monkeypatch, capsys):
    first = _check(tmp_path, monkeypatch, capsys, GOOD)
    assert _check(tmp_path, monkeypatch, capsys, GOOD) == first


def test_pipeline_syntax_error(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, SYNTAX_ERROR)
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "check script.py: FAILED - 0 pipelines, 1 error, 0 warnings"
    assert lines[1].startswith(
        "error: script.py:14: PipelineSyntaxError in pipeline 'process': `if` statements are not supported"
    )
    assert lines[2] == "    if out is None:"
    assert lines[3].startswith("    Hint: move the condition inside a filter")


def test_filter_raises(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, FILTER_RAISES)
    assert code == 1
    assert out.splitlines() == [
        "check script.py: FAILED - 1 pipeline, 1 error, 0 warnings",
        "pipeline 'process' (inputs: img)",
        "  controls: gain = 1 slider(float) in [0, 2]",
        "  outputs : not run (error)",
        "error: script.py:8: pipeline 'process': filter 'amplify' raised NameError: "
        "name 'undefined_name' is not defined",
    ]


def test_misleading_output(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, MISLEADING)
    assert code == 0  # warnings do not fail
    lines = out.splitlines()
    assert lines[0] == "check script.py: OK - 1 pipeline, 0 errors, 1 warning"
    assert "            counts  (8, 8, 3) int64 [127, 127]" in lines
    assert lines[-1].startswith("warning: output 'counts' is displayed misleadingly: int64 image")
    assert "Fix:" in lines[-1]


def test_pipelines_only_defined(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, ONLY_DEFINED)
    assert code == 0
    assert "pipeline 'generator' (inputs: none)" in out
    assert "  outputs : img  (8, 8) float64 [1, 1]" in out  # run once with its defaults
    assert "outputs : not run (built but not called by the script (needs inputs: img))" in out


def test_no_pipeline_is_an_error(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, "x = 1\n")
    assert code == 1
    assert "error: the script neither called nor defined a pipeline" in out


def test_script_error_outside_a_pipeline(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, HEADER + "\n\ndata = np.load('missing.npy')\n")
    assert code == 1
    assert "error: script.py:6: FileNotFoundError:" in out


def test_set_and_clamp_warning(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, GOOD, "--set", "gain=5")
    assert code == 0
    assert "            out  (8, 12, 3) float64 [0.5, 0.5]" in out  # clamped to 2
    assert "warning: --set(): gain=5 is outside the range of control 'gain' [0.0, 2.0], clamped to 2" in out
    assert out.count("outside") == 1  # once (the control's own log line is not repeated)


def test_bad_set_is_a_usage_error(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, GOOD, "--set", "gian=5")
    assert code == 2
    assert "Did you mean 'gian' -> 'gain'?" in out


def test_script_prints_go_to_stderr(tmp_path, monkeypatch, capsys):
    code, out, err = _check(tmp_path, monkeypatch, capsys, GOOD + "\nprint('hello from the script')\n")
    assert code == 0
    assert "hello" not in out and "hello from the script" in err


def test_json(tmp_path, monkeypatch, capsys):
    code, out, _ = _check(tmp_path, monkeypatch, capsys, MISLEADING, "--json")
    assert code == 0
    report = json.loads(out)
    assert report["ok"] is True and report["exit_code"] == 0 and report["errors"] == []
    (pipeline,) = report["pipelines"]
    assert pipeline["name"] == "process" and pipeline["inputs"] == ["img"] and pipeline["status"] == "ok"
    assert pipeline["outputs"][1] == {
        "name": "counts",
        "type": "array",
        "shape": [8, 8, 3],
        "dtype": "int64",
        "min": 127,
        "max": 127,
    }
    assert len(report["warnings"]) == 1
    code, out, _ = _check(tmp_path, monkeypatch, capsys, FILTER_RAISES, "--json")
    error = json.loads(out)["errors"][0]
    assert code == 1
    assert error == {
        "pipeline": "process",
        "type": "FilterError",
        "message": "filter 'amplify' raised NameError: name 'undefined_name' is not defined",
        "file": "script.py",
        "line": 8,
    }


def test_describe_value():
    import numpy as np

    assert describe_value(np.array([np.nan, 1.0, 2.0])) == {
        "type": "array",
        "shape": [3],
        "dtype": "float64",
        "min": 1.0,
        "max": 2.0,
        "non_finite": 1,
    }
    assert describe_value(np.zeros((2, 2), bool))["max"] is False
    assert describe_value("abc") == {"type": "str", "length": 3}
    assert describe_value(None) == {"type": "None"}
    assert describe_value(np.zeros((0, 3))) == {"type": "array", "shape": [0, 3], "dtype": "float64"}


def test_undisplayable_output_is_an_error(tmp_path, monkeypatch, capsys):
    source = HEADER + textwrap.dedent(
        """
        @interactive()
        def channel_first(img):
            return np.zeros((3, 8, 8))


        @interactive_pipeline(gui="mpl")
        def process(img):
            out = channel_first(img)
            return out


        process(np.zeros((8, 8, 3)))
        """
    )
    code, out, _ = _check(tmp_path, monkeypatch, capsys, source)
    assert code == 1
    assert "DisplayError" in out and "np.moveaxis(img, 0, -1)" in out
