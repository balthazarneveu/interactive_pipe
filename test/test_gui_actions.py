"""Actions registry: default keys, menus and help all come from one table."""

import importlib

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.graphical.actions import DEFAULT_ACTIONS, MENU_GROUPS, Action
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.pipeline import HeadlessPipeline

BACKENDS = [
    ("interactive_pipe.graphical.qt_gui", "InteractivePipeQT"),
    ("interactive_pipe.graphical.dpg_gui", "InteractivePipeDPG"),
    ("interactive_pipe.graphical.mpl_gui", "InteractivePipeMatplotlib"),
]


def _backend_classes():
    classes = []
    for module_name, class_name in BACKENDS:
        try:
            module = importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            continue
        classes.append(getattr(module, class_name))
    return classes


@interactive(gain=(0.5, [0.0, 1.0]))
def actions_gain(img, gain=0.5):
    return img * gain


def actions_pipeline(img):
    out = actions_gain(img)
    return out


class DummyGUI(InteractivePipeGUI):
    """Backend-free GUI: binds the registry keys, prints nowhere."""

    def init_app(self, **kwargs):
        self.messages = []
        self.set_default_key_bindings()

    def print_message(self, message_list):
        self.messages.append(message_list)


def build_dummy(**kwargs):
    pipeline = HeadlessPipeline.from_function(actions_pipeline, inputs=["img"])
    gui = DummyGUI(pipeline=pipeline, name="dummy gui", **kwargs)
    gui.pipeline.inputs = [np.ones((2, 2))]
    return gui


def test_registry_keys_and_names_are_unique():
    keys = [action.key for action in DEFAULT_ACTIONS]
    names = [action.name for action in DEFAULT_ACTIONS]
    assert len(set(keys)) == len(keys)
    assert len(set(names)) == len(names)
    assert all(action.menu in MENU_GROUPS for action in DEFAULT_ACTIONS)


def test_action_rejects_unknown_menu():
    with pytest.raises(ValueError):
        Action("x", "X", "x", "Edit", "close", "nope")


@pytest.mark.parametrize("gui_class", _backend_classes(), ids=lambda cls: cls.__name__)
def test_every_backend_action_maps_to_a_method(gui_class):
    actions = gui_class.default_actions()
    assert actions
    for action in actions:
        assert callable(getattr(gui_class, action.method))
    expected = {a.name for a in DEFAULT_ACTIONS}
    if not hasattr(gui_class, "toggle_full_screen"):
        expected.discard("full_screen")
    if gui_class.__name__ != "InteractivePipeQT":
        # the zoomable image viewer only exists on Qt
        expected -= {"fit_view", "actual_size", "zoom_in", "zoom_out"}
    assert {a.name for a in actions} == expected


def test_base_class_has_no_full_screen_action():
    names = [action.name for action in InteractivePipeGUI.default_actions()]
    assert "full_screen" not in names
    menus = InteractivePipeGUI.actions_by_menu()
    assert list(menus) == ["File", "Pipeline", "Help"]  # empty View menu skipped
    assert [a.key for a in menus["File"]] == ["w", "e", "o", "q"]


def test_default_bindings_follow_registry_and_user_bindings_win():
    gui = build_dummy()
    assert set(gui.key_bindings) == {a.key for a in gui.default_actions()}
    assert gui.key_bindings["r"] == gui.reset_parameters

    def custom():
        """custom r"""

    gui.key_bindings = {"r": custom}
    gui.set_default_key_bindings()
    assert gui.key_bindings["r"] is custom
    assert gui.key_bindings["e"] == gui.save_parameters


def test_help_lists_every_action_label_and_context_events():
    gui = build_dummy()
    gui.bind_key_to_context("n", "noise_evt", "toggle noise")
    lines = gui.show_help()
    text = "\n".join(lines)
    for action in gui.default_actions():
        assert action.label in text
    assert "[n]    : toggle noise (event 'noise_evt')" in lines
    assert gui.messages[-1] == lines


def test_run_action_calls_the_method(monkeypatch):
    gui = build_dummy()
    calls = []
    monkeypatch.setattr(gui, "print_parameters", lambda: calls.append("print"))
    action = next(a for a in DEFAULT_ACTIONS if a.name == "print")
    gui.run_action(action)
    assert calls == ["print"]


def test_save_parameters_writes_the_chosen_file(tmp_path, monkeypatch):
    gui = build_dummy()
    target = tmp_path / "tuning.yaml"
    asked = {}

    def fake_ask(title, save, extensions, default_name):
        asked.update(title=title, save=save, extensions=extensions, default_name=default_name)
        return target

    monkeypatch.setattr(gui, "ask_path", fake_ask)
    gui.save_parameters()
    assert target.exists()
    assert Parameters.from_file(target).data["actions_gain"]["gain"] == pytest.approx(0.5)
    assert asked["save"] is True and asked["default_name"].startswith("dummy_gui_tuning")
    gui.save_parameters()  # overwriting a confirmed path is fine
    assert not (tmp_path / "tuning_1.yaml").exists()


def test_cancelled_dialogs_do_nothing(tmp_path, monkeypatch):
    gui = build_dummy()
    monkeypatch.setattr(gui, "ask_path", lambda *_a, **_k: None)
    monkeypatch.setattr(gui.pipeline, "export_tuning", lambda *_a, **_k: pytest.fail("export on cancel"))
    monkeypatch.setattr(gui.pipeline, "import_tuning", lambda *_a, **_k: pytest.fail("import on cancel"))
    monkeypatch.setattr(gui.pipeline, "save", lambda *_a, **_k: pytest.fail("save on cancel"))
    gui.save_parameters()
    gui.load_parameters()
    gui.save_images()


def test_terminal_ask_path_empty_input_cancels(monkeypatch):
    gui = build_dummy()
    monkeypatch.setattr("builtins.input", lambda *_a: "  ")
    assert gui.ask_path("Export tuning", True, [".yaml"], "x.yaml") is None
    monkeypatch.setattr("builtins.input", lambda *_a: "out/x.yaml")
    assert str(gui.ask_path("Export tuning", True, [".yaml"], "x.yaml")) == "out/x.yaml"


def test_load_parameters_round_trip_and_sync_hook(tmp_path, monkeypatch):
    gui = build_dummy()
    target = tmp_path / "tuning.json"
    Parameters({"actions_gain": {"gain": 0.2}}).save(target)
    synced = []
    monkeypatch.setattr(gui, "on_parameters_loaded", lambda: synced.append(True))
    monkeypatch.setattr(gui, "ask_path", lambda *_a, **_k: target)
    gui.load_parameters()
    assert gui.pipeline.parameters["actions_gain"]["gain"] == pytest.approx(0.2)
    assert synced == [True]


def test_save_images_uses_the_chosen_path(tmp_path, monkeypatch):
    gui = build_dummy()
    saved = {}
    monkeypatch.setattr(gui.pipeline, "save", lambda path, **_k: saved.setdefault("path", path))
    monkeypatch.setattr(gui, "ask_path", lambda *_a, **_k: tmp_path / "shot")
    gui.save_images()
    assert saved["path"] == tmp_path / "shot.png"  # default extension added
