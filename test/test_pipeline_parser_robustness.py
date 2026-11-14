"""Unusual pipeline functions either work or raise PipelineSyntaxError with a hint,
never a raw KeyError / AttributeError / IndexError / TypeError."""

import functools

import numpy as np
import pytest

from interactive_pipe import PipelineSyntaxError, interactive, interactive_pipeline
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMG = np.ones(2)


@interactive()
def rb_double(img):
    return img * 2


@interactive()
def rb_pair(img):
    return img, img


def _passthrough(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@_passthrough
def stacked(img):
    out = rb_double(img)
    return out


class Holder:
    def method(self, img):
        out = rb_double(img)
        return out


async def asynchronous(img):
    out = rb_double(img)
    return out


def annotated(img):
    out: np.ndarray = rb_double(img)
    return out


def long_body(img):
    x0 = rb_double(img)
    x1 = rb_double(x0)
    x2 = rb_double(x1)
    x3 = rb_double(x2)
    x4 = rb_double(x3)
    x5 = rb_double(x4)
    x6 = rb_double(x5)
    x7 = rb_double(x6)
    return x7


@pytest.mark.parametrize("function", [stacked, Holder().method, asynchronous, annotated, long_body])
def test_these_build_and_run(function):
    (out,) = interactive_pipeline(gui=None)(function)(IMG)
    assert out[0] >= 2


def walrus(img):
    (out := rb_double(img))
    return out


def star_target(img):
    first, *rest = rb_pair(img)
    return first


def chained(img):
    a = b = rb_double(img)
    return a, b


def recursive(img):
    out = recursive(img)
    return out


inner_pipeline = interactive_pipeline(gui=None)(stacked)


def nests_a_pipeline(img):
    out = inner_pipeline(img)
    return out


def filter_defined_later(img):
    out = rb_later(img)  # noqa: F821 - a filter defined after the decoration is unknown at build time
    return out


@pytest.mark.parametrize(
    "function, message",
    [
        (walrus, "walrus"),
        (star_target, "flat list of variable names"),
        (chained, "chained assignment"),
        (recursive, "the pipeline function calls itself"),
        (nests_a_pipeline, "'inner_pipeline' is a pipeline, not a filter"),
        (filter_defined_later, "(?s)name 'rb_later' is not defined.*defined or imported before the pipeline function"),
    ],
)
def test_these_raise_a_pipeline_syntax_error(function, message):
    with pytest.raises(PipelineSyntaxError, match=message) as info:
        HeadlessPipeline.from_function(function)
    assert info.value.hint


@pytest.mark.parametrize(
    "function, message",
    [
        (lambda img: rb_double(img), "regular `def` function"),
        (functools.partial(stacked), "got a partial"),
        (print, "got a builtin_function_or_method"),
        (inner_pipeline, "already a pipeline"),
    ],
)
def test_not_a_def_function(function, message):
    with pytest.raises(PipelineSyntaxError, match=message):
        interactive_pipeline(gui=None)(function)
