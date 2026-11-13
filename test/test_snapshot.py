"""HeadlessPipeline.snapshot: run once with overrides, render, restore the state."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from interactive_pipe import Control, FilterError, interactive, interactive_pipeline, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve  # noqa: E402

SIZE = 24


@interactive(gain=(0.5, [0.0, 1.0]))
def snap_amplify(img, gain=0.5):
    layout.style("amplified", title=f"gain={gain:.2f}")
    return img * gain


@interactive(bins=(8, [2, 32]))
def snap_histogram(img, bins=8):
    hist, _ = np.histogram(img, bins=bins, range=(0.0, 1.0))
    return Curve([hist])


@interactive(crash=Control(False))
def snap_maybe_crash(img, crash=False):
    if crash:
        raise ZeroDivisionError("boom")
    return img


@interactive(title=("plain", ["plain", "fancy"]))
def snap_titled(img, title="plain"):
    return img if title == "plain" else 1.0 - img


@interactive(arrangement=("row", ["row", "column"]))
def snap_layout(arrangement="row"):
    if arrangement == "column":
        layout.grid([["amplified"], ["histo"]])


def snap_pipeline(img):
    amplified = snap_amplify(img)
    histo = snap_histogram(amplified)
    snap_layout()
    return amplified, histo


def snap_crash_pipeline(img):
    amplified = snap_amplify(img)
    checked = snap_maybe_crash(amplified)
    return [checked]


def snap_titled_pipeline(img):
    titled = snap_titled(img)
    return [titled]


def snap_repeat_pipeline(img):
    first = snap_amplify(img)
    second = snap_amplify(first)
    return first, second


@interactive(level=(0.25, [0.0, 1.0]))
def snap_constant(level=0.25):
    return np.full((SIZE, SIZE), level)


def snap_no_input_pipeline():
    constant = snap_constant()
    return [constant]


def white():
    return np.ones((SIZE, SIZE, 3), dtype=np.float32)


def make(function, **kwargs):
    return interactive_pipeline(gui=None, **kwargs)(function)


def control_values(pipe):
    return {ctrl.name: ctrl.value for ctrl in pipe.controls}


def test_snapshot_writes_a_png_and_returns_its_path(tmp_path):
    pipe = make(snap_pipeline)
    path = pipe.snapshot(tmp_path / "sub" / "out.png", white())
    assert path == tmp_path / "sub" / "out.png"
    with PILImage.open(path) as img:
        assert img.format == "PNG"
        width, height = img.size
    assert width > height  # two outputs on one row


def test_snapshot_without_path_returns_an_rgb_array():
    rgb = make(snap_pipeline).snapshot(None, white())
    assert rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3
    assert rgb.std() > 0


def test_parameters_change_the_picture_and_are_restored():
    pipe = make(snap_pipeline)
    pipe(white())
    params_before, controls_before = pipe.parameters, control_values(pipe)
    results_before = pipe.results
    dark = pipe.snapshot(None, output="amplified", gain=0.0, caption=False)
    bright = pipe.snapshot(None, output="amplified", gain=1.0, caption=False)
    assert dark.mean() < bright.mean()
    assert pipe.parameters == params_before
    assert control_values(pipe) == controls_before
    assert pipe.results is results_before
    # the next run uses the restored values
    np.testing.assert_allclose(pipe.run()[0], white() * 0.5)


def test_snapshot_restores_with_cache_enabled():
    pipe = make(snap_pipeline, cache=True)
    pipe(white())
    pipe.snapshot(None, gain=1.0)
    np.testing.assert_allclose(pipe.run()[0], white() * 0.5)


def test_layout_and_styles_changed_during_the_snapshot_are_restored():
    pipe = make(snap_pipeline)
    pipe(white())
    outputs_before = list(pipe.outputs)
    styles_before = dict(pipe.framework_state.output_styles)
    tall = pipe.snapshot(None, arrangement="column", gain=0.9)
    assert tall.shape[0] > tall.shape[1]  # layout.grid inside a filter is honored
    assert pipe.outputs == outputs_before
    assert pipe.framework_state.output_styles == styles_before


def test_state_is_restored_when_a_filter_raises():
    pipe = make(snap_crash_pipeline)
    pipe(white())
    params_before, controls_before = pipe.parameters, control_values(pipe)
    with pytest.raises(FilterError) as info:
        pipe.snapshot(None, crash=True, gain=0.9)
    assert isinstance(info.value.original_error, ZeroDivisionError)
    assert pipe.parameters == params_before
    assert control_values(pipe) == controls_before


def test_unknown_parameter_raises_with_a_close_match():
    pipe = make(snap_pipeline)
    with pytest.raises(TypeError, match="'gain'") as info:
        pipe.snapshot(None, white(), gian=2.0)
    assert "bins" in str(info.value)  # lists the available names


def test_unknown_parameter_is_detected_before_running(tmp_path):
    pipe = make(snap_crash_pipeline)
    with pytest.raises(TypeError):
        pipe.snapshot(tmp_path / "never.png", white(), crash=True, nope=1)
    assert not (tmp_path / "never.png").exists()


def test_inputs_are_required_once_then_reused():
    pipe = make(snap_pipeline)
    with pytest.raises(TypeError, match="img"):
        pipe.snapshot(None)
    pipe.snapshot(None, white())
    assert pipe.snapshot(None).std() > 0  # previous inputs reused
    assert pipe.snapshot(None, inputs={"img": white()}).std() > 0


def test_pipeline_without_inputs():
    pipe = make(snap_no_input_pipeline)
    low = pipe.snapshot(None, level=0.0, caption=False)
    high = pipe.snapshot(None, level=1.0, caption=False)
    assert low.mean() < high.mean()


def test_output_selection():
    pipe = make(snap_pipeline)
    both = pipe.snapshot(None, white())
    only_image = pipe.snapshot(None, output="amplified")
    only_curve = pipe.snapshot(None, output=1)
    assert only_image.shape[1] < both.shape[1]
    assert only_curve.shape[1] < both.shape[1]
    with pytest.raises(ValueError, match="available outputs"):
        pipe.snapshot(None, output="missing")


def test_params_dict_for_names_clashing_with_options():
    pipe = make(snap_titled_pipeline)
    plain = pipe.snapshot(None, white(), caption=False)
    fancy = pipe.snapshot(None, params={"title": "fancy"}, caption=False)
    assert fancy.mean() < plain.mean()


def test_control_name_and_dotted_names_target_one_repeat():
    pipe = make(snap_repeat_pipeline)
    pipe(white())
    clone_name = [ctrl.name for ctrl in pipe.controls if ctrl.name != "gain"][0]
    by_clone = pipe.snapshot(None, output=1, caption=False, **{clone_name: 0.0})
    by_dotted = pipe.snapshot(None, output=1, caption=False, **{"snap_amplify_1.gain": 0.0})
    default = pipe.snapshot(None, output=1, caption=False)
    np.testing.assert_array_equal(by_clone, by_dotted)
    assert by_clone.mean() < default.mean()


def test_out_of_range_value_is_clamped_with_a_warning():
    pipe = make(snap_pipeline)
    with pytest.warns(UserWarning, match="clamped"):
        pipe.snapshot(None, white(), gain=5.0)
    assert pipe.parameters["snap_amplify"]["gain"] == 0.5


def test_caption_lists_the_parameters_used():
    pipe = make(snap_pipeline)
    with_caption = pipe.snapshot(None, white())
    without = pipe.snapshot(None, caption=False)
    assert with_caption.shape[0] > without.shape[0]
