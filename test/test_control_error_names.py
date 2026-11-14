"""Errors raised while building a Gradio / notebook control widget name the
control and its filter (``Expected int control type, got <class 'float'>``
named nothing)."""

import inspect

import pytest

from interactive_pipe.graphical.control_errors import control_label
from interactive_pipe.headless.control import Control, RangeControl

CANDIDATES = {
    "int": lambda: Control(3, [0, 10], name="wrong_int"),
    "float": lambda: Control(0.5, [0.0, 1.0], name="wrong_float"),
    "bool": lambda: Control(True, name="wrong_bool"),
    "choice": lambda: Control("a", ["a", "b"], name="wrong_choice"),
    "prompt": lambda: Control("text", name="wrong_prompt"),
    "range": lambda: RangeControl((0.2, 0.4), [0.0, 1.0], name="wrong_range"),
}


def _factory_classes(module):
    base = module.BaseControl
    return [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, base) and cls is not base and cls.__module__ == module.__name__
    ]


def _build(module, cls, ctrl):
    if module.__name__.endswith("gradio_control"):
        widget = cls(ctrl.name, ctrl, lambda *args: None)
    else:
        widget = cls(ctrl.name, ctrl)
    widget.create()


@pytest.mark.parametrize("module_name", ["gradio_control", "nb_control"])
def test_every_factory_error_names_the_control(module_name):
    module = pytest.importorskip(f"interactive_pipe.graphical.{module_name}")
    if module_name == "gradio_control":
        pytest.importorskip("gradio")
    else:
        pytest.importorskip("ipywidgets")
    classes = _factory_classes(module)
    assert classes
    for cls in classes:
        raised = 0
        for make in CANDIDATES.values():
            ctrl = make()
            try:
                _build(module, cls, ctrl)
            except (TypeError, ValueError) as error:
                raised += 1
                assert str(error).startswith(f"control {ctrl.name!r}"), (cls.__name__, str(error))
            except Exception:  # noqa: S112 - a widget library refusing a value the factory never passes
                continue
        assert raised, f"{cls.__name__} accepted every kind of control"


def test_control_label_names_the_filter():
    class Filter:
        name = "amplify"

    class Widget:
        name = "gain"
        ctrl = type("Ctrl", (), {"filter_to_connect": Filter(), "name": "gain"})()

    assert control_label(Widget()) == "control 'gain' (filter 'amplify')"


def test_messages_are_not_prefixed_twice():
    gradio_control = pytest.importorskip("interactive_pipe.graphical.gradio_control")
    pytest.importorskip("gradio")
    with pytest.raises(TypeError) as info:
        gradio_control.IntSliderControl("gain", Control(0.5, [0.0, 1.0], name="gain"), lambda *a: None)
    assert str(info.value) == "control 'gain': Expected int control type, got <class 'float'>"
