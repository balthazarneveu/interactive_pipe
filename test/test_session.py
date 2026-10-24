"""Session restore: the GUI remembers the slider values between launches.

Built on the matplotlib backend (Agg, never shown) plus one Qt offscreen
check that the new keyword arguments are not forwarded to the window.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import logging  # noqa: E402
from pathlib import Path  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.data_objects.parameters import Parameters  # noqa: E402
from interactive_pipe.graphical.actions import DEFAULT_ACTIONS  # noqa: E402
from interactive_pipe.graphical.gui import InteractivePipeGUI  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    import matplotlib.pyplot as plt

    plt.close("all")


INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(session_gain=(0.5, [0.0, 1.0]))
def session_adjust(img, session_gain=0.5):
    return img * session_gain


def session_pipeline(img):
    adjusted = session_adjust(img)
    return adjusted


def _make_gui(name="session test", **kwargs):
    pipeline = HeadlessPipeline.from_function(session_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipeline, name=name, **kwargs)
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def _gain(gui) -> float:
    return gui.pipeline.parameters["session_adjust"]["session_gain"]


def test_exit_saves_session_and_runs_user_custom_end(tmp_path):
    session = tmp_path / "sessions" / "demo.json"
    calls = []
    gui = _make_gui(restore_session=True, session_path=session, custom_end=lambda: calls.append("end"))
    assert gui.session_file == session
    gui.pipeline.parameters = {"session_adjust": {"session_gain": 0.2}}
    gui.custom_end()  # what every backend calls once its event loop exits
    assert calls == ["end"]
    assert Parameters.from_file(session).data["session_adjust"]["session_gain"] == pytest.approx(0.2)
    gui.close()


def test_exit_does_not_save_when_disabled(tmp_path):
    session = tmp_path / "demo.json"
    gui = _make_gui(session_path=session)
    gui.custom_end()
    assert not session.exists()
    gui.close()


def test_fresh_gui_restores_saved_values_and_syncs_widgets(tmp_path, monkeypatch):
    session = tmp_path / "demo.json"
    Parameters({"session_adjust": {"session_gain": 0.3}}).save(session)
    synced = []
    original = mpl_gui.InteractivePipeMatplotlib.on_parameters_loaded

    def spy(self):
        synced.append(_gain(self))
        original(self)

    monkeypatch.setattr(mpl_gui.InteractivePipeMatplotlib, "on_parameters_loaded", spy)
    monkeypatch.setattr(mpl_gui.plt, "show", lambda: None)
    pipeline = HeadlessPipeline.from_function(session_pipeline, inputs=["img"])
    gui = mpl_gui.InteractivePipeMatplotlib(
        pipeline=pipeline, name="session restore", restore_session=True, session_path=session
    )
    # values restored at construction, before the inputs exist
    assert _gain(gui) == pytest.approx(0.3)
    assert gui.window.ctrl["session_gain"].value == pytest.approx(0.3)
    assert synced == []  # widgets cannot refresh without inputs: synced when run() starts
    gui(INPUT_IMAGE.copy())
    assert synced == [pytest.approx(0.3)]
    assert gui.window.sliders_list["session_gain"].val == pytest.approx(0.3)
    gui(INPUT_IMAGE.copy())
    assert len(synced) == 1  # only once


def test_load_session_with_inputs_syncs_right_away(tmp_path, monkeypatch):
    session = tmp_path / "demo.json"
    gui = _make_gui(session_path=session)
    gui.window.refresh()
    loaded = []
    monkeypatch.setattr(gui, "on_parameters_loaded", lambda: loaded.append(_gain(gui)))
    assert gui.load_session() is False  # no file yet
    Parameters({"session_adjust": {"session_gain": 0.6}}).save(session)
    assert gui.load_session() is True
    assert loaded == [pytest.approx(0.6)]


def test_round_trip_between_two_launches(tmp_path):
    session = tmp_path / "demo.json"
    first = _make_gui(restore_session=True, session_path=session)
    first.pipeline.parameters = {"session_adjust": {"session_gain": 0.7}}
    first.custom_end()
    first.close()
    second = _make_gui(restore_session=True, session_path=session)
    assert _gain(second) == pytest.approx(0.7)
    second.close()


def test_missing_session_keeps_defaults(tmp_path, monkeypatch):
    loaded = []
    monkeypatch.setattr(mpl_gui.InteractivePipeMatplotlib, "on_parameters_loaded", lambda self: loaded.append(1))
    gui = _make_gui(restore_session=True, session_path=tmp_path / "nothing.json")
    assert _gain(gui) == pytest.approx(0.5)
    assert loaded == []
    gui.close()


@pytest.mark.parametrize(
    "content",
    ["{not json", '["a", "list"]', '{"session_adjust": {"session_gain": "not a number"}}'],
    ids=["unparsable", "not a dict", "bad value"],
)
def test_corrupt_session_warns_and_keeps_defaults(tmp_path, caplog, content):
    session = tmp_path / "demo.json"
    session.write_text(content)
    with caplog.at_level(logging.WARNING):
        gui = _make_gui(restore_session=True, session_path=session)
    assert any("Cannot restore the session" in record.getMessage() for record in caplog.records)
    assert _gain(gui) == pytest.approx(0.5)  # rejected values are rolled back
    assert gui.window.ctrl["session_gain"].value == pytest.approx(0.5)
    gui.close()


def test_stale_entries_are_ignored(tmp_path):
    session = tmp_path / "demo.json"
    Parameters(
        {"session_adjust": {"session_gain": 0.4, "removed_param": 1}, "removed_filter": {"x": 2}},
    ).save(session)
    gui = _make_gui(restore_session=True, session_path=session)
    assert gui.pipeline.parameters["session_adjust"] == {"session_gain": pytest.approx(0.4)}
    gui.close()


def test_clear_session_deletes_file_and_resets(tmp_path, monkeypatch):
    session = tmp_path / "demo.json"
    Parameters({"session_adjust": {"session_gain": 0.3}}).save(session)
    gui = _make_gui(restore_session=True, session_path=session)
    resets = []
    original = gui.reset_parameters
    monkeypatch.setattr(gui, "reset_parameters", lambda: (resets.append(1), original()))
    gui.clear_session()
    assert not session.exists()
    assert resets == [1]
    assert _gain(gui) == pytest.approx(0.5)
    gui.clear_session()  # no file left: still fine
    gui.close()


def test_clear_session_is_a_registry_action():
    action = next(a for a in DEFAULT_ACTIONS if a.name == "clear_session")
    assert action.method == "clear_session" and action.menu == "Pipeline"
    assert action in InteractivePipeGUI.default_actions()
    assert action in mpl_gui.InteractivePipeMatplotlib.default_actions()


def test_default_session_path_uses_name_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    gui = _make_gui(name="My demo: v2!", restore_session=True)
    extension = InteractivePipeGUI._file_extensions(Parameters)[-1]
    assert gui.session_file == tmp_path / ".interactive_pipe" / "sessions" / f"My_demo__v2_{extension}"
    gui.pipeline.parameters = {"session_adjust": {"session_gain": 0.9}}
    gui.custom_end()
    assert gui.session_file.is_file()
    gui.close()


def test_save_failure_only_warns(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("")
    gui = _make_gui(restore_session=True, session_path=blocker / "demo.json")  # parent is a file
    with caplog.at_level(logging.WARNING):
        assert gui.save_session() is None
    assert any("Cannot save the session" in record.getMessage() for record in caplog.records)
    gui.close()


def test_decorator_forwards_restore_session_to_the_gui(tmp_path, monkeypatch):
    from interactive_pipe import interactive_pipeline

    session = tmp_path / "demo.json"
    app = interactive_pipeline(gui="mpl", restore_session=True, session_path=session)(session_pipeline)
    assert app.pipeline.restore_session is True
    assert app.pipeline.session_file == session
    app.pipeline.close()


def test_qt_does_not_forward_session_kwargs_to_the_window(tmp_path):
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    session = tmp_path / "demo.json"
    Parameters({"session_adjust": {"session_gain": 0.25}}).save(session)
    pipeline = HeadlessPipeline.from_function(session_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="qt session", restore_session=True, session_path=session)
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    assert _gain(gui) == pytest.approx(0.25)
    assert gui.window.ctrl["session_gain"].value == pytest.approx(0.25)
    gui.pipeline.parameters = {"session_adjust": {"session_gain": 0.75}}
    gui.custom_end()
    assert Parameters.from_file(session).data["session_adjust"]["session_gain"] == pytest.approx(0.75)
    gui.window.close()
