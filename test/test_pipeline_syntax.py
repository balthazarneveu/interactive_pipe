"""Strict static analysis of pipeline functions (PipelineSyntaxError).

Every top-level statement of a pipeline body is validated: unsupported
constructs raise an error naming the line and the fix instead of building a
pipeline that silently runs something else.
"""

import inspect
import types

import numpy as np
import pytest

import interactive_pipe
from interactive_pipe import PipelineSyntaxError, interactive
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.graph import get_call_graph
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive()
def amplify(img, gain=2.0):
    return img * gain


@interactive()
def blur(img, radius=1):
    return img + radius


def build(func):
    return HeadlessPipeline.from_function(func)


def offending_line(func, needle):
    """Absolute line number of the first source line of func containing needle."""
    lines, start = inspect.getsourcelines(func)
    for offset, line in enumerate(lines):
        if needle in line:
            return start + offset
    raise AssertionError(f"{needle!r} not found")


# ----------------------------------------------------------------- rejected


def pipe_if(img, flag=True):
    out = amplify(img)
    if flag:
        out = blur(out)
    return out


def pipe_for(img):
    for _ in range(3):
        img = blur(img)
    return img


def pipe_while(img):
    while True:
        img = blur(img)
    return img


def pipe_with(img):
    with open("x") as handle:  # noqa: F841
        img = blur(img)
    return img


def pipe_try(img):
    try:
        img = blur(img)
    except ValueError:
        pass
    return img


def pipe_arithmetic(img):
    a = amplify(img)
    b = a * 2
    return b


def pipe_augassign(img):
    a = amplify(img)
    a += 1
    return a


def pipe_comprehension(img):
    outs = [blur(img) for _ in range(2)]
    return outs


def pipe_lambda(img):
    scale = lambda x: x * 2  # noqa: E731
    return scale


def pipe_two_returns(img):
    a = amplify(img)
    return a
    return img


def pipe_starred(*imgs):
    out = blur(*imgs)
    return out


def pipe_unknown_name(img):
    out = amplfy(img)  # noqa: F821
    return out


def pipe_builtin(img):
    out = print(img)
    return out


def pipe_return_expression(img):
    a = amplify(img)
    return a + 1


def pipe_subscript_target(img, store):
    store["x"] = amplify(img)
    return img


def pipe_bad_attribute(img):
    out = np.abss(img)
    return out


REJECTED = [
    (pipe_if, "`if`", "inside a filter", "if flag:"),
    (pipe_for, "`for`", "loop inside a filter", "for _ in range(3):"),
    (pipe_while, "`while`", "loop inside a filter", "while True:"),
    (pipe_with, "`with`", "inside a filter", "with open"),
    (pipe_try, "`try`", "inside the filter", "try:"),
    (pipe_arithmetic, "arithmetic", "wrap it in a filter", "b = a * 2"),
    (pipe_augassign, "augmented assignment", "wrap it in a filter", "a += 1"),
    (pipe_comprehension, "comprehension", "loop inside a filter", "outs = ["),
    (pipe_lambda, "lambda", "named filter", "scale = lambda"),
    (pipe_two_returns, "after the `return`", "returns once", "return img"),
    (pipe_starred, "star-unpacking", "explicitly", "out = blur(*imgs)"),
    (pipe_unknown_name, "'amplfy' is not defined", "did you mean 'amplify'", "out = amplfy(img)"),
    (pipe_builtin, "builtin", "inside a filter", "out = print(img)"),
    (pipe_return_expression, "arithmetic", "wrap it in a filter", "return a + 1"),
    (pipe_subscript_target, "variable names", "plain names", 'store["x"]'),
    (pipe_bad_attribute, "has no attribute 'abss'", "'abs'", "np.abss"),
]


@pytest.mark.parametrize("func, reason, hint, line", REJECTED, ids=[case[0].__name__ for case in REJECTED])
def test_rejected_construct_names_line_and_fix(func, reason, hint, line):
    with pytest.raises(PipelineSyntaxError) as exc_info:
        build(func)
    message = str(exc_info.value)
    assert f"pipeline '{func.__name__}'" in message
    assert __file__ in message
    assert f"line {offending_line(func, line)}" in message
    assert line in message  # the offending source line is quoted
    assert reason in message
    assert hint in message
    assert exc_info.value.lineno == offending_line(func, line)


def test_pipeline_syntax_error_is_a_value_error_and_exported():
    assert issubclass(PipelineSyntaxError, ValueError)
    assert interactive_pipe.PipelineSyntaxError is PipelineSyntaxError
    with pytest.raises(ValueError):
        build(pipe_if)


# ----------------------------------------------------------------- accepted


