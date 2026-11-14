"""The `interactive-pipe` command: skill, doctor, snapshot, describe."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from interactive_pipe.agent import AGENTS_MD_BLOCK, SKILL_NAME, skill_path, skill_text
from interactive_pipe.agent.command_line import main
from interactive_pipe.agent.run_script import default_output, run_script
from interactive_pipe.cli import SNAPSHOT_ENV_VAR, get_snapshot_hook

SRC = Path(__file__).resolve().parent.parent / "src"

SCRIPT = """
import sys
import numpy as np
from interactive_pipe import interactive, interactive_pipeline
from helper_module import OFFSET  # sibling module: the script folder is on sys.path


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return np.clip(img * gain + OFFSET, 0, 1)


@interactive_pipeline(gui="mpl")
def first(img):
    out = amplify(img)
    return img, out


@interactive_pipeline(gui="mpl")
def second(img):
    out = amplify(img)
    return out


def main():
    img = np.linspace(0, 1, 32 * 48 * 3).reshape(32, 48, 3)
    first(img)
    second(img, gain=0.5)
    first(img)
    print("ARGS", sys.argv[1:])


if __name__ == "__main__":
    main()
"""


@pytest.fixture
def script(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "helper_module.py").write_text("OFFSET = 0.0\n")
    path = folder / "demo_script.py"
    path.write_text(SCRIPT)
    return path


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(SNAPSHOT_ENV_VAR, raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)


# --- skill ------------------------------------------------------------------------------------


def test_skill_prints_the_skill(capsys):
    assert main(["skill"]) == 0
    assert capsys.readouterr().out == skill_text()


def test_skill_path_and_agents_md(capsys):
    assert main(["skill", "--path"]) == 0
    assert capsys.readouterr().out.strip() == str(skill_path())
    assert main(["skill", "--agents-md"]) == 0
    assert capsys.readouterr().out == AGENTS_MD_BLOCK


def test_skill_install_project(tmp_path, capsys):
    assert main(["skill", "--install", "--project", str(tmp_path)]) == 0
    target = tmp_path / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
    assert str(target) in capsys.readouterr().out
    assert target.read_text() == skill_text()
    assert main(["skill", "--install", "--project", str(tmp_path)]) == 0  # identical: fine
    target.write_text("local edits")
    assert main(["skill", "--install", "--project", str(tmp_path)]) == 1
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "local edits"
    assert main(["skill", "--install", "--project", str(tmp_path), "--force"]) == 0
    assert target.read_text() == skill_text()


def test_skill_install_user_is_the_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert main(["skill", "--install"]) == 0
    assert (tmp_path / ".claude" / "skills" / SKILL_NAME / "SKILL.md").read_text() == skill_text()


def test_skill_options_need_install(capsys):
    assert main(["skill", "--force"]) == 2
    assert "--install" in capsys.readouterr().err


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    for command in ("skill", "doctor", "snapshot", "describe"):
        assert command in out


def test_version(capsys):
    import interactive_pipe

    assert main(["--version"]) == 0
    assert interactive_pipe.__version__ in capsys.readouterr().out


def test_script_args_only_for_scripts():
    with pytest.raises(SystemExit):
        main(["doctor", "--", "x"])


# --- doctor -----------------------------------------------------------------------------------


def test_doctor_text(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "interactive_pipe" in out and "Python" in out
    for gui in ("qt", "dpg", "mpl", "nb", "gradio"):
        assert f"  {gui} " in out
    assert 'gui="auto" picks:' in out


def test_doctor_json(capsys, monkeypatch):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "mpl")
    assert main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["backends"]["mpl"]["available"] is True
    assert report["auto"] == {"gui": "mpl", "reason": "INTERACTIVE_PIPE_GUI=mpl"}
    assert report["environment"] == {"INTERACTIVE_PIPE_GUI": "mpl"}
    for status in report["backends"].values():
        assert status["available"] or "pip install" in status["install"]


def test_doctor_advice_without_display(monkeypatch):
    from interactive_pipe.agent import doctor

    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "mpl")
    report = doctor.diagnose()
    assert report["display"]["available"] is False
    assert any("no display" in advice for advice in report["advice"])


def test_doctor_opens_no_window():
    from interactive_pipe.agent.doctor import diagnose

    diagnose()
    qt_widgets = sys.modules.get("PyQt6.QtWidgets")
    if qt_widgets is not None:
        assert qt_widgets.QApplication.instance() is None


# --- snapshot ---------------------------------------------------------------------------------


def test_snapshot_every_call_writes_its_own_png(script, tmp_path, capsys):
    out = tmp_path / "shots"
    assert main(["snapshot", str(script), "-o", f"{out}/", "--", "--flag", "value"]) == 0
    printed = capsys.readouterr().out
    expected = [out / "first.png", out / "second.png", out / "first_2.png"]
    for path in expected:
        assert path.stat().st_size > 1000
        assert str(path) in printed
    assert "ARGS ['--flag', 'value']" in printed
    assert "3 snapshot(s) written" in printed


def test_snapshot_to_a_file_and_pattern(script, tmp_path):
    run = run_script(str(script), output=str(tmp_path / "out.png"))
    assert run.written == [tmp_path / "out.png", tmp_path / "out_2.png", tmp_path / "out_3.png"]
    run = run_script(str(script), output=str(tmp_path / "p_{name}"))
    assert run.written == [tmp_path / "p_first.png", tmp_path / "p_second.png", tmp_path / "p_first_2.png"]


def test_snapshot_default_output_is_outside_the_project(script, tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    run = run_script(str(script))
    assert default_output(script) == tmp_path / "tmp" / "interactive_pipe_snapshots" / "demo_script"
    assert run.written[0] == default_output(script) / "first.png"
    assert run.written[0].is_file()


def test_snapshot_restores_the_process_state(script, tmp_path, monkeypatch):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "headless")  # would bypass the snapshots
    argv, path = list(sys.argv), list(sys.path)
    run = run_script(str(script), output=f"{tmp_path}/")
    assert len(run.written) == 3
    assert os.environ["INTERACTIVE_PIPE_GUI"] == "headless"
    assert SNAPSHOT_ENV_VAR not in os.environ
    assert get_snapshot_hook() is None
    assert sys.argv == argv and sys.path == path


def test_snapshot_max_calls_stops_a_loop(tmp_path):
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
                out = amplify(img)
                return out

            while True:  # e.g. a script iterating over a dataset
                try:
                    looped(np.zeros((8, 8)))
                except Exception:  # must not swallow the stop
                    pass
            """
        )
    )
    run = run_script(str(script), output=f"{tmp_path}/shots/", max_calls=2)
    assert run.stopped_early and run.exit_code == 0
    assert [path.name for path in run.written] == ["looped.png", "looped_2.png"]


