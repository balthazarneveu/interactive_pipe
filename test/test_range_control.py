"""RangeControl: two-handle (lo, hi) slider - headless behaviour."""

import json

import numpy as np
import pytest

from interactive_pipe import RangeControl, interactive
from interactive_pipe.data_objects.parameters import YAML_SUPPORT
from interactive_pipe.headless.pipeline import HeadlessPipeline

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@interactive(window=RangeControl((0.2, 0.8), [0.0, 1.0]))
def range_clip(img, window=(0.2, 0.8)):
    lo, hi = window
    return np.clip(img, lo, hi)


def range_pipeline(img):
    clipped = range_clip(img)
    return clipped


def _pipeline():
    pipe = HeadlessPipeline.from_function(range_pipeline, inputs=["img"])
    pipe.inputs = [INPUT_IMAGE.copy()]
    return pipe


# --- construction / validation ---


def test_float_range_defaults():
    ctrl = RangeControl((0.2, 0.8), [0.0, 1.0], name="win")
    assert ctrl._type is float
    assert ctrl.value == (0.2, 0.8)
    assert ctrl.value_default == (0.2, 0.8)
    assert ctrl.value_range == [0.0, 1.0]
    assert ctrl.step == pytest.approx(0.01)
    assert "win" in repr(ctrl) and "(0.2, 0.8)" in repr(ctrl)


def test_int_range_and_list_default():
    ctrl = RangeControl([2, 5], [0, 10], step=2)
    assert ctrl._type is int
    assert ctrl.value == (2, 5)
    assert ctrl.step == 2
    assert RangeControl((2, 5), [0, 10]).step == 1


def test_mixed_types_give_float():
    ctrl = RangeControl((2, 5), [0, 10.0])
    assert ctrl._type is float
    assert ctrl.value == (2.0, 5.0)


@pytest.mark.parametrize(
    "default, value_range, exc",
    [
        ((0.8, 0.2), [0.0, 1.0], ValueError),  # lo > hi
        ((-0.1, 0.5), [0.0, 1.0], ValueError),  # out of range
        ((0.1, 1.5), [0.0, 1.0], ValueError),
        ((0.1, 0.2, 0.3), [0.0, 1.0], ValueError),
        ((0.1, 0.2), [1.0, 0.0], ValueError),  # min >= max
        ((0.1, 0.2), [0.0, 1.0, 2.0], ValueError),
        (0.5, [0.0, 1.0], TypeError),
        (("a", 0.2), [0.0, 1.0], TypeError),
        ((True, 1), [0, 1], TypeError),
    ],
)
def test_invalid_construction_raises(default, value_range, exc):
    with pytest.raises(exc):
        RangeControl(default, value_range)


def test_updates_are_sorted_and_clamped():
    ctrl = RangeControl((0.2, 0.8), [0.0, 1.0])
    ctrl.update([0.9, 0.1])
    assert ctrl.value == (0.1, 0.9)
    ctrl.update((-3, 5))
    assert ctrl.value == (0.0, 1.0)
    ctrl.update(np.array([0.25, 0.5]))
    assert ctrl.value == (0.25, 0.5)
    assert all(type(v) is float for v in ctrl.value)
    ctrl.update("0.3, 0.4")
    assert ctrl.value == (0.3, 0.4)
    ctrl.reset()
    assert ctrl.value == (0.2, 0.8)


def test_int_updates_round():
    ctrl = RangeControl((2, 5), [0, 10])
    ctrl.update((1.6, 20.0))
    assert ctrl.value == (2, 10)
    assert all(type(v) is int for v in ctrl.value)


@pytest.mark.parametrize("bad, exc", [((0.1,), ValueError), (0.5, TypeError), ("nope", ValueError)])
def test_invalid_updates_raise(bad, exc):
    ctrl = RangeControl((0.2, 0.8), [0.0, 1.0])
    with pytest.raises(exc):
        ctrl.update(bad)


def test_clone_unconnected_keeps_spec_and_resets():
    ctrl = RangeControl((2, 5), [0, 10], name="r")
    ctrl.update((0, 1))
    clone = ctrl._clone_unconnected("r_1")
    assert isinstance(clone, RangeControl)
    assert clone.name == "r_1"
    assert clone.value == (2, 5)
    assert clone.filter_to_connect is None
    assert ctrl.value == (0, 1)


# --- pipeline integration ---


def test_filter_receives_a_tuple():
    pipe = _pipeline()
    out = pipe.run()
    assert pipe.parameters["range_clip"]["window"] == (0.2, 0.8)
    assert out[0].min() == pytest.approx(0.2)
    assert out[0].max() == pytest.approx(0.8)


def test_parameters_setter_accepts_list_and_syncs_control():
    pipe = _pipeline()
    pipe.parameters = {"range_clip": {"window": [0.6, 0.3]}}
    ctrl = next(c for c in pipe.controls if isinstance(c, RangeControl))
    assert ctrl.value == (0.3, 0.6)
    out = pipe.run()
    assert pipe.parameters["range_clip"]["window"] == (0.3, 0.6)
    assert out[0].max() == pytest.approx(0.6)


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_tuning_round_trip(tmp_path, suffix):
    if suffix == ".yaml" and not YAML_SUPPORT:
        pytest.skip("PyYAML not installed")
    pipe = _pipeline()
    ctrl = next(c for c in pipe.controls if isinstance(c, RangeControl))
    ctrl.update((0.1, 0.4))
    pipe.run()
    path = tmp_path / f"tuning{suffix}"
    pipe.export_tuning(path)
    if suffix == ".json":
        assert json.loads(path.read_text())["range_clip"]["window"] == [0.1, 0.4]

    other = _pipeline()
    other.import_tuning(path)
    other_ctrl = next(c for c in other.controls if isinstance(c, RangeControl))
    assert other_ctrl.value == (0.1, 0.4)
    other.run()
    assert other.parameters["range_clip"]["window"] == (0.1, 0.4)
