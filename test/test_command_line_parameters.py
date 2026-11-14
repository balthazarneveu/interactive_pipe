"""`interactive-pipe snapshot --set`, `interactive-pipe sweep --param / --steps`, `--output`, `--pipeline`."""

import textwrap

import numpy as np
import pytest

from interactive_pipe.agent.command_line import main
from interactive_pipe.agent.parameters import (
    ParameterError,
    parse_assignments,
    parse_steps,
    parse_sweep_assignments,
    typed_axes,
    typed_settings,
)
from interactive_pipe.agent.run_script import CallOptions, run_script
from interactive_pipe.cli import SNAPSHOT_ENV_VAR

SCRIPT = """
import numpy as np
from interactive_pipe import interactive, interactive_pipeline, PointControl, RangeControl, TimeControl


@interactive(
    gain=(1.0, [0.0, 2.0]),
    mode=("dark", ["dark", "light"]),
    invert=False,
    seed=PointControl((0.5, 0.5)),
    band=RangeControl((0.2, 0.4), [0.0, 1.0]),
    t=TimeControl(),
    count=(3, [1, 10]),
)
def render(img, gain=1.0, mode="dark", invert=False, seed=(0.5, 0.5), band=(0.2, 0.4), t=0.0, count=3, scale=1.0):
    out = img * gain * scale * (0.5 if mode == "dark" else 1.0)
    out = 1 - out if invert else out
    out = out.copy()
    out[int(seed[1] * (out.shape[0] - 1)), :] = (t % 5) / 5
    return np.clip(out, 0, 1)


@interactive_pipeline(gui="mpl")
def pipe(img):
    out = render(img)
    return img, out


@interactive_pipeline(gui="mpl")
def other(img):
    return img


if __name__ == "__main__":
    img = np.full((16, 24, 3), 0.4)
    pipe(img, gain=0.5)
    other(img)
"""


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)


@pytest.fixture
def script(tmp_path):
    path = tmp_path / "params_script.py"
    path.write_text(SCRIPT)
    return path


def _out(run, name="out"):
    call = next(call for call in run.calls if call.name == "pipe")
    return dict(call.outputs)[name]


def _filter_values(run):
    call = next(call for call in run.calls if call.name == "pipe")
    return call.pipeline


# --- parsing ------------------------------------------------------------------------------------


def test_assignments_parsing():
    assert parse_assignments(["gain=2", "mode = dark", "gain=3"], "--set") == {"gain": "3", "mode": "dark"}
    assert parse_sweep_assignments(["gain=0.5,1", "gain=2"]) == {"gain": ["0.5,1", "2"]}
    assert parse_steps(["gain=5"]) == {"gain": 5}
    with pytest.raises(ParameterError, match="expected NAME=VALUE"):
        parse_assignments(["gain"], "--set")
    with pytest.raises(ParameterError, match="should be an integer"):
        parse_steps(["gain=many"])


@pytest.fixture
def headless(script):
    """The script's pipeline, built headless (same filters)."""
    namespace = {}
    exec(compile(SCRIPT.replace('gui="mpl"', "gui=None"), str(script), "exec"), namespace)
    return namespace["pipe"]


def test_values_are_typed_by_the_control(headless):
    typed = typed_settings(
        headless,
        {
            "gain": "2",
            "mode": "light",
            "invert": "yes",
            "seed": "0.2,0.4",
            "band": "(0.1, 0.3)",
            "t": "4",
            "count": "7",
            "scale": "0.5",
            "render.gain": "1.5",
        },
    )
    assert typed == {
        "gain": 2.0,
        "mode": "light",
        "invert": True,
        "seed": (0.2, 0.4),
        "band": (0.1, 0.3),
        "t": 4.0,
        "count": 7,
        "scale": 0.5,  # no control: the type of the default value
        "render.gain": 1.5,
    }
    assert isinstance(typed["count"], int) and isinstance(typed["gain"], float)


