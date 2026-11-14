"""Calling an @interactive filter directly, like a plain function."""

import numpy as np
import pytest

from interactive_pipe import interactive

IMG = np.ones((2, 2))


@interactive(gain=(1.0, [0.0, 3.0]))
def direct_amplify(img, gain=1.0):
    return img * gain


def test_positional_value_for_a_controlled_parameter_wins():
    # used to raise "TypeError: multiple values for argument 'gain'"
    assert direct_amplify(IMG, 2.0)[0, 0] == 2.0
    assert direct_amplify(IMG)[0, 0] == 1.0
    assert direct_amplify(IMG, gain=0.5)[0, 0] == 0.5


def test_unknown_keyword_names_the_filter_and_suggests():
    with pytest.raises(TypeError, match=r"direct_amplify\(\) got unexpected keyword argument\(s\) 'gian'") as info:
        direct_amplify(IMG, gian=2.0)
    assert "Did you mean 'gian' -> 'gain'?" in str(info.value)
    assert "Parameters: img, gain" in str(info.value)


def test_missing_input_names_the_filter():
    with pytest.raises(TypeError, match=r"direct_amplify\(\): missing a required argument: 'img'"):
        direct_amplify()


def test_too_many_positional_values_names_the_filter():
    with pytest.raises(TypeError, match=r"direct_amplify\(\): too many positional arguments"):
        direct_amplify(IMG, 1.0, 2.0)
