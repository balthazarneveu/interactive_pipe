"""Control declarations that cannot work raise at decoration, naming the filter
and the parameter."""

import pytest

from interactive_pipe import interactive
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.keyboard import KeyboardControl


def _declare(**decorator_controls):
    def declared(img, gain=1.0, mode="a", n=1):
        return img

    return interactive(**decorator_controls)(declared)


@pytest.mark.parametrize(
    "declaration, match",
    [
        ({"gain": (5.0, [0.0, 3.0])}, "value_default 5.0 must be within value_range"),
        ({"gain": (1.0, [3.0, 0.0])}, r"must satisfy min <= max \(did you mean \[0.0, 3.0\]\?\)"),
        ({"gain": (1.0, [0.0, 3.0, 10.0])}, "step 10.0 is larger than the range"),
        ({"gain": (1.0, [0.0, 3.0, 0])}, "step 0 must be > 0"),
        ({"gain": (1.0, [0.0, 3.0, -1])}, "step -1 must be > 0"),
        ({"gain": (1.0, [0.0, 3.0, 0.1, 5])}, "has too many elements"),
        ({"mode": ("a", [])}, "value_range cannot be empty"),
        ({"mode": ("z", ["a", "b"])}, r"z must be in \['a', 'b'\]"),
        ({"mode": []}, "cannot provide an empty list"),
        ({"gain": (True, [0, 1])}, "you do not need to provide a value range for a boolean"),
    ],
)
def test_invalid_shorthand_names_filter_and_parameter(declaration, match):
    param = next(iter(declaration))
    with pytest.raises(ValueError, match=match) as info:
        _declare(**declaration)
    message = str(info.value)
    assert message.startswith(f"@interactive filter '_declare.<locals>.declared', parameter '{param}':")
    # the error of the form actually written, not of the ultra-short fallback
    assert "max parameter should be numerical too" not in message
    assert "wrong abbreviation" not in message


def test_ultra_short_list_errors_are_reported_from_the_list_form():
    with pytest.raises(ValueError, match="please provide \\[min, max\\]"):
        _declare(gain=[1.0])


def test_typo_suggests_the_parameter_and_names_the_filter():
    with pytest.raises(ValueError, match="typo: control gian") as info:
        _declare(gian=(1.0, [0.0, 3.0]))
    assert "(@interactive filter '_declare.<locals>.declared')" in str(info.value)
    assert "Did you mean 'gain'?" in str(info.value)


@pytest.mark.parametrize(
    "build, match",
    [
        (lambda: Control(1.0, [0.0, 3.0], step=10), "larger than the range"),
        (lambda: Control(1.0, [0.0, 3.0], step=0), "must be > 0"),
        (lambda: Control(1, [3, 0]), "min <= max"),
        (lambda: KeyboardControl(1.0, [0.0, 3.0], keydown="a", step=-0.1), "must be > 0"),
    ],
)
def test_control_constructor_rejects_unusable_sliders(build, match):
    with pytest.raises(ValueError, match=match):
        build()


def test_single_value_range_is_allowed():
    # image selector pattern (0, [0, len(images) - 1]) with one image
    assert Control(0, [0, 0]).value_range == [0, 0]
    _declare(n=(0, [0, 0]))


def test_valid_steps_and_mixed_number_types_still_work():
    assert Control(1.0, [0.0, 3.0], step=3.0).step == 3.0
    assert Control(5, [0, 10], step=1)._type is int
    # an int default with a float range (and the reverse) gives a float slider
    assert Control(1, [0.0, 3.0])._type is float
    assert Control(1.5, [0, 3])._type is float


def test_redecorating_forgets_controls_removed_from_the_declaration():
    first = _declare(gain=(1.0, [0.0, 3.0]), n=(1, [0, 3]))
    assert set(Control.get_controls(first)) == {"gain", "n"}
    second = _declare(gain=(1.0, [0.0, 3.0]))  # same qualname: notebook cell re-run
    assert set(Control.get_controls(second)) == {"gain"}