def test_snapshot_reports_a_failing_script(tmp_path, capsys):
    script = tmp_path / "broken.py"
    script.write_text("raise RuntimeError('boom')\n")
    assert main(["snapshot", str(script), "-o", f"{tmp_path}/"]) == 1
    err = capsys.readouterr().err
    assert "RuntimeError: boom" in err
    assert "no GUI-decorated pipeline was called" in err


def test_snapshot_script_exit_code(tmp_path):
    script = tmp_path / "exits.py"
    script.write_text("import sys\nsys.exit(3)\n")
    assert run_script(str(script), output=f"{tmp_path}/").exit_code == 3


def test_snapshot_missing_script(capsys, tmp_path):
    assert main(["snapshot", str(tmp_path / "nope.py")]) == 2
    assert "script not found" in capsys.readouterr().err


def test_snapshot_invalid_max_calls(script, capsys):
    assert main(["snapshot", str(script), "--max-calls", "0"]) == 2


# --- describe ---------------------------------------------------------------------------------


def test_describe_text(script, capsys):
    assert main(["describe", str(script)]) == 0
    out = capsys.readouterr().out
    assert out.count("Pipeline 'first'") == 1  # called twice, described once
    assert "Pipeline 'second'" in out
    assert "gain" in out and "slider" in out
    assert "snapshot of" not in out  # no PNG noise


