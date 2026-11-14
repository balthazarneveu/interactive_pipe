"""HeadlessPipeline.sweep: contact sheets over one or two parameters."""

import warnings

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from interactive_pipe import Control, FilterError, RangeControl, interactive, interactive_pipeline, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve  # noqa: E402
from interactive_pipe.headless.explore import split_sweep_arguments, values_over_range  # noqa: E402

SIZE = 24


@interactive(gain=(0.5, [0.0, 1.0]), offset=(0, [0, 4]))
def sw_amplify(img, gain=0.5, offset=0):
    return np.clip(img * gain + 0.1 * offset, 0.0, 1.0)


@interactive(mode=Control("normal", ["normal", "invert", "half"]), flip=Control(False))
def sw_mode(img, mode="normal", flip=False):
    if mode == "invert":
        img = 1.0 - img
    elif mode == "half":
        img = img * 0.5
    if flip:
        if mode == "half":
            raise RuntimeError("cannot flip half")
        img = img[::-1]
    return img


@interactive(window=RangeControl((0.2, 0.8), [0.0, 1.0]))
def sw_crop(img, window=(0.2, 0.8)):
    start, stop = int(window[0] * img.shape[1]), max(int(window[1] * img.shape[1]), 1)
    return img[:, start:stop]


def sw_curve(img):
    return Curve([img.mean(axis=(0, 2))])


def sw_pipeline(img):
    amplified = sw_amplify(img)
    moded = sw_mode(amplified)
    profile = sw_curve(moded)
    return moded, profile


def sw_range_pipeline(img):
    cropped = sw_crop(img)
    return [cropped]


def gradient():
    x = np.linspace(0.0, 1.0, SIZE, dtype=np.float32)
    return np.repeat(np.repeat(x[None, :, None], SIZE, axis=0), 3, axis=2)


def make(function):
    pipe = interactive_pipeline(gui=None)(function)
    pipe(gradient())
    return pipe


def test_one_swept_parameter_is_one_row(tmp_path):
    pipe = make(sw_pipeline)
    path = pipe.sweep(tmp_path / "sweep.png", gain=[0.2, 0.5, 1.0])
    with PILImage.open(path) as img:
        width, height = img.size
    assert width > 2 * height


def test_many_values_wrap_into_rows():
    rgb = make(sw_pipeline).sweep(None, gain=list(np.linspace(0, 1, 9)), caption=False)
    assert 0.6 < rgb.shape[1] / rgb.shape[0] < 1.6  # 3 x 3


def test_two_swept_parameters_make_a_labelled_grid():
    pipe = make(sw_pipeline)
    rgb = pipe.sweep(None, gain=[0.2, 1.0], offset=[0, 2, 4], caption=False)
    assert rgb.shape[1] > rgb.shape[0]  # 2 rows x 3 columns
    assert rgb.std() > 0


