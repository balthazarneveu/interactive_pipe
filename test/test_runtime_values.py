"""Values given at call time, odd filter callables and unreadable pipeline sources."""

import functools

import numpy as np
import pytest

from interactive_pipe import PipelineSyntaxError, interactive
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMG = np.ones((2, 2))


@interactive(gain=(1.0, [0.0, 3.0]), n=(2, [0, 5]), mode=("a", ["a", "b"]))
def valued(img, gain=1.0, n=2, mode="a"):
    return img * gain * n


def valued_pipeline(img):
    out = valued(img)
    return out


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"gain": np.float32(2.0)}, 4.0),
        ({"gain": np.float64(0.5)}, 1.0),
        ({"n": np.int64(3), "gain": 1.0}, 3.0),
        ({"mode": np.str_("b"), "n": 2}, 2.0),
    ],
)
def test_numpy_scalars_are_accepted_by_controls(kwargs, expected):
    pipe = HeadlessPipeline.from_function(valued_pipeline)
    assert pipe(IMG, **kwargs)[0][0, 0] == pytest.approx(expected)
    for ctrl in pipe.controls:
        assert type(ctrl.value) in (int, float, str)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"gain": "2"}, "control 'gain' expects float, got str '2'"),
        ({"gain": True}, "control 'gain' expects a number, got True"),
        ({"n": False}, "control 'n' expects a number, got False"),
    ],
)
def test_wrong_value_types_name_the_control(kwargs, match):
    pipe = HeadlessPipeline.from_function(valued_pipeline)
    with pytest.raises(TypeError, match=match):
        pipe(IMG, **kwargs)


def test_control_check_value_directly():
    ctrl = Control(1.0, [0.0, 3.0], name="gain")
    assert ctrl.check_value(np.float32(2.0)) == 2.0
    with pytest.raises(TypeError, match="expects a number"):
        ctrl.check_value(True)


partial_amplify = functools.partial(valued, gain=2.0, n=1)


def partial_pipeline(img):
    out = partial_amplify(img)
    return out


def test_functools_partial_as_a_filter():
    # used to crash with AttributeError: 'functools.partial' object has no attribute '__qualname__'
    pipe = HeadlessPipeline.from_function(partial_pipeline)
    assert pipe(IMG)[0][0, 0] == 2.0
    assert "<partial at " in Control.registry_key(partial_amplify)


def test_pipeline_without_source_raises_a_clear_error():
    namespace = {"valued": valued}
    exec("def exec_pipeline(img):\n    out = valued(img)\n    return out\n", namespace)
    with pytest.raises(PipelineSyntaxError, match="cannot read the source code") as info:
        HeadlessPipeline.from_function(namespace["exec_pipeline"])
    assert "pipeline 'exec_pipeline'" in str(info.value)
    assert "define the pipeline function in a file or a notebook cell" in str(info.value)
