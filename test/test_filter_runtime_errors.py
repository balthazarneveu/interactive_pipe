"""Runtime mistakes inside filters: wrong number of returned values, a forgotten
``return``, a context key read before it is written, and the cache after a
failing run."""

import numpy as np
import pytest

from interactive_pipe import context, interactive
from interactive_pipe.core.engine import FilterError
from interactive_pipe.core.filter import FilterCore, FilterOutputError
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMG = np.ones((2, 2))
CACHE_MODES = [False, True, "graph"]


@interactive()
def rt_one(img):
    return img


@interactive()
def rt_two(img):
    return img, img * 2


@interactive()
def rt_three(img):
    return img, img, img


@interactive()
def rt_forgot_return(img):
    img * 2  # noqa: B018 - the mistake under test


@interactive()
def rt_explicit_none(img):
    return None


@interactive()
def rt_side_effect(img):
    context["seen"] = True


def two_names_from_one(img):
    a, b = rt_one(img)
    return a, b


def one_name_from_two(img):
    a = rt_two(img)
    return a


def two_names_from_three(img):
    a, b = rt_three(img)
    return a, b


def assigns_forgotten_return(img):
    a = rt_forgot_return(img)
    return a


def assigns_explicit_none(img):
    a = rt_explicit_none(img)
    return a


def statement_without_assignment(img):
    rt_side_effect(img)
    a = rt_one(img)
    return a


def exact_unpacking(img):
    a, b = rt_two(img)
    return a, b


def _error(pipe, cache):
    with pytest.raises(FilterError) as info:
        HeadlessPipeline.from_function(pipe, cache=cache)(IMG)
    assert isinstance(info.value.original_error, FilterOutputError)
    return str(info.value)


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_unpacking_two_names_from_one_value(cache):
    message = _error(two_names_from_one, cache)
    assert "filter 'rt_one' returned a single ndarray but the pipeline unpacks 2 values" in message
    assert "pipeline 'two_names_from_one'" in message and "a, b = rt_one(img)" in message
    assert "Fix:" in message
    assert "Traceback (user code only)" not in message  # no framework frame shown


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_one_name_for_two_values_is_an_error(cache):
    # used to keep the first value silently
    message = _error(one_name_from_two, cache)
    assert "filter 'rt_two' returned 2 values but the pipeline assigns 1 name(s)" in message
    assert "a = rt_two(img)" in message
    assert "out0, out1 = rt_two(img)" in message


rt_split = rt_two  # the pipeline calls the filter by another name


def one_name_from_alias(img):
    a = rt_split(img)
    return a


def test_alias_names_the_function_too():
    message = _error(one_name_from_alias, False)
    assert "filter 'rt_split' (function 'rt_two') returned 2 values but the pipeline assigns 1 name(s)" in message
    assert "out0, out1 = rt_split(img)" in message  # the fix uses the name of the pipeline line


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_two_names_for_three_values_is_an_error(cache):
    message = _error(two_names_from_three, cache)
    assert "returned 3 values but the pipeline assigns 2 name(s)" in message


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_forgotten_return(cache):
    message = _error(assigns_forgotten_return, cache)
    assert "filter 'rt_forgot_return' returned None: the function has no `return` statement" in message
    assert "add `return <result>`" in message


def test_explicit_none_and_unassigned_calls_still_work():
    assert HeadlessPipeline.from_function(assigns_explicit_none)(IMG) == (None,)
    out = HeadlessPipeline.from_function(statement_without_assignment)(IMG)
    assert out[0] is not None
    first, second = HeadlessPipeline.from_function(exact_unpacking)(IMG)
    assert second[0, 0] == 2


def test_hand_built_filters_keep_lenient_behaviour():
    # FilterCore assembled without a pipeline body: extra values are still dropped
    filt = FilterCore(apply_fn=lambda img: (img, img), inputs=[0], outputs=[1])
    assert len(filt.run(IMG)) == 2
    filt = FilterCore(apply_fn=lambda img: None, inputs=[0], outputs=[1])
    assert filt.run(IMG) is None


# --- context read before write -----------------------------------------------------


@interactive()
def ctx_reader(img):
    return img * context["gain_key"]


@interactive()
def ctx_attr_reader(img):
    return img * context.gain_key


@interactive()
def ctx_writer(img):
    context["gain_key"] = 2.0
    context["other_key"] = 1
    return img


def reads_before_write(img):
    a = ctx_reader(img)
    b = ctx_writer(a)
    return b


