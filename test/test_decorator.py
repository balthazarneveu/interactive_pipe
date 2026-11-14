import numpy as np

from interactive_pipe.headless.control import Control
from interactive_pipe.helper.filter_decorator import interactive


@interactive(
    coeff=Control(42, [0, 100], name="expo"),
    bias=Control(13, [-20, 20], name="bias expo"),
)
def mad_dec(img, coeff=50, bias=0):
    mad_res = img * coeff / 100.0 + (bias / 100.0)
    return mad_res


def test_decorated_normal_execution():
    out = mad_dec(np.array(1.0))
    assert out == 0.42 + 0.13


def test_direct_call_accepts_a_positional_control_value():
    """A decorated filter stays an ordinary function: f(img, 2.0) must not clash with its control."""
    from interactive_pipe import interactive

    @interactive(gain=(1.0, [0.0, 3.0]))
    def amplify_directly(value, gain=1.0):
        return value * gain

    assert amplify_directly(2.0) == 2.0  # control default
    assert amplify_directly(2.0, 3.0) == 6.0  # positional
    assert amplify_directly(2.0, gain=0.5) == 1.0  # keyword