def test_describe_json(script, capsys):
    assert main(["describe", str(script), "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)  # the script's own prints went to stderr
    assert "ARGS" in captured.err
    assert [entry["name"] for entry in data] == ["first", "second"]
    assert data[0]["controls"][0]["name"] == "gain"


# --- python -m ----------------------------------------------------------------------------------


def _run_module(*args, extra_env=None):
    env = dict(os.environ, PYTHONPATH=str(SRC), MPLBACKEND="Agg", QT_QPA_PLATFORM="offscreen", **(extra_env or {}))
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=env, timeout=120, check=False)


def test_python_dash_m_help_imports_no_gui_toolkit():
    result = _run_module("-X", "importtime", "-m", "interactive_pipe", "--help")
    assert result.returncode == 0, result.stderr
    assert "snapshot" in result.stdout
    imported = {line.split("|")[-1].strip() for line in result.stderr.splitlines() if "|" in line}
    for toolkit in ("PyQt6", "PyQt5", "PySide6", "dearpygui", "gradio", "ipywidgets"):
        assert toolkit not in imported


def test_python_dash_m_skill():
    result = _run_module("-m", "interactive_pipe", "skill")
    assert result.returncode == 0, result.stderr
    assert result.stdout == skill_text()


# --- review fixes -------------------------------------------------------------------------------

FILTER_SCRIPT = """
import numpy as np
from interactive_pipe import interactive

@interactive(gain=(1.0, [0.0, 2.0]))
def amp(img, gain=1.0):
    return img * gain

for _ in range(2):
    amp.interact(np.linspace(0, 1, 16).reshape(4, 4))
"""


def test_relative_output_survives_a_chdir_in_the_script(tmp_path, monkeypatch):
    folder = tmp_path / "proj"
    folder.mkdir()
    script = folder / "moves.py"
    script.write_text("import os\nos.chdir(os.path.dirname(os.path.abspath(__file__)))\n" + SCRIPT)
    (folder / "helper_module.py").write_text("OFFSET = 0.0\n")
    monkeypatch.chdir(tmp_path)
    run = run_script(str(script), output="shots/")
    assert run.written[0] == tmp_path / "shots" / "first.png"
    assert all(path.is_file() for path in run.written)


def test_name_pattern_then_folder_rule_like_the_variable(script, tmp_path):
    run = run_script(str(script), output=f"{tmp_path}/{{name}}/")
    assert run.written[:2] == [tmp_path / "first" / "first.png", tmp_path / "second" / "second.png"]


def test_signal_handlers_are_restored(tmp_path):
    import signal

    script = tmp_path / "signals.py"
    script.write_text("import signal\nsignal.signal(signal.SIGINT, signal.SIG_DFL)  # what the Qt backend does\n")
    before = signal.getsignal(signal.SIGINT)
    run_script(str(script), output=f"{tmp_path}/")
    assert signal.getsignal(signal.SIGINT) is before


def test_sibling_modules_are_forgotten(tmp_path):
    outputs = []
    for who in ("a", "b"):
        folder = tmp_path / who
        folder.mkdir()
        (folder / "sibling_helpers.py").write_text(f"WHO = {who!r}\n")
        (folder / "main.py").write_text("import sibling_helpers\nprint('WHO', sibling_helpers.WHO)\n")
        run_script(str(folder / "main.py"), output=f"{tmp_path}/")
        outputs.append(sys.modules.get("sibling_helpers"))
    assert outputs == [None, None]


def test_filter_interact_goes_through_the_hook(tmp_path, capsys):
    script = tmp_path / "filter_only.py"
    script.write_text(FILTER_SCRIPT)
    assert main(["snapshot", str(script), "-o", f"{tmp_path}/shots/"]) == 0
    assert (tmp_path / "shots" / "amp.png").is_file() and (tmp_path / "shots" / "amp_2.png").is_file()
    assert "2 snapshot(s) written" in capsys.readouterr().out


def test_interact_decorator_renders_instead_of_opening_a_window(tmp_path):
    import interactive_pipe.helper.filter_decorator as filter_decorator

    original = filter_decorator.get_interactive_pipeline_class
    script = tmp_path / "one_shot.py"
    script.write_text(
        "import numpy as np\nfrom interactive_pipe import interact\n\n"
        "@interact(np.linspace(0, 1, 16).reshape(4, 4), gain=(1.0, [0.0, 2.0]))\n"
        "def scaled(img, gain=1.0):\n    return img * gain\n"
    )
    run = run_script(str(script), output=f"{tmp_path}/shots/")
    assert run.exit_code == 0, run.error
    assert [path.name for path in run.written] == ["scaled.png"]
    assert filter_decorator.get_interactive_pipeline_class is original
