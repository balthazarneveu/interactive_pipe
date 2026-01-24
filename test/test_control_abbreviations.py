import pytest
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.control import Control

NAME = "light_is_on"
CHOICES = ["dog", "cat", "elephant", "rabbit"]


# Keyboard abbreviations have been removed for simplicity
# Use KeyboardControl(...) directly instead of tuple abbreviations
# Tests removed: test_abbreviation_keyboard


# Keyboard abbreviations have been removed for simplicity
# Use KeyboardControl(...) directly instead of tuple abbreviations
# Tests removed: test_ultra_abbreviation_keyboard


@pytest.mark.parametrize(
    "inp_tuple_and_error_type",
    [
        # Test that tuples with too many elements fail
        (
            (False, NAME, "group1", "extra"),
            AssertionError,
        ),  # Too many elements for boolean
        (
            (10, [-15, 18], "name", "group", "extra"),
            AssertionError,
        ),  # Too many elements for numeric
    ],
)
def test_abbreviation_expected_fail(inp_tuple_and_error_type):
    inp_tuple, error_type = inp_tuple_and_error_type
    with pytest.raises(error_type):
        ctrl = control_from_tuple(inp_tuple)  # noqa: F841


@pytest.mark.parametrize(
    "inp_tuple",
    [
        (False),
        (True),
        (False, None, None),
        (False, NAME, None),
        (0.0, [-2.0, 2.0]),
        (1, [-2, 2]),
        (CHOICES[0], CHOICES),
    ],
)
def test_abbreviation_control(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    assert isinstance(ctrl, Control) and not isinstance(
        ctrl, KeyboardControl
    ), f"wrong type {ctrl}"


@pytest.mark.parametrize(
    "inp_tuple",
    [([-2.0, 2.0],), ([-2, 2],), ([-2, 2, None, -1],), ([-10, 10, 4, -1],), (CHOICES,)],
)
def test_ultra_abbreviation_control(inp_tuple):
    ctrl = control_from_tuple(inp_tuple)
    print(ctrl)
    assert isinstance(ctrl, Control) and not isinstance(
        ctrl, KeyboardControl
    ), f"wrong type {ctrl}"


@pytest.mark.parametrize(
    "inp_tuple_and_error_type",
    [
        ((True, [-2, 2]), AssertionError),  # Wrong: bool with range
        (
            (True, [True, False], "flag"),
            AssertionError,
        ),  # Wrong: list as name
        (("dolphin", CHOICES), ValueError),  # Value not in choices
        ((-10, [-5, 8], None), ValueError),  # Default outside range
    ],
)
def test_abbreviation_control_expected_fail(inp_tuple_and_error_type):
    inp_tuple, error_type = inp_tuple_and_error_type
    with pytest.raises(error_type):
        ctrl = control_from_tuple(inp_tuple)  # noqa: F841