def pipe_documented(img):
    """Docstring."""
    pass
    a = amplify(img)
    "a string comment"
    ...
    blur(a)
    return [[img, a], [None, a]]


def test_docstring_pass_ellipsis_bare_call_and_nested_return_accepted():
    pipe = build(pipe_documented)
    assert [filt.name for filt in pipe.filters] == ["amplify", "blur"]
    assert pipe.outputs == [["img", "a"], ["a"]]


def test_pipeline_defined_in_an_indented_scope():
    @interactive()
    def local_gain(img, gain=3.0):
        return img * gain

    def local_pipeline(img):
        out = local_gain(img)
        return out

    pipe = build(local_pipeline)
    np.testing.assert_allclose(pipe(np.ones(3))[0], 3.0)


def test_indented_pipeline_with_unindented_docstring_lines():
    def local_pipeline(img):
        """Docstring whose second line is
        less indented than the body."""
        out = amplify(img)
        return out

    pipe = build(local_pipeline)
    np.testing.assert_allclose(pipe(np.ones(3))[0], 2.0)


def test_closure_variable_shadows_module_global():
    @interactive()
    def amplify(img, gain=10.0):  # noqa: F811 - shadows the module-level filter on purpose
        return img * gain

    def local_pipeline(img):
        out = amplify(img)
        return out

    pipe = build(local_pipeline)
    np.testing.assert_allclose(pipe(np.ones(3))[0], 10.0)


def pipe_numpy(img):
    out = np.abs(img)
    return out


def test_dotted_module_call_is_resolved_on_the_module():
    pipe = build(pipe_numpy)
    assert pipe.filters[0].name == "abs"
    np.testing.assert_allclose(pipe(-np.ones(3))[0], 1.0)


lib = types.SimpleNamespace(tools=types.SimpleNamespace(blur=blur))


def pipe_attribute_chain(img):
    out = lib.tools.blur(img)
    return out


def test_attribute_chain_call_resolves_the_chain():
    pipe = build(pipe_attribute_chain)
    assert pipe.filters[0].name == "blur"
    np.testing.assert_allclose(pipe(np.zeros(3))[0], 1.0)


def offset(img, delta=5):
    return img + delta


offset_filter = FilterCore(apply_fn=offset)


def pipe_filter_instance(img):
    out = offset_filter(img)
    return out


def test_filter_instance_path():
    pipe = build(pipe_filter_instance)
    assert pipe.filters[0] is offset_filter
    assert pipe.filters[0].name == "offset_filter"
    np.testing.assert_allclose(pipe(np.zeros(3))[0], 5.0)


def pipe_two_stages(img):
    a = amplify(img)
    b = blur(a)
    return a, b


def test_routing_by_indexes_path():
    pipe = HeadlessPipeline.from_function(pipe_two_stages, _routing_by_indexes=True)
    assert pipe.inputs_routing == [0]
    assert pipe.outputs == [1, 2]
    out_a, out_b = pipe(np.ones(3))
    np.testing.assert_allclose(out_a, 2.0)
    np.testing.assert_allclose(out_b, 3.0)


def test_get_call_graph_accepts_explicit_global_context():
    graph = get_call_graph(pipe_two_stages, global_context={"amplify": amplify, "blur": blur})
    assert [node["function_name"] for node in graph["call_graph"]] == ["amplify", "blur"]
    with pytest.raises(PipelineSyntaxError, match="'blur' is not defined"):
        get_call_graph(pipe_two_stages, global_context={"amplify": amplify})


# ------------------------------------------- B: literal kwargs, nested calls


@interactive(gain=(1.0, [0.0, 3.0]))
def controlled_gain(img, gain=1.0):
    return img * gain


def pipe_literal_kwarg(img):
    out = amplify(img, gain=2.5)
    return out


def test_literal_keyword_argument_sets_the_parameter():
    pipe = build(pipe_literal_kwarg)
    assert pipe.parameters["amplify"]["gain"] == 2.5
    np.testing.assert_allclose(pipe(np.ones(3))[0], 2.5)


def pipe_literal_kwarg_on_control(img):
    out = controlled_gain(img, gain=2.5)
    return out


def pipe_plain_control(img):
    out = controlled_gain(img)
    return out


def test_literal_keyword_argument_becomes_the_instance_control_default():
    from interactive_pipe.headless.control import Control

    registered = Control.get_controls(controlled_gain)["gain"]
    pipe = build(pipe_literal_kwarg_on_control)
    (ctrl,) = pipe.controls
    assert ctrl is not registered
    assert ctrl.value_default == 2.5 and ctrl.value == 2.5
    assert ctrl.name == "gain"
    np.testing.assert_allclose(pipe(np.ones(3))[0], 2.5)
    # the shared registered control does not leak into other pipelines
    assert registered.value_default == 1.0
    plain = build(pipe_plain_control)
    assert plain.controls[0].value_default == 1.0
    np.testing.assert_allclose(plain(np.ones(3))[0], 1.0)
    # rebuilding gives the same result
    assert build(pipe_literal_kwarg_on_control).controls[0].value_default == 2.5


