import argparse

import pytest

import interactive_pipe.helper.pipeline_decorator as pipeline_decorator
from interactive_pipe import Backend, interactive, interactive_pipeline
from interactive_pipe.cli import (
    add_gui_arguments,
    gui_from_env,
    gui_kwargs_from_args,
    parse_gui_args,
    parse_size,
    resolve_gui,
    size_from_env,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper import _private
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)
    monkeypatch.delenv("INTERACTIVE_PIPE_SIZE", raising=False)


# --- parse_size ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("fullscreen", "fullscreen"),
        ("full", "fullscreen"),
        ("FullScreen", "fullscreen"),
        ("maximized", "maximized"),
        ("max", "maximized"),
        ("1280x800", (1280, 800)),
        (" 640X480 ", (640, 480)),
    ],
)
def test_parse_size_valid(value, expected):
    assert parse_size(value) == expected


@pytest.mark.parametrize("value", ["", "big", "640", "640x", "x480", "0x480", "-1x2", "640x480x3", "6.5x4"])
def test_parse_size_invalid(value):
    with pytest.raises(ValueError):
        parse_size(value)


# --- argument parsing ---------------------------------------------------------


def test_no_arguments_gives_empty_kwargs():
    args, kwargs = parse_gui_args([])
    assert kwargs == {}
    assert args.gui is None


@pytest.mark.parametrize("gui", ["auto", "qt", "dpg", "mpl", "nb", "gradio"])
def test_gui_flag(gui):
    _, kwargs = parse_gui_args(["--gui", gui])
    assert kwargs == {"gui": gui}


def test_gui_headless_maps_to_none():
    _, kwargs = parse_gui_args(["--gui", "headless"])
    assert kwargs == {"gui": None}


def test_invalid_gui_exits():
    with pytest.raises(SystemExit):
        parse_gui_args(["--gui", "tk"])


def test_fullscreen_flag():
    assert parse_gui_args(["--fullscreen"])[1] == {"size": "fullscreen"}


def test_maximized_flag():
    assert parse_gui_args(["--maximized"])[1] == {"size": "maximized"}


def test_size_flag():
    assert parse_gui_args(["--size", "640x480"])[1] == {"size": (640, 480)}


@pytest.mark.parametrize("value", ["640", "huge", "fullscreen"])
def test_invalid_size_exits(value):
    with pytest.raises(SystemExit):
        parse_gui_args(["--size", value])


@pytest.mark.parametrize(
    "argv", [["--fullscreen", "--maximized"], ["--fullscreen", "--size", "10x10"], ["--maximized", "--size", "1x1"]]
)
def test_window_flags_are_mutually_exclusive(argv):
    with pytest.raises(SystemExit):
        parse_gui_args(argv)


def test_name_flag():
    assert parse_gui_args(["--name", "My demo"])[1] == {"name": "My demo"}


def test_combination():
    _, kwargs = parse_gui_args(["--gui", "qt", "--fullscreen", "--name", "demo"])
    assert kwargs == {"gui": "qt", "size": "fullscreen", "name": "demo"}


def test_custom_parser_keeps_its_own_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="img.png")
    args, kwargs = parse_gui_args(["--input", "a.png", "--gui", "mpl"], parser=parser)
    assert args.input == "a.png"
    assert kwargs == {"gui": "mpl"}


def test_add_gui_arguments_returns_group_and_defaults():
    parser = argparse.ArgumentParser()
    group = add_gui_arguments(parser, defaults={"gui": "mpl", "size": "800x600"})
    assert isinstance(group, argparse._ArgumentGroup)
    args = parser.parse_args([])
    assert gui_kwargs_from_args(args) == {"gui": "mpl", "size": (800, 600)}
    # command line still wins over the defaults
    args = parser.parse_args(["--gui", "qt", "--fullscreen"])
    assert gui_kwargs_from_args(args) == {"gui": "qt", "size": "fullscreen"}


def test_add_gui_arguments_rejects_unknown_defaults():
    with pytest.raises(ValueError):
        add_gui_arguments(argparse.ArgumentParser(), defaults={"color": "red"})


def test_gui_kwargs_from_partial_namespace():
    # A namespace built by hand (or by a parser without all the options) works too
    assert gui_kwargs_from_args(argparse.Namespace()) == {}
    assert gui_kwargs_from_args(argparse.Namespace(size=[3, 4])) == {"size": (3, 4)}


# --- environment parsing ------------------------------------------------------


def test_env_unset():
    assert gui_from_env() is None
    assert size_from_env() is None


@pytest.mark.parametrize(
    "value, expected", [("qt", "qt"), (" MPL ", "mpl"), ("none", "headless"), ("headless", "headless"), ("", None)]
)
def test_gui_from_env(monkeypatch, value, expected):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", value)
    assert gui_from_env() == expected


def test_gui_from_env_invalid(monkeypatch):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "tk")
    with pytest.raises(ValueError, match="INTERACTIVE_PIPE_GUI"):
        gui_from_env()


@pytest.mark.parametrize(
    "value, expected", [("fullscreen", "fullscreen"), ("max", "maximized"), ("1280x800", (1280, 800))]
)
def test_size_from_env(monkeypatch, value, expected):
    monkeypatch.setenv("INTERACTIVE_PIPE_SIZE", value)
    assert size_from_env() == expected


def test_size_from_env_invalid(monkeypatch):
    monkeypatch.setenv("INTERACTIVE_PIPE_SIZE", "1280by800")
    with pytest.raises(ValueError, match="INTERACTIVE_PIPE_SIZE"):
        size_from_env()


