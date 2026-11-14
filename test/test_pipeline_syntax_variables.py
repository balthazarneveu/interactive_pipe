"""Build-time checks on the variables and inputs used in a pipeline body, and atomic parameter updates."""

import functools

import numpy as np
import pytest

from interactive_pipe import PipelineSyntaxError, interactive, interactive_pipeline
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMG = np.full((4, 4, 3), 0.25)


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0):
    return img * gain


@interactive(sigma=(1, [0, 5]))
def offset(img, sigma=1):
    return img + sigma


def stack(*imgs):
    return sum(imgs)


def blend(a, b, alpha=0.5):
    return (1 - alpha) * a + alpha * b


doubled = functools.partial(amplify, gain=2.0)


def test_undefined_input_variable_raises_with_suggestion():
    def pipe(img):
        amplified = amplify(img)  # noqa: F841
        out = offset(amplifed)  # noqa: F821
        return out

    with pytest.raises(PipelineSyntaxError, match="'amplifed' is not a variable of the pipeline") as excinfo:
        HeadlessPipeline.from_function(pipe)
    assert "amplified" in str(excinfo.value)


def test_variable_used_before_its_filter_call_raises():
    def pipe(img):
        out = offset(amplified)  # noqa: F821
        amplified = amplify(img)
        return out, amplified

    with pytest.raises(PipelineSyntaxError, match="'amplified' is not a variable"):
        HeadlessPipeline.from_function(pipe)


def test_undefined_returned_variable_raises():
    def pipe(img):
        amplified = amplify(img)
        return amplified, other  # noqa: F821

    with pytest.raises(PipelineSyntaxError, match="'other' is returned but is not a variable"):
        HeadlessPipeline.from_function(pipe)


def test_missing_filter_input_raises_at_build_time():
    def pipe(img):
        out = blend(img)
        return out

    with pytest.raises(PipelineSyntaxError, match=r"filter 'blend' expects 2 inputs \(a, b\), got 1: missing b"):
        HeadlessPipeline.from_function(pipe)


def test_var_positional_filter_accepts_any_input_count():
    def pipe(img):
        amplified = amplify(img)
        out = stack(img, amplified, img)
        return out

    (out,) = HeadlessPipeline.from_function(pipe)(IMG)
    np.testing.assert_allclose(out, 0.75)


def test_generator_filter_without_inputs_still_builds():
    def make():
        return IMG

    def pipe():
        out = make()
        return out

    (out,) = HeadlessPipeline.from_function(pipe)()
    np.testing.assert_allclose(out, IMG)


def test_method_call_on_pipeline_variable_raises():
    def pipe(img):
        out = img.copy()
        return out

    with pytest.raises(PipelineSyntaxError, match="'img' is a variable of the pipeline"):
        HeadlessPipeline.from_function(pipe)


def test_pipeline_arguments_with_defaults_are_variables():
    def pipe(img, other=None):
        out = amplify(img)
        return out, img

    out, same = HeadlessPipeline.from_function(pipe)(IMG)
    np.testing.assert_allclose(out, same)


def test_functools_partial_is_a_filter_without_controls():
    def pipe(img):
        out = doubled(img)
        return out

    pipeline = HeadlessPipeline.from_function(pipe)
    assert pipeline.controls == []
    np.testing.assert_allclose(pipeline(IMG)[0], 0.5)


def test_lambda_pipeline_has_a_clear_error():
    with pytest.raises(ValueError, match="must be a regular `def` function"):
        interactive_pipeline(gui=None)(lambda img: amplify(img))


def test_pipeline_without_source_has_a_clear_error():
    namespace = {"amplify": amplify}
    exec("def dyn(img):\n    out = amplify(img)\n    return out\n", namespace)
    with pytest.raises(ValueError, match="cannot read the source code of the pipeline function"):
        HeadlessPipeline.from_function(namespace["dyn"])


def _pipeline():
    def pipe(img):
        amplified = amplify(img)
        out = offset(amplified)
        return out

    return HeadlessPipeline.from_function(pipe)


def test_unknown_parameter_in_parameters_dict_raises_with_suggestion():
    pipeline = _pipeline()
    with pytest.raises(ValueError, match=r"filter 'amplify' has no parameter 'gian' \(did you mean 'gain'\?\)"):
        pipeline(IMG, parameters={"amplify": {"gian": 2.0}})


def test_rejected_parameters_leave_the_pipeline_usable():
    pipeline = _pipeline()
    before = pipeline.parameters
    with pytest.raises(ValueError):
        pipeline(IMG, parameters={"offset": {"sigma": 3}, "amplify": {"gian": 2.0}})
    assert pipeline.parameters == before  # nothing applied, not even the valid entry
    np.testing.assert_allclose(pipeline(IMG, gain=2.0)[0], 1.5)


def test_unknown_filter_in_parameters_dict_suggests_a_name():
    with pytest.raises(ValueError, match="did you mean 'amplify'"):
        _pipeline()(IMG, parameters={"amplif": {"gain": 2.0}})
