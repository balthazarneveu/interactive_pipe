"""Bare scalar values in @interactive(...) keyword arguments."""

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline


def test_bare_bool_in_decorator_makes_a_checkbox():
    @interactive(flip=True)
    def flipper(img, flip=False):
        return img[::-1] if flip else img

    ctrl = Control.get_controls(flipper)["flip"]
    assert ctrl._type is bool
    assert ctrl.value is True and ctrl.name == "flip"

    def pipe(img):
        out = flipper(img)
        return out

    pipeline = HeadlessPipeline.from_function(pipe)
    assert [c.name for c in pipeline.controls] == ["flip"]
    np.testing.assert_array_equal(pipeline(np.arange(3))[0], [2, 1, 0])
    np.testing.assert_array_equal(pipeline(np.arange(3), flip=False)[0], [0, 1, 2])


def test_bare_false_in_decorator_makes_an_unchecked_checkbox():
    @interactive(flip=False)
    def flipper_off(img, flip=True):
        return img

    assert Control.get_controls(flipper_off)["flip"].value is False


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, "gain=(1.0, [0, 2.0])"),
        (3, "gain=(3, [0, 6])"),
        ("dark", "gain=('dark', ['dark', 'other choice'])"),
    ],
)
def test_bare_number_or_string_in_decorator_raises_with_the_right_spelling(value, expected):
    with pytest.raises(ValueError) as exc_info:

        @interactive(gain=value)
        def filt(img, gain=value):
            return img

    message = str(exc_info.value)
    assert f"@interactive(gain={value!r})" in message
    assert expected in message
    assert "if no widget is wanted" in message


def test_bare_default_in_signature_still_means_no_widget():
    @interactive()
    def plain(img, flip=True, gain=1.0, mode="dark"):
        return img

    assert Control.get_controls(plain) == {}