def attr_reads_before_write(img):
    a = ctx_attr_reader(img)
    b = ctx_writer(a)
    return b


def writes_then_reads(img):
    a = ctx_writer(img)
    b = ctx_reader(a)
    return b


@pytest.mark.parametrize("cache", CACHE_MODES)
@pytest.mark.parametrize("pipe", [reads_before_write, attr_reads_before_write])
def test_context_key_read_before_write(pipe, cache):
    with pytest.raises(FilterError) as info:
        HeadlessPipeline.from_function(pipe, cache=cache)(IMG)
    message = str(info.value)
    assert "Context key 'gain_key' was read before any filter wrote it" in message
    assert "Keys in the context now: none" in message
    assert "Filters run in the order of the pipeline body" in message
    assert "context.get('gain_key', default)" in message
    assert "Filter(s) running later that mention 'gain_key': ctx_writer" in message


def test_context_hint_lists_existing_keys():
    with pytest.raises(FilterError) as info:
        HeadlessPipeline.from_function(reads_before_write)(IMG, context={"present": 1})
    assert "Keys in the context now: 'present'" in str(info.value)


def test_context_written_first_works():
    assert HeadlessPipeline.from_function(writes_then_reads)(IMG)[0][0, 0] == 2.0


@interactive()
def plain_key_error(img):
    return {"a": 1}["b"]


def plain_key_error_pipe(img):
    a = plain_key_error(img)
    return a


def test_other_key_errors_get_no_context_hint():
    with pytest.raises(FilterError) as info:
        HeadlessPipeline.from_function(plain_key_error_pipe)(IMG)
    assert "Context key" not in str(info.value)


# --- reassigned / shadowed names ----------------------------------------------------


@interactive()
def add_one(img):
    return img + 1


@interactive()
def times_ten(img):
    return img * 10


def reassigned(img):
    a = add_one(img)
    a = times_ten(a)
    return a


def shadows_input(img):
    img = add_one(img)
    b = times_ten(img)
    return img, b


def reassigned_twice(img):
    a = add_one(img)
    b = times_ten(a)
    a = add_one(b)
    return a, b


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_reassigned_and_shadowed_names(cache):
    def values(pipe, img):
        return [float(np.asarray(out).ravel()[0]) for out in pipe(img)]

    for pipe_fn, expected_zero, expected_one in [
        (reassigned, [10.0], [20.0]),
        (shadows_input, [1.0, 10.0], [2.0, 20.0]),
        (reassigned_twice, [11.0, 10.0], [21.0, 20.0]),
    ]:
        pipe = HeadlessPipeline.from_function(pipe_fn, cache=cache)
        assert values(pipe, np.zeros(1)) == expected_zero
        assert values(pipe, np.zeros(1)) == expected_zero
        assert values(pipe, np.ones(1)) == expected_one


# --- a failing run never leaves a stale cache --------------------------------------

FLAKY_STATE = {"fail": False}


@interactive(gain=(1.0, [0.0, 3.0]))
def flaky(img, gain=1.0):
    if FLAKY_STATE["fail"]:
        raise RuntimeError("boom")
    return img * gain


@interactive()
def plus_hundred(img):
    return img + 100


def flaky_pipeline(img):
    a = flaky(img)
    b = plus_hundred(a)
    return b


@pytest.mark.parametrize("cache", CACHE_MODES)
def test_rerun_after_exception_recomputes(cache):
    pipe = HeadlessPipeline.from_function(flaky_pipeline, cache=cache)
    try:
        assert pipe(np.ones(1), gain=1.0)[0][0] == 101
        FLAKY_STATE["fail"] = True
        with pytest.raises(FilterError):
            pipe(np.ones(1), gain=2.0)
        FLAKY_STATE["fail"] = False
        assert pipe(np.ones(1))[0][0] == 102  # parameters of the failing run
        assert pipe(np.ones(1), gain=1.0)[0][0] == 101
        FLAKY_STATE["fail"] = True
        with pytest.raises(FilterError):
            pipe(np.ones(1), gain=1.0)  # same parameters as the cached result
        FLAKY_STATE["fail"] = False
        assert pipe(np.ones(1), gain=1.0)[0][0] == 101
    finally:
        FLAKY_STATE["fail"] = False


def empty_pipeline(img): ...


def test_pipeline_without_any_filter_says_so():
    # used to raise IndexError: list index out of range
    with pytest.raises(ValueError, match="pipeline 'empty_pipeline' calls no filter and returns nothing"):
        HeadlessPipeline.from_function(empty_pipeline)
