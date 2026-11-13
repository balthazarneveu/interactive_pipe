"""Call-time validation: unknown keywords, out-of-range values, wrong number of inputs."""

import logging

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control, RangeControl, TimeControl
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def call_gain(img, gain=1.0):
    return img * gain


@interactive()
def call_offset(img, offset=0.0):
    return img + offset


def call_pipeline(img):
    out = call_gain(img)
    shifted = call_offset(out)
    return shifted


def call_two_inputs(img, mask):
    out = call_gain(img)
    return out, mask


class DummyGUI(InteractivePipeGUI):
    """Backend-free GUI: run() just runs the pipeline."""

    def init_app(self, **kwargs):
        pass

    def run(self):
        return self.pipeline.run()


@pytest.fixture
def pipe():
    return HeadlessPipeline.from_function(call_pipeline)


# ------------------------------------------------------------ unknown kwargs


def test_unknown_keyword_raises_type_error_with_suggestion(pipe):
    with pytest.raises(TypeError) as exc_info:
        pipe(np.ones(3), gian=2.0)
    message = str(exc_info.value)
    assert "pipeline 'call_pipeline' got unexpected keyword argument(s) 'gian'" in message
    assert "Available parameters: gain, offset" in message
    assert "'gian' -> 'gain'" in message


def test_unknown_keyword_changes_nothing(pipe):
    pipe(np.ones(3), gain=2.0)
    with pytest.raises(TypeError):
        pipe(np.ones(3), gain=3.0, gian=2.0)
    assert pipe.parameters["call_gain"]["gain"] == 2.0


def test_known_and_reserved_keywords_still_work(pipe):
    np.testing.assert_allclose(pipe(np.ones(3), gain=2.0, offset=1.0)[0], 3.0)
    np.testing.assert_allclose(pipe(inputs={"img": np.ones(3)})[0], 3.0)
    out = pipe(np.ones(3), parameters={"call_gain": {"gain": 0.5}}, context={"anything": 1})
    np.testing.assert_allclose(out[0], 1.5)


def test_gui_call_rejects_unknown_keyword_and_accepts_reserved_ones(pipe):
    gui = DummyGUI(pipeline=pipe, name="dummy")
    with pytest.raises(TypeError, match="'gian' -> 'gain'"):
        gui(np.ones(3), gian=2.0)
    np.testing.assert_allclose(gui(np.ones(3), gain=2.0)[0], 2.0)
    np.testing.assert_allclose(gui(inputs={"img": np.ones(3)}, context={"k": 1})[0], 2.0)


# --------------------------------------------------------- out-of-range clamp


def test_out_of_range_value_is_clamped_with_a_warning(pipe, caplog):
    with caplog.at_level(logging.WARNING):
        out = pipe(np.ones(3), gain=99)
    np.testing.assert_allclose(out[0], 3.0)  # clamped, not an exception
    assert pipe.controls[0].value == 3.0
    assert "Control 'gain': value 99.0 is outside its range [0.0, 3.0], clamped to 3.0" in caplog.text


def test_in_range_and_float_noise_values_do_not_warn(caplog):
    ctrl = Control(0.5, [0.0, 1.0], name="noise")
    with caplog.at_level(logging.WARNING):
        ctrl.value = 0.7
        ctrl.value = 1.0 + 1e-12
    assert caplog.text == ""


def test_range_control_clamp_warns(caplog):
    ctrl = RangeControl((0.2, 0.8), [0.0, 1.0], name="window")
    with caplog.at_level(logging.WARNING):
        ctrl.value = (0.1, 1.5)
    assert ctrl.value == (0.1, 1.0)
    assert "Control 'window'" in caplog.text and "clamped to (0.1, 1.0)" in caplog.text


def test_time_control_running_past_its_range_stays_quiet(caplog):
    ctrl = TimeControl(name="t")
    with caplog.at_level(logging.WARNING):
        ctrl.value = 4000.0
    assert ctrl.value == 3600.0
    assert caplog.text == ""


# ------------------------------------------------------------ input count


def test_missing_input_names_the_expected_inputs(pipe):
    with pytest.raises(ValueError, match=r"^pipeline 'call_pipeline' expects 1 input \(img\), got 0$"):
        pipe()


def test_too_many_inputs(pipe):
    with pytest.raises(ValueError, match=r"pipeline 'call_pipeline' expects 1 input \(img\), got 2"):
        pipe(np.ones(3), np.ones(3))


def test_dict_inputs_missing_a_key():
    pipe = HeadlessPipeline.from_function(call_two_inputs)
    with pytest.raises(ValueError, match=r"expects 2 inputs \(img, mask\), the inputs dict is missing mask"):
        pipe(inputs={"img": np.ones(3)})


def test_gui_call_with_missing_input(pipe):
    gui = DummyGUI(pipeline=pipe, name="dummy")
    with pytest.raises(ValueError, match=r"expects 1 input \(img\), got 0"):
        gui()