def pipe_literal_out_of_range(img):
    out = controlled_gain(img, gain=99.0)
    return out


def pipe_literal_wrong_type(img):
    out = controlled_gain(img, gain="high")
    return out


def pipe_unknown_kwarg(img):
    out = amplify(img, gian=2.0)
    return out


def pipe_non_literal_kwarg(img):
    out = amplify(img, gain=np.pi)
    return out


def pipe_input_as_kwarg(img):
    out = amplify(img=img)
    return out


def pipe_positional_literal(img):
    out = blur(img, 3)
    return out


def pipe_expression_argument(img):
    out = blur(img * 2)
    return out


REJECTED_B = [
    (pipe_literal_out_of_range, "outside the range [0.0, 3.0]", "control", "gain=99.0"),
    (pipe_literal_wrong_type, "expects a number", "control", 'gain="high"'),
    (pipe_unknown_kwarg, "'gian' is not a parameter of filter 'amplify'", "did you mean 'gain'", "gian=2.0"),
    (pipe_non_literal_kwarg, "must be a literal", "control", "gain=np.pi"),
    (pipe_input_as_kwarg, "'img' is an input of filter 'amplify'", "positionally", "amplify(img=img)"),
    (pipe_positional_literal, "positional literal", "`radius=3`", "blur(img, 3)"),
    (pipe_expression_argument, "arithmetic", "wrap it in a filter", "blur(img * 2)"),
]


@pytest.mark.parametrize("func, reason, hint, line", REJECTED_B, ids=[case[0].__name__ for case in REJECTED_B])
def test_rejected_call_arguments_name_line_and_fix(func, reason, hint, line):
    test_rejected_construct_names_line_and_fix(func, reason, hint, line)


def pipe_nested(img):
    out = blur(amplify(img))
    return out


def test_nested_call_is_hoisted_into_its_own_filter():
    pipe = build(pipe_nested)
    assert [filt.name for filt in pipe.filters] == ["amplify", "blur"]
    assert pipe.filters[0].outputs == ["amplify(img)"]
    assert pipe.filters[1].inputs == ["amplify(img)"]
    np.testing.assert_allclose(pipe(np.ones(3))[0], 3.0)


def pipe_return_call(img):
    return amplify(img)


def pipe_return_mixed(img):
    a = amplify(img, gain=3.0)
    return [[a, blur(a)], [blur(amplify(img)), None]]


def test_return_of_a_call_is_hoisted():
    pipe = build(pipe_return_call)
    assert pipe.outputs == ["amplify(img)"]
    np.testing.assert_allclose(pipe(np.ones(3))[0], 2.0)


def test_calls_in_a_nested_return_are_hoisted_with_unique_names():
    pipe = build(pipe_return_mixed)
    assert pipe.outputs == [["a", "blur(a)"], ["blur(amplify(img))"]]
    assert [filt.name for filt in pipe.filters] == ["amplify", "blur", "amplify_1", "blur_1"]
    rows = pipe(np.ones(3))
    np.testing.assert_allclose(rows[0][0], 3.0)
    np.testing.assert_allclose(rows[0][1], 4.0)
    np.testing.assert_allclose(rows[1][0], 3.0)


def pipe_same_nested_call_twice(img):
    a = blur(amplify(img))
    b = blur(amplify(img))
    return a, b


def test_identical_nested_calls_get_distinct_names():
    pipe = build(pipe_same_nested_call_twice)
    assert pipe.filters[0].outputs == ["amplify(img)"]
    assert pipe.filters[2].outputs == ["amplify(img) #2"]
    assert pipe.filters[3].inputs == ["amplify(img) #2"]


@interactive(window=interactive_pipe.RangeControl((0.2, 0.8), [0.0, 1.0]))
def crop_window(img, window=(0.2, 0.8)):
    return img * (window[1] - window[0])


def pipe_range_literal(img):
    out = crop_window(img, window=(0.0, 0.5))
    return out


def pipe_range_literal_out_of_range(img):
    out = crop_window(img, window=(0.0, 1.5))
    return out


def test_literal_keyword_argument_on_a_range_control():
    pipe = build(pipe_range_literal)
    assert pipe.controls[0].value == (0.0, 0.5)
    np.testing.assert_allclose(pipe(np.ones(3))[0], 0.5)
    with pytest.raises(PipelineSyntaxError, match="outside the range"):
        build(pipe_range_literal_out_of_range)
