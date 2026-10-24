"""A decorator control takes precedence over a tuple default in the signature."""

from interactive_pipe import Control, interactive
from interactive_pipe.headless.control import Control as HeadlessControl


@interactive(span=Control(0.5, [0.0, 1.0]))
def tuple_default_filter(img, span=(0.2, 0.8)):
    return img


def test_decorator_control_wins_over_tuple_default():
    controls = HeadlessControl.get_controls(tuple_default_filter)
    assert list(controls) == ["span"]
    assert controls["span"].value_range == [0.0, 1.0]
    assert controls["span"].value == 0.5