def test_cells_differ_and_state_is_restored():
    pipe = make(sw_pipeline)
    params_before = pipe.parameters
    controls_before = {ctrl.name: ctrl.value for ctrl in pipe.controls}
    rgb = pipe.sweep(None, gain=[0.0, 1.0], caption=False)
    left, right = rgb[:, : rgb.shape[1] // 2], rgb[:, rgb.shape[1] // 2 :]
    assert left.mean() < right.mean()
    assert pipe.parameters == params_before
    assert {ctrl.name: ctrl.value for ctrl in pipe.controls} == controls_before


def test_state_is_restored_when_a_cell_raises():
    pipe = make(sw_pipeline)
    params_before = pipe.parameters
    with pytest.raises(FilterError):
        pipe.sweep(None, mode=["normal", "half"], flip=True)
    assert pipe.parameters == params_before
    assert all(ctrl.value == ctrl.value_default for ctrl in pipe.controls)


def test_scalars_are_fixed_overrides():
    _, fixed = split_sweep_arguments(make(sw_pipeline), {"gain": [0.1, 0.2], "offset": 3}, None)
    assert fixed == {"offset": 3}


def test_more_than_two_axes_or_none_raise():
    pipe = make(sw_pipeline)
    with pytest.raises(ValueError, match="one or two"):
        pipe.sweep(None, gain=[0.1, 1], offset=[0, 1], mode=["normal", "invert"])
    with pytest.raises(ValueError, match="needs a parameter to sweep"):
        pipe.sweep(None, gain=0.3)
    with pytest.raises(ValueError, match="no values"):
        pipe.sweep(None, gain=[])


def test_unknown_names_raise_type_error():
    pipe = make(sw_pipeline)
    with pytest.raises(TypeError, match="Did you mean 'gain'"):
        pipe.sweep(None, gane=[0.1, 0.2])
    with pytest.raises(TypeError, match="gian"):
        pipe.sweep(None, steps={"gian": 3})


def test_steps_over_the_declared_range():
    pipe = make(sw_pipeline)
    targets = {"gain": [("sw_amplify", "gain")], "offset": [("sw_amplify", "offset")]}
    assert values_over_range(pipe, "gain", targets["gain"], 5) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert values_over_range(pipe, "offset", targets["offset"], 3) == [0, 2, 4]
    assert values_over_range(pipe, "mode", [("sw_mode", "mode")], 5) == ["normal", "invert", "half"]
    assert values_over_range(pipe, "mode", [("sw_mode", "mode")], 2) == ["normal", "half"]
    assert values_over_range(pipe, "flip", [("sw_mode", "flip")], 7) == [False, True]
    with pytest.raises(ValueError, match="positive int"):
        values_over_range(pipe, "gain", targets["gain"], 0)
    rgb = pipe.sweep(None, steps={"gain": 4}, caption=False)
    assert rgb.shape[1] > 2 * rgb.shape[0]
    with pytest.raises(ValueError, match="both"):
        pipe.sweep(None, gain=[0.1, 0.2], steps={"gain": 3})


def test_range_control_tuples_are_values_lists_are_axes():
    pipe = make(sw_range_pipeline)
    with pytest.raises(ValueError, match="needs a parameter to sweep"):
        split_sweep_arguments(pipe, {"window": (0.1, 0.9)}, None)  # one (lo, hi) value, not an axis
    axes, _ = split_sweep_arguments(pipe, {"window": [(0.0, 0.5), (0.5, 1.0)]}, None)
    assert axes == {"window": [(0.0, 0.5), (0.5, 1.0)]}
    rgb = pipe.sweep(None, window=[(0.0, 0.5), (0.5, 1.0)], caption=False)
    left, right = rgb[:, : rgb.shape[1] // 2], rgb[:, rgb.shape[1] // 2 :]
    assert left.mean() < right.mean()  # dark half of the gradient vs bright half
    with pytest.raises(ValueError, match="RangeControl"):
        pipe.sweep(None, steps={"window": 3})


def test_output_selection_default_all_and_name():
    pipe = make(sw_pipeline)
    default = pipe.sweep(None, gain=[0.2, 1.0], caption=False)  # first image output
    curves = pipe.sweep(None, gain=[0.2, 1.0], output="profile", caption=False)
    everything = pipe.sweep(None, gain=[0.2, 1.0], output="all", caption=False)
    assert everything.shape[1] > default.shape[1]
    assert not np.array_equal(default, curves[: default.shape[0], : default.shape[1]])


def test_tuple_of_values_is_an_axis_for_plain_parameters():
    axes, _ = split_sweep_arguments(make(sw_pipeline), {"gain": (0.1, 0.9)}, None)
    assert axes == {"gain": [0.1, 0.9]}
    axes, _ = split_sweep_arguments(make(sw_pipeline), {"gain": np.array([0.1, 0.9])}, None)
    assert axes == {"gain": [0.1, 0.9]}


@interactive(count=(2, [1, 5]), on=Control(True))
def sw_counted(img, count=2, on=True):
    return img * (count / 5.0) if on else img * 0.0


@interactive(choice=Control("a", ["a", "b"]))
def sw_relayout(img, choice="a"):
    if choice == "b":
        layout.grid([["right"]])
    return img * 0.2, img


def sw_numpy_pipeline(img):
    counted = sw_counted(img)
    return [counted]


def sw_relayout_pipeline(img):
    left, right = sw_relayout(img)
    return left, right


def test_numpy_axes_of_any_dtype():
    pipe = make(sw_numpy_pipeline)
    assert pipe.sweep(None, count=np.arange(1, 4)).ndim == 3
    assert pipe.sweep(None, on=np.array([True, False]), count=np.int64(3)).ndim == 3


def test_default_output_follows_layout_changes():
    pipe = make(sw_relayout_pipeline)
    rgb = pipe.sweep(None, choice=["a", "b"], caption=False)  # 'left' disappears from the second layout
    assert rgb.ndim == 3


def test_range_list_override_does_not_warn():
    pipe = make(sw_range_pipeline)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pipe.snapshot(None, window=[0.1, 0.4])


def test_none_override_of_a_control_raises():
    with pytest.raises(TypeError, match="None"):
        make(sw_pipeline).snapshot(None, gain=None)
