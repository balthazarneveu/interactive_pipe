"""Single-filter entry points on @interactive functions (GitHub issue #21)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pickle  # noqa: E402
import warnings  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import Control, Curve, FilterError, context, interactive, interactive_pipeline, layout  # noqa: E402

SIZE = 16


@interactive(gain=(0.5, [0.0, 1.0]))
def fe_amplify(img, gain=0.5):
    """Multiply the image."""
    layout.style("fe_amplify", title=f"gain {gain:.2f}")
    return img * gain


@interactive(split=(0.5, [0.1, 0.9]))
def fe_split(img, split=0.5):
    cut = int(split * img.shape[1])
    return img[:, :cut], img[:, cut:]


@interactive(level=(0.2, [0.0, 1.0]))
def fe_constant(level=0.2):
    return np.full((SIZE, SIZE), level)


@interactive(fail=Control(False))
def fe_fragile(img, fail=False):
    if fail:
        raise ValueError("asked to fail")
    return img


@interactive(frequency=(1.0, [0.0, 10.0]))
def fe_get_curve(frequency=1.0):
    x = np.linspace(0, 1, 20)
    return Curve([[x, np.sin(2 * np.pi * frequency * x)]])


def fe_pipeline(img):
    amplified = fe_amplify(img)
    return [amplified]


def white():
    return np.ones((SIZE, SIZE, 3))


def gain_control():
    return Control.get_controls(fe_amplify)["gain"]


def test_decorated_filter_stays_a_plain_function():
    assert fe_amplify.__name__ == "fe_amplify" and fe_amplify.__doc__ == "Multiply the image."
    assert pickle.loads(pickle.dumps(fe_amplify)) is fe_amplify
    for name in ("snapshot", "sweep", "describe", "summary", "interact"):
        assert callable(getattr(fe_amplify, name))


def test_filter_snapshot_to_file_and_array(tmp_path):
    path = fe_amplify.snapshot(tmp_path / "amp.png", white(), gain=1.0)
    assert path.is_file()
    dark = fe_amplify.snapshot(None, white(), gain=0.0, caption=False)
    bright = fe_amplify.snapshot(None, white(), gain=1.0, caption=False)
    assert dark.mean() < bright.mean()
    assert fe_amplify.snapshot(None, inputs={"img": white()}).ndim == 3


def test_filter_snapshot_uses_layout_style_and_multi_outputs():
    single = fe_amplify.snapshot(None, white(), caption=False)
    double = fe_split.snapshot(None, white(), caption=False)
    assert double.shape[1] > single.shape[1]
    data = fe_split.describe(white())
    assert data["outputs"] == ["fe_split[0]", "fe_split[1]"]


def test_filter_sweep():
    rgb = fe_amplify.sweep(None, white(), gain=[0.0, 1.0], caption=False)
    left, right = rgb[:, : rgb.shape[1] // 2], rgb[:, rgb.shape[1] // 2 :]
    assert left.mean() < right.mean()
    assert fe_amplify.sweep(None, white(), steps={"gain": 3}).ndim == 3


def test_filter_without_inputs():
    assert fe_constant.snapshot(None, level=0.9).mean() > fe_constant.snapshot(None, level=0.0).mean()
    assert fe_constant.describe()["outputs"] == ["fe_constant"]


def test_filter_describe_and_summary():
    data = fe_amplify.describe()
    assert data["inputs"] == ["img"] and data["outputs"] is None  # no dry run without inputs
    assert data["filters"][0]["doc"] == "Multiply the image."
    assert data["controls"][0]["name"] == "gain" and data["controls"][0]["range"] == [0.0, 1.0]
    assert "fe_amplify(img) -> fe_amplify" in fe_amplify.summary(white())


def test_wrong_inputs_raise():
    with pytest.raises(TypeError, match="expects 1 input"):
        fe_amplify.snapshot(None)
    with pytest.raises(TypeError, match="misses"):
        fe_amplify.snapshot(None, inputs={"image": white()})
    with pytest.raises(TypeError, match=r"snapshot\(\) got unexpected keyword argument\(s\) 'gian'"):
        fe_amplify.snapshot(None, white(), gian=1.0)


def test_filter_error_propagates_and_controls_are_restored():
    ctrl = Control.get_controls(fe_fragile)["fail"]
    with pytest.raises(FilterError):
        fe_fragile.snapshot(None, white(), fail=True)
    assert ctrl.value is False
    ctrl.value = True
    try:
        with pytest.raises(FilterError):  # failing dry run is a FilterError too
            fe_fragile.snapshot(None, white())
        assert ctrl.value is True
    finally:
        ctrl.value = False


def test_filter_calls_leave_the_pipeline_untouched():
    pipe = interactive_pipeline(gui=None)(fe_pipeline)
    ctrl = pipe.controls[0]  # the pipeline's own clone of the declared control
    assert ctrl is not gain_control() and gain_control().filter_to_connect is None
    pipe_filter = ctrl.filter_to_connect
    assert pipe_filter is pipe.filters[0]
    ctrl.update(0.25)  # tuned in the pipeline
    fe_amplify.snapshot(None, white(), gain=1.0)
    fe_amplify.sweep(None, white(), gain=[0.1, 0.9])
    fe_amplify.describe(white())
    assert ctrl.filter_to_connect is pipe_filter
    assert ctrl.parameter_name_to_connect == "gain"
    assert ctrl.value == 0.25
    np.testing.assert_allclose(pipe(white())[0], white() * 0.25)
    ctrl.update(0.75)  # the control still drives the pipeline filter
    assert pipe_filter.values["gain"] == 0.75
    ctrl.update(0.5)


def test_issue_21_explicit_keyword_is_not_ignored():
    """get_curve_2(frequency=5.) used to return the curve for the control value."""
    curve = fe_get_curve(frequency=5.0)
    expected = np.sin(2 * np.pi * 5.0 * np.linspace(0, 1, 20))
    np.testing.assert_allclose(curve.curves[0].y, expected)
    default = fe_get_curve()
    np.testing.assert_allclose(default.curves[0].y, np.sin(2 * np.pi * np.linspace(0, 1, 20)))


def test_interact_opens_the_gui_on_one_filter(monkeypatch):
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)
    ctrl = gain_control()
    before = (ctrl.filter_to_connect, ctrl.value)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # Agg: plt.show() is a no-op
        results = fe_amplify.interact(white(), gui="mpl")
    plt.close("fe_amplify")
    assert len(results) == 1
    np.testing.assert_allclose(np.asarray(results[0]).squeeze(), white() * 0.5)
    assert (ctrl.filter_to_connect, ctrl.value) == before


@interactive(gain=(0.5, [0.0, 1.0]))
def fe_with_context(img, gain=0.5):
    context["mean"] = float(img.mean())
    return img * gain * context.get("scale", 1.0)


def test_filters_using_the_context_proxy():
    assert fe_with_context.snapshot(None, white()).ndim == 3
    assert fe_with_context.sweep(None, white(), gain=[0.1, 0.9]).ndim == 3
    assert fe_with_context.describe(white())["outputs"] == ["fe_with_context"]
