"""pipeline(...), snapshot, sweep and the filter entry points accept the same
parameter spellings and reject unknown ones with the same message."""

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMG = np.ones((2, 2))


@interactive(gain=(1.0, [0.0, 3.0]))
def pn_amplify(img, gain=1.0):
    return img * gain


@interactive(gain=(1.0, [0.0, 3.0]), exposure=(0.0, [-1.0, 1.0], "Exposure"))
def pn_blend(img, gain=1.0, exposure=0.0):
    return img * gain + exposure


def names_pipeline(img):
    a = pn_amplify(img)
    b = pn_blend(a)
    return b


@pytest.fixture
def pipe():
    return HeadlessPipeline.from_function(names_pipeline)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"gain": 2.0}, 4.0),  # bare name: every filter having it
        ({"pn_amplify.gain": 2.0}, 2.0),  # control name (disambiguated) / filter.param
        ({"pn_blend.gain": 3.0}, 3.0),
        ({"Exposure": 0.5}, 1.5),  # explicit control name
        ({"pn_blend.exposure": 0.5}, 1.5),  # filter.param of an explicitly named control
    ],
)
def test_call_accepts_the_snapshot_spellings(pipe, kwargs, expected):
    assert pipe(IMG, **kwargs)[0][0, 0] == pytest.approx(expected)


@pytest.mark.parametrize(
    "kwargs, expected",
    [({"pn_amplify.gain": 2.0}, 2.0), ({"Exposure": 0.5}, 1.5), ({"gain": 2.0}, 4.0)],
)
def test_snapshot_accepts_the_same_spellings(pipe, kwargs, expected, tmp_path):
    from interactive_pipe.headless.explore import run_snapshot

    reset = {"gain": 1.0, "Exposure": 0.0}  # registered controls are shared between tests
    pipe(IMG * 0.1, **reset)
    _, result = run_snapshot(pipe, tmp_path / "s.png", IMG * 0.1, **kwargs)
    assert result[0][0, 0] == pytest.approx(pipe(IMG * 0.1, **kwargs)[0][0, 0])


def _message(callable_, *args, exception=TypeError, **kwargs):
    with pytest.raises(exception) as info:
        callable_(*args, **kwargs)
    return str(info.value)


def test_same_message_style_everywhere(pipe, tmp_path):
    call = _message(pipe, IMG, gian=2.0)
    snap = _message(pipe.snapshot, tmp_path / "s.png", IMG, gian=2.0)
    sweep = _message(pipe.sweep, tmp_path / "w.png", IMG, gian=[1.0, 2.0])
    assert call.startswith("pipeline 'names_pipeline' got unexpected keyword argument(s) 'gian'.")
    assert snap.startswith("snapshot() got unexpected keyword argument(s) 'gian'.")
    assert sweep.startswith("sweep() got unexpected keyword argument(s) 'gian'.")
    for message in (call, snap, sweep):
        assert "Available parameters: Exposure, exposure, gain" in message
        assert "Did you mean 'gian' -> 'gain'?" in message
        assert "write 'filter.parameter'" in message
    assert "(reserved keywords: inputs, parameters, context)" in call


def test_unknown_filter_parameter_spelling(pipe):
    message = _message(pipe, IMG, **{"pn_amplify.gian": 2.0})
    assert "'pn_amplify.gian' -> 'pn_amplify.gain'" in message


def test_parameters_dict_is_validated_before_running(pipe):
    pipe(IMG, gain=2.0)
    message = _message(pipe, IMG, parameters={"pn_amplify": {"gian": 1.0}}, exception=ValueError)
    assert "filter 'pn_amplify' has no parameter 'gian' (did you mean 'gain'?)" in message
    message = _message(pipe, IMG, parameters={"pn_amplfy": {"gain": 1.0}}, exception=ValueError)
    assert "no filter 'pn_amplfy' (did you mean 'pn_amplify'?)" in message
    message = _message(pipe, IMG, parameters={"pn_amplify": 2.0}, exception=ValueError)
    assert "parameters['pn_amplify'] must be a dict" in message
    # nothing changed by the rejected calls
    assert pipe.parameters["pn_amplify"]["gain"] == 2.0
    assert pipe(IMG, parameters={"pn_amplify": {"gain": 0.5}})[0][0, 0] == pytest.approx(1.0)


def test_parameters_dict_errors_are_the_same_through_a_gui_call():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=HeadlessPipeline.from_function(names_pipeline), name="pn gui")
    try:
        with pytest.raises(ValueError, match=r"has no parameter 'gian' \(did you mean 'gain'\?\)"):
            gui(IMG, parameters={"pn_amplify": {"gian": 1.0}})
    finally:
        gui.close()