@pytest.mark.parametrize(
    "name, raw, message",
    [
        ("gain", "abc", r"'abc' is not a number \(control 'gain' is a slider \(float\) in \[0.0, 2.0\]\)"),
        ("count", "2.5", "'2.5' is not an integer"),
        ("invert", "maybe", "'maybe' is not true or false"),
        ("seed", "0.2", None),  # wrong length: rejected by the control when applied
        ("seed", "a,b", "comma-separated numbers, e.g. 0.2,0.4"),
    ],
)
def test_wrong_values_name_the_control(headless, name, raw, message):
    if message is None:
        assert typed_settings(headless, {name: raw}) == {name: (0.2,)}
        return
    with pytest.raises(ParameterError, match=message):
        typed_settings(headless, {name: raw})


def test_unknown_names_use_the_library_resolver(headless):
    with pytest.raises(ParameterError) as info:
        typed_settings(headless, {"gian": "2"})
    message = str(info.value)
    assert "'gian'" in message and "Available parameters: band, count, gain" in message
    assert "Did you mean 'gian' -> 'gain'?" in message


def test_swept_values(headless):
    axes = typed_axes(headless, {"gain": ["0.5,1", "2"], "seed": ["0.1,0.1;0.6,0.4"], "mode": ["dark,light"]})
    assert axes == {"gain": [0.5, 1.0, 2.0], "seed": [(0.1, 0.1), (0.6, 0.4)], "mode": ["dark", "light"]}
    with pytest.raises(ParameterError, match="no value to sweep"):
        typed_axes(headless, {"gain": [""]})


# --- snapshot --set -----------------------------------------------------------------------------


def test_set_overrides_the_script_values(script, tmp_path):
    run = run_script(str(script), output=f"{tmp_path}/", options=CallOptions(settings={"t": "4", "mode": "light"}))
    out = _out(run)
    # gain=0.5 from the script's call is kept, mode and t come from --set
    assert np.allclose(out[0, 0], 0.4 * 0.5)
    assert np.allclose(out[int(0.5 * 15), 0], 0.8)
    run = run_script(str(script), output=f"{tmp_path}/", options=CallOptions(settings={"gain": "2"}))
    assert np.allclose(_out(run)[0, 0], 0.4 * 2 * 0.5)  # --set wins over the script's gain=0.5


def test_set_does_not_leak_into_the_next_call(script, tmp_path):
    run = run_script(str(script), output=f"{tmp_path}/", options=CallOptions(settings={"gain": "2"}))
    pipeline = run.calls[0].pipeline
    control = next(ctrl for ctrl in pipeline.controls if ctrl.name == "gain")
    assert control.value == 1.0  # restored after the snapshot


def test_set_from_the_command_line(script, tmp_path, capsys):
    argv = ["snapshot", str(script), "-o", f"{tmp_path}/", "--set", "gain=2.0", "--set", "seed=0.2,0.4"]
    assert main(argv) == 0
    assert (tmp_path / "pipe.png").is_file() and (tmp_path / "other.png").is_file()
    printed = capsys.readouterr().out
    assert "2 snapshot(s) written" in printed


@pytest.mark.parametrize(
    "setting, message",
    [
        ("gian=2", "Did you mean 'gian' -> 'gain'?"),
        ("mode=shiny", "'shiny' is not one of the choices ['dark', 'light']"),
        ("gain=abc", "'abc' is not a number"),
        ("seed=0.2", "seed"),
    ],
)
def test_bad_set_fails_with_exit_code_2_and_writes_nothing(script, tmp_path, capsys, setting, message):
    assert main(["snapshot", str(script), "-o", f"{tmp_path}/", "--set", setting]) == 2
    captured = capsys.readouterr()
    assert message in captured.err
    assert "snapshot(s) written" not in captured.out
    assert not list(tmp_path.glob("*.png"))


def test_out_of_range_set_value_is_clamped_with_a_warning(script, tmp_path, caplog):
    with pytest.warns(UserWarning, match="gain=7 is outside the range of control 'gain'"):
        run = run_script(str(script), output=f"{tmp_path}/", options=CallOptions(settings={"gain": "7"}))
    assert np.allclose(_out(run)[0, 0], 0.4 * 2 * 0.5)
    assert "outside its range" not in caplog.text  # warned once, not again by the control


