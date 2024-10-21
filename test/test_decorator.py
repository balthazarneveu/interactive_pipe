from interactive_pipe.headless.control import Control
from interactive_pipe.helper.filter_decorator import interactive
import numpy as np


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