def test_resolve_gui(monkeypatch):
    assert resolve_gui("auto") == "auto"
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "dpg")
    assert resolve_gui("auto") == "dpg"
    assert resolve_gui("mpl") == "mpl"
    assert resolve_gui(None) is None
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "none")
    assert resolve_gui("auto") is None


# --- environment overrides in interactive_pipeline ----------------------------


@interactive(gain=(1.0, [0.0, 2.0]))
def _amplify(img, gain=1.0):
    return img * gain


def _cli_pipeline(img):
    out = _amplify(img)
    return out


class _FakeGui:
    def __init__(self, pipeline=None, **kwargs):
        self.pipeline = pipeline
        self.kwargs = kwargs

    def graph_representation(self, *args, **kwargs):
        return None


@pytest.fixture
def recorded(monkeypatch):
    """Replace the backend lookup so no real GUI is instantiated; record the requested gui."""
    calls = []

    def fake_get_class(gui="auto"):
        calls.append(gui)
        return _FakeGui

    monkeypatch.setattr(pipeline_decorator, "get_interactive_pipeline_class", fake_get_class)
    return calls


def test_env_gui_overrides_auto(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "qt")
    interactive_pipeline(gui="auto")(_cli_pipeline)
    interactive_pipeline()(_cli_pipeline)
    interactive_pipeline(gui=Backend.AUTO)(_cli_pipeline)
    assert recorded == ["qt", "qt", "qt"]


def test_no_env_keeps_auto(recorded):
    interactive_pipeline(**{})(_cli_pipeline)
    assert recorded == ["auto"]


def test_explicit_gui_ignores_env(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "qt")
    interactive_pipeline(gui="mpl")(_cli_pipeline)
    assert recorded == ["mpl"]


@pytest.mark.parametrize("value", ["headless", "none", "NONE"])
def test_env_headless_returns_headless_pipeline(monkeypatch, recorded, value):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", value)
    result = interactive_pipeline()(_cli_pipeline)
    assert isinstance(result, HeadlessPipeline)
    assert recorded == []


def test_explicit_headless_ignores_env(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "qt")
    assert isinstance(interactive_pipeline(gui=None)(_cli_pipeline), HeadlessPipeline)
    assert isinstance(interactive_pipeline(gui="headless")(_cli_pipeline), HeadlessPipeline)
    assert recorded == []


def test_env_invalid_gui_raises(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "tk")
    with pytest.raises(ValueError, match="INTERACTIVE_PIPE_GUI"):
        interactive_pipeline()(_cli_pipeline)


@pytest.mark.parametrize(
    "value, expected", [("fullscreen", "fullscreen"), ("max", "maximized"), ("800x600", (800, 600))]
)
def test_env_size_used_when_not_given(monkeypatch, recorded, value, expected):
    monkeypatch.setenv("INTERACTIVE_PIPE_SIZE", value)
    demo = interactive_pipeline(gui="mpl")(_cli_pipeline)
    assert demo.pipeline.kwargs["size"] == expected


def test_explicit_size_ignores_env(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_SIZE", "fullscreen")
    demo = interactive_pipeline(gui="mpl", size=(320, 240))(_cli_pipeline)
    assert demo.pipeline.kwargs["size"] == (320, 240)


def test_no_env_size_passes_nothing(recorded):
    demo = interactive_pipeline(gui="mpl")(_cli_pipeline)
    assert "size" not in demo.pipeline.kwargs


def test_cli_kwargs_win_over_env(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "qt")
    monkeypatch.setenv("INTERACTIVE_PIPE_SIZE", "maximized")
    _, gui_kwargs = parse_gui_args(["--gui", "dpg", "--size", "640x480", "--name", "cli"])
    demo = interactive_pipeline(**gui_kwargs)(_cli_pipeline)
    assert recorded == ["dpg"]
    assert demo.pipeline.kwargs["size"] == (640, 480)
    assert demo.pipeline.kwargs["name"] == "cli"


def test_cli_headless(monkeypatch, recorded):
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "qt")
    _, gui_kwargs = parse_gui_args(["--gui", "headless"])
    assert isinstance(interactive_pipeline(**gui_kwargs)(_cli_pipeline), HeadlessPipeline)


# --- get_interactive_pipeline_class: env vs the cached auto choice -----------


def test_cached_auto_choice_does_not_swallow_env(monkeypatch):
    monkeypatch.setattr(_private, "auto_gui", None)
    pytest.importorskip("matplotlib")
    from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib

    # Populate the auto cache with a fake choice, then the env must still win
    monkeypatch.setattr(_private, "auto_gui", "gradio")
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "mpl")
    assert get_interactive_pipeline_class("auto") is InteractivePipeMatplotlib
    assert _private.auto_gui == "gradio"  # cache untouched by the override


def test_env_headless_keeps_auto_choice_for_direct_lookup(monkeypatch):
    # @interact calls get_interactive_pipeline_class directly: "headless" cannot apply there
    pytest.importorskip("matplotlib")
    from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib

    monkeypatch.setattr(_private, "auto_gui", "mpl")
    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "headless")
    assert get_interactive_pipeline_class("auto") is InteractivePipeMatplotlib


def test_env_does_not_override_explicit_lookup(monkeypatch):
    pytest.importorskip("matplotlib")
    from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib

    monkeypatch.setenv("INTERACTIVE_PIPE_GUI", "gradio")
    assert get_interactive_pipeline_class("mpl") is InteractivePipeMatplotlib
