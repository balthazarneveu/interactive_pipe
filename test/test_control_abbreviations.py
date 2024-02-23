import pytest
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.control import Control

NAME = "light_is_on"
CHOICES = ["dog", "cat", "elephant", "rabbit"]


@pytest.mark.parametrize(
    "inp_tuple", [
        (False, NAME, "+"),
        (False, NAME, ("-", "+")),
        (10, [-15, 18], None, ("-", "+", True)),
        (10, [-15, 18], None, ["-", "+", True]),
        (10, [-15, 18], None, ("pageup", "pagedown", True)),
        (0, [-5, 8], None, ("up", "down", False)),
        ("dog", CHOICES, None, ["p", "n", True]),
        ("dog", CHOICES, None, ("p", "n", True)),
        ("dog", CHOICES, None, (None, "n", True)),
        ("dog", CHOICES, None, ("w", True)),
        ("dog", CHOICES, None, ("w", None, True))
    ]
)
def test_abbreviation_keyboard(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    assert isinstance(ctrl, KeyboardControl)


@pytest.mark.parametrize(
    "inp_tuple", [
        ((-10, 10), "counter", ("-", "+")),
        ((-10, 10, 3, -4), "counter_assym", ("-", "+", True)),
        (CHOICES, None, ["p", "n", True]),
        (CHOICES, None, ("p", "n", True)),
        (CHOICES, None, (None, "n", True)),
        (CHOICES, None, ("w", True)),
        (CHOICES, None, ("w", None, True))
    ]
)
def test_ultra_abbreviation_keyboard(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    print(ctrl)
    assert isinstance(ctrl, KeyboardControl)


@pytest.mark.parametrize(
    "inp_tuple_and_error_type", [
        ((False, NAME, 12), TypeError),
        ((False, NAME, "ctrl"), AssertionError),  # un supported key
        ((False, NAME, "F25"), AssertionError),  # un supported key,
        ((True, NAME, [True, False], "+"), AssertionError),
        (("dog", CHOICES, None, (True, "b", True)), AssertionError),
        (("dog", CHOICES, None, ("w", "b", "z")), AssertionError),
    ]
)
def test_abbreviation_keyboard_expected_fail(inp_tuple_and_error_type):
    inp_tuple, error_type = inp_tuple_and_error_type
    with pytest.raises(error_type):
        ctrl = control_from_tuple(inp_tuple)


@pytest.mark.parametrize(
    "inp_tuple", [
        (False),
        (True),
        (False, None, None),
        (False, NAME, None),
        (0., [-2., 2.]),
        (1, [-2, 2]),
        (CHOICES[0], CHOICES)
    ]
)
def test_abbreviation_control(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    assert isinstance(ctrl, Control) and not isinstance(
        ctrl, KeyboardControl), f"wrong type {ctrl}"


@pytest.mark.parametrize(
    "inp_tuple", [
        ([-2., 2.],),
        ([-2, 2],),
        ([-2, 2, None, -1],),
        ([-10, 10, 4, -1],),
        (CHOICES,)
    ]
)
def test_ultra_abbreviation_control(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    print(ctrl)
    assert isinstance(ctrl, Control) and not isinstance(
        ctrl, KeyboardControl), f"wrong type {ctrl}"


@pytest.mark.parametrize(
    "inp_tuple_and_error_type", [
        ((True, [-2, 2]), AssertionError),
        ((True, "flag", [-2, 2]), AssertionError),
        ((True, [True, False], "flag"), AssertionError),
        (("dolphin", CHOICES), AssertionError),
        ((-10, [-5, 8], None), AssertionError),
    ]
)
def test_abbreviation_control_expected_fail(inp_tuple_and_error_type):
    inp_tuple, error_type = inp_tuple_and_error_type
    with pytest.raises(error_type):
        ctrl = control_from_tuple(inp_tuple)
