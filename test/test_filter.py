import numpy as np
import pytest

from interactive_pipe.core.filter import FilterCore, PureFilter


input_image = np.array([[1, 2, 3], [4, 5, 6]])

# -----------------------------------------------------
# pure class approach to define a filter
# -----------------------------------------------------


class MadFilter(PureFilter):
    def apply(self, img, coeff=-1, bias=-6):
        mad_res = img*coeff+bias
        return [mad_res]


def test_pure_filter_no_func():
    filt_instance = MadFilter()
    res = filt_instance.run(input_image)
    assert (res == (-1*input_image - 6)).all()
    assert filt_instance.name == "MadFilter"
    # name of the class is used here by default for the filter instance name

# -----------------------------------------------------
# functional way of defining a filter
# -----------------------------------------------------


def mad(img, coeff=1, bias=-6):
    mad_res = img*coeff+bias
    return [mad_res]


def test_pure_filter_no_params():
    # Default parameters are used. This is similar to executing the mad function
    filt = PureFilter(apply_fn=mad)
    res = filt.run(input_image)
    assert (res == (input_image - 6)).all()
    assert (res == mad(input_image)[0]).all()
    # Modify parameters and re-execute
    filt.values = {"coeff": 2, "bias": 8}
    res = filt.run(input_image)
    assert (res == (2*input_image + 8)).all()


def test_pure_filter_using_params():
    # Default parameters are manually defined.
    # Pay attention when you type your dictionary keys,
    # it should match with the keyword args
    # This is one of the motivation of using AutoFilter
    filt_forced_params = PureFilter(
        apply_fn=mad, default_params={"coeff": 2, "bias": 8})
    res = filt_forced_params.run(input_image)
    assert (res == (2*input_image + 8)).all()
    assert filt_forced_params.name == "mad"
    # name of the apply_fn is used here by default for the filter instance name


# -----------------------------------------------------
# functional way of defining a filter - use context
# -----------------------------------------------------

def mad_with_context(img, global_params={}, coeff=1, bias=-6):
    mad_res = (img*coeff+bias)/global_params["ratio"]
    global_params["mean"] = mad_res.mean()  # update shared global context
    return [mad_res]


def test_pure_filter_global_params():
    # Default parameters are used. This is similar to executing the mad function
    context = {"ratio": 100}
    filt = PureFilter(apply_fn=mad_with_context, default_params={
                      "coeff": 2, "bias": 8})
    filt.global_params = context
    res = filt.run(input_image)
    expected_output = (2*input_image + 8)/100
    assert (res == expected_output).all()
    assert context["mean"] == expected_output.mean()