def test_output_selection_and_one_pipeline(script, tmp_path):
    argv = ["snapshot", str(script), "-o", f"{tmp_path}/", "--output", "out", "--pipeline", "pipe"]
    assert main(argv) == 0
    assert [path.name for path in tmp_path.glob("*.png")] == ["pipe.png"]
    assert main(["snapshot", str(script), "-o", f"{tmp_path}/x/", "--output", "nope"]) == 2


def test_unknown_pipeline_lists_the_called_ones(script, tmp_path, capsys):
    assert main(["snapshot", str(script), "-o", f"{tmp_path}/", "--pipeline", "pipee"]) == 2
    assert "the script called other, pipe, not --pipeline" in capsys.readouterr().err


# --- sweep ----------------------------------------------------------------------------------------


def test_sweep_an_unmodified_script(script, tmp_path, capsys):
    argv = ["sweep", str(script), "-o", f"{tmp_path}/", "--pipeline", "pipe", "--param", "gain=0.5,1,2"]
    assert main([*argv, "--param", "mode=dark,light", "--output", "out"]) == 0
    sheet = tmp_path / "pipe_sweep.png"
    assert sheet.stat().st_size > 1000
    assert "1 sweep(s) written" in capsys.readouterr().out


def test_sweep_matches_the_python_sweep(script, headless, tmp_path):
    from PIL import Image as PILImage

    cli = tmp_path / "cli.png"
    argv = ["sweep", str(script), "-o", str(cli), "--pipeline", "pipe", "--param", "seed=0.1,0.1;0.6,0.9"]
    assert main([*argv, "--set", "t=2", "--output", "out"]) == 0
    python = headless.sweep(
        None,
        np.full((16, 24, 3), 0.4),
        seed=[(0.1, 0.1), (0.6, 0.9)],
        output="out",
        params={"t": 2, "render.gain": 0.5},
    )
    assert np.array_equal(np.asarray(PILImage.open(cli).convert("RGB")), python)


def test_sweep_steps(script, tmp_path):
    argv = ["sweep", str(script), "-o", f"{tmp_path}/s.png", "--pipeline", "pipe", "--steps", "count=3"]
    assert main(argv) == 0
    assert (tmp_path / "s.png").is_file()


def test_sweep_needs_something_to_sweep(script, capsys):
    assert main(["sweep", str(script)]) == 2
    assert "nothing to sweep" in capsys.readouterr().err


def test_sweep_unknown_name(script, tmp_path, capsys):
    argv = ["sweep", str(script), "-o", f"{tmp_path}/", "--pipeline", "pipe", "--param", "gian=1,2"]
    assert main(argv) == 2
    assert "Did you mean 'gian' -> 'gain'?" in capsys.readouterr().err


def test_sweep_too_many_axes(script, tmp_path, capsys):
    argv = ["sweep", str(script), "-o", f"{tmp_path}/", "--pipeline", "pipe"]
    argv += ["--param", "gain=1,2", "--param", "mode=dark,light", "--param", "count=1,2"]
    assert main(argv) == 2
    assert "one or two parameters at a time" in capsys.readouterr().err


def test_sweep_script_with_a_name_pattern(tmp_path):
    script = tmp_path / "loop.py"
    script.write_text(
        textwrap.dedent(
            """
            import numpy as np
            from interactive_pipe import interactive, interactive_pipeline

            @interactive(gain=(1.0, [0.0, 2.0]))
            def amplify(img, gain=1.0):
                return img * gain

            @interactive_pipeline(gui="mpl")
            def looped(img):
                return amplify(img)

            for _ in range(2):
                looped(np.zeros((4, 4)))
            """
        )
    )
    run = run_script(
        str(script), output=f"{tmp_path}/{{name}}.png", options=CallOptions(mode="sweep", axes={"gain": ["1,2"]})
    )
    assert [path.name for path in run.written] == ["looped_sweep.png", "looped_sweep_2.png"]
